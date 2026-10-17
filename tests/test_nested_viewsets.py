from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from tortoise.exceptions import DoesNotExist

from drfast.serializers import CharField, Serializer, UUIDField
from drfast.views import ModelViewSet


class LocationSerializer(Serializer[Any]):
	id = UUIDField(read_only=True)
	merchant = UUIDField(write_only=True)
	name = CharField()
	last_created_data: dict[str, Any] = {}
	last_updated_data: dict[str, Any] = {}

	async def create(self, validated_data: dict[str, Any]) -> dict[str, Any]:
		type(self).last_created_data = validated_data
		return {"id": uuid4(), "name": validated_data["name"]}

	async def update(
		self, instance: dict[str, Any], validated_data: dict[str, Any]
	) -> dict[str, Any]:
		type(self).last_updated_data = validated_data
		return {**instance, **validated_data}


class LocationQuerySet:
	def __init__(self, locations: list[dict[str, Any]], filters: dict[str, Any]) -> None:
		self.locations = locations
		self.filters = filters

	def filter(self, **filters: Any) -> LocationQuerySet:
		return LocationQuerySet(self.locations, {**self.filters, **filters})

	def _matches(self, location: dict[str, Any]) -> bool:
		return all(location.get(name) == value for name, value in self.filters.items())

	def __await__(self):
		async def resolve() -> list[dict[str, Any]]:
			return [location for location in self.locations if self._matches(location)]

		return resolve().__await__()

	async def get(self) -> dict[str, Any]:
		for location in self.locations:
			if self._matches(location):
				return location
		raise DoesNotExist(LocationModel)

	async def count(self) -> int:
		return len(await self)

	def offset(self, offset: int) -> LocationQuerySet:
		return LocationQuerySet(self.locations[offset:], self.filters)

	def limit(self, limit: int) -> LocationQuerySet:
		return LocationQuerySet(self.locations[:limit], self.filters)


class LocationModel:
	locations: list[dict[str, Any]] = []

	@classmethod
	def filter(cls, **filters: Any) -> LocationQuerySet:
		return LocationQuerySet(cls.locations, filters)


class LocationViewSet(ModelViewSet):
	model = LocationModel  # type: ignore[assignment]
	serializer_class = LocationSerializer
	pagination_class = None


@pytest.fixture
def locations() -> tuple[UUID, UUID, UUID, UUID]:
	merchant_id = uuid4()
	other_merchant_id = uuid4()
	location_id = uuid4()
	other_location_id = uuid4()
	LocationModel.locations = [
		{"id": location_id, "merchant_id": merchant_id, "name": "Downtown"},
		{"id": other_location_id, "merchant_id": other_merchant_id, "name": "Airport"},
	]
	LocationSerializer.last_created_data = {}
	LocationSerializer.last_updated_data = {}
	return merchant_id, other_merchant_id, location_id, other_location_id


@pytest.mark.asyncio
async def test_nested_viewset_scopes_routes_and_documents_parent_parameter(
	locations: tuple[UUID, UUID, UUID, UUID],
) -> None:
	merchant_id, other_merchant_id, location_id, other_location_id = locations
	app = FastAPI()
	app.include_router(
		LocationViewSet().as_router(
			prefix="/merchants/{merchant_id}/locations",
			parent_parameter="merchant_id",
			parent_field="merchant_id",
		)
	)

	async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
		listed = await client.get(f"/merchants/{merchant_id}/locations/")
		created = await client.post(
			f"/merchants/{merchant_id}/locations/",
			json={"merchant_id": str(other_merchant_id), "name": "Harbor"},
		)
		retrieved_elsewhere = await client.get(
			f"/merchants/{merchant_id}/locations/{other_location_id}"
		)
		updated = await client.put(
			f"/merchants/{merchant_id}/locations/{location_id}",
			json={"merchant_id": str(other_merchant_id), "name": "Uptown"},
		)
		patched_elsewhere = await client.patch(
			f"/merchants/{merchant_id}/locations/{other_location_id}",
			json={"name": "Should not update"},
		)
		deleted_elsewhere = await client.delete(
			f"/merchants/{merchant_id}/locations/{other_location_id}"
		)

	assert listed.status_code == 200
	assert [location["id"] for location in listed.json()] == [str(location_id)]
	assert created.status_code == 201
	assert LocationSerializer.last_created_data["merchant_id"] == merchant_id
	assert retrieved_elsewhere.status_code == 404
	assert updated.status_code == 200
	assert LocationSerializer.last_updated_data["merchant_id"] == merchant_id
	assert patched_elsewhere.status_code == 404
	assert deleted_elsewhere.status_code == 404

	operations = app.openapi()["paths"]["/merchants/{merchant_id}/locations/{pk}"]
	collection_operations = app.openapi()["paths"]["/merchants/{merchant_id}/locations/"]
	for operation in [*operations.values(), *collection_operations.values()]:
		parent = next(
			parameter for parameter in operation["parameters"] if parameter["name"] == "merchant_id"
		)
		assert parent == {
			"name": "merchant_id",
			"in": "path",
			"required": True,
			"schema": {"type": "string", "format": "uuid", "title": "Merchant Id"},
		}
	create_schema = collection_operations["post"]["requestBody"]["content"][
		"application/json"
	]["schema"]
	create_schema_name = create_schema["$ref"].rsplit("/", maxsplit=1)[-1]
	create_properties = app.openapi()["components"]["schemas"][create_schema_name]["properties"]
	assert "merchant" not in create_properties
	assert "merchant_id" not in create_properties


def test_nested_viewset_requires_both_parent_arguments() -> None:
	with pytest.raises(ValueError, match="provided together"):
		LocationViewSet().as_router(
			prefix="/merchants/{merchant_id}/locations", parent_parameter="merchant_id"
		)


@pytest.mark.asyncio
async def test_unnested_viewsets_preserve_legacy_method_overrides() -> None:
	class LegacyLocationViewSet(LocationViewSet):
		async def list(self, request: Any) -> list[dict[str, Any]]:
			return []

	app = FastAPI()
	app.include_router(LegacyLocationViewSet().as_router(prefix="/locations"))

	async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
		response = await client.get("/locations/")

	assert response.status_code == 200
	assert response.json() == []
