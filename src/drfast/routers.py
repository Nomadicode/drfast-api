"""Router registry for model viewsets."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI

from drfast.views import ModelViewSet


class DefaultRouter:
	"""Register viewsets then mount their FastAPI routes explicitly."""

	def __init__(self) -> None:
		self._registry: list[tuple[str, type[ModelViewSet], str | None]] = []

	def register(
		self,
		prefix: str,
		viewset: type[ModelViewSet],
		*,
		basename: str | None = None,
	) -> None:
		self._registry.append((prefix.rstrip("/"), viewset, basename))

	def urls(self) -> list[APIRouter]:
		return [
			viewset().as_router(prefix=prefix, tags=[basename or prefix])
			for prefix, viewset, basename in self._registry
		]

	def include_in(self, app: FastAPI, *, prefix: str = "") -> None:
		for router in self.urls():
			app.include_router(router, prefix=prefix)

	def routes(self) -> list[dict[str, Any]]:
		return [
			{"prefix": prefix, "viewset": viewset.__name__, "basename": basename}
			for prefix, viewset, basename in self._registry
		]

