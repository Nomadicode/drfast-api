"""Django-inspired management CLI for DRFast projects."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import subprocess
from getpass import getpass
from pathlib import Path
from textwrap import dedent


def _write(path: Path, content: str) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(dedent(content).lstrip(), encoding="utf-8")


def startproject(name: str, destination: str) -> None:
	"""Generate a runnable application with local SQLite configuration."""
	if not name.isidentifier():
		raise SystemExit("Project name must be a valid Python identifier.")
	root = Path(destination).resolve() / name
	if root.exists() and any(root.iterdir()):
		raise SystemExit(f"Refusing to overwrite non-empty directory: {root}")
	package = name
	_write(
		root / "pyproject.toml",
		f'''
		[project]
		name = "{name}"
		version = "0.1.0"
		requires-python = ">=3.11"
		dependencies = ["drfast-api[postgres]"]

		[tool.tortoise]
		tortoise_orm = "{package}.settings.TORTOISE_ORM"
		''',
	)
	_write(root / ".env.example", """DEBUG=true
DATABASE_URL=sqlite://db.sqlite3
SECRET_KEY=replace-before-production
""")
	_write(root / package / "__init__.py", "")
	_write(
		root / package / "settings.py",
		f'''
		from drfast import DRFastSettings


		class Settings(DRFastSettings):
			app_name: str = "{name}"
			debug: bool = True
			installed_apps: list[str] = [
				"{package}.users.models",
				"{package}.apps.todo.models",
			]


		settings = Settings()
		TORTOISE_ORM = settings.tortoise_config()
		''',
	)
	_write(root / package / "users" / "__init__.py", "")
	_write(
		root / package / "users" / "models.py",
		"""
		from drfast.auth import FastAPIUserModel


		class User(FastAPIUserModel):
			pass
		""",
	)
	_write(
		root / package / "users" / "auth.py",
		f'''
		from collections.abc import AsyncGenerator
		from uuid import UUID

		from fastapi import Depends
		from fastapi_users import schemas
		from drfast.auth import (
			DRFastUserManager,
			TortoiseUserDatabase,
			build_fastapi_users,
			jwt_authentication,
		)

		from {package}.settings import settings
		from {package}.users.models import User


		class UserRead(schemas.BaseUser[UUID]):
			pass


		class UserCreate(schemas.BaseUserCreate):
			pass


		class UserUpdate(schemas.BaseUserUpdate):
			pass


		async def get_user_db() -> AsyncGenerator[TortoiseUserDatabase[User], None]:
			yield TortoiseUserDatabase(User)


		class UserManager(DRFastUserManager[User]):
			reset_password_token_secret = settings.secret_key.get_secret_value()
			verification_token_secret = settings.secret_key.get_secret_value()


		async def get_user_manager(
			user_db: TortoiseUserDatabase[User] = Depends(get_user_db),
		) -> AsyncGenerator[UserManager, None]:
			yield UserManager(user_db)


		auth_backend = jwt_authentication(
			settings.secret_key.get_secret_value(), settings.jwt_lifetime_seconds
		)
		fastapi_users = build_fastapi_users(get_user_manager, auth_backend)
		''',
	)
	_write(root / package / "apps" / "__init__.py", "")
	_write(root / package / "apps" / "todo" / "__init__.py", "")
	_write(
		root / package / "apps" / "todo" / "models.py",
		"""
		from tortoise import fields
		from drfast import Model, TimestampedModel


		class Todo(Model, TimestampedModel):
			title = fields.CharField(max_length=200)
			completed = fields.BooleanField(default=False)
		""",
	)
	_write(
		root / package / "apps" / "todo" / "serializers.py",
		f'''
		from drfast import BooleanField, CharField, ModelSerializer, UUIDField
		from {package}.apps.todo.models import Todo


		class TodoSerializer(ModelSerializer[Todo]):
			model = Todo
			id = UUIDField(read_only=True)
			title = CharField()
			completed = BooleanField(required=False, default=False)
		''',
	)
	_write(
		root / package / "apps" / "todo" / "views.py",
		f'''
		from drfast import FilterSet, ModelViewSet
		from {package}.apps.todo.models import Todo
		from {package}.apps.todo.serializers import TodoSerializer


		class TodoFilters(FilterSet):
			fields = {{"completed": ("exact",)}}


		class TodoViewSet(ModelViewSet):
			model = Todo
			serializer_class = TodoSerializer
			filterset_class = TodoFilters
			ordering_fields = ("created_at", "title")
		''',
	)
	_write(
		root / package / "urls.py",
		f'''
		from drfast import DefaultRouter
		from {package}.apps.todo.views import TodoViewSet

		router = DefaultRouter()
		router.register("/todos", TodoViewSet, basename="todos")
		''',
	)
	_write(
		root / package / "main.py",
		f'''
		from drfast.orm import create_app
		from {package}.settings import settings
		from {package}.urls import router
		from {package}.users.auth import (
			UserCreate,
			UserRead,
			UserUpdate,
			auth_backend,
			fastapi_users,
		)

		app = create_app(settings)
		router.include_in(app, prefix="/api")
		app.include_router(
			fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
		)
		app.include_router(
			fastapi_users.get_register_router(UserRead, UserCreate), prefix="/auth", tags=["auth"]
		)
		app.include_router(
			fastapi_users.get_users_router(UserRead, UserUpdate), prefix="/users", tags=["users"]
		)
		''',
	)
	_write(
		root / "README.md",
		f"# {name}\n\nRun `drfast init`, `drfast migrate`, then `drfast runserver`.\n",
	)
	print(f"Created {root}")


def startapp(name: str, project: str = ".") -> None:
	"""Generate a conventional models/serializers/views app package."""
	if not name.isidentifier():
		raise SystemExit("App name must be a valid Python identifier.")
	project_root = Path(project).resolve()
	root = project_root / "apps" / name
	if root.exists():
		raise SystemExit(f"App already exists: {root}")
	for filename in ("__init__.py", "models.py", "serializers.py", "views.py", "tests.py"):
		_write(root / filename, "")
	package = project_root.name.replace("-", "_")
	settings_path = project_root / package / "settings.py"
	if settings_path.exists():
		settings = settings_path.read_text(encoding="utf-8")
		marker = "\t]\n\n\nsettings = Settings()"
		entry = f'\t\t"{package}.apps.{name}.models",\n'
		if marker not in settings:
			raise SystemExit(f"Could not update installed_apps in {settings_path}")
		settings_path.write_text(settings.replace(marker, f"{entry}{marker}", 1), encoding="utf-8")
	print(f"Created {root}")


def _run_tortoise(arguments: list[str]) -> int:
	return subprocess.run(["tortoise", *arguments], check=False).returncode


async def _create_superuser(project: str, email: str) -> None:
	settings_module = importlib.import_module(f"{project}.settings")
	user_module = importlib.import_module(f"{project}.users.models")
	from fastapi_users.password import PasswordHelper
	from tortoise import Tortoise

	password = getpass("Password: ")
	confirm = getpass("Password (again): ")
	if password != confirm:
		raise SystemExit("Passwords do not match.")
	await Tortoise.init(config=settings_module.TORTOISE_ORM)
	try:
		await user_module.User.create(
			email=email,
			hashed_password=PasswordHelper().hash(password),
			is_active=True,
			is_superuser=True,
			is_verified=True,
		)
	finally:
		await Tortoise.close_connections()


def _project_name() -> str:
	return Path.cwd().name.replace("-", "_")


def main(argv: list[str] | None = None) -> None:
	parser = argparse.ArgumentParser(prog="drfast")
	subparsers = parser.add_subparsers(dest="command", required=True)
	project_parser = subparsers.add_parser("startproject")
	project_parser.add_argument("name")
	project_parser.add_argument("destination", nargs="?", default=".")
	app_parser = subparsers.add_parser("startapp")
	app_parser.add_argument("name")
	app_parser.add_argument("--project", default=".")
	run_parser = subparsers.add_parser("runserver")
	run_parser.add_argument("--host", default="127.0.0.1")
	run_parser.add_argument("--port", type=int, default=8000)
	run_parser.add_argument("--project", default=None)
	subparsers.add_parser("check")
	subparsers.add_parser("routes")
	user_parser = subparsers.add_parser("createsuperuser")
	user_parser.add_argument("--email", required=True)
	user_parser.add_argument("--project", default=None)
	for command in (
		"init",
		"makemigrations",
		"migrate",
		"downgrade",
		"history",
		"heads",
		"sqlmigrate",
	):
		migration_parser = subparsers.add_parser(command)
		migration_parser.add_argument("args", nargs=argparse.REMAINDER)

	args = parser.parse_args(argv)
	if args.command == "startproject":
		startproject(args.name, args.destination)
		return
	if args.command == "startapp":
		startapp(args.name, args.project)
		return
	if args.command == "runserver":
		project = args.project or _project_name()
		result = subprocess.run(
			[
				"uvicorn",
				f"{project}.main:app",
				"--host",
				args.host,
				"--port",
				str(args.port),
				"--reload",
			],
			check=False,
		)
		raise SystemExit(result.returncode)
	if args.command in {
		"init",
		"makemigrations",
		"migrate",
		"downgrade",
		"history",
		"heads",
		"sqlmigrate",
	}:
		raise SystemExit(_run_tortoise([args.command, *args.args]))
	if args.command == "createsuperuser":
		asyncio.run(_create_superuser(args.project or _project_name(), args.email))
		return
	project = _project_name()
	if args.command == "check":
		importlib.import_module(f"{project}.main")
		print("System check identified no issues.")
		return
	if args.command == "routes":
		app = importlib.import_module(f"{project}.main").app
		for route in app.routes:
			methods = ",".join(sorted(getattr(route, "methods", [])))
			print(f"{getattr(route, 'path', ''):30} {methods}")


if __name__ == "__main__":
	main()

