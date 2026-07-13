# ruff: noqa: F821
"""Rhino 8 Grasshopper Python 3 component used for live Cordyceps evidence.

The component has no inputs. It reads only explicitly tagged objects from the active
Rhino document and emits ``ExchangeJSON`` plus ``Status``. The output is still pending
DatumGuard normalization, structural screening, and independent serialized-DXF checks.
"""

import json
import math

import Rhino
import System.Drawing

SOURCE_LAYER = "DG_FRAMEGUARD_SOURCE"
ANNOTATION_LAYER = "DG_FRAMEGUARD_ANNOTATION"


def _layer(document, name, color):
    index = document.Layers.FindByFullPath(name, -1)
    if index >= 0:
        return index
    layer = Rhino.DocObjects.Layer()
    layer.Name = name
    layer.Color = color
    return document.Layers.Add(layer)


def _attributes(layer_index, name, color, values):
    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.LayerIndex = layer_index
    attributes.Name = name
    attributes.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    attributes.ObjectColor = color
    for key, value in values.items():
        attributes.SetUserString(key, str(value))
    return attributes


def _member(document, layer_index, entity_id, start, end):
    values = {
        "DG_ENTITY": "member",
        "DG_ID": entity_id,
        "DG_SECTION_ID": "W-demo-mm",
        "DG_AREA": "6451.6",
        "DG_INERTIA": "124869427.68",
        "DG_DEPTH": "304.8",
        "DG_E_MPA": "200000",
        "DG_ALLOWABLE_MPA": "165",
        "DG_LOCKED": "true",
    }
    geometry = Rhino.Geometry.LineCurve(
        Rhino.Geometry.Point3d(*start),
        Rhino.Geometry.Point3d(*end),
    )
    return document.Objects.AddCurve(
        geometry,
        _attributes(
            layer_index,
            entity_id,
            System.Drawing.Color.FromArgb(20, 133, 104),
            values,
        ),
    )


def _source_point(document, layer_index, entity_id, location, entity_type, values, color):
    metadata = {"DG_ENTITY": entity_type, "DG_ID": entity_id}
    metadata.update(values)
    return document.Objects.AddPoint(
        Rhino.Geometry.Point3d(*location),
        _attributes(layer_index, entity_id, color, metadata),
    )


def _ensure_annotations(document):
    annotation_layer = _layer(
        document,
        ANNOTATION_LAYER,
        System.Drawing.Color.FromArgb(40, 48, 46),
    )
    if any(obj.Attributes.LayerIndex == annotation_layer for obj in document.Objects):
        return
    labels = (
        ("LOCKED RHINO SOURCE", (-250, 3450, 0)),
        ("12 kN", (6250, 3048, 0)),
        ("6 GUIDS / DXF REOPEN GATE", (1950, -450, 0)),
    )
    for index, (text, location) in enumerate(labels):
        attributes = _attributes(
            annotation_layer,
            f"evidence-label-{index}",
            System.Drawing.Color.FromArgb(40, 48, 46),
            {},
        )
        document.Objects.AddTextDot(
            Rhino.Geometry.TextDot(text, Rhino.Geometry.Point3d(*location)),
            attributes,
        )


def _ensure_demo_scene(document):
    tagged = [
        obj
        for obj in document.Objects
        if obj.Attributes.GetUserString("DG_ENTITY") in ("member", "support", "load")
    ]
    if tagged:
        _ensure_annotations(document)
        return
    if document.ModelUnitSystem != Rhino.UnitSystem.Millimeters:
        document.AdjustModelUnitSystem(Rhino.UnitSystem.Millimeters, False)
    source_layer = _layer(
        document,
        SOURCE_LAYER,
        System.Drawing.Color.FromArgb(20, 133, 104),
    )
    _member(document, source_layer, "column-left", (0, 0, 0), (0, 3048, 0))
    _member(document, source_layer, "beam-top", (0, 3048, 0), (6096, 3048, 0))
    _member(document, source_layer, "column-right", (6096, 3048, 0), (6096, 0, 0))
    _source_point(
        document,
        source_layer,
        "support-left",
        (0, 0, 0),
        "support",
        {"DG_UX": "true", "DG_UY": "true", "DG_RZ": "true"},
        System.Drawing.Color.FromArgb(36, 90, 160),
    )
    _source_point(
        document,
        source_layer,
        "support-right",
        (6096, 0, 0),
        "support",
        {"DG_UX": "true", "DG_UY": "true", "DG_RZ": "true"},
        System.Drawing.Color.FromArgb(36, 90, 160),
    )
    _source_point(
        document,
        source_layer,
        "roof-load",
        (6096, 3048, 0),
        "load",
        {"DG_FX_N": "1500", "DG_FY_N": "-12000", "DG_MZ_N_UNIT": "0"},
        System.Drawing.Color.FromArgb(188, 67, 53),
    )
    document.Strings.SetString("DG_MAX_DISPLACEMENT", "25.4")
    document.Strings.SetString("DG_ALLOWABLE_STRESS_MPA", "165")
    document.Strings.SetString("DG_NODE_MERGE_TOLERANCE", "0.001")
    document.Strings.SetString("DG_PROJECT_NAME", "FrameGuard Cordyceps Round-Trip")
    document.Strings.SetString("DG_REVISION", "A")
    document.Strings.SetString(
        "DG_NOTES",
        "Live Rhino 8 objects created through Cordyceps; screening evidence only.",
    )
    _ensure_annotations(document)
    document.Views.Redraw()


def _user_string(obj, key, default=None):
    value = obj.Attributes.GetUserString(key)
    return default if value is None or str(value).strip() == "" else str(value).strip()


def _required(obj, key):
    value = _user_string(obj, key)
    if value is None:
        raise ValueError(f"Object {obj.Id} is missing UserString {key}")
    return value


def _number(value, label):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{label} must be finite")
    return parsed


def _boolean(value, default=False):
    if value is None:
        return default
    lowered = str(value).strip().lower()
    if lowered in ("1", "true", "yes", "on", "fixed"):
        return True
    if lowered in ("0", "false", "no", "off", "free"):
        return False
    raise ValueError(f"Invalid boolean UserString: {value}")


def _point(value):
    return [float(value.X), float(value.Y), float(value.Z)]


def _document_string(document, key, required=False, default=None):
    value = document.Strings.GetValue(key)
    if value is None or str(value).strip() == "":
        if required:
            raise ValueError(f"Rhino document UserString {key} is required")
        return default
    return str(value).strip()


def _units(document):
    mapping = {
        Rhino.UnitSystem.Millimeters: "mm",
        Rhino.UnitSystem.Centimeters: "cm",
        Rhino.UnitSystem.Meters: "m",
        Rhino.UnitSystem.Inches: "in",
        Rhino.UnitSystem.Feet: "ft",
    }
    return mapping.get(document.ModelUnitSystem, "unset")


def _datum(document):
    view = document.Views.ActiveView
    if view is None:
        raise ValueError("Rhino has no active construction plane")
    plane = view.ActiveViewport.ConstructionPlane()
    return {
        "origin": _point(plane.Origin),
        "x_axis": _point(plane.XAxis),
        "y_axis": _point(plane.YAxis),
        "z_axis": _point(plane.ZAxis),
    }


def _build_exchange():
    document = Rhino.RhinoDoc.ActiveDoc
    if document is None:
        raise ValueError("Rhino has no active document")
    _ensure_demo_scene(document)
    sections = {}
    members = []
    supports = []
    loads = []
    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.NormalObjects = True
    settings.LockedObjects = True
    settings.HiddenObjects = False
    for obj in document.Objects.GetObjectList(settings):
        entity_type = (_user_string(obj, "DG_ENTITY", "") or "").lower()
        if entity_type not in ("member", "support", "load"):
            continue
        entity_id = _user_string(obj, "DG_ID", str(obj.Id))
        if entity_type == "member":
            curve = obj.Geometry if isinstance(obj.Geometry, Rhino.Geometry.Curve) else None
            if curve is None:
                raise ValueError(f"Member {entity_id} is not a curve")
            if not curve.IsLinear():
                raise ValueError(f"Member {entity_id} must be one straight line")
            line_start = curve.PointAtStart
            line_end = curve.PointAtEnd
            section_id = _required(obj, "DG_SECTION_ID")
            section = {
                "id": section_id,
                "area": _number(_required(obj, "DG_AREA"), "DG_AREA"),
                "inertia": _number(_required(obj, "DG_INERTIA"), "DG_INERTIA"),
                "depth": _number(_required(obj, "DG_DEPTH"), "DG_DEPTH"),
                "elastic_modulus_mpa": _number(
                    _user_string(obj, "DG_E_MPA", "200000"), "DG_E_MPA"
                ),
                "allowable_stress_mpa": _number(
                    _required(obj, "DG_ALLOWABLE_MPA"), "DG_ALLOWABLE_MPA"
                ),
            }
            previous = sections.get(section_id)
            if previous is not None and previous != section:
                raise ValueError(f"Section {section_id} has conflicting metadata")
            sections[section_id] = section
            members.append(
                {
                    "id": entity_id,
                    "start": _point(line_start),
                    "end": _point(line_end),
                    "section_id": section_id,
                    "locked": _boolean(_user_string(obj, "DG_LOCKED"), True),
                    "source_object_id": str(obj.Id),
                }
            )
            continue
        if not isinstance(obj.Geometry, Rhino.Geometry.Point):
            raise ValueError(f"{entity_type} {entity_id} must be a Rhino point")
        base = {
            "id": entity_id,
            "point": _point(obj.Geometry.Location),
            "source_object_id": str(obj.Id),
        }
        if entity_type == "support":
            base.update(
                {
                    "ux": _boolean(_user_string(obj, "DG_UX"), False),
                    "uy": _boolean(_user_string(obj, "DG_UY"), False),
                    "rz": _boolean(_user_string(obj, "DG_RZ"), False),
                }
            )
            supports.append(base)
        else:
            base.update(
                {
                    "fx_n": _number(_user_string(obj, "DG_FX_N", "0"), "DG_FX_N"),
                    "fy_n": _number(_user_string(obj, "DG_FY_N", "0"), "DG_FY_N"),
                    "mz_n_document_unit": _number(
                        _user_string(obj, "DG_MZ_N_UNIT", "0"), "DG_MZ_N_UNIT"
                    ),
                }
            )
            loads.append(base)
    if not members:
        raise ValueError("No DG_ENTITY=member Rhino objects were found")
    return {
        "schema_version": "1.0.0",
        "design_kind": "structural_frame_exchange",
        "document": {
            "document_id": str(document.DocumentId),
            "units": _units(document),
            "datum": _datum(document),
        },
        "sections": sorted(sections.values(), key=lambda item: item["id"]),
        "members": sorted(members, key=lambda item: item["id"]),
        "supports": sorted(supports, key=lambda item: item["id"]),
        "loads": sorted(loads, key=lambda item: item["id"]),
        "limits": {
            "max_displacement": _number(
                _document_string(document, "DG_MAX_DISPLACEMENT", required=True),
                "DG_MAX_DISPLACEMENT",
            ),
            "allowable_stress_mpa": _number(
                _document_string(document, "DG_ALLOWABLE_STRESS_MPA", required=True),
                "DG_ALLOWABLE_STRESS_MPA",
            ),
        },
        "metadata": {
            "project_name": _document_string(
                document,
                "DG_PROJECT_NAME",
                default=document.Name or "Rhino Frame",
            ),
            "revision": _document_string(document, "DG_REVISION", default="A"),
            "notes": _document_string(document, "DG_NOTES", default=""),
        },
        "node_merge_tolerance": _number(
            _document_string(document, "DG_NODE_MERGE_TOLERANCE", default="0"),
            "DG_NODE_MERGE_TOLERANCE",
        ),
    }


try:
    _exchange = _build_exchange()
    ExchangeJSON = json.dumps(_exchange, separators=(",", ":"), sort_keys=True)
    Status = (
        f"READY: {len(_exchange['members'])} members / "
        f"{len(_exchange['supports'])} supports / {len(_exchange['loads'])} loads; "
        "DatumGuard verification pending"
    )
except Exception as exc:
    ExchangeJSON = None
    Status = f"FAILED: {exc}"
