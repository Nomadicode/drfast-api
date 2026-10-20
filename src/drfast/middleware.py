"""Class-based application middleware with deterministic hook ordering."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar, Literal, cast

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse


class BaseMiddleware:
	"""Implement any async hook; returning a response from request short-circuits."""

	async def process_request(self, request: Request) -> Response | None:
		return None

	async def process_response(self, request: Request, response: Response) -> Response:
		return response

	async def process_exception(self, request: Request, exc: Exception) -> Response | None:
		return None


class BaseThrottle:
	"""Contract for application-defined request rate policies."""

	async def allow_request(self, request: Request) -> bool:
		return True

	async def wait(self, request: Request) -> int | None:
		return None


class ThrottleMiddleware(BaseMiddleware):
	"""Apply configured throttle classes before routing a request."""

	throttle_classes: ClassVar[tuple[type[BaseThrottle], ...]] = ()

	def __init__(self) -> None:
		self.throttles = tuple(throttle() for throttle in self.throttle_classes)

	async def process_request(self, request: Request) -> Response | None:
		for throttle in self.throttles:
			if await throttle.allow_request(request):
				continue
			headers: dict[str, str] = {}
			wait = await throttle.wait(request)
			if wait is not None:
				headers["Retry-After"] = str(wait)
			return JSONResponse(
				{"detail": "Request was throttled."},
				status_code=status.HTTP_429_TOO_MANY_REQUESTS,
				headers=headers,
			)
		return None


class VersioningMiddleware(BaseMiddleware):
	"""Extract and validate an API version into ``request.state.api_version``.

	A simple policy for string versions. For integer versions that select routes, default
	to the latest and announce deprecations, use ``drfast.versioning`` instead.
	"""

	source: ClassVar[Literal["header", "query", "path"]] = "header"
	header_name: ClassVar[str] = "X-API-Version"
	query_parameter: ClassVar[str] = "version"
	path_prefix: ClassVar[str] = "/v"
	allowed_versions: ClassVar[tuple[str, ...]] = ()
	default_version: ClassVar[str | None] = None

	def version(self, request: Request) -> str | None:
		if self.source == "header":
			return request.headers.get(self.header_name)
		if self.source == "query":
			return request.query_params.get(self.query_parameter)
		path = request.url.path.removeprefix("/")
		segment = path.partition("/")[0]
		prefix = self.path_prefix.removeprefix("/")
		return segment.removeprefix(prefix) if segment.startswith(prefix) else None

	async def process_request(self, request: Request) -> Response | None:
		version = self.version(request) or self.default_version
		if self.allowed_versions and version not in self.allowed_versions:
			return JSONResponse(
				{"detail": "Unsupported API version."},
				status_code=status.HTTP_406_NOT_ACCEPTABLE,
			)
		request.state.api_version = version
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


def install_asgi_middleware(
	app: FastAPI,
	middleware_class: type[Any],
	**options: Any,
) -> None:
	"""Install an imported Starlette or ASGI middleware with its options."""
	app.add_middleware(cast(Any, middleware_class), **options)


def install_policy_middleware(
	app: FastAPI,
	policies: Sequence[type[BaseMiddleware]],
) -> None:
	"""Semantic alias for installing throttle, version, and custom policies."""
	install_middleware(app, list(policies))

