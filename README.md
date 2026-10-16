# DRFast API

DRFast API brings familiar Django REST Framework patterns to fully async FastAPI applications backed by Tortoise ORM.

It is pre-1.0 software. The public surface includes serializers, model viewsets, routers, permissions, middleware, settings, Tortoise lifecycle integration, FastAPI Users integration, and the `drfast` management CLI.

## Quick start

```bash
uv add drfast-api
drfast startproject config
cd config
drfast migrate
drfast runserver
```

Generated projects use SQLite locally. Set `DATABASE_URL` to a PostgreSQL URL and install `drfast-api[postgres]` for production.

## Application structure

Projects explicitly list Tortoise model modules in `Settings.installed_apps`. A generated app keeps models, serializers, and views separate:

```python
class TodoSerializer(ModelSerializer[Todo]):
	model = Todo
	id = UUIDField(read_only=True)
	title = CharField()


class TodoViewSet(ModelViewSet):
	model = Todo
	serializer_class = TodoSerializer
	ordering_fields = ("created_at", "title")
```

Register it with `DefaultRouter`, then include the router in the FastAPI application. Viewset handlers, serializer hooks, permission methods, and middleware hooks are asynchronous.

`drfast` delegates migration operations to Tortoise’s current built-in migration CLI:

```bash
drfast init
drfast makemigrations --name add_todos
drfast migrate
drfast history
```

The starter’s authentication uses FastAPI Users with DRFast’s Tortoise adapter. It enables registration and bearer JWT login; password reset and email verification require application-provided delivery hooks before they are enabled.

## Configuration

Copy `.env.example` to `.env` in generated projects. `SECRET_KEY` must be changed and `DEBUG=false` set for production. SQLite is suitable for local development and isolated tests; production should use PostgreSQL, explicit migrations, and an `asyncpg` connection URL.

## Development

```bash
uv sync
uv run ruff check .
uv run mypy src
uv run pytest
uv run bandit -q -r src
uv run pip-audit --skip-editable
uv run python -m build
```

The CI workflow also runs Bandit and pip-audit. Configure the PyPI trusted publisher for the `pypi` GitHub environment before tagging a release.

