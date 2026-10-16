Permissions and authentication
==============================

Permissions determine whether an authenticated or anonymous request may access
a view or object. Authentication identifies the caller. Keep those concerns
separate: authentication dependencies populate the request state, and
permissions make authorization decisions.

Permissions
-----------

Every DRFast view allows requests by default with ``AllowAny``. Set
``permission_classes`` on a viewset to require a user or administrator:

.. code-block:: python

   from drfast import IsAuthenticated, ModelViewSet

   class PrivateArticleViewSet(ModelViewSet):
       model = Article
       serializer_class = ArticleSerializer
       permission_classes = (IsAuthenticated,)

``IsAuthenticated`` and ``IsAdminUser`` read ``request.state.user``. The
authentication setup below provides that value. For object-level rules, subclass
``BasePermission`` and implement ``has_permission`` and/or ``has_object_permission``:

.. code-block:: python

   from fastapi import Request
   from drfast import BasePermission

   class IsArticleAuthor(BasePermission):
       async def has_object_permission(
           self, request: Request, view: object, obj: Article
       ) -> bool:
           user = getattr(request.state, "user", None)
           return user is not None and obj.author_id == user.id

   class ArticleViewSet(ModelViewSet):
       model = Article
       serializer_class = ArticleSerializer
       permission_classes = (IsArticleAuthor,)

Views call object permissions when retrieving, updating, and deleting an object.
Collection operations call ``has_permission``. Return ``False`` to produce a
403 response.

FastAPI Users integration
-------------------------

DRFast API includes helpers for `FastAPI Users
<https://fastapi-users.github.io/fastapi-users/>`_ with Tortoise. Define a user
model and configure the user database, manager, and JWT backend during
application setup:

.. code-block:: python

   from collections.abc import AsyncGenerator
   from fastapi import Depends
   from drfast.auth import (
       DRFastUserManager,
       FastAPIUserModel,
       TortoiseUserDatabase,
       build_fastapi_users,
       current_user_middleware,
       jwt_authentication,
   )

   class User(FastAPIUserModel):
       pass

   async def get_user_db() -> AsyncGenerator[TortoiseUserDatabase[User], None]:
       yield TortoiseUserDatabase(User)

   class UserManager(DRFastUserManager[User]):
       reset_password_token_secret = settings.secret_key.get_secret_value()
       verification_token_secret = settings.secret_key.get_secret_value()

   async def get_user_manager(
       user_db: TortoiseUserDatabase[User] = Depends(get_user_db),
   ) -> AsyncGenerator[UserManager, None]:
       yield UserManager(user_db)

   auth_backend = jwt_authentication(settings.secret_key.get_secret_value())
   fastapi_users = build_fastapi_users(get_user_manager, auth_backend)

   app.include_router(
       fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
   )
   app.include_router(fastapi_users.get_register_router(), prefix="/auth", tags=["auth"])

``current_user_middleware`` is a dependency that puts the currently active
user on ``request.state.user``. Apply it to a protected viewset:

.. code-block:: python

   class PrivateArticleViewSet(ModelViewSet):
       model = Article
       serializer_class = ArticleSerializer
       permission_classes = (IsAuthenticated,)
       authentication_dependencies = (
           current_user_middleware(fastapi_users.current_user(active=True)),
       )

Register account-related models in ``DRFAST_INSTALLED_APPS`` and run migrations
before using these routes. Keep the JWT secret in ``DRFAST_SECRET_KEY`` outside
version control and rotate it using your normal secret-management process.
