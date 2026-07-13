"""Generate the deterministic synthetic Virtual FAB IFC research corpus.

The generator is intentionally independent from DatumGuard's detector code. Ground truth is
derived only from the mutation plan selected before any model is serialized.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import random
import shutil
import tempfile
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import ifcopenshell
import ifcopenshell.guid

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "fixtures" / "openbim"
GENERATOR_VERSION = "1.0.0"
SCHEMA_VERSION = "openbim-fixture-v1"
FIXED_TIMESTAMP = "2026-07-12T00:00:00"
GUID_NAMESPACE = uuid.UUID("f58d12bb-3fab-4c1d-84ae-c4dfd5df4570")
IDS_NAMESPACE = "http://standards.buildingsmart.org/IDS"
XS_NAMESPACE = "http://www.w3.org/2001/XMLSchema"
XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"

LAYOUT_COUNTS = {
    "L1": {"tools": 4, "pipes": 18, "valves": 4, "fittings": 2, "supports": 4},
    "L2": {"tools": 5, "pipes": 24, "valves": 4, "fittings": 3, "supports": 4},
    "L3": {"tools": 6, "pipes": 28, "valves": 5, "fittings": 4, "supports": 5},
}
PILOT_SEEDS = {
    "L1": [1101, 1102],
    "L2": [1201, 1202],
    "L3": [1301, 1302],
}
EVALUATION_SEEDS = {
    "L1": list(range(2101, 2111)),
    "L2": list(range(2201, 2211)),
    "L3": list(range(2301, 2311)),
}
REPRESENTATIVE = ("L1", 20260712)
UTILITY_TYPES = ("PCW", "CDA", "VAC", "EXH")
APPLICABLE_CLASSES = (
    "IfcBuildingElementProxy",
    "IfcPipeSegment",
    "IfcPipeFitting",
    "IfcValve",
)


@dataclass
class AssetSpec:
    asset_key: str
    asset_tag: str
    ifc_class: str
    name: str
    object_type: str | None
    x: float
    y: float
    z: float
    size_x: float
    size_y: float
    size_z: float
    rotation_deg: int = 0
    utility_type: str | None = None
    system_code: str | None = None
    criticality: str | None = None
    service_side: str | None = None
    service_depth: float | None = None
    classified: bool = True
    contained: bool = True
    global_id_override: str | None = None


def canonical_json(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def compact_canonical_json(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(data))


def sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def stable_guid(key: str) -> str:
    return ifcopenshell.guid.compress(uuid.uuid5(GUID_NAMESPACE, key).hex)


def asset_code(ifc_class: str, object_type: str | None) -> str:
    if object_type == "FAB_TOOL":
        return "TL"
    if object_type == "UTILITY_SUPPORT":
        return "SP"
    return {
        "IfcPipeSegment": "PS",
        "IfcPipeFitting": "PF",
        "IfcValve": "VL",
    }[ifc_class]


def base_assets(layout: str, seed: int) -> list[AssetSpec]:
    counts = LAYOUT_COUNTS[layout]
    rng = random.Random(seed ^ 0xD47A6A)
    assets: list[AssetSpec] = []

    def add(
        ifc_class: str,
        index: int,
        *,
        object_type: str | None,
        xyz: tuple[float, float, float],
        size: tuple[float, float, float],
        utility_type: str | None = None,
        rotation_deg: int = 0,
    ) -> None:
        code = asset_code(ifc_class, object_type)
        asset_key = f"{layout}-{code}-{index:03d}"
        system_code = f"SYS-{utility_type}-A" if utility_type else None
        assets.append(
            AssetSpec(
                asset_key=asset_key,
                asset_tag=f"VF-{code}-{index:03d}",
                ifc_class=ifc_class,
                name=f"{layout} {code} {index:03d}",
                object_type=object_type,
                x=round(xyz[0], 6),
                y=round(xyz[1], 6),
                z=round(xyz[2], 6),
                size_x=size[0],
                size_y=size[1],
                size_z=size[2],
                rotation_deg=rotation_deg,
                utility_type=utility_type,
                system_code=system_code,
                criticality=("HIGH", "MEDIUM", "LOW")[index % 3] if utility_type else None,
                service_side="+X" if object_type == "FAB_TOOL" else None,
                service_depth=0.6 if object_type == "FAB_TOOL" else None,
            )
        )

    for index in range(1, counts["tools"] + 1):
        add(
            "IfcBuildingElementProxy",
            index,
            object_type="FAB_TOOL",
            xyz=((index - 1) * 5.0, 0.0, 0.0),
            size=(1.4, 1.6, 1.2),
        )

    for index in range(1, counts["pipes"] + 1):
        row = (index - 1) // 10
        column = (index - 1) % 10
        jitter = rng.uniform(-0.04, 0.04)
        utility_type = UTILITY_TYPES[(index - 1) % len(UTILITY_TYPES)]
        add(
            "IfcPipeSegment",
            index,
            object_type="UTILITY",
            xyz=(column * 1.65 + jitter, 4.5 + row * 1.0, 1.7 + row * 0.35),
            size=(1.2, 0.12, 0.12),
            utility_type=utility_type,
        )

    for index in range(1, counts["valves"] + 1):
        utility_type = UTILITY_TYPES[index % len(UTILITY_TYPES)]
        add(
            "IfcValve",
            index,
            object_type="UTILITY",
            xyz=(index * 2.7, 7.5, 1.8),
            size=(0.35, 0.3, 0.35),
            utility_type=utility_type,
        )

    for index in range(1, counts["fittings"] + 1):
        utility_type = UTILITY_TYPES[(index + 1) % len(UTILITY_TYPES)]
        add(
            "IfcPipeFitting",
            index,
            object_type="UTILITY",
            xyz=(index * 3.1 + 0.8, 8.4, 1.6),
            size=(0.3, 0.3, 0.3),
            utility_type=utility_type,
        )

    for index in range(1, counts["supports"] + 1):
        add(
            "IfcBuildingElementProxy",
            index,
            object_type="UTILITY_SUPPORT",
            xyz=(index * 3.4, 6.3, 0.0),
            size=(0.25, 0.5, 1.5),
        )

    return assets


def authorization_for_layout(layout: str) -> dict[str, Any]:
    return {
        "asset_key": f"{layout}-PS-001",
        "field": "DG_VFabUtility.SystemCode",
        "before": "SYS-PCW-A",
        "after": "SYS-PCW-B",
        "reason": "Synthetic approved utility routing revision for research control.",
    }


def make_profile() -> dict[str, Any]:
    return {
        "profile_id": "virtual-fab-v1",
        "version": "1.0.0",
        "ifc_schema": "IFC4",
        "applicable_entities": list(APPLICABLE_CLASSES),
        "tool_object_type": "FAB_TOOL",
        "obstacle_entities": ["IfcPipeSegment", "IfcPipeFitting", "IfcValve"],
        "required_container_types": ["IfcBuildingStorey", "IfcSpace"],
        "asset_key_path": "DG_Identity.AssetKey",
        "allowed_service_sides": ["+X", "-X", "+Y", "-Y"],
        "locked_fields": [
            "DG_Identity.AssetTag",
            "DG_VFabUtility.UtilityType",
            "DG_VFabUtility.SystemCode",
            "container",
        ],
        "default_service_depth_m": 0.6,
        "clearance_epsilon_m": 1e-9,
        "authorized_changes": [
            authorization_for_layout(layout) for layout in sorted(LAYOUT_COUNTS)
        ],
        "max_products": 500,
        "max_geometry_vertices": 2_000_000,
        "max_bcf_topics": 1000,
    }


def add_simple_value(parent: ET.Element, name: str, value: str) -> None:
    node = ET.SubElement(parent, name)
    ET.SubElement(node, "simpleValue").text = value


def add_entity(parent: ET.Element, ifc_class: str) -> None:
    entity = ET.SubElement(parent, "entity")
    add_simple_value(entity, "name", ifc_class.upper())


def add_property(
    parent: ET.Element,
    *,
    pset: str,
    name: str,
    data_type: str,
    values: Iterable[str] | None = None,
    pattern: str | None = None,
) -> None:
    prop = ET.SubElement(parent, "property", {"dataType": data_type, "cardinality": "required"})
    add_simple_value(prop, "propertySet", pset)
    add_simple_value(prop, "baseName", name)
    if values is not None or pattern is not None:
        value = ET.SubElement(prop, "value")
        restriction = ET.SubElement(value, f"{{{XS_NAMESPACE}}}restriction", {"base": "xs:string"})
        if pattern is not None:
            ET.SubElement(restriction, f"{{{XS_NAMESPACE}}}pattern", {"value": pattern})
        for item in values or ():
            ET.SubElement(restriction, f"{{{XS_NAMESPACE}}}enumeration", {"value": item})


def add_specification(
    specifications: ET.Element,
    *,
    identifier: str,
    name: str,
    ifc_class: str,
    requirements_builder: Any,
    object_type: str | None = None,
) -> None:
    specification = ET.SubElement(
        specifications,
        "specification",
        {
            "name": name,
            "ifcVersion": "IFC4",
            "identifier": identifier,
        },
    )
    applicability = ET.SubElement(
        specification, "applicability", {"minOccurs": "0", "maxOccurs": "unbounded"}
    )
    add_entity(applicability, ifc_class)
    if object_type is not None:
        attribute = ET.SubElement(applicability, "attribute")
        add_simple_value(attribute, "name", "ObjectType")
        add_simple_value(attribute, "value", object_type)
    requirements = ET.SubElement(specification, "requirements")
    requirements_builder(requirements)


def build_ids() -> bytes:
    ET.register_namespace("", IDS_NAMESPACE)
    ET.register_namespace("xs", XS_NAMESPACE)
    ET.register_namespace("xsi", XSI_NAMESPACE)
    root = ET.Element(
        f"{{{IDS_NAMESPACE}}}ids",
        {f"{{{XSI_NAMESPACE}}}schemaLocation": (f"{IDS_NAMESPACE} {IDS_NAMESPACE}/1.0/ids.xsd")},
    )
    info = ET.SubElement(root, "info")
    ET.SubElement(info, "title").text = "OpenBIM Evidence Guard - Virtual FAB v1"
    ET.SubElement(info, "copyright").text = "2026 DatumGuard research dataset"
    ET.SubElement(info, "version").text = "1.0.0"
    ET.SubElement(
        info, "description"
    ).text = "Synthetic educational information requirements; not an industrial FAB standard."
    ET.SubElement(info, "author").text = "research@datumguard.local"
    ET.SubElement(info, "date").text = "2026-07-12"
    ET.SubElement(info, "purpose").text = "BIM Awards 2026 controlled research evaluation"
    specifications = ET.SubElement(root, "specifications")

    for ifc_class in APPLICABLE_CLASSES:
        add_specification(
            specifications,
            identifier="IDS-01",
            name=f"IDS-01 AssetTag - {ifc_class}",
            ifc_class=ifc_class,
            requirements_builder=lambda node: add_property(
                node,
                pset="DG_Identity",
                name="AssetTag",
                data_type="IFCLABEL",
                pattern=r"VF-[A-Z]{2}-[0-9]{3}",
            ),
        )
        add_specification(
            specifications,
            identifier="IDS-04",
            name=f"IDS-04 Classification - {ifc_class}",
            ifc_class=ifc_class,
            requirements_builder=lambda node: _add_classification(node),
        )

    for ifc_class in ("IfcPipeSegment", "IfcPipeFitting", "IfcValve"):
        add_specification(
            specifications,
            identifier="IDS-02",
            name=f"IDS-02 UtilityType - {ifc_class}",
            ifc_class=ifc_class,
            requirements_builder=lambda node: add_property(
                node,
                pset="DG_VFabUtility",
                name="UtilityType",
                data_type="IFCLABEL",
                values=UTILITY_TYPES,
            ),
        )
        add_specification(
            specifications,
            identifier="IDS-03",
            name=f"IDS-03 SystemCode - {ifc_class}",
            ifc_class=ifc_class,
            requirements_builder=lambda node: add_property(
                node,
                pset="DG_VFabUtility",
                name="SystemCode",
                data_type="IFCLABEL",
            ),
        )
        add_specification(
            specifications,
            identifier="IDS-05",
            name=f"IDS-05 Criticality - {ifc_class}",
            ifc_class=ifc_class,
            requirements_builder=lambda node: add_property(
                node,
                pset="DG_VFabUtility",
                name="Criticality",
                data_type="IFCLABEL",
                values=("HIGH", "MEDIUM", "LOW"),
            ),
        )

    def clearance_requirements(node: ET.Element) -> None:
        add_property(
            node,
            pset="DG_VFabClearance",
            name="ServiceSide",
            data_type="IFCLABEL",
            values=("+X", "-X", "+Y", "-Y"),
        )
        add_property(
            node,
            pset="DG_VFabClearance",
            name="ServiceDepth",
            data_type="IFCLENGTHMEASURE",
        )

    add_specification(
        specifications,
        identifier="IDS-06",
        name="IDS-06 FAB tool service clearance metadata",
        ifc_class="IfcBuildingElementProxy",
        object_type="FAB_TOOL",
        requirements_builder=clearance_requirements,
    )

    ET.indent(root, space="    ")
    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml + b"\n"


def _add_classification(node: ET.Element) -> None:
    classification = ET.SubElement(node, "classification", {"cardinality": "required"})
    add_simple_value(classification, "value", "DG-VFAB-2026")
    add_simple_value(classification, "system", "DG-VFAB-2026")


def make_fault_plan(
    case_id: str, layout: str, seed: int, assets: list[AssetSpec]
) -> dict[str, Any]:
    rng = random.Random(seed ^ 0xE71D3E)
    by_key = {asset.asset_key: asset for asset in assets}
    authorization = authorization_for_layout(layout)
    used = {authorization["asset_key"]}

    def choose(predicate: Any) -> AssetSpec:
        candidates = sorted(
            (asset for asset in assets if asset.asset_key not in used and predicate(asset)),
            key=lambda asset: asset.asset_key,
        )
        if not candidates:
            raise RuntimeError(f"No mutation target remains for {case_id}")
        selected = candidates[rng.randrange(len(candidates))]
        used.add(selected.asset_key)
        return selected

    def is_utility(asset: AssetSpec) -> bool:
        return asset.ifc_class in {"IfcPipeSegment", "IfcPipeFitting", "IfcValve"}

    events: list[dict[str, Any]] = []

    def event(
        fault_id: str,
        rule_id: str,
        family: str,
        target: AssetSpec,
        field: str,
        before: Any,
        after: Any,
    ) -> None:
        admissible_secondary_rules = {
            "I01": ["REV-03"],
            "I02": ["REV-03"],
            "I03": ["REV-03"],
            "I04": ["REV-03"],
            "I06": ["REV-03"],
            "R01": ["REV-02"],
        }
        events.append(
            {
                "fault_id": fault_id,
                "rule_id": rule_id,
                "family": family,
                "target": {
                    "asset_key": target.asset_key,
                    "ifc_class": target.ifc_class,
                },
                "field": field,
                "before": before,
                "after": after,
                "expected_rule_ids": [rule_id],
                "admissible_secondary_rule_ids": admissible_secondary_rules.get(fault_id, []),
            }
        )

    target = choose(is_utility)
    event("I01", "IDS-01", "Information", target, "DG_Identity.AssetTag", target.asset_tag, None)
    target = choose(is_utility)
    event(
        "I02",
        "IDS-01",
        "Information",
        target,
        "DG_Identity.AssetTag",
        target.asset_tag,
        "INVALID TAG",
    )
    target = choose(is_utility)
    event(
        "I03",
        "IDS-02",
        "Information",
        target,
        "DG_VFabUtility.UtilityType",
        target.utility_type,
        "STEAM",
    )
    target = choose(is_utility)
    event(
        "I04",
        "IDS-03",
        "Information",
        target,
        "DG_VFabUtility.SystemCode",
        target.system_code,
        None,
    )
    target = choose(lambda asset: asset.object_type == "UTILITY_SUPPORT")
    event(
        "I05",
        "IDS-04",
        "Information",
        target,
        "classification",
        "DG-VFAB-2026",
        None,
    )
    target = choose(lambda asset: asset.object_type == "UTILITY_SUPPORT")
    event("I06", "IFC-03", "Integrity", target, "container", "IfcSpace", None)

    tools = sorted(
        (asset for asset in assets if asset.object_type == "FAB_TOOL"), key=lambda a: a.asset_key
    )
    pipe = choose(lambda asset: asset.ifc_class == "IfcPipeSegment")
    g01_after = {"x": tools[0].x + tools[0].size_x / 2 + 0.3, "y": tools[0].y, "z": 0.5}
    event(
        "G01",
        "GEO-01",
        "Geometry",
        pipe,
        "placement",
        {"x": pipe.x, "y": pipe.y, "z": pipe.z},
        g01_after,
    )
    events[-1]["entity_pair"] = [tools[0].asset_key, pipe.asset_key]

    fitting = choose(lambda asset: asset.ifc_class in {"IfcValve", "IfcPipeFitting"})
    g02_after = {"x": tools[1].x + tools[1].size_x / 2 + 0.3, "y": tools[1].y, "z": 0.5}
    event(
        "G02",
        "GEO-01",
        "Geometry",
        fitting,
        "placement",
        {"x": fitting.x, "y": fitting.y, "z": fitting.z},
        g02_after,
    )
    events[-1]["entity_pair"] = [tools[1].asset_key, fitting.asset_key]

    duplicate_a = choose(lambda asset: True)
    duplicate_b = choose(lambda asset: True)
    duplicate_guid = stable_guid(f"{case_id}|{duplicate_a.asset_key}")
    event(
        "R01",
        "IFC-02",
        "IFC Identity",
        duplicate_b,
        "GlobalId",
        stable_guid(f"{case_id}|{duplicate_b.asset_key}"),
        duplicate_guid,
    )
    events[-1]["target"]["asset_keys"] = [duplicate_a.asset_key, duplicate_b.asset_key]
    events[-1]["duplicate_global_id"] = duplicate_guid

    target = choose(is_utility)
    event(
        "R02",
        "REV-02",
        "Revision",
        target,
        "GlobalId",
        stable_guid(f"{case_id}|{target.asset_key}"),
        stable_guid(f"{case_id}|{target.asset_key}|R02-churn"),
    )
    target = choose(is_utility)
    after_utility = next(value for value in UTILITY_TYPES if value != target.utility_type)
    event(
        "R03",
        "REV-03",
        "Revision",
        target,
        "DG_VFabUtility.UtilityType",
        target.utility_type,
        after_utility,
    )

    assert len(events) == 11
    assert len(used) == 13  # one authorization + twelve unique mutation targets
    return {
        "schema_version": "openbim-mutation-plan-v1",
        "case_id": case_id,
        "layout": layout,
        "seed": seed,
        "authorized_changes": [authorization],
        "mutations": events,
        "corrections": [event["fault_id"] for event in events],
        "target_selection": "seeded selection without mutation-target overlap",
        "detector_independent": True,
        "asset_snapshot": {asset.asset_key: asdict(asset) for asset in assets},
        "_asset_lookup": by_key,
    }


def variant_assets(
    case_id: str,
    variant: str,
    assets: list[AssetSpec],
    fault_plan: dict[str, Any],
) -> list[AssetSpec]:
    result = copy.deepcopy(assets)
    by_key = {asset.asset_key: asset for asset in result}
    if variant == "v1_authorized":
        change = fault_plan["authorized_changes"][0]
        by_key[change["asset_key"]].system_code = change["after"]
    elif variant == "v1_faulty":
        for mutation in fault_plan["mutations"]:
            target = by_key[mutation["target"]["asset_key"]]
            fault_id = mutation["fault_id"]
            if fault_id in {"I01", "I02"}:
                target.asset_tag = mutation["after"]
            elif fault_id == "I03":
                target.utility_type = mutation["after"]
            elif fault_id == "I04":
                target.system_code = None
            elif fault_id == "I05":
                target.classified = False
            elif fault_id == "I06":
                target.contained = False
            elif fault_id in {"G01", "G02"}:
                target.x = mutation["after"]["x"]
                target.y = mutation["after"]["y"]
                target.z = mutation["after"]["z"]
            elif fault_id in {"R01", "R02"}:
                target.global_id_override = mutation["after"]
            elif fault_id == "R03":
                target.utility_type = mutation["after"]
            else:
                raise AssertionError(f"Unhandled fault: {fault_id}")
    elif variant not in {"v0_clean", "v2_corrected"}:
        raise ValueError(f"Unknown variant: {variant}")
    return result


def point(model: ifcopenshell.file, xyz: tuple[float, ...]) -> Any:
    return model.create_entity("IfcCartesianPoint", Coordinates=xyz)


def direction(model: ifcopenshell.file, ratios: tuple[float, ...]) -> Any:
    return model.create_entity("IfcDirection", DirectionRatios=ratios)


def local_placement(
    model: ifcopenshell.file, x: float, y: float, z: float, rotation_deg: int = 0
) -> Any:
    angle = math.radians(rotation_deg)
    axis = model.create_entity(
        "IfcAxis2Placement3D",
        Location=point(model, (x, y, z)),
        Axis=direction(model, (0.0, 0.0, 1.0)),
        RefDirection=direction(model, (math.cos(angle), math.sin(angle), 0.0)),
    )
    return model.create_entity("IfcLocalPlacement", PlacementRelTo=None, RelativePlacement=axis)


def product_shape(
    model: ifcopenshell.file,
    context: Any,
    size_x: float,
    size_y: float,
    size_z: float,
) -> Any:
    profile_position = model.create_entity(
        "IfcAxis2Placement2D",
        Location=point(model, (0.0, 0.0)),
        RefDirection=direction(model, (1.0, 0.0)),
    )
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        ProfileName=None,
        Position=profile_position,
        XDim=size_x,
        YDim=size_y,
    )
    solid_position = model.create_entity(
        "IfcAxis2Placement3D",
        Location=point(model, (0.0, 0.0, 0.0)),
        Axis=direction(model, (0.0, 0.0, 1.0)),
        RefDirection=direction(model, (1.0, 0.0, 0.0)),
    )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=solid_position,
        ExtrudedDirection=direction(model, (0.0, 0.0, 1.0)),
        Depth=size_z,
    )
    representation = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=context,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=(solid,),
    )
    return model.create_entity(
        "IfcProductDefinitionShape", Name=None, Description=None, Representations=(representation,)
    )


def property_value(model: ifcopenshell.file, value: Any, value_type: str) -> Any:
    return model.create_entity(value_type, value)


def attach_pset(
    model: ifcopenshell.file,
    case_id: str,
    asset_key: str,
    entity: Any,
    pset_name: str,
    values: list[tuple[str, Any, str]],
) -> None:
    properties = []
    for name, value, value_type in values:
        if value is None:
            continue
        properties.append(
            model.create_entity(
                "IfcPropertySingleValue",
                Name=name,
                Description=None,
                NominalValue=property_value(model, value, value_type),
                Unit=None,
            )
        )
    pset = model.create_entity(
        "IfcPropertySet",
        GlobalId=stable_guid(f"{case_id}|{asset_key}|PSET|{pset_name}"),
        Name=pset_name,
        Description="DatumGuard synthetic research property set",
        HasProperties=tuple(properties),
    )
    model.create_entity(
        "IfcRelDefinesByProperties",
        GlobalId=stable_guid(f"{case_id}|{asset_key}|REL|{pset_name}"),
        Name=None,
        Description=None,
        RelatedObjects=(entity,),
        RelatingPropertyDefinition=pset,
    )


def build_ifc(
    path: Path,
    *,
    case_id: str,
    layout: str,
    seed: int,
    variant: str,
    assets: list[AssetSpec],
) -> None:
    model = ifcopenshell.file(schema="IFC4")
    model.header.file_description.description = ("ViewDefinition [DesignTransferView]",)
    model.header.file_name.name = path.name
    model.header.file_name.time_stamp = FIXED_TIMESTAMP
    model.header.file_name.author = ("DatumGuard BIM Awards 2026",)
    model.header.file_name.organization = ("Synthetic Research Dataset",)
    model.header.file_name.preprocessor_version = (
        f"DatumGuard fixture generator {GENERATOR_VERSION}"
    )
    model.header.file_name.originating_system = "IfcOpenShell 0.8.5"
    model.header.file_name.authorization = "Research validation only"

    origin = point(model, (0.0, 0.0, 0.0))
    world = model.create_entity(
        "IfcAxis2Placement3D",
        Location=origin,
        Axis=direction(model, (0.0, 0.0, 1.0)),
        RefDirection=direction(model, (1.0, 0.0, 0.0)),
    )
    context = model.create_entity(
        "IfcGeometricRepresentationContext",
        ContextIdentifier="Model",
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=1e-6,
        WorldCoordinateSystem=world,
        TrueNorth=direction(model, (0.0, 1.0)),
    )
    length_unit = model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
    area_unit = model.create_entity("IfcSIUnit", UnitType="AREAUNIT", Name="SQUARE_METRE")
    volume_unit = model.create_entity("IfcSIUnit", UnitType="VOLUMEUNIT", Name="CUBIC_METRE")
    units = model.create_entity("IfcUnitAssignment", Units=(length_unit, area_unit, volume_unit))
    project = model.create_entity(
        "IfcProject",
        GlobalId=stable_guid(f"{case_id}|PROJECT"),
        Name=f"Virtual FAB {case_id}",
        Description=f"Synthetic {layout} seed {seed}; candidate {variant}",
        ObjectType="SYNTHETIC_RESEARCH_MODEL",
        LongName="OpenBIM Evidence Guard controlled fixture",
        Phase="RESEARCH",
        RepresentationContexts=(context,),
        UnitsInContext=units,
    )
    site = model.create_entity(
        "IfcSite",
        GlobalId=stable_guid(f"{case_id}|SITE"),
        Name="Synthetic Research Site",
        ObjectPlacement=local_placement(model, 0.0, 0.0, 0.0),
        CompositionType="ELEMENT",
    )
    building = model.create_entity(
        "IfcBuilding",
        GlobalId=stable_guid(f"{case_id}|BUILDING"),
        Name="Virtual FAB Building",
        ObjectPlacement=local_placement(model, 0.0, 0.0, 0.0),
        CompositionType="ELEMENT",
    )
    storey = model.create_entity(
        "IfcBuildingStorey",
        GlobalId=stable_guid(f"{case_id}|STOREY"),
        Name="Utility Level",
        ObjectPlacement=local_placement(model, 0.0, 0.0, 0.0),
        CompositionType="ELEMENT",
        Elevation=0.0,
    )
    space = model.create_entity(
        "IfcSpace",
        GlobalId=stable_guid(f"{case_id}|SPACE"),
        Name="Synthetic Tool Bay",
        ObjectPlacement=local_placement(model, 0.0, 0.0, 0.0),
        CompositionType="ELEMENT",
        PredefinedType="INTERNAL",
    )
    for parent, children, rel_name in (
        (project, (site,), "Project-Site"),
        (site, (building,), "Site-Building"),
        (building, (storey,), "Building-Storey"),
        (storey, (space,), "Storey-Space"),
    ):
        model.create_entity(
            "IfcRelAggregates",
            GlobalId=stable_guid(f"{case_id}|AGG|{rel_name}"),
            Name=rel_name,
            Description=None,
            RelatingObject=parent,
            RelatedObjects=children,
        )

    classification = model.create_entity(
        "IfcClassification",
        Source="DatumGuard",
        Edition="2026",
        EditionDate=None,
        Name="DG-VFAB-2026",
        Description="Synthetic educational classification",
        Location=None,
        ReferenceTokens=None,
    )
    class_ref = model.create_entity(
        "IfcClassificationReference",
        Location=None,
        Identification="DG-VFAB-2026",
        Name="Virtual FAB Research Asset",
        ReferencedSource=classification,
        Description="Synthetic classification reference",
        Sort=None,
    )

    products = []
    for asset in sorted(assets, key=lambda item: item.asset_key):
        global_id = asset.global_id_override or stable_guid(f"{case_id}|{asset.asset_key}")
        common: dict[str, Any] = {
            "GlobalId": global_id,
            "Name": asset.name,
            "Description": "Synthetic non-production research asset",
            "ObjectType": asset.object_type,
            "ObjectPlacement": local_placement(
                model, asset.x, asset.y, asset.z, rotation_deg=asset.rotation_deg
            ),
            "Representation": product_shape(
                model, context, asset.size_x, asset.size_y, asset.size_z
            ),
            "Tag": asset.asset_tag,
        }
        if asset.ifc_class == "IfcBuildingElementProxy":
            common["PredefinedType"] = "USERDEFINED"
        elif asset.ifc_class == "IfcPipeSegment":
            common["PredefinedType"] = "RIGIDSEGMENT"
        else:
            common["PredefinedType"] = "NOTDEFINED"
        entity = model.create_entity(asset.ifc_class, **common)
        products.append((asset, entity))
        attach_pset(
            model,
            case_id,
            asset.asset_key,
            entity,
            "DG_Identity",
            [
                ("AssetKey", asset.asset_key, "IfcIdentifier"),
                ("AssetTag", asset.asset_tag, "IfcLabel"),
            ],
        )
        if asset.utility_type is not None or asset.system_code is not None:
            attach_pset(
                model,
                case_id,
                asset.asset_key,
                entity,
                "DG_VFabUtility",
                [
                    ("UtilityType", asset.utility_type, "IfcLabel"),
                    ("SystemCode", asset.system_code, "IfcLabel"),
                    ("Criticality", asset.criticality, "IfcLabel"),
                ],
            )
        if asset.object_type == "FAB_TOOL":
            attach_pset(
                model,
                case_id,
                asset.asset_key,
                entity,
                "DG_VFabClearance",
                [
                    ("ServiceSide", asset.service_side, "IfcLabel"),
                    ("ServiceDepth", asset.service_depth, "IfcLengthMeasure"),
                ],
            )
        if asset.classified:
            model.create_entity(
                "IfcRelAssociatesClassification",
                GlobalId=stable_guid(f"{case_id}|CLASS|{asset.asset_key}"),
                Name=None,
                Description=None,
                RelatedObjects=(entity,),
                RelatingClassification=class_ref,
            )

    contained = tuple(entity for asset, entity in products if asset.contained)
    model.create_entity(
        "IfcRelContainedInSpatialStructure",
        GlobalId=stable_guid(f"{case_id}|CONTAINMENT"),
        Name="Synthetic asset containment",
        Description=None,
        RelatedElements=contained,
        RelatingStructure=space,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(path))


def asset_key_for_entity(entity: Any) -> str | None:
    for relation in getattr(entity, "IsDefinedBy", ()):
        if not relation.is_a("IfcRelDefinesByProperties"):
            continue
        pset = relation.RelatingPropertyDefinition
        if not pset.is_a("IfcPropertySet") or pset.Name != "DG_Identity":
            continue
        for prop in pset.HasProperties:
            if prop.Name == "AssetKey" and prop.NominalValue is not None:
                return str(prop.NominalValue.wrappedValue)
    return None


def reopen_index(path: Path) -> dict[str, dict[str, Any]]:
    model = ifcopenshell.open(str(path))
    if model.schema != "IFC4":
        raise RuntimeError(f"Unexpected IFC schema in {path}: {model.schema}")
    result: dict[str, dict[str, Any]] = {}
    for ifc_class in APPLICABLE_CLASSES:
        for entity in model.by_type(ifc_class, include_subtypes=False):
            key = asset_key_for_entity(entity)
            if key is None:
                raise RuntimeError(f"Missing AssetKey after reopen: #{entity.id()} in {path}")
            result[key] = {
                "step_id": entity.id(),
                "global_id": entity.GlobalId,
                "ifc_class": entity.is_a(),
            }
    return dict(sorted(result.items()))


def duplicate_global_id_groups(path: Path) -> dict[str, list[int]]:
    model = ifcopenshell.open(str(path))
    groups: dict[str, list[int]] = {}
    for entity in model.by_type("IfcRoot"):
        global_id = str(entity.GlobalId or "")
        groups.setdefault(global_id, []).append(entity.id())
    return {
        global_id: sorted(step_ids)
        for global_id, step_ids in sorted(groups.items())
        if not global_id or len(step_ids) > 1
    }


def expected_issue(
    mutation: dict[str, Any],
    faulty_index: dict[str, dict[str, Any]],
    *,
    rule_id: str | None = None,
) -> dict[str, Any]:
    target_key = mutation["target"]["asset_key"]
    issue: dict[str, Any] = {
        "fault_id": mutation["fault_id"],
        "rule_id": rule_id or mutation["rule_id"],
        "family": mutation["family"],
        "asset_key": target_key,
        "field": mutation["field"],
    }
    if "entity_pair" in mutation:
        issue["entity_pair"] = sorted(mutation["entity_pair"])
        issue["global_id_pair"] = sorted(
            faulty_index[key]["global_id"] for key in mutation["entity_pair"]
        )
    if mutation["fault_id"] == "R01":
        asset_keys = sorted(mutation["target"]["asset_keys"])
        issue["asset_keys"] = asset_keys
        issue["step_entity_ids"] = sorted(faulty_index[key]["step_id"] for key in asset_keys)
        issue["global_id"] = mutation["duplicate_global_id"]
    return issue


def generate_case(
    output_root: Path,
    *,
    split: str,
    layout: str,
    seed: int,
    ids_hash: str,
    profile_file_hash: str,
    profile_canonical_hash: str,
) -> dict[str, Any]:
    prefix = {"representative": "REP", "pilot": "PIL", "evaluation": "EVAL"}[split]
    case_id = f"{prefix}-{layout}-S{seed}"
    if split == "representative":
        case_dir = output_root / "representative"
    else:
        case_dir = output_root / split / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    assets = base_assets(layout, seed)
    fault_plan = make_fault_plan(case_id, layout, seed, assets)
    variants = ("v0_clean", "v1_authorized", "v1_faulty", "v2_corrected")
    artifact_hashes: dict[str, str] = {}
    reopened: dict[str, dict[str, dict[str, Any]]] = {}
    for variant in variants:
        path = case_dir / f"{variant}.ifc"
        build_ifc(
            path,
            case_id=case_id,
            layout=layout,
            seed=seed,
            variant=variant,
            assets=variant_assets(case_id, variant, assets, fault_plan),
        )
        reopened[variant] = reopen_index(path)
        if len(reopened[variant]) != len(assets):
            raise RuntimeError(f"Asset count changed after reopen in {case_id}/{variant}")
        artifact_hashes[path.name] = sha256_file(path)

    intended_duplicate = next(
        mutation["duplicate_global_id"]
        for mutation in fault_plan["mutations"]
        if mutation["fault_id"] == "R01"
    )
    duplicate_oracle = {
        variant: duplicate_global_id_groups(case_dir / f"{variant}.ifc") for variant in variants
    }
    for variant in ("v0_clean", "v1_authorized", "v2_corrected"):
        if duplicate_oracle[variant]:
            raise RuntimeError(f"Unexpected duplicate GlobalId in {case_id}/{variant}")
    if set(duplicate_oracle["v1_faulty"]) != {intended_duplicate}:
        raise RuntimeError(
            f"R01 created unintended duplicate groups in {case_id}: {duplicate_oracle['v1_faulty']}"
        )
    if len(duplicate_oracle["v1_faulty"][intended_duplicate]) != 2:
        raise RuntimeError(f"R01 duplicate group does not contain exactly two roots in {case_id}")

    mutations = copy.deepcopy(fault_plan["mutations"])
    for mutation in mutations:
        target_key = mutation["target"]["asset_key"]
        mutation["target"]["faulty_step_id"] = reopened["v1_faulty"][target_key]["step_id"]
        mutation["target"]["faulty_global_id"] = reopened["v1_faulty"][target_key]["global_id"]
        mutation["expected_detection_key"] = expected_issue(mutation, reopened["v1_faulty"])
    manifest = {
        key: value
        for key, value in fault_plan.items()
        if key not in {"_asset_lookup", "mutations", "asset_snapshot"}
    }
    manifest["schema_version"] = "openbim-mutation-manifest-v1"
    manifest["generator_version"] = GENERATOR_VERSION
    manifest["mutations"] = mutations
    manifest["integrity_oracle"] = {
        "expected_faulty_duplicate_global_id": intended_duplicate,
        "duplicate_groups_by_variant": duplicate_oracle,
    }
    manifest["artifact_hashes"] = {
        **artifact_hashes,
        "virtual_fab_v1.ids": ids_hash,
        "virtual_fab_profile.json": profile_file_hash,
        "virtual_fab_profile.canonical_json": profile_canonical_hash,
    }
    mutation_path = case_dir / "mutation_manifest.json"
    write_json(mutation_path, manifest)

    truth = {
        "schema_version": "openbim-ground-truth-v1",
        "case_id": case_id,
        "split": split,
        "layout": layout,
        "seed": seed,
        "generator_version": GENERATOR_VERSION,
        "ground_truth_source": "mutation_manifest.json (detector independent)",
        "mutation_manifest_hash": sha256_file(mutation_path),
        "candidates": {
            "v0_clean": {"expected_issues": []},
            "v1_authorized": {"expected_issues": []},
            "v1_faulty": {
                "expected_issues": [
                    expected_issue(mutation, reopened["v1_faulty"]) for mutation in mutations
                ],
                "admissible_secondary_issues": [
                    expected_issue(mutation, reopened["v1_faulty"], rule_id=rule_id)
                    for mutation in mutations
                    for rule_id in mutation["admissible_secondary_rule_ids"]
                ],
            },
            "v2_corrected": {"expected_issues": []},
        },
        "expected_fault_count": 11,
        "expected_primary_alert_count": 11,
        "admissible_secondary_alert_count": sum(
            len(mutation["admissible_secondary_rule_ids"]) for mutation in mutations
        ),
        "expected_family_counts": {
            "Geometry": 2,
            "IFC Identity": 1,
            "Information": 5,
            "Integrity": 1,
            "Revision": 2,
        },
        "artifact_hashes": artifact_hashes,
    }
    truth_path = case_dir / "truth.json"
    write_json(truth_path, truth)
    return {
        "case_id": case_id,
        "split": split,
        "layout": layout,
        "seed": seed,
        "object_count": len(assets),
        "fault_count": 11,
        "path": case_dir.relative_to(output_root).as_posix(),
        "files": {
            path.name: sha256_file(path) for path in sorted(case_dir.iterdir()) if path.is_file()
        },
    }


def selected_cases(split: str, evaluation_per_layout: int) -> list[tuple[str, str, int]]:
    result: list[tuple[str, str, int]] = []
    if split in {"representative", "all"}:
        result.append(("representative", *REPRESENTATIVE))
    if split in {"pilot", "all"}:
        for layout, seeds in PILOT_SEEDS.items():
            result.extend(("pilot", layout, seed) for seed in seeds)
    if split in {"evaluation", "all"}:
        if not 1 <= evaluation_per_layout <= 10:
            raise ValueError("--evaluation-per-layout must be between 1 and 10")
        for layout, seeds in EVALUATION_SEEDS.items():
            result.extend(("evaluation", layout, seed) for seed in seeds[:evaluation_per_layout])
    return result


def clean_generated_directories(output_root: Path, split: str) -> None:
    names = {
        "representative": ("representative",),
        "pilot": ("pilot",),
        "evaluation": ("evaluation",),
        "all": ("representative", "pilot", "evaluation"),
    }[split]
    resolved_root = output_root.resolve()
    for name in names:
        target = (output_root / name).resolve()
        if resolved_root not in target.parents:
            raise RuntimeError(f"Refusing to remove path outside output root: {target}")
        if target.exists():
            shutil.rmtree(target)


def generate_dataset(
    output_root: Path,
    *,
    split: str,
    evaluation_per_layout: int,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    clean_generated_directories(output_root, split)
    profile_path = output_root / "virtual_fab_profile.json"
    ids_path = output_root / "virtual_fab_v1.ids"
    profile_data = make_profile()
    write_json(profile_path, profile_data)
    ids_path.write_bytes(build_ids())
    profile_file_hash = sha256_file(profile_path)
    profile_canonical_hash = sha256_bytes(compact_canonical_json(profile_data))
    ids_hash = sha256_file(ids_path)
    cases = [
        generate_case(
            output_root,
            split=case_split,
            layout=layout,
            seed=seed,
            ids_hash=ids_hash,
            profile_file_hash=profile_file_hash,
            profile_canonical_hash=profile_canonical_hash,
        )
        for case_split, layout, seed in selected_cases(split, evaluation_per_layout)
    ]
    manifest = {
        "schema_version": "openbim-dataset-manifest-v1",
        "dataset_id": "virtual-fab-v1",
        "dataset_version": "1.0.0",
        "generator_version": GENERATOR_VERSION,
        "generation_epoch": "protocol-v1",
        "requested_split": split,
        "evaluation_cases_per_layout": evaluation_per_layout,
        "ids": {"path": ids_path.name, "sha256": ids_hash},
        "profile": {
            "path": profile_path.name,
            "sha256": profile_file_hash,
            "file_sha256": profile_file_hash,
            "canonical_json_sha256": profile_canonical_hash,
        },
        "case_count": len(cases),
        "cases": sorted(cases, key=lambda item: item["case_id"]),
        "totals": {
            "models": len(cases) * 4,
            "fault_events": len(cases) * 11,
            "pilot_cases": sum(case["split"] == "pilot" for case in cases),
            "evaluation_cases": sum(case["split"] == "evaluation" for case in cases),
        },
        "research_validation_only": True,
    }
    write_json(output_root / "dataset_manifest.json", manifest)
    return manifest


def relative_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def verify_determinism(
    output_root: Path,
    *,
    split: str,
    evaluation_per_layout: int,
) -> None:
    first = relative_hashes(output_root)
    with tempfile.TemporaryDirectory(prefix="datumguard-openbim-") as temp_dir:
        second_root = Path(temp_dir) / "openbim"
        generate_dataset(
            second_root,
            split=split,
            evaluation_per_layout=evaluation_per_layout,
        )
        second = relative_hashes(second_root)
    if first != second:
        differences = sorted(set(first) | set(second))
        mismatched = [path for path in differences if first.get(path) != second.get(path)]
        raise RuntimeError(f"Determinism verification failed: {mismatched[:20]}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--split",
        choices=("representative", "pilot", "evaluation", "all"),
        default="all",
    )
    parser.add_argument(
        "--evaluation-per-layout",
        type=int,
        default=10,
        help="Use 4 for minimum evaluation or 10 for the target corpus.",
    )
    parser.add_argument("--verify-determinism", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = args.output_root.resolve()
    manifest = generate_dataset(
        output_root,
        split=args.split,
        evaluation_per_layout=args.evaluation_per_layout,
    )
    if args.verify_determinism:
        verify_determinism(
            output_root,
            split=args.split,
            evaluation_per_layout=args.evaluation_per_layout,
        )
    print(
        json.dumps(
            {
                "output_root": str(output_root),
                "case_count": manifest["case_count"],
                "models": manifest["totals"]["models"],
                "fault_events": manifest["totals"]["fault_events"],
                "determinism_verified": args.verify_determinism,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
