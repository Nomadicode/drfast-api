"""Tortoise model bases with explicit, composable conventions."""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model as TortoiseModel


class Model(TortoiseModel):
	"""Abstract model with a UUID primary key."""

	id = fields.UUIDField(pk=True)

	class Meta:
		abstract = True


class TimestampedModel(TortoiseModel):
	"""Opt-in UTC creation and modification timestamps."""

	created_at = fields.DatetimeField(auto_now_add=True)
	updated_at = fields.DatetimeField(auto_now=True)

	class Meta:
		abstract = True


class SoftDeleteModel(TortoiseModel):
	"""Opt-in soft deletion convention.

	Applications choose whether ordinary queries exclude deleted rows; no manager
	behavior is hidden by this mixin.
	"""

	deleted_at = fields.DatetimeField(null=True)

	class Meta:
		abstract = True

	async def soft_delete(self) -> None:
		from datetime import UTC, datetime

		self.deleted_at = datetime.now(UTC)
		await self.save(update_fields=["deleted_at"])

