"""FastAPI lifespan wiring for Tortoise ORM."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from tortoise.contrib.fastapi import RegisterTortoise

from drfast.settings import DRFastSettings


def configure_orm(app: FastAPI, settings: DRFastSettings) -> None:
	"""Attach a Tortoise lifespan to an application.

	Schema generation is deliberately never enabled here; use migrations instead.
	"""
	settings.validate_production()

	@asynccontextmanager
	async def lifespan(_: FastAPI) -> AsyncIterator[None]:
		async with RegisterTortoise(config=settings.tortoise_config()):
			yield

	app.router.lifespan_context = lifespan


def create_app(settings: DRFastSettings, **kwargs: Any) -> FastAPI:
	"""Create a configured FastAPI application without hiding FastAPI itself."""
	app = FastAPI(title=settings.app_name, **kwargs)
	configure_orm(app, settings)
	return app

