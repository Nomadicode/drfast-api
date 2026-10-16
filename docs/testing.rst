Testing
=======

Test DRFast API applications with the same FastAPI and Tortoise tools used for
ordinary async applications. Focus tests on public HTTP behavior, serializer
validation, permissions, and important service workflows.

Serializer tests
----------------

Serializer validation is asynchronous because field and cross-field hooks may
be asynchronous. Use an async test for validation and assert the normalized
``validated_data``:

.. code-block:: python

   import pytest
   from drfast import CharField, Serializer

   class SlugSerializer(Serializer):
       slug = CharField()

       def validate_slug(self, value: str) -> str:
           if " " in value:
               raise ValueError("Spaces are not allowed.")
           return value.lower()

   @pytest.mark.asyncio
   async def test_serializer_normalizes_slug() -> None:
       serializer = SlugSerializer()
       await serializer.is_valid({"slug": "Hello-world"})
       assert serializer.validated_data == {"slug": "hello-world"}

API tests
---------

Use HTTPX's ASGI transport to issue requests to the app without opening a
network port. FastAPI lifespan setup must run when tests need Tortoise database
connections; use the lifespan support provided by your chosen test fixture or
manager.

.. code-block:: python

   import pytest
   from httpx import ASGITransport, AsyncClient

   @pytest.mark.asyncio
   async def test_article_list_is_paginated(app) -> None:
       transport = ASGITransport(app=app)
       async with AsyncClient(transport=transport, base_url="http://test") as client:
           response = await client.get("/api/articles/?limit=10")

       assert response.status_code == 200
       assert "results" in response.json()

Permission tests should cover both collection and object-level access. Seed
distinct users and resources, then assert that an authenticated user cannot
read, update, or delete another user's object when an object permission is in
place.

Database tests
--------------

Use an isolated database per test run. SQLite can be appropriate for fast unit
tests only when its behavior matches the feature under test; exercise
PostgreSQL-specific constraints, indexes, JSON operations, and transaction
behavior against PostgreSQL in CI. Apply migrations to the test database rather
than relying on startup schema generation.

Useful commands
---------------

.. code-block:: console

   uv run pytest
   uv run pytest tests/test_articles.py -q
   uv run ruff check .
   uv run mypy src

Run the complete quality gate listed in :doc:`deployment` before releases.
