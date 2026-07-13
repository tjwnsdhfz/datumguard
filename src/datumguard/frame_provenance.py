from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from .frame_models import (
    FrameSourceObject,
    FrameSourceProvenance,
    StructuralFrameContract,
)

if TYPE_CHECKING:
    from .frame_rhino_adapter import RhinoFrameExchange


def _exchange_objects(
    exchange: RhinoFrameExchange,
) -> Iterable[tuple[Literal["member", "support", "load"], str, str | None]]:
    for member in exchange.members:
        yield "member", member.id, (
            str(member.source_object_id) if member.source_object_id is not None else None
        )
    for support in exchange.supports:
        yield "support", support.id, (
            str(support.source_object_id) if support.source_object_id is not None else None
        )
    for load in exchange.loads:
        yield "load", load.id, (
            str(load.source_object_id) if load.source_object_id is not None else None
        )


def build_source_provenance(
    exchange: RhinoFrameExchange,
    exchange_hash: str,
) -> FrameSourceProvenance | None:
    """Build a deterministic, non-inferred source mapping from the exchange payload."""

    source_entries = list(_exchange_objects(exchange))
    mapped = [entry for entry in source_entries if entry[2] is not None]
    if not mapped:
        return None
    objects = [
        FrameSourceObject(
            entity_type=entity_type,
            entity_id=entity_id,
            source_object_id=UUID(source_object_id),
        )
        for entity_type, entity_id, source_object_id in sorted(mapped)
        if source_object_id is not None
    ]
    return FrameSourceProvenance(
        source_document_id=exchange.document.document_id,
        exchange_hash=exchange_hash,
        objects=objects,
        complete=len(mapped) == len(source_entries),
    )


def provenance_index(contract: StructuralFrameContract) -> dict[tuple[str, str], str]:
    if contract.provenance is None:
        return {}
    return {
        (item.entity_type, item.entity_id): str(item.source_object_id)
        for item in contract.provenance.objects
    }


def provenance_manifest(contract: StructuralFrameContract) -> dict[str, object] | None:
    provenance = contract.provenance
    if provenance is None:
        return None
    return {
        "source_system": provenance.source_system,
        "source_document_id": provenance.source_document_id,
        "exchange_hash": provenance.exchange_hash,
        "complete": provenance.complete,
        "objects": [
            item.model_dump(mode="json")
            for item in sorted(
                provenance.objects,
                key=lambda item: (item.entity_type, item.entity_id, item.source_object_id),
            )
        ],
    }


__all__ = [
    "build_source_provenance",
    "provenance_index",
    "provenance_manifest",
]
