"""One error envelope for every failure: ``{"error": {"code", "message", "details"}}``.

Call ``install_exception_handlers(app)``. Raise ``APIError`` from services and views for
failures the client can act on. Pass ``messages`` to translate the generic messages.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from tortoise.exceptions import DoesNotExist, IntegrityError
from tortoise.exceptions import ValidationError as TortoiseValidationError

logger = logging.getLogger(__name__)

STATUS_CODES = {
	400: "bad_request",
	401: "not_authenticated",
	403: "permission_denied",
	404: "not_found",
	405: "method_not_allowed",
	406: "not_acceptable",
	409: "conflict",
	422: "validation_error",
	429: "throttled",
}

DEFAULT_MESSAGES = {
	"invalid_request": "The request could not be processed.",
	"validation_error": "Check the submitted data.",
	"not_found": "Not found.",
	"conflict": "The record conflicts with an existing one.",
	"server_error": "An unexpected error occurred.",
}


class APIError(Exception):
	"""A failure the client can act on."""

	def __init__(
		self,
		status_code: int,
		code: str,
		message: str,
		details: Mapping[str, Any] | None = None,
	) -> None:
		super().__init__(message)
		self.status_code = status_code
		self.code = code
		self.message = message
		self.details = dict(details or {})


def error_response(
	status_code: int,
	code: str,
	message: str,
	details: Any = None,
	headers: Mapping[str, str] | None = None,
) -> JSONResponse:
	return JSONResponse(
		{"error": {"code": code, "message": message, "details": details or {}}},
		status_code=status_code,
		headers=dict(headers) if headers else None,
	)


def install_exception_handlers(app: FastAPI, *, messages: Mapping[str, str] | None = None) -> None:
	"""Render every error, including unhandled ones, in the envelope."""

	text = {**DEFAULT_MESSAGES, **(messages or {})}

	async def handle_api_error(request: Request, exc: Exception) -> JSONResponse:
		error = cast(APIError, exc)
		return error_response(error.status_code, error.code, error.message, error.details)

	async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
		error = cast(HTTPException, exc)
		code = STATUS_CODES.get(error.status_code, "error")
		details: dict[str, Any] = {}
		if isinstance(error.detail, str):
			message = error.detail
		else:
			message, details = text["invalid_request"], {"errors": error.detail}
		return error_response(error.status_code, code, message, details, error.headers)

	async def handle_request_validation(request: Request, exc: Exception) -> JSONResponse:
		errors = [
			{key: value for key, value in item.items() if key in {"loc", "msg", "type"}}
			for item in cast(RequestValidationError, exc).errors()
		]
		return error_response(422, "validation_error", text["validation_error"], {"errors": errors})

	async def handle_model_validation(request: Request, exc: Exception) -> JSONResponse:
		return error_response(422, "validation_error", str(exc))

	async def handle_does_not_exist(request: Request, exc: Exception) -> JSONResponse:
		return error_response(404, "not_found", text["not_found"])

	async def handle_integrity_error(request: Request, exc: Exception) -> JSONResponse:
		logger.info("Integrity error on %s: %s", request.url.path, exc)
		return error_response(409, "conflict", text["conflict"])

	async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
		logger.exception("Unhandled error on %s", request.url.path, exc_info=exc)
		return error_response(500, "server_error", text["server_error"])

	app.add_exception_handler(APIError, handle_api_error)
	app.add_exception_handler(HTTPException, handle_http_exception)
	app.add_exception_handler(RequestValidationError, handle_request_validation)
	app.add_exception_handler(TortoiseValidationError, handle_model_validation)
	app.add_exception_handler(DoesNotExist, handle_does_not_exist)
	app.add_exception_handler(IntegrityError, handle_integrity_error)
	app.add_exception_handler(Exception, handle_unexpected)
