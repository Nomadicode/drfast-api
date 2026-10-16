"""Async DRF-style permission primitives."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status


class BasePermission:
	"""Base for request-level and object-level access rules."""

	message = "You do not have permission to perform this action."

	async def has_permission(self, request: Request, view: Any) -> bool:
		return True

	async def has_object_permission(self, request: Request, view: Any, obj: Any) -> bool:
		return await self.has_permission(request, view)


class AllowAny(BasePermission):
	pass


class IsAuthenticated(BasePermission):
	message = "Authentication credentials were not provided."

	async def has_permission(self, request: Request, view: Any) -> bool:
		user = getattr(request.state, "user", None)
		return user is not None and bool(getattr(user, "is_active", True))


class IsAdminUser(IsAuthenticated):
	message = "Administrator access is required."

	async def has_permission(self, request: Request, view: Any) -> bool:
		return await super().has_permission(request, view) and bool(
			getattr(request.state.user, "is_superuser", False)
		)


async def enforce_permissions(request: Request, view: Any, obj: Any | None = None) -> None:
	"""Raise a uniform HTTP error for failed configured permissions."""
	for permission_type in getattr(view, "permission_classes", (AllowAny,)):
		permission = permission_type()
		allowed = (
			await permission.has_object_permission(request, view, obj)
			if obj is not None
			else await permission.has_permission(request, view)
		)
		if not allowed:
			raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=permission.message)

