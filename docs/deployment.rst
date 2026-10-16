Deployment
==========

Deploy DRFast API as a standard FastAPI ASGI application. Run migrations before
new application instances receive traffic, pass settings through environment
variables or a secret manager, and use a production ASGI server configuration
appropriate for your platform.

Production checklist
--------------------

* Set ``DEBUG=false`` and a high-entropy ``SECRET_KEY``.
* Use a managed PostgreSQL database and a least-privilege database user.
* Set ``DATABASE_URL`` and ``INSTALLED_APPS`` in the runtime environment.
* Run ``drfast migrate`` once per release before deploying application workers.
* Terminate TLS at a trusted proxy or directly at the application edge.
* Configure explicit CORS origins when serving browser clients.
* Restrict JWT lifetime to the needs of the application and rotate secrets.
* Send structured application and proxy logs to your observability system
  without recording tokens, passwords, or sensitive request bodies.

Run with Uvicorn
----------------

The development command enables reload. In production, run the application
module without reload, for example:

.. code-block:: console

   uvicorn config.main:app --host 0.0.0.0 --port 8000

Replace ``config`` with your generated project package. Your process manager,
container platform, or ASGI worker manager should supervise the process and
perform health checks against an application endpoint you define.

Quality gates
-------------

Run the project's checks before publishing or deploying a package:

.. code-block:: console

   uv sync
   uv run ruff check .
   uv run mypy src
   uv run pytest
   uv run bandit -q -r src
   uv run pip-audit --skip-editable
   uv build

``--skip-editable`` is required for ``pip-audit`` when auditing an unpublished
local project: the editable package itself does not yet exist on PyPI. It does
not exclude installed third-party dependencies from the audit.

Read the Docs
-------------

The repository includes ``.readthedocs.yaml``. Read the Docs builds with Python
3.12, installs the project with its ``docs`` extra, and executes Sphinx using
``docs/conf.py``. Warnings fail the build, so broken references and malformed
reStructuredText are caught before documentation is published.
