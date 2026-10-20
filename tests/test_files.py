from __future__ import annotations

import io
from collections.abc import AsyncIterator
from pathlib import Path

import boto3
import pytest
from botocore.stub import Stubber
from PIL import Image
from starlette.datastructures import Headers, UploadFile
from tortoise import Tortoise, fields
from tortoise.exceptions import ConfigurationError, ValidationError

from drfast.files import ContentFile, FieldFile, FileField, FileModelMixin, ImageField
from drfast.models import Model
from drfast.serializers import FileField as FileSerializerField
from drfast.serializers import Serializer
from drfast.settings import DRFastSettings, configure_settings
from drfast.storage import FileSystemStorage, S3Storage, private_storage, public_storage

storage = FileSystemStorage(Path("media-test"), "/media/")


def receipt_path(instance: Upload, filename: str) -> str:
	return f"receipts/{instance.label}/{filename}"


class Upload(FileModelMixin, Model):
	label: str = fields.CharField(max_length=50)
	document = FileField(upload_to="documents/", storage=lambda: storage, null=True)
	receipt = FileField(upload_to=receipt_path, storage=lambda: storage, null=True)
	photo = ImageField(upload_to="photos/%Y/", storage=lambda: storage, null=True)


class PlainUpload(Model):
	document = FileField(upload_to="documents/", storage=lambda: storage, null=True)


class UploadSerializer(Serializer[Upload]):
	document = FileSerializerField()


def png_bytes() -> bytes:
	buffer = io.BytesIO()
	Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
	return buffer.getvalue()


@pytest.fixture
async def database(tmp_path: Path) -> AsyncIterator[Path]:
	storage.location = tmp_path
	await Tortoise.init(
		db_url="sqlite://:memory:",
		modules={"models": [__name__]},
		_enable_global_fallback=True,
	)
	await Tortoise.generate_schemas()
	yield tmp_path
	await Tortoise.close_connections()


async def test_file_field_uploads_on_save_and_reads_back_a_field_file(database: Path) -> None:
	record = await Upload.create(label="a", document=ContentFile(b"hello", "../../Report 1.pdf"))

	assert record.document == "documents/Report_1.pdf"
	assert (database / "documents" / "Report_1.pdf").read_bytes() == b"hello"

	fetched = await Upload.get(id=record.id)
	assert isinstance(fetched.document, FieldFile)
	assert fetched.document.url == "/media/documents/Report_1.pdf"
	assert await fetched.document.read() == b"hello"
	assert fetched.photo is None


async def test_file_field_never_overwrites_an_existing_file(database: Path) -> None:
	first = await Upload.create(label="a", document=ContentFile(b"one", "same.txt"))
	second = await Upload.create(label="b", document=ContentFile(b"two", "same.txt"))

	assert first.document.name != second.document.name
	assert await first.document.read() == b"one"
	assert await second.document.read() == b"two"


async def test_file_field_accepts_upload_file_and_callable_upload_to(database: Path) -> None:
	upload = UploadFile(
		io.BytesIO(b"paid"),
		filename="receipt.txt",
		headers=Headers({"content-type": "text/plain"}),
	)
	record = await Upload.create(label="order-7", receipt=upload)

	assert record.receipt == "receipts/order-7/receipt.txt"


async def test_file_field_uploads_on_update_only_for_selected_fields(database: Path) -> None:
	record = await Upload.create(label="a")
	record.document = ContentFile(b"later", "later.txt")
	await record.save(update_fields=["document"])

	fetched = await Upload.get(id=record.id)
	assert await fetched.document.read() == b"later"


async def test_image_field_rejects_non_image_content(database: Path) -> None:
	with pytest.raises(ValidationError):
		await Upload.create(label="a", photo=ContentFile(b"not an image", "photo.png"))
	assert not any(database.rglob("photo*.png"))


async def test_image_field_stores_valid_images(database: Path) -> None:
	record = await Upload.create(label="a", photo=ContentFile(png_bytes(), "photo.png"))

	assert record.photo.name.startswith("photos/")
	assert await record.photo.read() == png_bytes()


async def test_model_without_mixin_refuses_pending_uploads(database: Path) -> None:
	with pytest.raises(ConfigurationError):
		await PlainUpload.create(document=ContentFile(b"x", "x.txt"))


async def test_serializer_field_renders_url(database: Path) -> None:
	record = await Upload.create(label="a", document=ContentFile(b"x", "x.txt"))

	assert UploadSerializer().representation(record) == {"document": "/media/documents/x.txt"}


def test_filesystem_storage_refuses_paths_outside_its_location(tmp_path: Path) -> None:
	with pytest.raises(ValueError):
		FileSystemStorage(tmp_path, "/media/").path("../escape.txt")


def test_file_field_keeps_storage_out_of_migrations() -> None:
	_, _, kwargs = Upload._meta.fields_map["document"].deconstruct()

	assert "storage" not in kwargs
	assert "upload_to" not in kwargs


def s3_client() -> object:
	return boto3.client(
		"s3",
		endpoint_url="https://account.r2.cloudflarestorage.com",
		region_name="auto",
		aws_access_key_id="key",
		aws_secret_access_key="secret",
	)


async def test_s3_storage_uploads_with_acl_under_its_location() -> None:
	client = s3_client()
	s3 = S3Storage(bucket_name="public", location="media", default_acl="public-read", client=client)
	with Stubber(client) as stub:
		stub.add_client_error("head_object", service_error_code="404", http_status_code=404)
		stub.add_response(
			"put_object",
			{},
			{
				"Bucket": "public",
				"Key": "media/logo.png",
				"Body": b"img",
				"ContentType": "image/png",
				"ACL": "public-read",
			},
		)
		assert await s3.save("logo.png", b"img") == "logo.png"
		stub.assert_no_pending_responses()


def test_s3_storage_urls_are_public_or_signed() -> None:
	client = s3_client()
	public = S3Storage(
		bucket_name="public", location="media", custom_domain="cdn.example.com", client=client
	)
	private = S3Storage(
		bucket_name="private",
		location="private",
		querystring_auth=True,
		custom_domain="cdn.example.com",
		client=client,
	)

	assert public.url("logo one.png") == "https://cdn.example.com/media/logo%20one.png"
	signed = private.url("cedula.jpg")
	assert "cdn.example.com" not in signed
	assert "/private/private/cedula.jpg" in signed
	assert "Signature" in signed or "X-Amz-Signature" in signed


def test_storage_factories_follow_settings() -> None:
	base = {
		"storage_backend": "s3",
		"aws_storage_bucket_name": "nex-public",
		"aws_private_storage_bucket_name": "nex-public",
		"aws_s3_endpoint_url": "https://account.r2.cloudflarestorage.com",
	}
	public_storage.cache_clear()
	private_storage.cache_clear()
	try:
		configure_settings(DRFastSettings(**base))
		public = public_storage()
		assert isinstance(public, S3Storage)
		assert public.bucket_name == "nex-public"
		with pytest.raises(ValueError):
			private_storage()

		separate = {**base, "aws_private_storage_bucket_name": "nex-private"}
		configure_settings(DRFastSettings(**separate))
		private = private_storage()
		assert isinstance(private, S3Storage)
		assert private.querystring_auth
		assert private.default_acl == "private"
		assert private.custom_domain is None
	finally:
		configure_settings(DRFastSettings())
		public_storage.cache_clear()
		private_storage.cache_clear()
