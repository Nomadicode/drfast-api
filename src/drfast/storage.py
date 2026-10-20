"""Storage backends for uploaded files — public assets vs. private evidence.

Two families, chosen per field:

* public — logos, product images: anything anyone may read.
* private — identity documents, receipts, evidence. Private ACL and signed URLs that expire.

``STORAGE_BACKEND=filesystem`` (the default) keeps both under ``MEDIA_ROOT``, which
nothing serves, so private files stay private in development and under test.
``STORAGE_BACKEND=s3`` targets any S3-compatible service (Cloudflare R2,
DigitalOcean Spaces, AWS S3).
"""

from __future__ import annotations

import asyncio
import mimetypes
import secrets
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from drfast.settings import get_settings


class Storage(ABC):
	"""Async interface the file fields write through."""

	@abstractmethod
	async def exists(self, name: str) -> bool: ...

	@abstractmethod
	async def write(self, name: str, content: bytes, content_type: str | None) -> None: ...

	@abstractmethod
	async def read(self, name: str) -> bytes: ...

	@abstractmethod
	async def delete(self, name: str) -> None: ...

	@abstractmethod
	def url(self, name: str) -> str: ...

	async def save(self, name: str, content: bytes, content_type: str | None = None) -> str:
		"""Store ``content`` under a free name derived from ``name`` and return that name."""

		name = await self.get_available_name(name)
		content_type = content_type or mimetypes.guess_type(name)[0]
		await self.write(name, content, content_type)
		return name

	async def get_available_name(self, name: str) -> str:
		"""Return ``name``, or ``name`` with a random suffix when it is already taken."""

		path = PurePosixPath(name)
		while await self.exists(name):
			name = str(path.with_name(f"{path.stem}_{secrets.token_hex(4)}{path.suffix}"))
		return name


class FileSystemStorage(Storage):
	"""Files on local disk under ``location``, addressed under ``base_url``."""

	def __init__(self, location: str | Path, base_url: str) -> None:
		self.location = Path(location).resolve()
		self.base_url = base_url if base_url.endswith("/") else f"{base_url}/"

	def path(self, name: str) -> Path:
		path = (self.location / name).resolve()
		if not path.is_relative_to(self.location):
			raise ValueError(f"'{name}' resolves outside the storage location.")
		return path

	async def exists(self, name: str) -> bool:
		return self.path(name).exists()

	async def write(self, name: str, content: bytes, content_type: str | None) -> None:
		path = self.path(name)

		def write_file() -> None:
			path.parent.mkdir(parents=True, exist_ok=True)
			path.write_bytes(content)

		await asyncio.to_thread(write_file)

	async def read(self, name: str) -> bytes:
		return await asyncio.to_thread(self.path(name).read_bytes)

	async def delete(self, name: str) -> None:
		await asyncio.to_thread(self.path(name).unlink, missing_ok=True)

	def url(self, name: str) -> str:
		return f"{self.base_url}{quote(name)}"


class S3Storage(Storage):
	"""Files in an S3-compatible bucket.

	With ``querystring_auth`` every URL is presigned and expires; signing is a local
	computation, so ``url()`` makes no network call. A ``custom_domain`` is only used
	for unsigned URLs — a CDN domain in front of a private bucket would otherwise
	hand out permanent links.
	"""

	def __init__(
		self,
		*,
		bucket_name: str,
		location: str = "",
		endpoint_url: str | None = None,
		region_name: str | None = None,
		access_key_id: str | None = None,
		secret_access_key: str | None = None,
		default_acl: str | None = None,
		querystring_auth: bool = False,
		querystring_expire: int = 300,
		custom_domain: str | None = None,
		client: Any = None,
	) -> None:
		self.bucket_name = bucket_name
		self.location = location.strip("/")
		self.endpoint_url = endpoint_url
		self.default_acl = default_acl
		self.querystring_auth = querystring_auth
		self.querystring_expire = querystring_expire
		self.custom_domain = custom_domain
		if client is None:
			import boto3

			client = boto3.client(
				"s3",
				endpoint_url=endpoint_url,
				region_name=region_name,
				aws_access_key_id=access_key_id,
				aws_secret_access_key=secret_access_key,
			)
		self.client = client

	def key(self, name: str) -> str:
		return f"{self.location}/{name}" if self.location else name

	async def exists(self, name: str) -> bool:
		from botocore.exceptions import ClientError

		try:
			await asyncio.to_thread(
				self.client.head_object, Bucket=self.bucket_name, Key=self.key(name)
			)
		except ClientError as exc:
			if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
				return False
			raise
		return True

	async def write(self, name: str, content: bytes, content_type: str | None) -> None:
		params: dict[str, Any] = {
			"Bucket": self.bucket_name,
			"Key": self.key(name),
			"Body": content,
		}
		if content_type:
			params["ContentType"] = content_type
		if self.default_acl:
			params["ACL"] = self.default_acl
		await asyncio.to_thread(self.client.put_object, **params)

	async def read(self, name: str) -> bytes:
		response = await asyncio.to_thread(
			self.client.get_object, Bucket=self.bucket_name, Key=self.key(name)
		)
		return await asyncio.to_thread(response["Body"].read)

	async def delete(self, name: str) -> None:
		await asyncio.to_thread(
			self.client.delete_object, Bucket=self.bucket_name, Key=self.key(name)
		)

	def url(self, name: str) -> str:
		key = self.key(name)
		if self.querystring_auth:
			signed: str = self.client.generate_presigned_url(
				"get_object",
				Params={"Bucket": self.bucket_name, "Key": key},
				ExpiresIn=self.querystring_expire,
			)
			return signed
		if self.custom_domain:
			return f"https://{self.custom_domain}/{quote(key)}"
		base = (self.endpoint_url or "https://s3.amazonaws.com").rstrip("/")
		return f"{base}/{self.bucket_name}/{quote(key)}"


def s3_storage(*, bucket_name: str, is_private: bool) -> S3Storage:
	settings = get_settings()
	if not bucket_name:
		raise ValueError(
			"STORAGE_BACKEND=s3 requires AWS_STORAGE_BUCKET_NAME and "
			"AWS_PRIVATE_STORAGE_BUCKET_NAME."
		)
	return S3Storage(
		bucket_name=bucket_name,
		location="private" if is_private else "media",
		endpoint_url=settings.aws_s3_endpoint_url or None,
		region_name=settings.aws_s3_region_name or None,
		access_key_id=settings.aws_access_key_id.get_secret_value() or None,
		secret_access_key=settings.aws_secret_access_key.get_secret_value() or None,
		default_acl="private" if is_private else (settings.aws_default_acl or None),
		querystring_auth=is_private,
		querystring_expire=settings.private_url_expire_seconds,
		custom_domain=None if is_private else (settings.aws_s3_custom_domain or None),
	)


@lru_cache
def public_storage() -> Storage:
	"""Storage for files anyone may read, such as logos and product images."""

	settings = get_settings()
	if settings.storage_backend == "s3":
		return s3_storage(bucket_name=settings.aws_storage_bucket_name, is_private=False)
	return FileSystemStorage(Path(settings.media_root) / "public", f"{settings.media_url}public/")


@lru_cache
def private_storage() -> Storage:
	"""Storage for identity documents and financial evidence, behind expiring signed URLs.

	The private bucket must differ from the public one: R2 has no per-object ACLs, so
	a shared bucket with a public domain would expose every private object.
	"""

	settings = get_settings()
	if settings.storage_backend == "s3":
		if settings.aws_private_storage_bucket_name == settings.aws_storage_bucket_name:
			raise ValueError("AWS_PRIVATE_STORAGE_BUCKET_NAME must name a separate bucket.")
		return s3_storage(bucket_name=settings.aws_private_storage_bucket_name, is_private=True)
	return FileSystemStorage(Path(settings.media_root) / "private", f"{settings.media_url}private/")
