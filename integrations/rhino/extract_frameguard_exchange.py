"""Rhino 8 Python script: export tagged frame objects to RhinoFrameExchange 1.0.0.

Tag Rhino objects with Attribute UserStrings:

* Common: ``DG_ENTITY`` = member/support/load, optional ``DG_ID``.
* Member curve: ``DG_SECTION_ID``, ``DG_AREA``, ``DG_INERTIA``, ``DG_DEPTH``,
  optional ``DG_E_MPA``, ``DG_ALLOWABLE_MPA``, ``DG_LOCKED``.
* Support point: ``DG_UX``, ``DG_UY``, ``DG_RZ``.
* Load point: ``DG_FX_N``, ``DG_FY_N``, ``DG_MZ_N_UNIT``.

Document UserStrings must define ``DG_MAX_DISPLACEMENT`` and
``DG_ALLOWABLE_STRESS_MPA``. Geometric section values and moments use powers of
the Rhino document length unit. This script performs extraction only; DatumGuard
performs the independent normalization and official verification.
"""

import json

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc


def _user_string(obj, key, default=None):
    value = obj.Attributes.GetUserString(key)
    return default if value is None or str(value).strip() == "" else str(value).strip()


def _required(obj, key):
    value = _user_string(obj, key)
    if value is None:
        raise ValueError(f"Object {obj.Id} is missing UserString {key}")
    return value


def _number(value, label):
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc


def _bool(value, default=False):
    if value is None:
        return default
    lowered = str(value).strip().lower()
    if lowered in ("1", "true", "yes", "on", "fixed"):
        return True
    if lowered in ("0", "false", "no", "off", "free"):
        return False
    raise ValueError(f"Boolean UserString has invalid value: {value}")


def _point(point):
    return [float(point.X), float(point.Y), float(point.Z)]


def _document_unit(document):
    mapping = {
        Rhino.UnitSystem.Millimeters: "mm",
        Rhino.UnitSystem.Centimeters: "cm",
        Rhino.UnitSystem.Meters: "m",
        Rhino.UnitSystem.Inches: "in",
        Rhino.UnitSystem.Feet: "ft",
    }
    return mapping.get(document.ModelUnitSystem, "unset")


def _document_string(document, key, required=False, default=None):
    value = document.Strings.GetValue(key)
    if value is None or str(value).strip() == "":
        if required:
            raise ValueError(f"Rhino document UserString {key} is required")
        return default
    return str(value).strip()


def _active_datum(document):
    view = document.Views.ActiveView
    if view is None:
        raise ValueError("Rhino has no active view for construction-plane datum extraction")
    plane = view.ActiveViewport.ConstructionPlane()
    return {
        "origin": _point(plane.Origin),
        "x_axis": _point(plane.XAxis),
        "y_axis": _point(plane.YAxis),
        "z_axis": _point(plane.ZAxis),
    }


def _objects(document, selected_only):
    if selected_only:
        return list(document.Objects.GetSelectedObjects(False, False))
    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.NormalObjects = True
    settings.LockedObjects = True
    settings.HiddenObjects = False
    return [obj for obj in document.Objects.GetObjectList(settings)]


def extract_frame_exchange(selected_only=False, document=None):
    document = document or sc.doc
    sections = {}
    members = []
    supports = []
    loads = []
    for obj in _objects(document, selected_only):
        entity_type = (_user_string(obj, "DG_ENTITY", "") or "").lower()
        if entity_type not in ("member", "support", "load"):
            continue
        entity_id = _user_string(obj, "DG_ID", str(obj.Id))
        if entity_type == "member":
            curve = obj.Geometry if isinstance(obj.Geometry, Rhino.Geometry.Curve) else None
            if curve is None:
                raise ValueError(f"Member {entity_id} is not a curve")
            success, line = curve.TryGetLine()
            if not success:
                raise ValueError(f"Member {entity_id} must be one straight centerline curve")
            section_id = _required(obj, "DG_SECTION_ID")
            section = {
                "id": section_id,
                "area": _number(_required(obj, "DG_AREA"), "DG_AREA"),
                "inertia": _number(_required(obj, "DG_INERTIA"), "DG_INERTIA"),
                "depth": _number(_required(obj, "DG_DEPTH"), "DG_DEPTH"),
                "elastic_modulus_mpa": _number(_user_string(obj, "DG_E_MPA", "200000"), "DG_E_MPA"),
                "allowable_stress_mpa": _number(
                    _required(obj, "DG_ALLOWABLE_MPA"), "DG_ALLOWABLE_MPA"
                ),
            }
            previous = sections.get(section_id)
            if previous is not None and previous != section:
                raise ValueError(f"Section {section_id} has conflicting member metadata")
            sections[section_id] = section
            members.append(
                {
                    "id": entity_id,
                    "start": _point(line.From),
                    "end": _point(line.To),
                    "section_id": section_id,
                    "locked": _bool(_user_string(obj, "DG_LOCKED"), True),
                    "source_object_id": str(obj.Id),
                }
            )
            continue
        geometry = obj.Geometry
        if not isinstance(geometry, Rhino.Geometry.Point):
            raise ValueError(f"{entity_type} {entity_id} must be a Rhino point")
        base = {
            "id": entity_id,
            "point": _point(geometry.Location),
            "source_object_id": str(obj.Id),
        }
        if entity_type == "support":
            base.update(
                {
                    "ux": _bool(_user_string(obj, "DG_UX"), False),
                    "uy": _bool(_user_string(obj, "DG_UY"), False),
                    "rz": _bool(_user_string(obj, "DG_RZ"), False),
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
        raise ValueError("No DG_ENTITY=member objects were found")
    return {
        "schema_version": "1.0.0",
        "design_kind": "structural_frame_exchange",
        "document": {
            "document_id": str(document.DocumentId),
            "units": _document_unit(document),
            "datum": _active_datum(document),
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
                document, "DG_PROJECT_NAME", default=document.Name or "Rhino Frame"
            ),
            "revision": _document_string(document, "DG_REVISION", default="A"),
            "notes": _document_string(document, "DG_NOTES", default=""),
        },
        "node_merge_tolerance": _number(
            _document_string(document, "DG_NODE_MERGE_TOLERANCE", default="0"),
            "DG_NODE_MERGE_TOLERANCE",
        ),
    }


def main():
    selected_only = rs.GetString("FrameGuard extraction scope", "Selected", ["Selected", "All"])
    if selected_only is None:
        return
    try:
        exchange = extract_frame_exchange(selected_only == "Selected")
        path = rs.SaveFileName("Save FrameGuard exchange", "JSON (*.json)|*.json||")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(exchange, stream, indent=2, sort_keys=True)
        print(f"FrameGuard exchange written: {path}")
    except Exception as exc:
        Rhino.UI.Dialogs.ShowMessage(str(exc), "FrameGuard extraction failed")
        raise


if __name__ == "__main__":
    main()
