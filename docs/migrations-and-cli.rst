Migrations and command line
===========================

The ``drfast`` command wraps the Tortoise CLI and adds project-oriented commands.
Run it from the generated project directory, or pass ``--project`` when a
command supports an explicit Python module name.

Project commands
----------------

.. list-table::
   :header-rows: 1

   * - Command
     - Description
   * - ``drfast startproject <name> [destination]``
     - Create a runnable project scaffold.
   * - ``drfast startapp <name> [--project PATH]``
     - Create an application package and add its models module to generated settings.
   * - ``drfast runserver [--host HOST] [--port PORT] [--project PACKAGE]``
     - Start Uvicorn with reload enabled.
   * - ``drfast check``
     - Import the project application to validate startup configuration.
   * - ``drfast routes``
     - Print the registered FastAPI routes.
   * - ``drfast createsuperuser --email EMAIL [--project PACKAGE]``
     - Interactively create an active, verified administrator user.

Schema workflow
---------------

Use migrations whenever models change:

.. code-block:: console

   drfast init
   drfast makemigrations
   drfast migrate

``init`` initializes Tortoise's migration configuration. Inspect generated
migrations before committing them. In deployments, run ``drfast migrate`` as a
separate release step before starting new application processes.

The following commands pass their remaining arguments through to Tortoise:

.. code-block:: console

   drfast history
   drfast heads
   drfast sqlmigrate <app> <migration>
   drfast downgrade

Use ``sqlmigrate`` to review SQL for consequential changes. Back up production
data and plan a backwards-compatible rollout before destructive schema changes.

Troubleshooting
---------------

If Tortoise cannot find a model, verify that the exact module containing it is
listed in ``INSTALLED_APPS``. A duplicate final package name in the installed
app list is rejected because it would create an ambiguous Tortoise app label.

If commands cannot import the project, invoke them from the directory that
contains the generated package or supply the command's ``--project`` option.
