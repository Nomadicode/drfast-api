"""DRF-shaped serializers backed by Pydantic v2 validation."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Any, ClassVar, Generic, Literal, TypeVar, cast
from uuid import UUID

from pydantic import (
	BaseModel,
	ConfigDict,
	EmailStr,
	ValidationError,
	create_model,
)
from pydantic import (
	Field as PydanticField,
)
from tortoise.models import Model as TortoiseModel

ModelType = TypeVar("ModelType", bound=TortoiseModel)


class SerializerValidationError(ValueError):
	"""Validation failure with a JSON-ready error detail."""

	def __init__(self, detail: Any) -> None:
		super().__init__("Serializer validation failed")
		self.detail = detail


class Field:
	"""A declarative serializer field.

	The field's concrete Python type is passed to Pydantic, so FastAPI retains
	native request validation and OpenAPI schemas.
	"""

	python_type: Any = Any

	def __init__(
		self,
		*,
		required: bool = True,
		default: Any = ...,
		read_only: bool = False,
		write_only: bool = False,
		alias: str | None = None,
	) -> None:
		self.required = required
		self.default = default
		self.read_only = read_only
		self.write_only = write_only
		self.alias = alias

	def pydantic_field(self, *, for_input: bool) -> tuple[Any, Any]:
		if (for_input and self.read_only) or (not for_input and self.write_only):
			return Any, PydanticField(exclude=True)
		default = self.default
		if not self.required and default is ...:
			default = None
		return self.python_type, PydanticField(default=default, alias=self.alias)


class CharField(Field):
	python_type = str


class EmailField(Field):
	python_type = EmailStr


class IntegerField(Field):
	python_type = int


class BooleanField(Field):
	python_type = bool


class UUIDField(Field):
	python_type = UUID


class RelatedField(Field):
	"""Read-only relationship rendered as primary keys or nested objects."""

	def __init__(
		self,
		serializer_class: type[Serializer[Any]] | None = None,
		*,
		many: bool = False,
		representation: Literal["pk", "nested"] = "pk",
		alias: str | None = None,
	) -> None:
		if representation == "nested" and serializer_class is None:
			raise ValueError("serializer_class is required for nested relationship output.")
		super().__init__(read_only=True, alias=alias)
		self.serializer_class = serializer_class
		self.many = many
		self.representation = representation

	def pydantic_field(self, *, for_input: bool) -> tuple[Any, Any]:
		if for_input:
			return super().pydantic_field(for_input=True)
		if self.representation == "nested":
			if self.serializer_class is None:
				raise RuntimeError("Nested relationship output requires a serializer class.")
			item_type: Any = self.serializer_class.output_schema()
		else:
			item_type = UUID
		return (list[item_type] if self.many else item_type), PydanticField(default=...)

	def representation_value(self, value: Any) -> Any:
		if value is None:
			return None
		values: Sequence[Any] = value if self.many else (value,)
		if self.representation == "nested":
			if self.serializer_class is None:
				raise RuntimeError("Nested relationship output requires a serializer class.")
			result = [self.serializer_class().representation(item) for item in values]
		else:
			result = [getattr(item, "id", item) for item in values]
		return result if self.many else result[0]


class SerializerMeta(type):
	def __new__(
		mcls: type[SerializerMeta],
		name: str,
		bases: tuple[type[Any], ...],
		namespace: dict[str, Any],
	) -> type[Serializer[Any]]:
		declared: dict[str, Field] = {}
		for base in bases:
			declared.update(getattr(base, "_declared_fields", {}))
		for key, value in list(namespace.items()):
			if isinstance(value, Field):
				declared[key] = value
				namespace.pop(key)
		namespace["_declared_fields"] = declared
		return cast("type[Serializer[Any]]", super().__new__(mcls, name, bases, namespace))


class Serializer(Generic[ModelType], metaclass=SerializerMeta):
	"""Serializer with explicit fields and async validation hooks."""

	_declared_fields: ClassVar[dict[str, Field]]

	def __init__(self, instance: ModelType | None = None, *, partial: bool = False) -> None:
		self.instance = instance
		self.partial = partial
		self.validated_data: dict[str, Any] = {}

	@classmethod
	def _schema(
		cls,
		*,
		for_input: bool,
		partial: bool = False,
		exclude_fields: Collection[str] = (),
	) -> type[BaseModel]:
		fields: dict[str, tuple[Any, Any]] = {}
		for name, field in cls._declared_fields.items():
			if name in exclude_fields:
				continue
			if (for_input and field.read_only) or (not for_input and field.write_only):
				continue
			annotation, default = field.pydantic_field(for_input=for_input)
			if partial and for_input and default is ...:
				default = None
			fields[name] = (annotation, default)
		model = create_model(
			f"{cls.__name__}{'Input' if for_input else 'Output'}",
			__config__=ConfigDict(from_attributes=True, populate_by_name=True),
			**cast(Any, fields),
		)
		return cast(type[BaseModel], model)

	@classmethod
	def input_schema(cls, *, exclude_fields: Collection[str] = ()) -> type[BaseModel]:
		return cls._schema(for_input=True, exclude_fields=exclude_fields)

	@classmethod
	def output_schema(cls) -> type[BaseModel]:
		return cls._schema(for_input=False)

	async def is_valid(
		self,
		data: Mapping[str, Any],
		*,
		exclude_fields: Collection[str] = (),
		additional_data: Mapping[str, Any] | None = None,
	) -> bool:
		try:
			parsed = self._schema(
				for_input=True,
				partial=self.partial,
				exclude_fields=exclude_fields,
			).model_validate(data)
		except ValidationError as exc:
			raise SerializerValidationError(exc.errors(include_url=False)) from exc
		values = parsed.model_dump(exclude_unset=self.partial, by_alias=False)
		if additional_data is not None:
			values.update(additional_data)
		for name, value in list(values.items()):
			validator = getattr(self, f"validate_{name}", None)
			if validator is not None:
				result = validator(value)
				values[name] = await result if hasattr(result, "__await__") else result
		validated = self.validate(values)
		self.validated_data = await validated if hasattr(validated, "__await__") else validated
		return True

	def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
		return attrs

	async def create(self, validated_data: dict[str, Any]) -> ModelType:
		raise NotImplementedError("Serializer.create() must be implemented")

	async def update(self, instance: ModelType, validated_data: dict[str, Any]) -> ModelType:
		raise NotImplementedError("Serializer.update() must be implemented")

	async def save(self) -> ModelType:
		if self.instance is None:
			self.instance = await self.create(self.validated_data)
		else:
			self.instance = await self.update(self.instance, self.validated_data)
		return self.instance

	def representation(self, instance: ModelType | Mapping[str, Any]) -> dict[str, Any]:
		relation_fields = {
			name: field
			for name, field in self._declared_fields.items()
			if isinstance(field, RelatedField)
		}
		if relation_fields:
			values: dict[str, Any] = {}
			for name, field in self._declared_fields.items():
				if field.write_only:
					continue
				value = (
					instance.get(name) if isinstance(instance, Mapping) else getattr(instance, name)
				)
				values[name] = (
					field.representation_value(value)
					if isinstance(field, RelatedField)
					else value
				)
			instance = values
		data = self.output_schema().model_validate(instance).model_dump(mode="json", by_alias=True)
		return {name: value for name, value in data.items() if value is not None}


class ModelSerializer(Serializer[ModelType]):
	"""Serializer with model-backed create and update behavior."""

	model: ClassVar[type[ModelType]]
	fields: ClassVar[tuple[str, ...] | str] = "__all__"
	read_only_fields: ClassVar[tuple[str, ...]] = ()

	@classmethod
	def _model_fields(cls) -> dict[str, Field]:
		if cls._declared_fields:
			return cls._declared_fields
		result: dict[str, Field] = {}
		selected = None if cls.fields == "__all__" else set(cls.fields)
		for name, db_field in cls.model._meta.fields_map.items():
			if selected is not None and name not in selected:
				continue
			is_automatic = name in {"id", "created_at", "updated_at", "deleted_at"}
			python_type = getattr(db_field, "field_type", Any)
			result[name] = Field(
				required=not getattr(db_field, "null", False),
				read_only=is_automatic or name in cls.read_only_fields,
			)
			result[name].python_type = python_type
		return result

	@classmethod
	def _schema(
		cls,
		*,
		for_input: bool,
		partial: bool = False,
		exclude_fields: Collection[str] = (),
	) -> type[BaseModel]:
		if not cls._declared_fields:
			cls._declared_fields = cls._model_fields()
		return super()._schema(
			for_input=for_input,
			partial=partial,
			exclude_fields=exclude_fields,
		)

	async def create(self, validated_data: dict[str, Any]) -> ModelType:
		return await self.model.create(**validated_data)

	async def update(self, instance: ModelType, validated_data: dict[str, Any]) -> ModelType:
		for name, value in validated_data.items():
			setattr(instance, name, value)
		await instance.save(update_fields=list(validated_data))
		return instance

