Versioning and errors
=====================

Header versioning
-----------------

:mod:`drfast.versioning` selects routes by an integer ``X-API-Version`` header.
A request without the header gets the latest version; bump the version only for
breaking changes. Have your own clients always send the header, or an installed
app silently moves to the next version on release day.

.. code-block:: python

   from datetime import date
   from fastapi import APIRouter
   from drfast import VersionedRoute, VersionPolicy, configure_versioning, versions

   router = APIRouter(route_class=VersionedRoute)

   @router.get("/orders")
   @versions(until=1)
   async def list_orders_v1(): ...

   @router.get("/orders")
   @versions(since=2)
   async def list_orders_v2(): ...

   app.include_router(router)
   configure_versioning(
       app,
       VersionPolicy(versions=(1, 2), deprecated={1: date(2027, 1, 31)},
                     unversioned_paths=("/health", "/openapi.json", "/docs", "/redoc")),
   )

Unmarked routes exist in every version. Responses echo ``X-API-Version`` and
``Vary`` on it; deprecated versions add ``Deprecation`` and ``Sunset``. An
unsupported version returns ``400`` with code ``unsupported_api_version``.
``/openapi.json?version=N`` serves the routes of one version. Call
``configure_versioning`` after including routers: it refuses ``@versions`` on a
route that is not a ``VersionedRoute``.

The older :class:`drfast.VersioningMiddleware` remains for simple string-version
policies that only record the version.

Error envelope
--------------

``install_exception_handlers(app)`` renders every failure as:

.. code-block:: json

   {"error": {"code": "not_found", "message": "Not found.", "details": {}}}

Raise :class:`drfast.APIError` for failures the client can act on:

.. code-block:: python

   raise APIError(409, "phone_taken", "That phone number is already registered.")

HTTP exceptions take their code from the status, request validation lists its
errors under ``details.errors``, Tortoise ``DoesNotExist`` becomes ``404`` and
``IntegrityError`` ``409``. Unexpected exceptions are logged and returned as a
generic ``server_error``. Pass ``messages={"not_found": "No encontrado."}`` to
translate the generic messages.
