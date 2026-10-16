"""Class-based application middleware with deterministic hook ordering."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, Response


class BaseMiddleware:
	"""Implement any async hook; returning a response from request short-circuits."""

	async def process_request(self, request: Request) -> Response | None:
		return None

	async def process_response(self, request: Request, response: Response) -> Response:
		return response

	async def process_exception(self, request: Request, exc: Exception) -> Response | None:
		return None


def install_middleware(app: FastAPI, middleware_classes: list[type[BaseMiddleware]]) -> None:
	"""Install one ASGI-compatible pipeline around FastAPI routes.

	Request hooks run in declaration order; response and exception hooks run in
	reverse order, matching stack unwinding semantics.
	"""
	instances = [middleware() for middleware in middleware_classes]

	@app.middleware("http")
	async def drfast_middleware(request: Request, call_next: Any) -> Response:
		try:
			for middleware in instances:
				response = await middleware.process_request(request)
				if response is not None:
					return response
			response = await call_next(request)
		except Exception as exc:
			for middleware in reversed(instances):
				response = await middleware.process_exception(request, exc)
				if response is not None:
					return response
			raise
		for middleware in reversed(instances):
			response = await middleware.process_response(request, response)
		return response

