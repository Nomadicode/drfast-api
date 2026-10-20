"""Typed application settings and Tortoise configuration generation."""

from __future__ import annotations

from typing import Any, Literal

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

	# Fernet key(s) for ``EncryptedCharField``. Comma-separate to rotate: the first encrypts,
	# all of them decrypt. Empty derives a key from ``secret_key``.
	encryption_key: SecretStr = SecretStr("")

	# Uploaded files (``drfast.files``). "s3" targets any S3-compatible service; the private
	# bucket must differ from the public one, since providers such as R2 have no object ACLs.
	storage_backend: Literal["filesystem", "s3"] = "filesystem"
	media_root: str = "media"
	media_url: str = "/media/"
	private_url_expire_seconds: int = 300
	aws_access_key_id: SecretStr = SecretStr("")
	aws_secret_access_key: SecretStr = SecretStr("")
	aws_s3_endpoint_url: str = ""
	aws_s3_region_name: str = ""
	aws_storage_bucket_name: str = ""
	aws_private_storage_bucket_name: str = ""
	aws_s3_custom_domain: str = ""
	aws_default_acl: str = ""

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



_configured: DRFastSettings | None = None


def configure_settings(settings: DRFastSettings) -> None:
	"""Register the application's settings for fields and storage that read them lazily.

	``create_app`` and ``orm_context`` call this; call it yourself in other entry points.
	"""
	global _configured
	_configured = settings


def get_settings() -> DRFastSettings:
	"""The registered settings, or settings read from the environment when none are."""
	global _configured
	if _configured is None:
		_configured = DRFastSettings()
	return _configured
