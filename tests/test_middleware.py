import pytest
from fastapi import FastAPI, Request, Response
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware

from drfast.middleware import (
	BaseMiddleware,
	BaseThrottle,
	ThrottleMiddleware,
	VersioningMiddleware,
	install_asgi_middleware,
	install_middleware,
)


@pytest.mark.asyncio
async def test_middleware_has_stack_order_and_can_short_circuit() -> None:
	events: list[str] = []

	class First(BaseMiddleware):
		async def process_request(self, request):
			events.append("first-request")
			return None

		async def process_response(self, request, response):
			events.append("first-response")
			return response

	class Second(BaseMiddleware):
		async def process_request(self, request):
			events.append("second-request")
			return Response("stopped", status_code=418)

		async def process_response(self, request, response):
			events.append("second-response")
			return response

	app = FastAPI()
	install_middleware(app, [First, Second])

	@app.get("/")
	async def endpoint():
		events.append("endpoint")
		return {"ok": True}

	async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
		response = await client.get("/")
	assert response.status_code == 418
	assert events == ["first-request", "second-request"]


@pytest.mark.asyncio
async def test_throttle_and_versioning_middleware_are_configurable() -> None:
	class DenyThrottle(BaseThrottle):
		async def allow_request(self, request: Request) -> bool:
			return request.url.path != "/limited"

		async def wait(self, request: Request) -> int | None:
			return 30

	class Limits(ThrottleMiddleware):
		throttle_classes = (DenyThrottle,)

	class ApiVersion(VersioningMiddleware):
		allowed_versions = ("1",)
		default_version = "1"

	app = FastAPI()
	install_middleware(app, [Limits, ApiVersion])

	@app.get("/version")
	async def version(request: Request) -> dict[str, str | None]:
		return {"version": request.state.api_version}

	@app.get("/limited")
	async def limited() -> dict[str, bool]:
		return {"ok": True}

	async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
		default_version = await client.get("/version")
		unsupported_version = await client.get("/version", headers={"X-API-Version": "2"})
		throttled = await client.get("/limited")

	assert default_version.json() == {"version": "1"}
	assert unsupported_version.status_code == 406
	assert throttled.status_code == 429
	assert throttled.headers["retry-after"] == "30"


@pytest.mark.asyncio
async def test_imported_asgi_middleware_can_be_installed_with_options() -> None:
	class HeaderMiddleware(BaseHTTPMiddleware):
		def __init__(self, app, *, value: str) -> None:
			super().__init__(app)
			self.value = value

		async def dispatch(self, request, call_next):
			response = await call_next(request)
			response.headers["X-Policy"] = self.value
			return response

	app = FastAPI()
	install_asgi_middleware(app, HeaderMiddleware, value="enabled")

	@app.get("/")
	async def endpoint() -> dict[str, bool]:
		return {"ok": True}

	async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
		response = await client.get("/")

	assert response.headers["x-policy"] == "enabled"

