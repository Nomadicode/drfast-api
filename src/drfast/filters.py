"""Explicit filtering configuration for list endpoints."""

from __future__ import annotations

from typing import ClassVar

from fastapi import HTTPException, Request, status


class FilterSet:
	"""Allowlist exact filters and explicitly declared Tortoise lookups."""

	fields: ClassVar[dict[str, tuple[str, ...]] | tuple[str, ...]] = ()

	@classmethod
	def allowed_lookups(cls, name: str) -> tuple[str, ...]:
		if isinstance(cls.fields, dict):
			return cls.fields.get(name, ())
		return ("exact",) if name in cls.fields else ()

	@classmethod
	def filters_from_request(cls, request: Request) -> dict[str, str]:
		filters: dict[str, str] = {}
		for name, value in request.query_params.multi_items():
			if name in {"limit", "offset", "ordering"}:
				continue
			field, separator, lookup = name.partition("__")
			lookup = lookup if separator else "exact"
			if lookup not in cls.allowed_lookups(field):
				raise HTTPException(
					status_code=status.HTTP_400_BAD_REQUEST,
					detail=f"Filtering by '{name}' is not allowed.",
				)
			filters[name] = value
		return filters

