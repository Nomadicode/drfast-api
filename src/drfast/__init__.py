"""DRF-inspired primitives for async FastAPI applications."""

from drfast.actions import action
from drfast.filters import FilterSet
from drfast.middleware import (
	BaseMiddleware,
	BaseThrottle,
	ThrottleMiddleware,
	VersioningMiddleware,
	install_asgi_middleware,
	install_middleware,
	install_policy_middleware,
)
from drfast.models import Model, SoftDeleteModel, TimestampedModel
from drfast.pagination import LimitOffsetPagination
from drfast.permissions import AllowAny, BasePermission, IsAdminUser, IsAuthenticated
from drfast.routers import DefaultRouter
from drfast.serializers import (
	BooleanField,
	CharField,
	EmailField,
	IntegerField,
	ModelSerializer,
	RelatedField,
	Serializer,
	UUIDField,
)
from drfast.settings import DRFastSettings
from drfast.views import APIView, ModelViewSet

__all__ = [
	"APIView",
	"action",
	"AllowAny",
	"BaseMiddleware",
	"BaseThrottle",
	"BasePermission",
	"BooleanField",
	"CharField",
	"DRFastSettings",
	"DefaultRouter",
	"EmailField",
	"FilterSet",
	"IntegerField",
	"IsAdminUser",
	"IsAuthenticated",
	"LimitOffsetPagination",
	"Model",
	"ModelSerializer",
	"ModelViewSet",
	"RelatedField",
	"Serializer",
	"SoftDeleteModel",
	"ThrottleMiddleware",
	"TimestampedModel",
	"UUIDField",
	"VersioningMiddleware",
	"install_asgi_middleware",
	"install_middleware",
	"install_policy_middleware",
]

