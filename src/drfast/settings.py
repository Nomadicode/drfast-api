"""Typed application settings and Tortoise configuration generation."""

from __future__ import annotations

from typing import Any

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DRFastSettings(BaseSettings):
	"""Settings consumed by project wiring, never by views directly."""

	model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

	app_name: str = "DRFast API"
	debug: bool = False
	database_url: str = "sqlite://db.sqlite3"
	installed_apps: list[str] = Field(default_factory=list)
	secret_key: SecretStr = SecretStr("change-me-in-production")
	jwt_lifetime_seconds: int = 3600
	cors_origins: list[str] = Field(default_factory=list)

	def tortoise_config(self) -> dict[str, Any]:
		"""Return the configuration shared by runtime and migration commands."""
		apps: dict[str, dict[str, Any]] = {}
		for module in self.installed_apps:
			package, _, _ = module.rpartition(".")
			label = package.rsplit(".", maxsplit=1)[-1]
			if label in apps:
				raise ValueError(f"Duplicate Tortoise app label '{label}' in installed_apps")
			apps[label] = {
				"models": [module],
				"default_connection": "default",
				"migrations": f"{package}.migrations",
			}
		return {
			"connections": {"default": self.database_url},
			"apps": apps,
		}

	def validate_production(self) -> None:
		if not self.debug and self.secret_key.get_secret_value() == "change-me-in-production":
			raise ValueError("SECRET_KEY must be set when DEBUG is false")

