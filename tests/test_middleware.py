import pytest
from fastapi import FastAPI, Response
from httpx import ASGITransport, AsyncClient

from drfast.middleware import BaseMiddleware, install_middleware


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

