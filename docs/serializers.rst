Serializers
===========

Serializers turn request payloads into validated data and model instances into
JSON-ready dictionaries. The validation schema is generated with Pydantic, so
viewsets retain FastAPI request validation and useful OpenAPI documentation.

Explicit serializers
--------------------

Subclass :class:`drfast.Serializer` when the payload is not a direct model
mapping or when the creation workflow needs custom behavior. Declare fields with
``CharField``, ``EmailField``, ``IntegerField``, ``BooleanField``, or
``UUIDField``.

.. code-block:: python

   from drfast import CharField, IntegerField, Serializer

   class InvitationSerializer(Serializer):
       email = CharField()
       project_id = CharField()
       expires_in_days = IntegerField(required=False, default=7)

       def validate_expires_in_days(self, value: int) -> int:
           if not 1 <= value <= 30:
               raise ValueError("Must be between 1 and 30 days.")
           return value

       def validate(self, attrs: dict[str, object]) -> dict[str, object]:
           if attrs["email"].endswith("@example.invalid"):
               raise ValueError("Disposable email addresses are not allowed.")
           return attrs

       async def create(self, validated_data: dict[str, object]):
           return await create_invitation(**validated_data)

Field-specific hooks named ``validate_<field_name>`` and the cross-field
``validate`` hook may be synchronous or asynchronous. Raise ``ValueError`` for
invalid values; they are reported like Pydantic errors, located at the field.
Calling ``await serializer.is_valid(payload)`` raises
``SerializerValidationError`` when validation fails; ``ModelViewSet`` converts
that error to a 422 response automatically.

``serializer.save(**kwargs)`` adds server-owned values to the validated data
before ``create`` or ``update``, as in Django REST Framework.

Model serializers
-----------------

For ordinary Tortoise persistence, subclass :class:`drfast.ModelSerializer`:

.. code-block:: python

   from drfast import ModelSerializer
   from .models import Article

   class ArticleSerializer(ModelSerializer[Article]):
       model = Article
       fields = ("id", "title", "body", "created_at", "updated_at")
       read_only_fields = ("title",)

``ModelSerializer`` provides asynchronous ``create`` and ``update`` methods.
If no fields are declared, it derives fields from the selected Tortoise model
fields. Automatic identifier and timestamp fields are read-only, nullable
columns accept and return ``null``, and decimal columns become ``DecimalField``
with the column's decimal places.

More field types
----------------

* ``allow_null=True`` on any field accepts and returns ``None``.
* ``DecimalField`` renders fixed-point strings (``"6000.00"``), never exponent
  notation. Pass ``decimal_places`` for a constant number of places.
* ``FileField`` (alias ``ImageField``) renders a model file field as its URL and
  is read-only; see :doc:`fields-and-files`.

Input and output control
------------------------

Set ``read_only=True`` or ``write_only=True`` on a declared field to keep it out
of input or output respectively. ``alias=`` exposes a different JSON name while
the validated dictionary uses the Python field name:

.. code-block:: python

   from drfast import CharField, Serializer

   class ProfileSerializer(Serializer):
       display_name = CharField(alias="displayName")
       password = CharField(write_only=True)
       account_id = CharField(read_only=True)

Use ``partial=True`` when constructing a serializer for patch-style updates; a
``ModelViewSet`` handles this for its ``PATCH`` route. Avoid accepting fields
that users should not control, even if a model has them—select explicit fields
rather than relying on ``"__all__"`` for public APIs.

Read-only relationships
-----------------------

Use ``RelatedField`` to expose a relationship without making it writable. The
default representation is the related object's UUID; pass a serializer and set
``representation="nested"`` to return the complete related representation.
Set ``many=True`` for a collection.

.. code-block:: python

   from drfast import RelatedField, ModelSerializer

   class MerchantSerializer(ModelSerializer[Merchant]):
       model = Merchant
       fields = ("id", "name")

   class LocationSerializer(ModelSerializer[Location]):
       model = Location
       fields = ("id", "name", "merchant")

       # {"merchant": "f4f..."}
       merchant = RelatedField()

       # Or: {"merchant": {"id": "f4f...", "name": "Northwind"}}
       merchant = RelatedField(MerchantSerializer, representation="nested")

The relation must be loaded before serialization; use Tortoise prefetching when
listing nested objects to avoid N+1 queries. ``RelatedField`` is output-only in
this release. Use an explicit ``merchant_id`` field when a create or update
workflow intentionally accepts a relationship identifier.
