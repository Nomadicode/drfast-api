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
