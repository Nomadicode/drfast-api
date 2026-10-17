Views and routers
=================

``ModelViewSet`` supplies conventional asynchronous CRUD endpoints for a
Tortoise model. It keeps routing declarative while allowing overrides at the
same methods a resource needs: ``list``, ``retrieve``, ``create``, ``update``,
and ``destroy``.

Define a viewset
----------------

Set the model and serializer class. The default list response uses limit/offset
pagination; set ``pagination_class = None`` when a resource should return a
plain list.

.. code-block:: python

   from drfast import FilterSet, ModelViewSet
   from .models import Article
   from .serializers import ArticleSerializer

   class ArticleFilter(FilterSet):
       fields = ("author_id", "published")

   class ArticleViewSet(ModelViewSet):
       model = Article
       serializer_class = ArticleSerializer
       filterset_class = ArticleFilter
       ordering_fields = ("created_at", "title")

The generated collection and detail routes are:

.. list-table::
   :header-rows: 1

   * - Method
     - Path
     - Action
   * - ``GET``
     - ``/articles/``
     - List records
   * - ``POST``
     - ``/articles/``
     - Create a record
   * - ``GET``
     - ``/articles/{pk}``
     - Retrieve a record
   * - ``PUT`` / ``PATCH``
     - ``/articles/{pk}``
     - Replace / partially update a record
   * - ``DELETE``
     - ``/articles/{pk}``
     - Delete a record

Filtering, ordering, and pagination
------------------------------------

``FilterSet.fields`` is an allowlist of Tortoise fields and lookups accepted
from query parameters. Do not expose arbitrary query lookup expressions.

``ordering_fields`` similarly allowlists sort fields. Clients pass a
comma-separated ``ordering`` query parameter; prefix a field with ``-`` for
descending order:

.. code-block:: text

   GET /articles/?published=true&ordering=-created_at

The default pagination accepts ``limit`` and ``offset`` and returns a response
with ``count``, ``next``, ``previous``, and ``results``. Override
``pagination_class`` with your own :class:`drfast.LimitOffsetPagination`
subclass to choose different defaults or response behavior.

Register viewsets
-----------------

Use :class:`drfast.DefaultRouter` to combine several viewsets into an
``APIRouter``. Pass tags when registering a route to organize Swagger and ReDoc:

.. code-block:: python

   from drfast import DefaultRouter

   router = DefaultRouter()
   router.register("/articles", ArticleViewSet, basename="articles")
   router.include_in(app, prefix="/api")

Nested resources
----------------

Nest a viewset below a parent resource by specifying the path parameter and the
child model field that stores the parent UUID. This scopes every CRUD operation
to the parent: lists only return that parent's children, and detail, update,
and delete return ``404`` for a child owned by another parent. On creates,
DRFast takes the parent value from the URL rather than the request body.

.. code-block:: python

   api_router.include_router(
       MerchantLocationViewSet().as_router(
           prefix="/merchants/{merchant_id}/locations",
           tags=["merchant-locations"],
           parent_parameter="merchant_id",
           parent_field="merchant_id",
       )
   )

The parent parameter is typed as a UUID in the generated handlers and OpenAPI
schema. The parent field is omitted from nested create and update request
schemas, so clients cannot assign or move a child through the payload.

Extra actions
-------------

Use ``@action`` for domain commands that belong to a resource. Detail actions
are appended after the configured lookup URL; collection actions omit it. An
action can use a dedicated request serializer, its own authentication
dependencies and permissions, and a status code.

.. code-block:: python

   from uuid import UUID

   from fastapi import Request
   from drfast import CharField, ModelViewSet, Serializer, action

   class DisableLocationSerializer(Serializer):
       reason = CharField()

   class MerchantLocationViewSet(ModelViewSet):
       model = Location
       serializer_class = LocationSerializer

       @action(
           detail=True,
           methods=("POST",),
           path="disable",
           serializer_class=DisableLocationSerializer,
           status_code=204,
       )
       async def disable(
           self,
           request: Request,
           pk: UUID,
           merchant_id: UUID,
           payload: dict[str, object],
       ) -> None:
           location = await self.get_object(
               request,
               pk,
               parent_field="merchant_id",
               parent_pk=merchant_id,
           )
           await disable_location(location, reason=str(payload["reason"]))

This produces ``POST /merchants/{merchant_id}/locations/{pk}/disable``. The
action receives named parent path parameters; an action serializer is validated
by FastAPI and supplied to the method as a dictionary.

Custom lookups
--------------

Detail URLs use UUID primary keys by default. Configure all three lookup
attributes to address a resource by another unique model field:

.. code-block:: python

   class LocationViewSet(ModelViewSet):
       model = Location
       serializer_class = LocationSerializer
       lookup_field = "slug"
       lookup_url_kwarg = "location_slug"
       lookup_type = str

The generated detail URL is ``/locations/{location_slug}``, while database
lookups filter on ``slug``. Detail actions use the same URL parameter.

Custom behavior
---------------

Override viewset methods only when the resource protocol differs. For example,
use a regular FastAPI router for a domain command such as publication rather
than disguising it as CRUD:

.. code-block:: python

   from fastapi import APIRouter, HTTPException

   commands = APIRouter(prefix="/articles", tags=["articles"])

   @commands.post("/{article_id}/publish")
   async def publish_article(article_id: str) -> dict[str, bool]:
       article = await Article.get_or_none(id=article_id)
       if article is None:
           raise HTTPException(status_code=404, detail="Not found.")
       article.published = True
       await article.save(update_fields=["published"])
       return {"published": True}

For class-based non-CRUD views, subclass :class:`drfast.APIView`, define
``permission_classes``, and expose methods through a normal FastAPI router.
This retains explicit request and response models where they add clarity.
