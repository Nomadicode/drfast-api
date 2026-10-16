from drfast.middleware import BaseMiddleware, install_middleware
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient


def test_middleware_has_stack_order_and_can_short_circuit() -> None:
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

	response = TestClient(app).get("/")
	assert response.status_code == 418
	assert events == ["first-request", "second-request"]

