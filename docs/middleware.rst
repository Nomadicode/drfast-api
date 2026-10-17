Middleware
==========

DRFast middleware uses a small class-based protocol over Starlette's standard
request/response flow. It is useful for cross-cutting concerns such as request
IDs, timing, tenancy, or audit context.

Define middleware
-----------------

Subclass :class:`drfast.BaseMiddleware` and implement one or more of the
``process_request``, ``process_response``, and ``process_exception`` hooks.
``process_request`` can return a response to short-circuit the request:

.. code-block:: python

   import time
   from fastapi import Request, Response
   from drfast import BaseMiddleware

   class TimingMiddleware(BaseMiddleware):
       async def process_request(self, request: Request) -> Response | None:
           request.state.started_at = time.perf_counter()
           return None

       async def process_response(self, request: Request, response: Response) -> Response:
           response.headers["X-Process-Time"] = str(
               time.perf_counter() - request.state.started_at
           )
           return response

Install it
----------

Use :func:`drfast.middleware.install_middleware` during application creation:

.. code-block:: python

   from drfast.middleware import install_middleware

   install_middleware(app, [TimingMiddleware])

Pass middleware classes in request order. Request hooks run in declaration
order; response and exception hooks run in reverse order. This lets middleware
unwind like a normal call stack.
Keep authentication and authorization checks in dependencies and permissions;
middleware should not silently grant access or make resource-specific decisions.

Policy middleware
-----------------

``ThrottleMiddleware`` runs one or more application-defined ``BaseThrottle``
classes before routing. Return ``False`` from ``allow_request`` to return a
``429`` response. Optionally return a number of seconds from ``wait`` to add a
``Retry-After`` header.

.. code-block:: python

   from fastapi import Request
   from drfast import BaseThrottle, ThrottleMiddleware, install_policy_middleware

   class AccountRateThrottle(BaseThrottle):
       async def allow_request(self, request: Request) -> bool:
           return await rate_limiter.permit(request.state.user.id)

       async def wait(self, request: Request) -> int | None:
           return 60

   class APIThrottling(ThrottleMiddleware):
       throttle_classes = (AccountRateThrottle,)

   install_policy_middleware(app, [APIThrottling])

``VersioningMiddleware`` extracts a version into ``request.state.api_version``.
Subclass it to select a header (the default), query parameter, or path-prefix
source, accepted versions, and a default:

.. code-block:: python

   from drfast import VersioningMiddleware, install_policy_middleware

   class APIVersion(VersioningMiddleware):
       source = "header"
       header_name = "X-API-Version"
       allowed_versions = ("1", "2")
       default_version = "1"

   install_policy_middleware(app, [APIVersion])

An unsupported version returns ``406``. Version extraction does not rewrite
routes; mount versioned routers explicitly when different versions expose
different paths.

Imported ASGI middleware
------------------------

Use ``install_asgi_middleware`` for a Starlette-compatible middleware imported
from another package, including any constructor options:

.. code-block:: python

   from starlette.middleware.gzip import GZipMiddleware
   from drfast import install_asgi_middleware

   install_asgi_middleware(app, GZipMiddleware, minimum_size=1_000)
