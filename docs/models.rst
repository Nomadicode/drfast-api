Models
======

DRFast API uses Tortoise ORM models directly. Its base classes only provide
common identifiers, timestamps, and soft-deletion behavior; all Tortoise fields,
relations, queries, constraints, and transactions remain available.

Base classes
------------

Use :class:`drfast.Model` for a UUID primary key. Use
:class:`drfast.TimestampedModel` when the resource should track creation and
update time. :class:`drfast.SoftDeleteModel` adds a nullable deletion timestamp
and a ``soft_delete()`` coroutine.

.. code-block:: python

   from tortoise import fields
   from drfast import SoftDeleteModel, TimestampedModel

   class Project(TimestampedModel):
       name = fields.CharField(max_length=120)
       is_archived = fields.BooleanField(default=False)

   class Document(SoftDeleteModel):
       project = fields.ForeignKeyField("models.Project", related_name="documents")
       name = fields.CharField(max_length=255)

   document = await Document.get(id=document_id)
   await document.soft_delete()

``SoftDeleteModel`` does not hide deleted rows automatically. Apply
``deleted_at__isnull=True`` in the query or override a viewset query method when
the API should exclude them.

Relationships and query efficiency
----------------------------------

Declare relationships with ordinary Tortoise fields. Use ``select_related`` for
foreign keys and ``prefetch_related`` for collections before serializing data to
avoid N+1 queries:

.. code-block:: python

   projects = await Project.all().prefetch_related("documents")
   project = await Project.get(id=project_id).select_related("owner")

For rules involving more than one model—such as publishing a project and
creating an audit record—use an explicit service and a Tortoise transaction.
This keeps models and HTTP views focused.

User models
-----------

The optional FastAPI Users integration supplies :class:`drfast.auth.FastAPIUserModel`.
Subclass it rather than recreating password and account fields:

.. code-block:: python

   from tortoise import fields
   from drfast.auth import FastAPIUserModel

   class User(FastAPIUserModel):
       display_name = fields.CharField(max_length=120)

See :doc:`permissions-and-authentication` for wiring that model to routes and
current-user permissions.
