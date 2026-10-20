from __future__ import annotations

import httpx
from fastapi import FastAPI, HTTPException
from tortoise.exceptions import DoesNotExist

from drfast.exceptions import APIError, install_exception_handlers


def build_app() -> FastAPI:
	app = FastAPI()
	install_exception_handlers(app, messages={"not_found": "No encontrado."})

	@app.get("/domain")
	async def domain() -> None:
		raise APIError(409, "phone_taken", "Phone in use.", {"field": "phone"})

	@app.get("/forbidden")
	async def forbidden() -> None:
		raise HTTPException(403, "Nope.")

	@app.get("/missing")
	async def missing() -> None:
		raise DoesNotExist("gone")

	@app.get("/boom")
	async def boom() -> None:
		raise RuntimeError("secret detail")

	@app.get("/typed")
	async def typed(limit: int) -> None:
		return None

	return app


async def get(path: str) -> httpx.Response:
	transport = httpx.ASGITransport(app=build_app(), raise_app_exceptions=False)
	async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
		return await http.get(path)


async def test_api_error_keeps_code_message_and_details() -> None:
	response = await get("/domain")

	assert response.status_code == 409
	assert response.json() == {
		"error": {"code": "phone_taken", "message": "Phone in use.", "details": {"field": "phone"}}
	}


async def test_http_exceptions_get_a_code_from_their_status() -> None:
	response = await get("/forbidden")

	assert response.json()["error"] == {
		"code": "permission_denied",
		"message": "Nope.",
		"details": {},
	}


async def test_messages_can_be_translated() -> None:
	assert (await get("/missing")).json()["error"]["message"] == "No encontrado."


async def test_request_validation_lists_errors() -> None:
	response = await get("/typed?limit=x")

	assert response.status_code == 422
	assert response.json()["error"]["details"]["errors"][0]["loc"] == ["query", "limit"]


async def test_unexpected_errors_do_not_leak_details() -> None:
	response = await get("/boom")

	assert response.status_code == 500
	assert response.json()["error"]["code"] == "server_error"
	assert "secret" not in response.text
