from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from drfast import CharField, RelatedField, Serializer, UUIDField


@dataclass
class Merchant:
	id: UUID
	name: str


@dataclass
class Location:
	id: UUID
	merchant: Merchant


@dataclass
class MerchantGroup:
	id: UUID
	merchants: list[Merchant]


class MerchantSerializer(Serializer[Any]):
	id = UUIDField()
	name = CharField()


class LocationPrimaryKeySerializer(Serializer[Any]):
	id = UUIDField()
	merchant = RelatedField()


class LocationNestedSerializer(Serializer[Any]):
	id = UUIDField()
	merchant = RelatedField(MerchantSerializer, representation="nested")


class MerchantGroupSerializer(Serializer[Any]):
	id = UUIDField()
	merchants = RelatedField(MerchantSerializer, many=True, representation="nested")


def test_related_field_can_render_a_primary_key_or_nested_object() -> None:
	merchant = Merchant(id=uuid4(), name="Northwind")
	location = Location(id=uuid4(), merchant=merchant)

	assert LocationPrimaryKeySerializer().representation(location) == {
		"id": str(location.id),
		"merchant": str(merchant.id),
	}
	assert LocationNestedSerializer().representation(location) == {
		"id": str(location.id),
		"merchant": {"id": str(merchant.id), "name": "Northwind"},
	}
	group = MerchantGroup(id=uuid4(), merchants=[merchant])
	assert MerchantGroupSerializer().representation(group) == {
		"id": str(group.id),
		"merchants": [{"id": str(merchant.id), "name": "Northwind"}],
	}
