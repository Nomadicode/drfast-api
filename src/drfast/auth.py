"""Current FastAPI Users integration backed by Tortoise ORM.

FastAPI Users no longer ships a Tortoise adapter. This module maintains the
small persistence bridge while leaving its authentication and security flows
to FastAPI Users.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import Any, Generic, Protocol, Self, TypeVar
from uuid import UUID

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.db import BaseUserDatabase
from fastapi_users.manager import UUIDIDMixin
from fastapi_users.models import UserProtocol
from tortoise import fields

from drfast.models import Model, TimestampedModel


class TortoiseUserProtocol(UserProtocol[UUID], Protocol):
	"""Structural contract required by the Tortoise FastAPI Users adapter."""

	@classmethod
	async def get_or_none(cls, **kwargs: Any) -> Self | None: ...

	@classmethod
	async def create(cls, **kwargs: Any) -> Self: ...

	async def save(self, *, update_fields: list[str]) -> None: ...

	async def delete(self) -> None: ...


UserType = TypeVar("UserType", bound=TortoiseUserProtocol)
AuthUserType = TypeVar("AuthUserType", bound=UserProtocol[UUID])


class FastAPIUserModel(Model, TimestampedModel):
	"""Ready-to-use Tortoise user table base with FastAPI Users fields."""

	email = fields.CharField(max_length=320, unique=True, index=True)
	hashed_password = fields.CharField(max_length=1024)
	is_active = fields.BooleanField(default=True)
	is_superuser = fields.BooleanField(default=False)
	is_verified = fields.BooleanField(default=False)

	class Meta:
		abstract = True


class TortoiseUserDatabase(BaseUserDatabase[UserType, UUID], Generic[UserType]):
	"""FastAPI Users persistence adapter for a Tortoise UUID user model."""

	def __init__(self, user_model: type[UserType]) -> None:
		self.user_model = user_model

	async def get(self, id: UUID) -> UserType | None:
		return await self.user_model.get_or_none(id=id)

	async def get_by_email(self, email: str) -> UserType | None:
		return await self.user_model.get_or_none(email=email)

	async def create(self, create_dict: dict[str, Any]) -> UserType:
		return await self.user_model.create(**create_dict)

	async def update(self, user: UserType, update_dict: dict[str, Any]) -> UserType:
		for key, value in update_dict.items():
			setattr(user, key, value)
		await user.save(update_fields=list(update_dict))
		return user

	async def delete(self, user: UserType) -> None:
		await user.delete()


class DRFastUserManager(UUIDIDMixin, BaseUserManager[UserType, UUID], Generic[UserType]):
	"""Base manager applications subclass to add password and event policies."""

	reset_password_token_secret: str
	verification_token_secret: str


def jwt_authentication(
	secret: str,
	lifetime_seconds: int = 3600,
) -> AuthenticationBackend[AuthUserType, UUID]:
	"""Build FastAPI Users' bearer/JWT backend for generated projects."""
	bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")

	def get_strategy() -> JWTStrategy[AuthUserType, UUID]:
		return JWTStrategy(secret=secret, lifetime_seconds=lifetime_seconds)

	return AuthenticationBackend[AuthUserType, UUID](
		name="jwt", transport=bearer_transport, get_strategy=get_strategy
	)


def build_fastapi_users(
	get_user_manager: Callable[..., AsyncGenerator[DRFastUserManager[UserType], None]],
	backend: AuthenticationBackend[UserType, UUID],
) -> FastAPIUsers[UserType, UUID]:
	"""Create a FastAPI Users facade from application dependencies."""
	return FastAPIUsers(get_user_manager, [backend])


def current_user_middleware(
	current_active_user: Callable[..., Any],
) -> Callable[[Request, Any], Any]:
	"""Adapt a FastAPI Users dependency for DRFast permission classes.

	Use this with a normal FastAPI dependency on protected routes when request
	state is desired by custom `BasePermission` implementations.
	"""
	async def dependency(  # noqa: B008 - FastAPI resolves dependencies from the signature.
		request: Request, user: Any = Depends(current_active_user)  # noqa: B008
	) -> Any:
		request.state.user = user
		return user

	return dependency

