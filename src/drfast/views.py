"""Class-based FastAPI views and Tortoise model viewsets."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, ClassVar
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from tortoise.exceptions import DoesNotExist
from tortoise.models import Model as TortoiseModel

from drfast.filters import FilterSet
from drfast.pagination import LimitOffsetPagination
from drfast.permissions import AllowAny, BasePermission, enforce_permissions
from drfast.serializers import ModelSerializer, SerializerValidationError


class APIView:
	"""Base class for a FastAPI route group with DRF-style permissions."""

	permission_classes: ClassVar[tuple[type[BasePermission], ...]] = (AllowAny,)
	authentication_dependencies: ClassVar[tuple[Callable[..., Any], ...]] = ()

	async def check_permissions(self, request: Request, obj: Any | None = None) -> None:
		await enforce_permissions(request, self, obj)


class ModelViewSet(APIView):
	"""Async CRUD viewset for a Tortoise model."""

	model: ClassVar[type[TortoiseModel]]
	serializer_class: ClassVar[type[ModelSerializer[Any]]]
	filterset_class: ClassVar[type[FilterSet] | None] = None
	pagination_class: ClassVar[type[LimitOffsetPagination] | None] = LimitOffsetPagination
	ordering_fields: ClassVar[tuple[str, ...]] = ()

	def serializer(
		self,
		instance: Any | None = None,
		*,
		partial: bool = False,
	) -> ModelSerializer[Any]:
		return self.serializer_class(instance, partial=partial)

	async def get_object(self, request: Request, pk: UUID) -> TortoiseModel:
		try:
			obj = await self.model.get(id=pk)
		except DoesNotExist as exc:
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.") from exc
		await self.check_permissions(request, obj)
		return obj

	def _queryset(self, request: Request) -> Any:
		queryset = self.model.all()
		if self.filterset_class is not None:
			queryset = queryset.filter(**self.filterset_class.filters_from_request(request))
		ordering = request.query_params.get("ordering")
		if ordering:
			fields = tuple(field.strip() for field in ordering.split(",") if field.strip())
			if not fields or any(
				field.removeprefix("-") not in self.ordering_fields for field in fields
			):
				raise HTTPException(
					status_code=status.HTTP_400_BAD_REQUEST,
					detail="Invalid ordering.",
				)
			queryset = queryset.order_by(*fields)
		return queryset

	async def list(self, request: Request) -> dict[str, Any] | list[dict[str, Any]]:
		await self.check_permissions(request)
		queryset = self._queryset(request)
		if self.pagination_class is None:
			instances = await queryset
			return [self.serializer(instance).representation(instance) for instance in instances]
		paginator = self.pagination_class()
		limit, offset = paginator.parameters(request)
		count = await queryset.count()
		instances = await queryset.offset(offset).limit(limit)
		return paginator.response(
			request,
			count=count,
			offset=offset,
			limit=limit,
			results=[
				self.serializer(instance).representation(instance) for instance in instances
			],
		)

	async def retrieve(self, request: Request, pk: UUID) -> dict[str, Any]:
		instance = await self.get_object(request, pk)
		return self.serializer(instance).representation(instance)

	async def create(self, request: Request, payload: dict[str, Any]) -> dict[str, Any]:
		await self.check_permissions(request)
		serializer = self.serializer()
		try:
			await serializer.is_valid(payload)
		except SerializerValidationError as exc:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
				detail=exc.detail,
			) from exc
		instance = await serializer.save()
		return serializer.representation(instance)

	async def update(
		self,
		request: Request,
		pk: UUID,
		payload: dict[str, Any],
		*,
		partial: bool,
	) -> dict[str, Any]:
		instance = await self.get_object(request, pk)
		serializer = self.serializer(instance, partial=partial)
		try:
			await serializer.is_valid(payload)
		except SerializerValidationError as exc:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
				detail=exc.detail,
			) from exc
		instance = await serializer.save()
		return serializer.representation(instance)

	async def destroy(self, request: Request, pk: UUID) -> None:
		instance = await self.get_object(request, pk)
		await instance.delete()

	def as_router(self, *, prefix: str, tags: list[str] | None = None) -> APIRouter:
		"""Build conventional collection/detail routes for this viewset."""
		router = APIRouter(prefix=prefix, tags=tags or [])
		input_schema = self.serializer_class.input_schema()
		partial_input_schema = self.serializer_class._schema(for_input=True, partial=True)
		output_schema = self.serializer_class.output_schema()
		dependencies = [Depends(dependency) for dependency in self.authentication_dependencies]

		@router.get("/", response_model=None, dependencies=dependencies)
		async def list_view(request: Request) -> Any:
			return await self.list(request)

		@router.get("/{pk}", response_model=output_schema, dependencies=dependencies)
		async def retrieve_view(request: Request, pk: UUID) -> Any:
			return await self.retrieve(request, pk)

		async def create_view(request: Request, payload: Any) -> Any:
			return await self.create(request, payload.model_dump(exclude_unset=True))

		async def update_view(request: Request, pk: UUID, payload: Any) -> Any:
			return await self.update(
				request, pk, payload.model_dump(exclude_unset=True), partial=False
			)

		async def partial_update_view(request: Request, pk: UUID, payload: Any) -> Any:
			return await self.update(
				request, pk, payload.model_dump(exclude_unset=True), partial=True
			)

		def signature(*parameters: inspect.Parameter) -> inspect.Signature:
			return inspect.Signature(parameters)

		request_parameter = inspect.Parameter(
			"request", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Request
		)
		pk_parameter = inspect.Parameter(
			"pk", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=UUID
		)
		create_view.__signature__ = signature(
			request_parameter,
			inspect.Parameter(
				"payload",
				inspect.Parameter.POSITIONAL_OR_KEYWORD,
				default=Body(...),
				annotation=input_schema,
			),
		)
		update_view.__signature__ = signature(
			request_parameter,
			pk_parameter,
			inspect.Parameter(
				"payload",
				inspect.Parameter.POSITIONAL_OR_KEYWORD,
				default=Body(...),
				annotation=input_schema,
			),
		)
		partial_update_view.__signature__ = signature(
			request_parameter,
			pk_parameter,
			inspect.Parameter(
				"payload",
				inspect.Parameter.POSITIONAL_OR_KEYWORD,
				default=Body(...),
				annotation=partial_input_schema,
			),
		)
		router.add_api_route(
			"/",
			create_view,
			methods=["POST"],
			response_model=output_schema,
			status_code=status.HTTP_201_CREATED,
			dependencies=dependencies,
		)
		router.add_api_route(
			"/{pk}",
			update_view,
			methods=["PUT"],
			response_model=output_schema,
			dependencies=dependencies,
		)
		router.add_api_route(
			"/{pk}",
			partial_update_view,
			methods=["PATCH"],
			response_model=output_schema,
			dependencies=dependencies,
		)

		@router.delete(
			"/{pk}", status_code=status.HTTP_204_NO_CONTENT, dependencies=dependencies
		)
		async def destroy_view(request: Request, pk: UUID) -> None:
			await self.destroy(request, pk)

		return router

