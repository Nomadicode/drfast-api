"""Tortoise ORM lifecycle for FastAPI applications and other entry points."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from tortoise import Tortoise
from tortoise.contrib.fastapi import RegisterTortoise

from drfast.settings import DRFastSettings, configure_settings

StartupCheck = Callable[[], Awaitable[None]]


def configure_orm(
	app: FastAPI,
	settings: DRFastSettings,
	*,
	startup_checks: Sequence[StartupCheck] = (),
) -> None:
	"""Attach a Tortoise lifespan to an application.

	``startup_checks`` run once the ORM is ready; raise from one to refuse to start, for
	example when required configuration rows are missing. Schema generation is
	deliberately never enabled here; use migrations instead.
	"""
	settings.validate_production()
	configure_settings(settings)

	@asynccontextmanager
	async def lifespan(_: FastAPI) -> AsyncIterator[None]:
		async with RegisterTortoise(config=settings.tortoise_config()):
			for check in startup_checks:
				await check()
			yield

	app.router.lifespan_context = lifespan


@asynccontextmanager
async def orm_context(settings: DRFastSettings) -> AsyncIterator[None]:
	"""Run Tortoise outside FastAPI: background workers, scripts and management commands."""
	configure_settings(settings)
	await Tortoise.init(config=settings.tortoise_config())
	try:
		yield
	finally:
		await Tortoise.close_connections()


def create_app(
	settings: DRFastSettings,
	*,
	startup_checks: Sequence[StartupCheck] = (),
	**kwargs: Any,
) -> FastAPI:
	"""Create a configured FastAPI application without hiding FastAPI itself."""
	app = FastAPI(title=settings.app_name, **kwargs)
	configure_orm(app, settings, startup_checks=startup_checks)
	return app
