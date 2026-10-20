"""Class-based FastAPI views and Tortoise model viewsets."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from typing import Any, ClassVar, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.routing import APIRoute
from tortoise.exceptions import DoesNotExist
from tortoise.models import Model as TortoiseModel

from drfast.actions import Action
from drfast.filters import FilterSet
from drfast.pagination import LimitOffsetPagination
from drfast.permissions import AllowAny, BasePermission, enforce_permissions
from drfast.serializers import ModelSerializer, SerializerValidationError

# Starlette renamed the 422 constant; the literal works with every supported version.
HTTP_422_UNPROCESSABLE = 422


class APIView:
	"""Base class for a FastAPI route group with DRF-style permissions."""

	permission_classes: ClassVar[tuple[type[BasePermission], ...]] = (AllowAny,)
	authentication_dependencies: ClassVar[tuple[Callable[..., Any], ...]] = ()

	async def check_permissions(
		self,
		request: Request,
		obj: Any | None = None,
		*,
		permission_classes: Sequence[type[BasePermission]] | None = None,
	) -> None:
		configured_permissions = permission_classes or getattr(
			request.state, "drfast_permission_classes", None
		)
		await enforce_permissions(
			request, self, obj, permission_classes=configured_permissions
		)


class ModelViewSet(APIView):
	"""Async CRUD viewset for a Tortoise model."""

	model: ClassVar[type[TortoiseModel]]
	serializer_class: ClassVar[type[ModelSerializer[Any]]]
	filterset_class: ClassVar[type[FilterSet] | None] = None
	pagination_class: ClassVar[type[LimitOffsetPagination] | None] = LimitOffsetPagination
	ordering_fields: ClassVar[tuple[str, ...]] = ()
	lookup_field: ClassVar[str] = "id"
	lookup_url_kwarg: ClassVar[str] = "pk"
	lookup_type: ClassVar[type[Any]] = UUID

	def get_queryset(self, request: Request) -> Any:
		"""Rows this request may reach; list, retrieve, update and delete all start here.

		Override to scope rows to the requester. Rows outside it are a 404, not a 403.
		"""
		return self.model.filter()

	async def perform_create(self, request: Request, serializer: ModelSerializer[Any]) -> Any:
		"""Save a new instance; override to add server-owned values via ``serializer.save()``."""
		return await serializer.save()

	async def perform_update(self, request: Request, serializer: ModelSerializer[Any]) -> Any:
		return await serializer.save()

	async def perform_destroy(self, request: Request, instance: TortoiseModel) -> None:
		await instance.delete()

	def serializer(
		self,
		instance: Any | None = None,
		*,
		partial: bool = False,
	) -> ModelSerializer[Any]:
		return self.serializer_class(instance, partial=partial)

	async def get_object(
		self,
		request: Request,
		pk: Any,
		*,
		parent_field: str | None = None,
		parent_pk: UUID | None = None,
	) -> TortoiseModel:
		try:
			parent_filter = self._parent_filter(parent_field, parent_pk)
			obj = await self.get_queryset(request).filter(
				**{self.lookup_field: pk, **parent_filter}
			).get()
		except DoesNotExist as exc:
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.") from exc
		await self.check_permissions(request, obj)
		return cast(TortoiseModel, obj)

	@staticmethod
	def _parent_filter(parent_field: str | None, parent_pk: UUID | None) -> dict[str, UUID]:
		if parent_field is None and parent_pk is None:
			return {}
		if parent_field is None or parent_pk is None:
			raise ValueError("parent_field and parent_pk must be provided together.")
		return {parent_field: parent_pk}

	@staticmethod
	def _parent_input_fields(parent_field: str | None) -> tuple[str, ...]:
		if parent_field is None:
			return ()
		relation_field = parent_field.removesuffix("_id")
		return (parent_field,) if relation_field == parent_field else (parent_field, relation_field)

	def _queryset(
		self,
		request: Request,
		*,
		parent_field: str | None = None,
		parent_pk: UUID | None = None,
	) -> Any:
		parent_filter = self._parent_filter(parent_field, parent_pk)
		queryset = self.get_queryset(request)
		if parent_filter:
			queryset = queryset.filter(**parent_filter)
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

	async def list(
		self,
		request: Request,
		*,
		parent_field: str | None = None,
		parent_pk: UUID | None = None,
	) -> dict[str, Any] | list[dict[str, Any]]:
		await self.check_permissions(request)
		queryset = self._queryset(request, parent_field=parent_field, parent_pk=parent_pk)
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

	async def retrieve(
		self,
		request: Request,
		pk: Any,
		*,
		parent_field: str | None = None,
		parent_pk: UUID | None = None,
	) -> dict[str, Any]:
		instance = await self.get_object(
			request, pk, parent_field=parent_field, parent_pk=parent_pk
		)
		return self.serializer(instance).representation(instance)

	async def create(
		self,
		request: Request,
		payload: dict[str, Any],
		*,
		parent_field: str | None = None,
		parent_pk: UUID | None = None,
	) -> dict[str, Any]:
		await self.check_permissions(request)
		serializer = self.serializer()
		parent_filter = self._parent_filter(parent_field, parent_pk)
		try:
			if parent_filter:
				await serializer.is_valid(
					payload,
					exclude_fields=self._parent_input_fields(parent_field),
					additional_data=parent_filter,
				)
			else:
				await serializer.is_valid(payload)
		except SerializerValidationError as exc:
			raise HTTPException(
				status_code=HTTP_422_UNPROCESSABLE,
				detail=exc.detail,
			) from exc
		if parent_filter:
			serializer.validated_data.update(parent_filter)
		instance = await self.perform_create(request, serializer)
		return serializer.representation(instance)

	async def update(
		self,
		request: Request,
		pk: Any,
		payload: dict[str, Any],
		*,
		partial: bool,
		parent_field: str | None = None,
		parent_pk: UUID | None = None,
	) -> dict[str, Any]:
		parent_filter = self._parent_filter(parent_field, parent_pk)
		instance = await self.get_object(
			request, pk, parent_field=parent_field, parent_pk=parent_pk
		)
		serializer = self.serializer(instance, partial=partial)
		try:
			if parent_filter:
				await serializer.is_valid(
					payload,
					exclude_fields=self._parent_input_fields(parent_field),
					additional_data=parent_filter,
				)
			else:
				await serializer.is_valid(payload)
		except SerializerValidationError as exc:
			raise HTTPException(
				status_code=HTTP_422_UNPROCESSABLE,
				detail=exc.detail,
			) from exc
		if parent_filter:
			serializer.validated_data.update(parent_filter)
		instance = await self.perform_update(request, serializer)
		return serializer.representation(instance)

	async def destroy(
		self,
		request: Request,
		pk: Any,
		*,
		parent_field: str | None = None,
		parent_pk: UUID | None = None,
	) -> None:
		instance = await self.get_object(
			request, pk, parent_field=parent_field, parent_pk=parent_pk
		)
		await self.perform_destroy(request, instance)

	def as_router(
		self,
		*,
		prefix: str,
		tags: Sequence[str] | None = None,
		parent_parameter: str | None = None,
		parent_field: str | None = None,
		route_class: type[APIRoute] = APIRoute,
	) -> APIRouter:
		"""Build conventional collection/detail routes for this viewset.

		Pass ``route_class=VersionedRoute`` so ``@versions`` on actions is enforced.
		"""
		if (parent_parameter is None) != (parent_field is None):
			raise ValueError("parent_parameter and parent_field must be provided together.")
		if parent_parameter is not None and f"{{{parent_parameter}}}" not in prefix:
			raise ValueError("parent_parameter must be present in the router prefix.")
		if not self.lookup_url_kwarg or "/" in self.lookup_url_kwarg:
			raise ValueError("lookup_url_kwarg must be a single path parameter name.")
		if parent_parameter == self.lookup_url_kwarg:
			raise ValueError("lookup_url_kwarg must differ from parent_parameter.")

		router = APIRouter(prefix=prefix, tags=[*tags] if tags else [], route_class=route_class)
		parent_input_fields = self._parent_input_fields(parent_field)
		if parent_input_fields:
			input_schema = self.serializer_class.input_schema(exclude_fields=parent_input_fields)
			partial_input_schema = self.serializer_class._schema(
				for_input=True, partial=True, exclude_fields=parent_input_fields
			)
		else:
			input_schema = self.serializer_class.input_schema()
			partial_input_schema = self.serializer_class._schema(for_input=True, partial=True)
		output_schema = self.serializer_class.output_schema()
		dependencies = [Depends(dependency) for dependency in self.authentication_dependencies]

		def parent_pk(path_parameters: dict[str, Any]) -> UUID | None:
			return path_parameters.get(parent_parameter) if parent_parameter is not None else None

		def lookup_value(path_parameters: dict[str, Any]) -> Any:
			return path_parameters[self.lookup_url_kwarg]

		async def list_view(request: Request, **path_parameters: Any) -> Any:
			if parent_field is None:
				return await self.list(request)
			return await self.list(
				request, parent_field=parent_field, parent_pk=parent_pk(path_parameters)
			)

		async def retrieve_view(request: Request, **path_parameters: Any) -> Any:
			pk = lookup_value(path_parameters)
			if parent_field is None:
				return await self.retrieve(request, pk)
			return await self.retrieve(
				request,
				pk,
				parent_field=parent_field,
				parent_pk=parent_pk(path_parameters),
			)

		async def create_view(request: Request, payload: Any, **path_parameters: Any) -> Any:
			if parent_field is None:
				return await self.create(request, payload.model_dump(exclude_unset=True))
			return await self.create(
				request,
				payload.model_dump(exclude_unset=True),
				parent_field=parent_field,
				parent_pk=parent_pk(path_parameters),
			)

		async def update_view(request: Request, payload: Any, **path_parameters: Any) -> Any:
			pk = lookup_value(path_parameters)
			if parent_field is None:
				return await self.update(
					request, pk, payload.model_dump(exclude_unset=True), partial=False
				)
			return await self.update(
				request,
				pk,
				payload.model_dump(exclude_unset=True),
				partial=False,
				parent_field=parent_field,
				parent_pk=parent_pk(path_parameters),
			)

		async def partial_update_view(
			request: Request, payload: Any, **path_parameters: Any
		) -> Any:
			pk = lookup_value(path_parameters)
			if parent_field is None:
				return await self.update(
					request, pk, payload.model_dump(exclude_unset=True), partial=True
				)
			return await self.update(
				request,
				pk,
				payload.model_dump(exclude_unset=True),
				partial=True,
				parent_field=parent_field,
				parent_pk=parent_pk(path_parameters),
			)

		async def destroy_view(request: Request, **path_parameters: Any) -> None:
			pk = lookup_value(path_parameters)
			if parent_field is None:
				await self.destroy(request, pk)
				return
			await self.destroy(
				request,
				pk,
				parent_field=parent_field,
				parent_pk=parent_pk(path_parameters),
			)

		def signature(*parameters: inspect.Parameter) -> inspect.Signature:
			return inspect.Signature(parameters)

		request_parameter = inspect.Parameter(
			"request", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Request
		)
		pk_parameter = inspect.Parameter(
			self.lookup_url_kwarg,
			inspect.Parameter.POSITIONAL_OR_KEYWORD,
			annotation=self.lookup_type,
		)
		parent_parameter_definition = (
			inspect.Parameter(
				parent_parameter, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=UUID
			)
			if parent_parameter is not None
			else None
		)
		path_parameters = (
			(parent_parameter_definition,) if parent_parameter_definition is not None else ()
		)
		cast(Any, list_view).__signature__ = signature(request_parameter, *path_parameters)
		cast(Any, retrieve_view).__signature__ = signature(
			request_parameter, *path_parameters, pk_parameter
		)
		cast(Any, create_view).__signature__ = signature(
			request_parameter,
			*path_parameters,
			inspect.Parameter(
				"payload",
				inspect.Parameter.POSITIONAL_OR_KEYWORD,
				default=Body(...),
				annotation=input_schema,
			),
		)
		cast(Any, update_view).__signature__ = signature(
			request_parameter,
			*path_parameters,
			pk_parameter,
			inspect.Parameter(
				"payload",
				inspect.Parameter.POSITIONAL_OR_KEYWORD,
				default=Body(...),
				annotation=input_schema,
			),
		)
		cast(Any, partial_update_view).__signature__ = signature(
			request_parameter,
			*path_parameters,
			pk_parameter,
			inspect.Parameter(
				"payload",
				inspect.Parameter.POSITIONAL_OR_KEYWORD,
				default=Body(...),
				annotation=partial_input_schema,
			),
		)
		cast(Any, destroy_view).__signature__ = signature(
			request_parameter, *path_parameters, pk_parameter
		)
		router.add_api_route(
			"/",
			list_view,
			methods=["GET"],
			response_model=None,
			dependencies=dependencies,
		)

		def action_parameters(
			handler: Callable[..., Any], configuration: Action, *, detail: bool
		) -> tuple[inspect.Parameter, ...]:
			parameters = inspect.signature(handler).parameters
			path_names = {"request", *(() if parent_parameter is None else (parent_parameter,))}
			if detail:
				path_names.add(self.lookup_url_kwarg)
				path_names.add("pk")
			additional = [
				parameter
				for name, parameter in parameters.items()
				if name not in path_names
				and parameter.kind
				not in {inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL}
			]
			if configuration.serializer_class is not None:
				additional = [parameter for parameter in additional if parameter.name != "payload"]
				additional.append(
					inspect.Parameter(
						"payload",
						inspect.Parameter.POSITIONAL_OR_KEYWORD,
						default=Body(...),
						annotation=configuration.serializer_class.input_schema(),
					)
				)
			return tuple(additional)

		def action_view(
			handler: Callable[..., Any], configuration: Action
		) -> Callable[..., Any]:
			handler_parameters = inspect.signature(handler).parameters
			accepts_keyword_arguments = any(
				parameter.kind == inspect.Parameter.VAR_KEYWORD
				for parameter in handler_parameters.values()
			)

			async def endpoint(**route_arguments: Any) -> Any:
				request = cast(Request, route_arguments["request"])
				if configuration.permission_classes is not None:
					request.state.drfast_permission_classes = configuration.permission_classes
					await self.check_permissions(request)
				if "payload" in route_arguments and hasattr(
					route_arguments["payload"], "model_dump"
				):
					route_arguments["payload"] = route_arguments["payload"].model_dump(
						exclude_unset=True
					)
				if self.lookup_url_kwarg not in handler_parameters and "pk" in handler_parameters:
					route_arguments["pk"] = route_arguments[self.lookup_url_kwarg]
				arguments = (
					route_arguments
					if accepts_keyword_arguments
					else {
						name: value
						for name, value in route_arguments.items()
						if name in handler_parameters
					}
				)
				result = handler(**arguments)
				return await result if inspect.isawaitable(result) else result

			return endpoint

		def add_actions(*, detail: bool) -> None:
			for name, handler in inspect.getmembers(self, predicate=callable):
				configuration = getattr(handler, "__drfast_action__", None)
				if not isinstance(configuration, Action) or configuration.detail != detail:
					continue
				path = (configuration.path or name.replace("_", "-")).strip("/")
				if not path:
					raise ValueError("An action path cannot be empty.")
				route_path = (
					f"/{{{self.lookup_url_kwarg}}}/{path}" if detail else f"/{path}"
				)
				endpoint = action_view(handler, configuration)
				parameters = [request_parameter, *path_parameters]
				if detail:
					parameters.append(pk_parameter)
				parameters.extend(action_parameters(handler, configuration, detail=detail))
				cast(Any, endpoint).__signature__ = signature(*parameters)
				action_dependencies = [
					*dependencies,
					*[
						Depends(dependency)
						for dependency in configuration.authentication_dependencies or ()
					],
				]
				router.add_api_route(
					route_path,
					endpoint,
					methods=list(configuration.methods),
					response_model=configuration.response_model,
					status_code=configuration.status_code,
					dependencies=action_dependencies,
					tags=list(configuration.tags) if configuration.tags is not None else None,
				)

		add_actions(detail=False)
		add_actions(detail=True)
		router.add_api_route(
			f"/{{{self.lookup_url_kwarg}}}",
			retrieve_view,
			methods=["GET"],
			response_model=output_schema,
			dependencies=dependencies,
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
			f"/{{{self.lookup_url_kwarg}}}",
			update_view,
			methods=["PUT"],
			response_model=output_schema,
			dependencies=dependencies,
		)
		router.add_api_route(
			f"/{{{self.lookup_url_kwarg}}}",
			partial_update_view,
			methods=["PATCH"],
			response_model=output_schema,
			dependencies=dependencies,
		)

		router.add_api_route(
			f"/{{{self.lookup_url_kwarg}}}",
			destroy_view,
			methods=["DELETE"],
			status_code=status.HTTP_204_NO_CONTENT,
			dependencies=dependencies,
		)

		return router

