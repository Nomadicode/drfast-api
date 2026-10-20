from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from tortoise import Tortoise
from tortoise.exceptions import ValidationError
from tortoise.utils import get_schema_sql

from drfast.fields import EncryptedCharField
from drfast.models import Model
from drfast.settings import DRFastSettings, configure_settings


class SecretRecord(Model):
	secret = EncryptedCharField(max_length=255)
	optional_secret = EncryptedCharField(max_length=255, null=True)


@pytest.fixture(autouse=True)
def default_settings() -> None:
	configure_settings(DRFastSettings())


@pytest.fixture
async def database() -> AsyncIterator[None]:
	await Tortoise.init(
		db_url="sqlite://:memory:", modules={"models": [__name__]}, _enable_global_fallback=True
	)
	await Tortoise.generate_schemas()
	yield
	await Tortoise.close_connections()


async def test_values_are_encrypted_in_the_database(database: None) -> None:
	record = await SecretRecord.create(secret="my-api-token", optional_secret=None)

	_, rows = await Tortoise.get_connection("default").execute_query(
		'SELECT "secret", "optional_secret" FROM "secretrecord" WHERE "id" = ?', [str(record.id)]
	)
	assert rows[0]["secret"].startswith("gAAAAA")
	assert rows[0]["optional_secret"] is None
	fetched = await SecretRecord.get(id=record.id)
	assert (fetched.secret, fetched.optional_secret) == ("my-api-token", None)


def test_column_is_unbounded_because_ciphertext_outgrows_plaintext(database: None) -> None:
	sql = get_schema_sql(Tortoise.get_connection("default"), safe=False)

	assert '"secret" TEXT NOT NULL' in sql
	ciphertext = SecretRecord._meta.fields_map["secret"].to_db_value("x" * 255, SecretRecord)
	assert len(ciphertext) > 255


def test_keys_rotate_newest_first() -> None:
	old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
	field = EncryptedCharField(max_length=50)
	configure_settings(DRFastSettings(encryption_key=SecretStr(old)))
	written_with_old = field.to_db_value("top-secret", SecretRecord)

	configure_settings(DRFastSettings(encryption_key=SecretStr(f"{new},{old}")))

	assert field.to_python_value(written_with_old) == "top-secret"
	written_with_new = field.to_db_value("top-secret", SecretRecord)
	assert Fernet(new.encode()).decrypt(written_with_new.encode()) == b"top-secret"


def test_plaintext_from_before_encryption_reads_back_unchanged() -> None:
	assert EncryptedCharField(max_length=50).to_python_value("legacy value") == "legacy value"


def test_plaintext_length_is_validated() -> None:
	field = EncryptedCharField(max_length=5)
	field.model_field_name = "secret"

	with pytest.raises(ValidationError):
		field.to_db_value("too-long", SecretRecord)
