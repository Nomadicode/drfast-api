API reference
=============

The following modules form the supported public API. Prefer imports from
``drfast`` for the primary primitives and module-level imports for specialized
helpers such as application creation and authentication integration.

Core primitives
---------------

.. automodule:: drfast

Application and ORM integration
-------------------------------

.. automodule:: drfast.orm
   :members:

.. automodule:: drfast.settings
   :members:

Serialization
-------------

.. automodule:: drfast.serializers
   :members:

Fields, files, and storage
--------------------------

.. automodule:: drfast.fields
   :members:

.. automodule:: drfast.files
   :members:

.. automodule:: drfast.storage
   :members:

Views and routing
-----------------

.. automodule:: drfast.actions
   :members:

.. automodule:: drfast.views
   :members:

.. automodule:: drfast.routers
   :members:

Permissions, filters, pagination, and middleware
-------------------------------------------------

.. automodule:: drfast.permissions
   :members:

.. automodule:: drfast.filters
   :members:

.. automodule:: drfast.pagination
   :members:

.. automodule:: drfast.middleware
   :members:

Versioning and errors
---------------------

.. automodule:: drfast.versioning
   :members:

.. automodule:: drfast.exceptions
   :members:

Authentication and commands
---------------------------

.. automodule:: drfast.auth
   :members:

.. automodule:: drfast.cli
   :members:
