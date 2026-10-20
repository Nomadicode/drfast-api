from __future__ import annotations

from datetime import date

import httpx
import pytest
from fastapi import APIRouter, FastAPI

from drfast.versioning import (
	VersionedRoute,
	VersionPolicy,
	check_versioned_routes,
	configure_versioning,
	openapi_for,
	versions,
)

POLICY = VersionPolicy(versions=(1, 2), deprecated={1: date(2027, 1, 31)})


def build_app(policy: VersionPolicy = POLICY) -> FastAPI:
	app = FastAPI()
	router = APIRouter(route_class=VersionedRoute)

	@router.get("/things")
	@versions(until=1)
	async def things_v1() -> dict[str, int]:
		return {"served_by": 1}

	@router.get("/things")
	@versions(since=2)
	async def things_v2() -> dict[str, int]:
		return {"served_by": 2}

	@router.get("/always")
	async def always() -> dict[str, bool]:
		return {"ok": True}

	app.include_router(router)
	configure_versioning(app, policy)
	return app


async def get(app: FastAPI, path: str, version: str | None = None) -> httpx.Response:
	headers = {"X-API-Version": version} if version is not None else {}
	async with httpx.AsyncClient(
		transport=httpx.ASGITransport(app=app), base_url="http://test"
	) as http:
		return await http.get(path, headers=headers)


async def test_missing_header_gets_the_latest_version() -> None:
	response = await get(build_app(), "/things")

	assert response.json() == {"served_by": 2}
	assert response.headers["X-API-Version"] == "2"
	assert "X-API-Version" in response.headers["Vary"]
	assert "Deprecation" not in response.headers


async def test_routes_are_selected_by_requested_version() -> None:
	app = build_app()

	assert (await get(app, "/things", "1")).json() == {"served_by": 1}
	assert (await get(app, "/things", "2")).json() == {"served_by": 2}
	assert (await get(app, "/always", "1")).status_code == 200


@pytest.mark.parametrize("version", ["99", "abc", "1.5"])
async def test_unsupported_version_is_rejected_with_envelope(version: str) -> None:
	response = await get(build_app(), "/always", version)

	assert response.status_code == 400
	assert response.json()["error"]["code"] == "unsupported_api_version"
	assert response.json()["error"]["details"]["supported_versions"] == [1, 2]


async def test_deprecated_versions_announce_their_sunset() -> None:
	response = await get(build_app(), "/always", "1")

	assert response.headers["Deprecation"] == "true"
	assert response.headers["Sunset"] == "Sun, 31 Jan 2027 00:00:00 GMT"


async def test_unversioned_paths_ignore_the_header() -> None:
	app = build_app(VersionPolicy(versions=(1,), unversioned_paths=("/always",)))

	assert (await get(app, "/always", "99")).status_code == 200


def test_openapi_lists_only_the_routes_of_each_version() -> None:
	app = build_app()
	v1 = openapi_for(app, POLICY, 1)
	v2 = openapi_for(app, POLICY, 2)

	assert v1["paths"]["/things"]["get"]["operationId"] == "things_v1_things_get"
	assert v2["paths"]["/things"]["get"]["operationId"] == "things_v2_things_get"
	assert v1["info"]["x-api-version"] == 1
	assert app.openapi()["info"]["x-api-version"] == 2


async def test_openapi_endpoint_serves_requested_version() -> None:
	app = build_app()

	assert (await get(app, "/openapi.json?version=1")).json()["info"]["x-api-version"] == 1
	assert (await get(app, "/openapi.json?version=7")).status_code == 400


def test_version_marks_on_plain_routes_are_refused() -> None:
	app = FastAPI()

	@app.get("/plain")
	@versions(since=2)
	async def plain() -> None:
		return None

	with pytest.raises(RuntimeError):
		check_versioned_routes(app)


def test_policy_needs_a_version() -> None:
	with pytest.raises(ValueError):
		VersionPolicy(versions=())
