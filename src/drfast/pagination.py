"""Native JSON limit/offset pagination."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status


class LimitOffsetPagination:
	default_limit = 50
	max_limit = 100

	def parameters(self, request: Request) -> tuple[int, int]:
		try:
			limit = int(request.query_params.get("limit", self.default_limit))
			offset = int(request.query_params.get("offset", 0))
		except ValueError as exc:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Invalid pagination.",
			) from exc
		if limit < 1 or limit > self.max_limit or offset < 0:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="Invalid pagination.",
			)
		return limit, offset

	def response(
		self,
		request: Request,
		*,
		count: int,
		offset: int,
		limit: int,
		results: list[Any],
	) -> dict[str, Any]:
		def link(next_offset: int) -> str | None:
			if next_offset < 0 or next_offset >= count:
				return None
			params = dict(request.query_params)
			params.update({"limit": str(limit), "offset": str(next_offset)})
			query = "&".join(f"{key}={value}" for key, value in params.items())
			return f"{request.url.path}?{query}"

		return {
			"count": count,
			"next": link(offset + limit),
			"previous": link(max(offset - limit, -1)),
			"results": results,
		}

