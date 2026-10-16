import pytest
from drfast.serializers import CharField, IntegerField, Serializer, SerializerValidationError


class ArticleSerializer(Serializer):
	title = CharField()
	priority = IntegerField(required=False, default=1)

	async def validate_title(self, value: str) -> str:
		if not value.strip():
			raise ValueError("Title is required")
		return value.strip()


@pytest.mark.asyncio
async def test_serializer_uses_pydantic_and_async_field_validation() -> None:
	serializer = ArticleSerializer()
	assert await serializer.is_valid({"title": "  Ship it  "})
	assert serializer.validated_data == {"title": "Ship it", "priority": 1}


@pytest.mark.asyncio
async def test_serializer_reports_structured_validation_errors() -> None:
	with pytest.raises(SerializerValidationError) as error:
		await ArticleSerializer().is_valid({"title": 3})
	assert error.value.detail[0]["loc"] == ("title",)

