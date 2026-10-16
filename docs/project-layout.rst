Project layout
==============

The scaffold deliberately keeps FastAPI visible. A typical project separates
application configuration from domain applications:

.. code-block:: text

   config/
   ├── .env
   ├── main.py
   ├── settings.py
   ├── users/
   │   ├── models.py
   │   ├── serializers.py
   │   └── views.py
   └── articles/
       ├── models.py
       ├── serializers.py
       ├── views.py
       └── services.py

Create a domain application with:

.. code-block:: console

   drfast startapp articles

The generated application contains model, serializer, view, and service modules.
Keep endpoint classes thin: place single-model rules on the model or serializer,
and multi-model workflows or external integrations in ``services.py``.

Register models
---------------

Tortoise discovers models through ``DRFAST_INSTALLED_APPS``. Each value is a
Python module containing models, usually an application's ``models`` module:

.. code-block:: ini

   DRFAST_INSTALLED_APPS=["users.models", "articles.models"]

For a code-defined settings class, supply the same values as a tuple:

.. code-block:: python

   from drfast import DRFastSettings

   class Settings(DRFastSettings):
       installed_apps = ("users.models", "articles.models")

The database schema is never created automatically by application startup. Use
the migration commands described in :doc:`migrations-and-cli` so development,
test, and production schemas evolve predictably.

Register routes centrally
-------------------------

Keep router registration in the application entrypoint or in a dedicated
``urls.py``-style module. That makes the public API easy to audit:

.. code-block:: python

   from drfast import DefaultRouter
   from articles.views import ArticleViewSet
   from users.views import UserViewSet

   api_router = DefaultRouter()
   api_router.register("/articles", ArticleViewSet, basename="articles")
   api_router.register("/users", UserViewSet, basename="users")

   api_router.include_in(app, prefix="/api")

For a small number of non-resource endpoints, use ordinary FastAPI routers and
dependencies alongside DRFast API. They share the same ``app`` and OpenAPI
schema.
