from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, Request
from tortoise import Tortoise, fields

from drfast.models import Model
from drfast.serializers import (
	CharField,
	DecimalField,
	ModelSerializer,
	SerializerValidationError,
	UUIDField,
)
from drfast.views import ModelViewSet


class Note(Model):
	owner_id = fields.UUIDField()
	title = fields.CharField(max_length=100)
	body = fields.TextField(null=True)
	price = fields.DecimalField(max_digits=12, decimal_places=2, null=True)


class NoteSerializer(ModelSerializer[Note]):
	model = Note

	id = UUIDField(read_only=True)
	title = CharField()
	body = CharField(required=False, allow_null=True)
	price = DecimalField(required=False, allow_null=True, decimal_places=2)

	def validate_title(self, value: str) -> str:
		if value.startswith("!"):
			raise ValueError("Titles cannot start with '!'.")
		return value


class AutoNoteSerializer(ModelSerializer[Note]):
	model = Note


def test_decimal_field_without_places_never_uses_exponents() -> None:
	class Plain(ModelSerializer[Note]):
		model = Note
		price = DecimalField()

	assert Plain().representation({"price": Decimal("6E+3")}) == {"price": "6000"}


async def test_list_and_detail_render_nulls_alike(client: httpx.AsyncClient) -> None:
	headers = {"X-User": str(uuid4())}
	created = (await client.post("/notes/", json={"title": "x"}, headers=headers)).json()

	listed = (await client.get("/notes/", headers=headers)).json()["results"][0]

	assert listed == created
	assert listed["body"] is None


def requester(request: Request) -> UUID:
	return UUID(request.headers["X-User"])


class NoteViewSet(ModelViewSet):
	model = Note
	serializer_class = NoteSerializer

	def get_queryset(self, request: Request) -> Any:
		return Note.filter(owner_id=requester(request))

	async def perform_create(self, request: Request, serializer: Any) -> Any:
		return await serializer.save(owner_id=requester(request))


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
	await Tortoise.init(
		db_url="sqlite://:memory:", modules={"models": [__name__]}, _enable_global_fallback=True
	)
	await Tortoise.generate_schemas()
	app = FastAPI()
	app.include_router(NoteViewSet().as_router(prefix="/notes"))
	async with httpx.AsyncClient(
		transport=httpx.ASGITransport(app=app), base_url="http://test"
	) as http:
		yield http
	await Tortoise.close_connections()


async def test_perform_create_adds_server_owned_values(client: httpx.AsyncClient) -> None:
	owner = uuid4()

	response = await client.post("/notes/", json={"title": "Hola"}, headers={"X-User": str(owner)})

	assert response.status_code == 201
	assert (await Note.get(id=response.json()["id"])).owner_id == owner


async def test_get_queryset_scopes_every_route(client: httpx.AsyncClient) -> None:
	mine, theirs = {"X-User": str(uuid4())}, {"X-User": str(uuid4())}
	note = (await client.post("/notes/", json={"title": "Mine"}, headers=mine)).json()

	assert (await client.get("/notes/", headers=theirs)).json()["count"] == 0
	assert (await client.get(f"/notes/{note['id']}", headers=theirs)).status_code == 404
	assert (await client.delete(f"/notes/{note['id']}", headers=theirs)).status_code == 404
	assert (await client.get(f"/notes/{note['id']}", headers=mine)).status_code == 200


async def test_validator_value_errors_are_reported_as_validation_errors(
	client: httpx.AsyncClient,
) -> None:
	response = await client.post("/notes/", json={"title": "!x"}, headers={"X-User": str(uuid4())})

	assert response.status_code == 422
	assert response.json()["detail"][0]["loc"] == ["title"]


async def test_nullable_fields_and_fixed_point_decimals(client: httpx.AsyncClient) -> None:
	headers = {"X-User": str(uuid4())}
	created = await client.post(
		"/notes/", json={"title": "Precio", "body": None, "price": "6000"}, headers=headers
	)

	assert created.status_code == 201
	detail = (await client.get(f"/notes/{created.json()['id']}", headers=headers)).json()
	assert detail["price"] == "6000.00"
	assert detail["body"] is None


async def test_model_serializer_infers_nullable_and_decimal_fields(
	client: httpx.AsyncClient,
) -> None:
	note = await Note.create(owner_id=uuid4(), title="Auto", price=Decimal("6000"))

	data = AutoNoteSerializer().representation(note)

	assert data["price"] == "6000.00"
	assert data["body"] is None


async def test_serializer_save_merges_keyword_values() -> None:
	serializer = NoteSerializer()
	serializer.validated_data = {"title": "x"}

	async def create(validated_data: dict[str, Any]) -> dict[str, Any]:
		return validated_data

	serializer.create = create  # type: ignore[assignment,method-assign]

	assert await serializer.save(owner_id="me") == {"title": "x", "owner_id": "me"}


def test_serializer_validation_error_is_a_value_error() -> None:
	assert issubclass(SerializerValidationError, ValueError)
