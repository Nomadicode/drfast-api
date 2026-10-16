Getting started
===============

Requirements
------------

DRFast API supports Python 3.11 and newer. It uses FastAPI, Pydantic v2, and
Tortoise ORM. PostgreSQL is the recommended production database.

Install the package into an existing `uv <https://docs.astral.sh/uv/>`_ project:

.. code-block:: console

   uv add drfast-api

For PostgreSQL through asyncpg, install the optional extra:

.. code-block:: console

   uv add "drfast-api[postgres]"

Create a project
----------------

The command-line tool creates a conventional application layout, including an
environment file template and a Todo example:

.. code-block:: console

   drfast startproject config
   cd config
   cp .env.example .env
   uv sync
   drfast init
   drfast migrate
   drfast runserver

Open ``http://127.0.0.1:8000/docs`` to inspect FastAPI's generated OpenAPI
documentation. The generated project requires a PostgreSQL database URL in
``.env`` before it can start.

First resource
--------------

These four pieces define a normal CRUD resource: a Tortoise model, a serializer,
a viewset, and a router registration.

.. code-block:: python

   # articles/models.py
   from tortoise import fields
   from drfast import TimestampedModel

   class Article(TimestampedModel):
       title = fields.CharField(max_length=200)
       body = fields.TextField()

.. code-block:: python

   # articles/serializers.py
   from drfast import ModelSerializer
   from .models import Article

   class ArticleSerializer(ModelSerializer[Article]):
       model = Article
       fields = ("id", "title", "body", "created_at", "updated_at")

.. code-block:: python

   # articles/views.py
   from drfast import ModelViewSet
   from .models import Article
   from .serializers import ArticleSerializer

   class ArticleViewSet(ModelViewSet):
       model = Article
       serializer_class = ArticleSerializer
       ordering_fields = ("created_at", "title")

.. code-block:: python

   # main.py
   from drfast import DRFastSettings, DefaultRouter
   from drfast.orm import create_app
   from articles.views import ArticleViewSet

   settings = DRFastSettings()
   app = create_app(settings)

   router = DefaultRouter()
   router.register("/articles", ArticleViewSet, basename="articles")
   router.include_in(app)

The resulting routes are ``GET`` and ``POST /articles/`` plus ``GET``, ``PUT``,
``PATCH``, and ``DELETE /articles/{pk}``. Continue with :doc:`models`,
:doc:`serializers`, and :doc:`views-and-routers` for the options available on
each layer.
