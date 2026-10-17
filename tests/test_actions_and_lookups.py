from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from test_nested_viewsets import LocationModel, LocationViewSet

from drfast import BasePermission, CharField, Serializer, action


class DisableLocationSerializer(Serializer[Any]):
	reason = CharField()


class ActionLocationViewSet(LocationViewSet):
	@action(
		detail=True,
		methods=("POST",),
		path="disable",
		serializer_class=DisableLocationSerializer,
		status_code=202,
	)
	async def disable(
		self,
		request: Request,
		pk: UUID,
		merchant_id: UUID,
		payload: dict[str, Any],
	) -> dict[str, str]:
		return {
			"location_id": str(pk),
			"merchant_id": str(merchant_id),
			"reason": str(payload["reason"]),
		}


class SlugLocationViewSet(LocationViewSet):
	lookup_field = "slug"
	lookup_url_kwarg = "location_slug"
	lookup_type = str


class DenyPermission(BasePermission):
	async def has_permission(self, request: Request, view: Any) -> bool:
		return False


class ProtectedActionViewSet(LocationViewSet):
	@action(detail=False, permission_classes=(DenyPermission,))
	async def internal(self) -> dict[str, bool]:
		return {"ok": True}


@pytest.mark.asyncio
async def test_detail_action_receives_nested_path_values_and_validated_payload() -> None:
	merchant_id = uuid4()
	location_id = uuid4()
	app = FastAPI()
	app.include_router(
		ActionLocationViewSet().as_router(
			prefix="/merchants/{merchant_id}/locations",
			parent_parameter="merchant_id",
			parent_field="merchant_id",
		)
	)

	async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
		response = await client.post(
			f"/merchants/{merchant_id}/locations/{location_id}/disable",
			json={"reason": "seasonal closure"},
		)

	assert response.status_code == 202
	assert response.json() == {
		"location_id": str(location_id),
		"merchant_id": str(merchant_id),
		"reason": "seasonal closure",
	}
	operation = app.openapi()["paths"][
		"/merchants/{merchant_id}/locations/{pk}/disable"
	]["post"]
	assert {parameter["name"] for parameter in operation["parameters"]} == {"merchant_id", "pk"}


@pytest.mark.asyncio
async def test_viewset_lookup_can_use_a_slug() -> None:
	location_id = uuid4()
	LocationModel.locations = [
		{
			"id": location_id,
			"merchant_id": uuid4(),
			"slug": "downtown",
			"name": "Downtown",
		}
	]
	app = FastAPI()
	app.include_router(SlugLocationViewSet().as_router(prefix="/locations"))

	async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
		response = await client.get("/locations/downtown")

	assert response.status_code == 200
	assert response.json()["id"] == str(location_id)


@pytest.mark.asyncio
async def test_action_can_override_viewset_permissions() -> None:
	app = FastAPI()
	app.include_router(ProtectedActionViewSet().as_router(prefix="/locations"))

	async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
		response = await client.get("/locations/internal")

	assert response.status_code == 403
