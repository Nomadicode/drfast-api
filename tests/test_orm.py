from __future__ import annotations

import pytest
from tortoise import Tortoise

from drfast.orm import create_app, orm_context
from drfast.settings import DRFastSettings, get_settings

# The ORM only needs some app to start; this one deliberately declares no concrete models.
pytestmark = pytest.mark.filterwarnings("ignore:Module .* has no models:RuntimeWarning")

SETTINGS = DRFastSettings(
	app_name="Probe",
	debug=True,
	database_url="sqlite://:memory:",
	installed_apps=["drfast.auth"],
)


async def test_startup_checks_run_once_the_orm_is_ready() -> None:
	seen: list[bool] = []

	async def check() -> None:
		seen.append(Tortoise._inited)

	app = create_app(SETTINGS, startup_checks=[check])
	async with app.router.lifespan_context(app):
		assert seen == [True]


async def test_a_failing_startup_check_refuses_to_start() -> None:
	async def check() -> None:
		raise RuntimeError("missing configuration")

	app = create_app(SETTINGS, startup_checks=[check])
	with pytest.raises(RuntimeError, match="missing configuration"):
		async with app.router.lifespan_context(app):
			pass


async def test_orm_context_registers_settings_and_closes_connections(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	closed: list[bool] = []
	close_connections = Tortoise.close_connections

	async def record_close() -> None:
		closed.append(True)
		await close_connections()

	monkeypatch.setattr(Tortoise, "close_connections", record_close)

	async with orm_context(SETTINGS):
		assert Tortoise._inited
		assert get_settings() is SETTINGS
	assert closed == [True]
