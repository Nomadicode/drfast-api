"""Header-based, route-aware API versioning.

Clients send ``X-API-Version: <int>``; a request without it gets the latest version. Bump the
version only for breaking changes, and have your own clients always send the header: an
installed app relying on "latest" silently moves to the next version on release day.

.. code-block:: python

   configure_versioning(app, VersionPolicy(versions=(1, 2), deprecated={1: date(2027, 1, 31)}))

   router = APIRouter(route_class=VersionedRoute)

   @router.get("/things")
   @versions(until=1)
   async def things_v1(): ...

   @router.get("/things")
   @versions(since=2)
   async def things_v2(): ...

Unmarked routes exist in every version. Call ``configure_versioning`` after including routers;
it also serves one OpenAPI document per version at ``/openapi.json?version=N``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from email.utils import format_datetime
from typing import Any, TypeVar, cast

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from drfast.exceptions import error_response

EndpointType = TypeVar("EndpointType", bound=Callable[..., Any])

STATE_KEY = "api_version"


@dataclass(frozen=True)
class VersionPolicy:
	"""Which versions are served, which are deprecated, and how clients ask for one."""

	versions: tuple[int, ...]
	deprecated: Mapping[int, date] = field(default_factory=dict)
	header: str = "X-API-Version"
	unversioned_paths: tuple[str, ...] = ("/openapi.json", "/docs", "/redoc")

	def __post_init__(self) -> None:
		if not self.versions:
			raise ValueError("VersionPolicy needs at least one version.")

	@property
	def latest(self) -> int:
		return max(self.versions)

	def parse(self, raw: str | None) -> int | None:
		"""The requested version, the latest when absent, or None when unsupported."""
		if raw is None or not raw.strip():
			return self.latest
		try:
			version = int(raw)
		except ValueError:
			return None
		return version if version in self.versions else None

	def unsupported(self) -> JSONResponse:
		return error_response(
			400,
			"unsupported_api_version",
			"Unsupported API version.",
			{"supported_versions": list(self.versions)},
		)


def request_version(request: Request) -> int | None:
	"""The API version resolved for ``request``, or None without the middleware."""
	return cast(int | None, request.scope.get("state", {}).get(STATE_KEY))


class ApiVersionMiddleware:
	"""Resolve the version before routing and label the response with it."""

	def __init__(self, app: ASGIApp, policy: VersionPolicy) -> None:
		self.app = app
		self.policy = policy

	async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
		if scope["type"] not in {"http", "websocket"}:
			await self.app(scope, receive, send)
			return

		state = scope.setdefault("state", {})
		if scope["path"].startswith(self.policy.unversioned_paths):
			state[STATE_KEY] = self.policy.latest
			await self.app(scope, receive, send)
			return

		version = self.policy.parse(Headers(scope=scope).get(self.policy.header))
		if version is None:
			if scope["type"] == "websocket":
				await send({"type": "websocket.close", "code": 1008})
			else:
				await self.policy.unsupported()(scope, receive, send)
			return
		state[STATE_KEY] = version

		async def send_with_version(message: Message) -> None:
			if message["type"] == "http.response.start":
				headers = MutableHeaders(scope=message)
				headers[self.policy.header] = str(version)
				headers.add_vary_header(self.policy.header)
				sunset = self.policy.deprecated.get(version)
				if sunset is not None:
					headers["Deprecation"] = "true"
					headers["Sunset"] = format_datetime(
						datetime.combine(sunset, time(), tzinfo=UTC), usegmt=True
					)
			await send(message)

		await self.app(scope, receive, send_with_version)


def versions(
	*, since: int | None = None, until: int | None = None
) -> Callable[[EndpointType], EndpointType]:
	"""Limit an endpoint to API versions ``since`` through ``until``, both inclusive."""

	def decorator(endpoint: EndpointType) -> EndpointType:
		cast(Any, endpoint).__api_versions__ = (since, until)
		return endpoint

	return decorator


class VersionedRoute(APIRoute):
	"""An ``APIRoute`` that only matches requests for the versions its endpoint declares."""

	def __init__(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
		super().__init__(path, endpoint, **kwargs)
		declared: tuple[int | None, int | None] = getattr(
			endpoint, "__api_versions__", (None, None)
		)
		self.since, self.until = declared

	def supports(self, version: int) -> bool:
		return (self.since is None or version >= self.since) and (
			self.until is None or version <= self.until
		)

	def matches(self, scope: Scope) -> tuple[Match, Scope]:
		match, child_scope = super().matches(scope)
		version = scope.get("state", {}).get(STATE_KEY)
		if match is not Match.NONE and version is not None and not self.supports(version):
			return Match.NONE, {}
		return match, child_scope


def route_entries(app: FastAPI) -> Iterator[tuple[BaseRoute, Any]]:
	"""Each route with the object ``get_openapi`` expects for it.

	FastAPI 0.143 keeps included routers nested and documents them through route contexts;
	older versions flatten them into ``app.routes``.
	"""
	try:
		from fastapi.routing import iter_route_contexts
	except ImportError:
		for route in app.routes:
			yield route, route
		return
	for context in iter_route_contexts(app.routes):
		yield context.original_route, context


def check_versioned_routes(app: FastAPI) -> None:
	"""Fail fast when ``@versions`` marks a route that cannot enforce it."""
	for route, _ in route_entries(app):
		endpoint = getattr(route, "endpoint", None)
		if hasattr(endpoint, "__api_versions__") and not isinstance(route, VersionedRoute):
			path = getattr(route, "path", repr(route))
			raise RuntimeError(f"{path} declares API versions but is not a VersionedRoute.")


def openapi_for(app: FastAPI, policy: VersionPolicy, version: int) -> dict[str, Any]:
	"""The OpenAPI schema of the routes that exist in ``version``."""
	cache: dict[int, dict[str, Any]] = app.state.__dict__.setdefault("openapi_by_version", {})
	if version not in cache:
		routes = [
			entry
			for route, entry in route_entries(app)
			if not isinstance(route, VersionedRoute) or route.supports(version)
		]
		schema = get_openapi(
			title=app.title,
			version=app.version,
			description=f"API version {version}. Send `{policy.header}: {version}`.",
			routes=routes,
		)
		schema["info"]["x-api-version"] = version
		cache[version] = schema
	return cache[version]


def configure_versioning(app: FastAPI, policy: VersionPolicy) -> None:
	"""Install the version middleware and serve one OpenAPI document per version."""
	check_versioned_routes(app)
	app.add_middleware(ApiVersionMiddleware, policy=policy)
	app.openapi = lambda: openapi_for(app, policy, policy.latest)  # type: ignore[method-assign]
	openapi_url = app.openapi_url or "/openapi.json"
	app.router.routes = [
		route for route in app.router.routes if getattr(route, "path", None) != openapi_url
	]

	async def openapi(version: int | None = None) -> JSONResponse:
		requested = policy.latest if version is None else version
		if requested not in policy.versions:
			return policy.unsupported()
		return JSONResponse(openapi_for(app, policy, requested))

	app.add_api_route(openapi_url, openapi, methods=["GET"], include_in_schema=False)
