"""File and image model fields, and the model mixin that uploads them on save.

``ImageField`` needs the ``images`` extra (Pillow); S3 storage needs the ``s3`` extra.

Assign a ``ContentFile`` or a FastAPI ``UploadFile`` to a file field and save the
model: the upload is written to the field's storage under ``upload_to`` and the
column stores only the resulting name. Reading the field returns a ``FieldFile``
whose ``url`` comes from that storage.

	class Merchant(FileModelMixin, Model):
		logo = ImageField(upload_to="merchants/logos/%Y/%m/", null=True)
		rut = FileField(upload_to=rut_path, storage=private_storage, null=True)

	merchant.logo = upload_file
	await merchant.save()
	merchant.logo.url
"""

from __future__ import annotations

import io
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from starlette.datastructures import UploadFile
from tortoise import fields
from tortoise.exceptions import ConfigurationError, ValidationError
from tortoise.models import Model as TortoiseModel

from drfast.storage import Storage, public_storage

if TYPE_CHECKING:
	from tortoise.backends.base.client import BaseDBAsyncClient

UploadTo = str | Callable[[Any, str], str]
StorageSource = Storage | Callable[[], Storage]


@dataclass(frozen=True)
class ContentFile:
	"""In-memory file content waiting to be uploaded through a file field."""

	content: bytes
	name: str
	content_type: str | None = None


class FieldFile:
	"""A stored file, as read back from a file field."""

	def __init__(self, name: str, storage: Storage) -> None:
		self.name = name
		self.storage = storage

	@property
	def url(self) -> str:
		return self.storage.url(self.name)

	async def read(self) -> bytes:
		return await self.storage.read(self.name)

	async def delete(self) -> None:
		"""Remove the stored object. The model's column keeps the name until it is cleared."""

		await self.storage.delete(self.name)

	def __str__(self) -> str:
		return self.name

	def __repr__(self) -> str:
		return f"<FieldFile: {self.name}>"

	def __eq__(self, other: object) -> bool:
		if isinstance(other, FieldFile):
			return self.name == other.name and self.storage is other.storage
		return isinstance(other, str) and self.name == other

	def __hash__(self) -> int:
		return hash(self.name)


PENDING_TYPES = (ContentFile, UploadFile)


def clean_filename(filename: str) -> str:
	"""Reduce a client-supplied filename to a safe basename."""

	name = re.sub(r"[^\w.-]", "_", PurePosixPath(filename.replace("\\", "/")).name).strip("._")
	return name or "file"


class FileField(fields.CharField[Any]):
	"""A column holding the storage name of an uploaded file.

	``upload_to`` is a directory, which may contain ``strftime`` tokens, or a callable
	``(instance, filename) -> name`` returning the full name. ``storage`` is a
	``Storage`` or a zero-argument callable returning one, resolved on first use so
	settings are read at runtime rather than at import.
	"""

	def __init__(
		self,
		upload_to: UploadTo = "",
		storage: StorageSource = public_storage,
		max_length: int = 255,
		**kwargs: Any,
	) -> None:
		super().__init__(max_length=max_length, **kwargs)
		self.upload_to = upload_to
		self.storage_source = storage

	@property
	def storage(self) -> Storage:
		if isinstance(self.storage_source, Storage):
			return self.storage_source
		return self.storage_source()

	def deconstruct(self) -> tuple[str, list[Any], dict[str, Any]]:
		# Where and how files are stored is not schema, so migrations must not pin it.
		path, args, kwargs = super().deconstruct()
		kwargs.pop("upload_to", None)
		kwargs.pop("storage", None)
		return path, args, kwargs

	def generate_filename(self, instance: TortoiseModel, filename: str) -> str:
		filename = clean_filename(filename)
		if callable(self.upload_to):
			return self.upload_to(instance, filename)
		directory = datetime.now(UTC).strftime(self.upload_to)
		return str(PurePosixPath(directory) / filename)

	def validate_content(self, content: bytes) -> None:
		"""Reject content this field must not store. Subclasses narrow what is accepted."""

	async def store(self, instance: TortoiseModel, upload: ContentFile | UploadFile) -> FieldFile:
		"""Validate and write ``upload`` to storage, returning the stored file."""

		if isinstance(upload, UploadFile):
			content = await upload.read()
			upload = ContentFile(content, upload.filename or "file", upload.content_type)
		self.validate_content(upload.content)
		name = self.generate_filename(instance, upload.name)
		if len(name) > self.max_length:
			raise ValidationError(
				f"{self.model_field_name}: the file name is too long."
			)
		storage = self.storage
		stored_name = await storage.save(name, upload.content, upload.content_type)
		return FieldFile(stored_name, storage)

	def to_db_value(self, value: Any, instance: type[TortoiseModel] | TortoiseModel) -> str | None:
		if isinstance(value, PENDING_TYPES):
			model = instance if isinstance(instance, type) else type(instance)
			raise ConfigurationError(
				f"{model.__name__} must inherit FileModelMixin to upload '{self.model_field_name}'."
			)
		if isinstance(value, FieldFile):
			value = value.name
		stored: str | None = super().to_db_value(value, instance)
		return stored

	def to_python_value(self, value: Any) -> Any:
		if value is None or value == "":
			return None
		if isinstance(value, (FieldFile, *PENDING_TYPES)):
			return value
		return FieldFile(str(value), self.storage)


class ImageField(FileField):
	"""A file field that accepts only content Pillow recognises as an image."""

	def validate_content(self, content: bytes) -> None:
		from PIL import Image

		try:
			with Image.open(io.BytesIO(content)) as image:
				image.verify()
		except Exception as exc:
			raise ValidationError(f"{self.model_field_name}: upload a valid image.") from exc


class FileModelMixin(TortoiseModel):
	"""Uploads pending files assigned to its file fields before the row is written."""

	class Meta:
		abstract = True

	async def _pre_save(
		self,
		using_db: BaseDBAsyncClient | None = None,
		update_fields: Iterable[str] | None = None,
	) -> None:
		selected = None if update_fields is None or not self._saved_in_db else set(update_fields)
		for name, field in self._meta.fields_map.items():
			if not isinstance(field, FileField) or (selected is not None and name not in selected):
				continue
			value = getattr(self, name, None)
			if isinstance(value, PENDING_TYPES):
				setattr(self, name, await field.store(self, value))
		await super()._pre_save(using_db, update_fields)
