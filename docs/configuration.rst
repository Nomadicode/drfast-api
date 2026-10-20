Configuration
=============

``DRFastSettings`` is a typed Pydantic settings class. By default it reads a
``.env`` file in the current directory and environment variables with no prefix.
Environment values override the values in the file.

Settings reference
------------------

.. list-table::
   :header-rows: 1

   * - Setting
     - Environment variable
     - Purpose
   * - ``app_name``
     - ``APP_NAME``
     - FastAPI title
   * - ``debug``
     - ``DEBUG``
     - Enables development-safe validation behavior
   * - ``database_url``
     - ``DATABASE_URL``
     - Tortoise connection URL
   * - ``installed_apps``
     - ``INSTALLED_APPS``
     - JSON list of model modules
   * - ``secret_key``
     - ``SECRET_KEY``
     - JWT and application secret material
   * - ``jwt_lifetime_seconds``
     - ``JWT_LIFETIME_SECONDS``
     - JWT validity duration
   * - ``cors_origins``
     - ``CORS_ORIGINS``
     - JSON list available to your CORS middleware configuration
   * - ``encryption_key``
     - ``ENCRYPTION_KEY``
     - Fernet key(s) for ``EncryptedCharField``, newest first, comma-separated
   * - ``storage_backend``
     - ``STORAGE_BACKEND``
     - ``filesystem`` or ``s3``; see :doc:`fields-and-files` for the storage settings

For example:

.. code-block:: ini

   APP_NAME="Article service"
   DEBUG=false
   DATABASE_URL="postgres://app:password@db:5432/articles"
   INSTALLED_APPS=["config.users.models", "config.apps.articles.models"]
   SECRET_KEY="load-this-from-a-secret-manager"
   JWT_LIFETIME_SECONDS=3600
   CORS_ORIGINS=["https://app.example.com"]

Create the app
--------------

Use :func:`drfast.orm.create_app` to make FastAPI and Tortoise share the same
settings. It sets a lifespan that opens and closes Tortoise connections.

.. code-block:: python

   from drfast import DRFastSettings
   from drfast.orm import create_app

   settings = DRFastSettings()
   app = create_app(settings, description="Article API")

``create_app`` deliberately does not create schema at startup. Manage schema
changes through migrations. It also calls ``validate_production()``: when
``DEBUG`` is false, the default ``change-me-in-production`` secret is rejected.

``create_app`` registers the settings for fields and storage that read them
lazily. Pass ``startup_checks`` (async callables) to refuse to start when, for
example, required configuration rows are missing; they run once the ORM is ready.

Outside FastAPI (background workers, scripts) use
:func:`drfast.orm.orm_context`, which registers the settings and opens and closes
Tortoise:

.. code-block:: python

   async with orm_context(settings):
       await run_worker()

Custom settings
---------------

Subclass the settings class for fixed project defaults while retaining
environment overrides:

.. code-block:: python

   from drfast import DRFastSettings

   class Settings(DRFastSettings):
       app_name: str = "Article service"
       installed_apps: list[str] = [
           "config.users.models",
           "config.apps.articles.models",
       ]

   settings = Settings()

Keep ``.env`` out of source control and commit an ``.env.example`` containing
only non-secret defaults. Configure Starlette's ``CORSMiddleware`` explicitly
if browser clients need it; ``cors_origins`` is a settings value, not automatic
middleware installation.
