"""Declarative extra routes for model viewsets."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Action:
	"""Configuration attached to a viewset method by :func:`action`."""

	detail: bool
	methods: tuple[str, ...]
	path: str | None
	serializer_class: type[Any] | None
	permission_classes: tuple[type[Any], ...] | None
	authentication_dependencies: tuple[Callable[..., Any], ...] | None
	response_model: Any
	status_code: int | None
	tags: tuple[str, ...] | None


def action(
	*,
	detail: bool,
	methods: Sequence[str] = ("GET",),
	path: str | None = None,
	serializer_class: type[Any] | None = None,
	permission_classes: Sequence[type[Any]] | None = None,
	authentication_dependencies: Sequence[Callable[..., Any]] | None = None,
	response_model: Any = None,
	status_code: int | None = None,
	tags: Sequence[str] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
	"""Expose a viewset method as a detail or collection route.

	Action handlers receive the same named path parameters declared by their
	router prefix. When ``serializer_class`` is set, a ``payload`` argument is
	validated using that serializer's input schema.
	"""
	if not methods:
		raise ValueError("An action must declare at least one HTTP method.")
	if any(not method or method.upper() != method for method in methods):
		raise ValueError("Action methods must be uppercase HTTP method names.")

	configuration = Action(
		detail=detail,
		methods=tuple(methods),
		path=path,
		serializer_class=serializer_class,
		permission_classes=tuple(permission_classes) if permission_classes else None,
		authentication_dependencies=(
			tuple(authentication_dependencies) if authentication_dependencies else None
		),
		response_model=response_model,
		status_code=status_code,
		tags=tuple(tags) if tags else None,
	)

	def decorate(handler: Callable[..., Any]) -> Callable[..., Any]:
		setattr(handler, "__drfast_action__", configuration)  # noqa: B010
		return handler

	return decorate
