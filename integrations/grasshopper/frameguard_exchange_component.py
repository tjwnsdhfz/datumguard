# ruff: noqa: F821
"""Grasshopper Python 3 component script for RhinoFrameExchange 1.0.0.

Component inputs (use item/list access as appropriate):
Curves, Supports, Loads, Sections, DocumentUnits, Datum, Limits, Metadata,
NodeMergeTolerance. ``Sections`` is a list of dictionaries with id/area/inertia/
depth and optional material values. Curve/support/load metadata may be supplied as
a dictionary alongside geometry: ``{"geometry": value, ...}``; otherwise curve
sections are assigned by matching list index. Outputs: ExchangeJSON, Messages.
"""

import json


def point_data(point):
    return [float(point.X), float(point.Y), float(point.Z)]


def unwrap(item):
    return item.Value if hasattr(item, "Value") else item


def item_geometry(item):
    item = unwrap(item)
    return item.get("geometry") if isinstance(item, dict) else item


def item_metadata(item):
    item = unwrap(item)
    return dict(item) if isinstance(item, dict) else {}


def line_endpoints(curve, entity_id):
    curve = unwrap(curve)
    success, line = curve.TryGetLine()
    if not success:
        raise ValueError(f"Member {entity_id} must be one straight line curve")
    return point_data(line.From), point_data(line.To)


def datum_data(value):
    value = unwrap(value)
    return {
        "origin": point_data(value.Origin),
        "x_axis": point_data(value.XAxis),
        "y_axis": point_data(value.YAxis),
        "z_axis": point_data(value.ZAxis),
    }


def build_exchange():
    sections = [dict(unwrap(item)) for item in (Sections or [])]
    if not sections:
        raise ValueError("Sections input is required")
    section_ids = {item["id"] for item in sections}
    members = []
    for index, raw in enumerate(Curves or []):
        metadata = item_metadata(raw)
        entity_id = str(metadata.get("id", f"member-{index + 1:03d}"))
        section_id = metadata.get("section_id", sections[min(index, len(sections) - 1)]["id"])
        if section_id not in section_ids:
            raise ValueError(f"Member {entity_id} references unknown section {section_id}")
        start, end = line_endpoints(item_geometry(raw), entity_id)
        members.append(
            {
                "id": entity_id,
                "start": start,
                "end": end,
                "section_id": section_id,
                "locked": bool(metadata.get("locked", True)),
                "source_object_id": metadata.get("source_object_id"),
            }
        )
    supports = []
    for index, raw in enumerate(Supports or []):
        metadata = item_metadata(raw)
        supports.append(
            {
                "id": str(metadata.get("id", f"support-{index + 1:03d}")),
                "point": point_data(item_geometry(raw)),
                "ux": bool(metadata.get("ux", False)),
                "uy": bool(metadata.get("uy", False)),
                "rz": bool(metadata.get("rz", False)),
                "source_object_id": metadata.get("source_object_id"),
            }
        )
    loads = []
    for index, raw in enumerate(Loads or []):
        metadata = item_metadata(raw)
        loads.append(
            {
                "id": str(metadata.get("id", f"load-{index + 1:03d}")),
                "point": point_data(item_geometry(raw)),
                "fx_n": float(metadata.get("fx_n", 0.0)),
                "fy_n": float(metadata.get("fy_n", 0.0)),
                "mz_n_document_unit": float(metadata.get("mz_n_document_unit", 0.0)),
                "source_object_id": metadata.get("source_object_id"),
            }
        )
    if not members:
        raise ValueError("Curves input must contain at least one straight centerline")
    limits = dict(unwrap(Limits))
    metadata = dict(unwrap(Metadata))
    return {
        "schema_version": "1.0.0",
        "design_kind": "structural_frame_exchange",
        "document": {
            "document_id": str(metadata.pop("document_id", "grasshopper-definition")),
            "units": str(DocumentUnits or "unset").lower(),
            "datum": datum_data(Datum),
        },
        "sections": sorted(sections, key=lambda item: item["id"]),
        "members": sorted(members, key=lambda item: item["id"]),
        "supports": sorted(supports, key=lambda item: item["id"]),
        "loads": sorted(loads, key=lambda item: item["id"]),
        "limits": limits,
        "metadata": metadata,
        "node_merge_tolerance": float(NodeMergeTolerance or 0.0),
    }


try:
    ExchangeJSON = json.dumps(build_exchange(), indent=2, sort_keys=True)
    Messages = ["READY: RhinoFrameExchange 1.0.0 created; DatumGuard verification pending"]
except Exception as exc:
    ExchangeJSON = None
    Messages = [f"FAILED: {exc}"]
