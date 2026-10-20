"""Additional Tortoise model fields.

``EncryptedCharField`` needs the ``encryption`` extra: ``pip install drfast-api[encryption]``.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from tortoise import fields

from drfast.settings import get_settings

if TYPE_CHECKING:
	from cryptography.fernet import MultiFernet
	from tortoise.models import Model


def encryption_keys() -> tuple[bytes, ...]:
	"""Configured Fernet keys, newest first, or one derived from ``secret_key``."""
	settings = get_settings()
	configured = settings.encryption_key.get_secret_value()
	keys = tuple(key.strip().encode() for key in configured.split(",") if key.strip())
	if keys:
		return keys
	digest = hashlib.sha256(
		f"field-encryption:{settings.secret_key.get_secret_value()}".encode()
	).digest()
	return (base64.urlsafe_b64encode(digest),)


@lru_cache(maxsize=4)
def fernet_for(keys: tuple[bytes, ...]) -> MultiFernet:
	from cryptography.fernet import Fernet, MultiFernet

	return MultiFernet([Fernet(key) for key in keys])


class EncryptedCharField(fields.CharField[str]):
	"""A character field encrypted at rest with Fernet.

	``max_length`` limits the plaintext. The column is unbounded text because Fernet
	ciphertext is several times longer than its plaintext. Values stored before the field
	was encrypted are returned as they are, so a plain column can be converted in place.
	"""

	def __init__(self, max_length: int = 512, **kwargs: Any) -> None:
		super().__init__(max_length=max_length, **kwargs)

	@property
	def SQL_TYPE(self) -> str:  # type: ignore[override]
		return "TEXT"

	class _db_oracle:
		SQL_TYPE = "NCLOB"

	class _db_mssql:
		SQL_TYPE = "NVARCHAR(MAX)"

	@property
	def fernet(self) -> MultiFernet:
		return fernet_for(encryption_keys())

	def to_db_value(self, value: Any, instance: type[Model] | Model) -> str | None:
		value = super().to_db_value(value, instance)
		if value is None:
			return None
		return self.fernet.encrypt(str(value).encode()).decode()

	def to_python_value(self, value: Any) -> str | None:
		from cryptography.fernet import InvalidToken

		if value is None:
			return None
		raw = value.encode() if isinstance(value, str) else value
		try:
			return self.fernet.decrypt(raw).decode()
		except InvalidToken:
			return str(super().to_python_value(value))
