from __future__ import annotations

import importlib
import re
from collections import Counter, defaultdict
from typing import Any

from .ifc_evidence import (
    aabb_positive_overlap,
    entity_container,
    entity_container_id,
    entity_global_id,
    entity_stable_id,
    entity_step_id,
    normalized_scalar,
    orthogonal_world_side,
    project_unit_scale_to_m,
    property_value,
    service_envelope,
    stable_issue_key,
    world_aabb,
)
from .openbim_models import (
    OpenBimAuthorization,
    OpenBimIssue,
    OpenBimProfile,
    OpenBimRuleResult,
    OpenBimRuleStatus,
    OpenBimScope,
    OpenBimSeverity,
    OpenBimSourceHashes,
)

_IDS_RULE_PATTERN = re.compile(r"\b(IDS-[0-9]{2,})\b", re.IGNORECASE)
_SAFE_IDS_RULE_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")


def _issue(
    *,
    rule_id: str,
    scope: OpenBimScope,
    severity: OpenBimSeverity,
    message: str,
    hashes: OpenBimSourceHashes,
    entities: list[Any] | None = None,
    entity_ids: list[str] | None = None,
    entity_pair: list[str] | None = None,
    field: str | None = None,
    expected: Any | None = None,
    actual: Any | None = None,
    location: tuple[float, float, float] | None = None,
    raw: dict[str, Any] | None = None,
    key_parts: tuple[Any, ...] = (),
) -> OpenBimIssue:
    resolved_entities = entities or []
    resolved_ids = entity_ids or [entity_stable_id(entity) for entity in resolved_entities]
    step_ids = [entity_step_id(entity) for entity in resolved_entities if entity_step_id(entity)]
    sorted_pair = sorted(entity_pair) if entity_pair is not None else None
    return OpenBimIssue(
        issue_key=stable_issue_key(rule_id, resolved_ids, sorted_pair, field, *key_parts),
        rule_id=rule_id,
        scope=scope,
        severity=severity,
        message=message,
        entity_ids=resolved_ids,
        entity_pair=sorted_pair,
        step_ids=step_ids,
        field=field,
        expected=normalized_scalar(expected),
        actual=normalized_scalar(actual),
        location=(
            (round(location[0], 9), round(location[1], 9), round(location[2], 9))
            if location
            else None
        ),
        source_hashes=hashes,
        raw=raw,
    )


def _result(
    rule_id: str,
    scope: OpenBimScope,
    status: OpenBimRuleStatus,
    *,
    evaluated_count: int,
    issue_count: int,
    summary: str,
    severity: OpenBimSeverity = OpenBimSeverity.ERROR,
) -> OpenBimRuleResult:
    return OpenBimRuleResult(
        rule_id=rule_id,
        scope=scope,
        status=status,
        severity=severity,
        evaluated_count=evaluated_count,
        issue_count=issue_count,
        summary=summary,
    )


def validate_ids_requirements(
    candidate: Any,
    ids_xml: str,
    hashes: OpenBimSourceHashes,
) -> tuple[list[OpenBimRuleResult], list[OpenBimIssue]]:
    upper_xml = ids_xml.upper()
    if "<!DOCTYPE" in upper_xml or "<!ENTITY" in upper_xml:
        raise ValueError("IDS DTD and entity declarations are not allowed")
    ids_module: Any = importlib.import_module("ifctester.ids")
    reporter_module: Any = importlib.import_module("ifctester.reporter")
    try:
        # IfcTester 0.8.5's from_string(validate=True) routes through stdlib
        # ElementTree and can lose the xs QName prefix mapping in valid IDS 1.0
        # restrictions. Validate the untouched XML against its bundled schema,
        # then parse that already-validated document without the buggy second pass.
        ids_module.get_schema().validate(ids_xml)
        ids_document = ids_module.from_string(ids_xml, validate=False)
    except Exception as exc:
        raise ValueError("IDS input failed schema validation") from exc
    if not getattr(ids_document, "specifications", None):
        raise ValueError("IDS input contains no specifications")
    try:
        ids_document.validate(candidate)
        reporter = reporter_module.Json(ids_document)
        raw_results = reporter.report()
    except Exception as exc:
        raise ValueError("IDS evaluation failed") from exc

    issues_by_rule: dict[str, list[OpenBimIssue]] = defaultdict(list)
    evaluated_by_rule: Counter[str] = Counter()
    seen: set[tuple[str, str, str]] = set()
    for specification_index, specification in enumerate(raw_results.get("specifications", []), 1):
        specification_name = str(specification.get("name") or f"IDS-{specification_index:02d}")
        match = _IDS_RULE_PATTERN.search(specification_name)
        rule_id = match.group(1).upper() if match else f"IDS-{specification_index:02d}"
        if not _SAFE_IDS_RULE_PATTERN.fullmatch(rule_id):
            rule_id = f"IDS-{specification_index:02d}"
        applicable_count = int(specification.get("total_applicable") or 0)
        evaluated_by_rule[rule_id] += applicable_count
        requirements = specification.get("requirements") or []
        for requirement_index, requirement in enumerate(requirements, 1):
            requirement_label = str(
                requirement.get("label")
                or requirement.get("description")
                or f"requirement-{requirement_index}"
            )[:200]
            for failure in requirement.get("failed_entities") or []:
                entity = failure.get("element")
                if entity is None:
                    continue
                entity_id = entity_stable_id(entity)
                dedupe_key = (rule_id, entity_id, requirement_label)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                reason = normalized_scalar(failure.get("reason"))
                issues_by_rule[rule_id].append(
                    _issue(
                        rule_id=rule_id,
                        scope=OpenBimScope.IDS_REQUIREMENT,
                        severity=OpenBimSeverity.ERROR,
                        message=f"IDS requirement failed: {requirement_label}",
                        hashes=hashes,
                        entities=[entity],
                        field=requirement_label,
                        expected=requirement.get("value") or requirement.get("description"),
                        actual=reason,
                        raw={
                            "specification": specification_name[:300],
                            "facet_type": str(requirement.get("facet_type") or "")[:100],
                            "reason": reason,
                        },
                    )
                )
        if not specification.get("status", False) and not issues_by_rule[rule_id]:
            issues_by_rule[rule_id].append(
                _issue(
                    rule_id=rule_id,
                    scope=OpenBimScope.IDS_REQUIREMENT,
                    severity=OpenBimSeverity.ERROR,
                    message=f"IDS specification failed: {specification_name[:300]}",
                    hashes=hashes,
                    expected="at least one applicable object satisfying every requirement",
                    actual={
                        "applicable": applicable_count,
                        "checks_failed": specification.get("total_checks_fail", 0),
                    },
                    key_parts=(specification_index,),
                )
            )

    all_rule_ids = sorted(set(evaluated_by_rule) | set(issues_by_rule))
    results = [
        _result(
            rule_id,
            OpenBimScope.IDS_REQUIREMENT,
            OpenBimRuleStatus.FAILED if issues_by_rule[rule_id] else OpenBimRuleStatus.PASSED,
            evaluated_count=evaluated_by_rule[rule_id],
            issue_count=len(issues_by_rule[rule_id]),
            summary=(
                f"{len(issues_by_rule[rule_id])} normalized IDS violation(s)"
                if issues_by_rule[rule_id]
                else "IDS requirement passed"
            ),
        )
        for rule_id in all_rule_ids
    ]
    issues = [issue for rule_id in all_rule_ids for issue in issues_by_rule[rule_id]]
    return results, issues


def validate_ifc_integrity(
    candidate: Any,
    profile: OpenBimProfile,
    hashes: OpenBimSourceHashes,
) -> tuple[list[OpenBimRuleResult], list[OpenBimIssue], bool]:
    results: list[OpenBimRuleResult] = []
    issues: list[OpenBimIssue] = []

    schema_issues: list[OpenBimIssue] = []
    schema_checker_available = True
    try:
        validate_module: Any = importlib.import_module("ifcopenshell.validate")
        logger = validate_module.json_logger()
        validate_module.validate(candidate, logger, express_rules=False)
        statements = list(getattr(logger, "statements", []))
    except Exception:
        schema_checker_available = False
        statements = []
    if not schema_checker_available:
        schema_issues.append(
            _issue(
                rule_id="IFC-00",
                scope=OpenBimScope.IFC_SCHEMA,
                severity=OpenBimSeverity.WARNING,
                message="IFC schema checker was not available; the rule is not evaluable.",
                hashes=hashes,
                expected="successful IfcOpenShell schema validation",
                actual="checker failure",
            )
        )
    elif statements:
        schema_issues.append(
            _issue(
                rule_id="IFC-00",
                scope=OpenBimScope.IFC_SCHEMA,
                severity=OpenBimSeverity.ERROR,
                message="IFC schema validation reported invalid instances.",
                hashes=hashes,
                expected="0 schema validation statements",
                actual=len(statements),
                raw={
                    "messages": [str(item.get("message", ""))[:500] for item in statements[:10]],
                    "truncated": len(statements) > 10,
                },
            )
        )
    results.append(
        _result(
            "IFC-00",
            OpenBimScope.IFC_SCHEMA,
            OpenBimRuleStatus.NOT_EVALUABLE
            if not schema_checker_available
            else OpenBimRuleStatus.FAILED
            if schema_issues
            else OpenBimRuleStatus.PASSED,
            evaluated_count=1,
            issue_count=len(schema_issues),
            summary="IFC schema validation completed",
        )
    )
    issues.extend(schema_issues)

    project_issues: list[OpenBimIssue] = []
    projects = list(candidate.by_type("IfcProject"))
    if str(candidate.schema).upper() != profile.ifc_schema:
        project_issues.append(
            _issue(
                rule_id="IFC-01",
                scope=OpenBimScope.IFC_SCHEMA,
                severity=OpenBimSeverity.ERROR,
                message="IFC schema does not match the registered profile.",
                hashes=hashes,
                expected=profile.ifc_schema,
                actual=str(candidate.schema),
                field="schema",
            )
        )
    if len(projects) != 1:
        project_issues.append(
            _issue(
                rule_id="IFC-01",
                scope=OpenBimScope.IFC_SCHEMA,
                severity=OpenBimSeverity.ERROR,
                message="Exactly one IfcProject is required.",
                hashes=hashes,
                expected=1,
                actual=len(projects),
                field="IfcProject",
            )
        )
    unit_scale = project_unit_scale_to_m(candidate)
    if unit_scale is None:
        project_issues.append(
            _issue(
                rule_id="IFC-01",
                scope=OpenBimScope.IFC_SCHEMA,
                severity=OpenBimSeverity.WARNING,
                message="Project length unit could not be established.",
                hashes=hashes,
                expected="declared positive LENGTHUNIT",
                actual=None,
                field="LENGTHUNIT",
            )
        )
    results.append(
        _result(
            "IFC-01",
            OpenBimScope.IFC_SCHEMA,
            OpenBimRuleStatus.FAILED
            if any(issue.severity == OpenBimSeverity.ERROR for issue in project_issues)
            else OpenBimRuleStatus.NOT_EVALUABLE
            if project_issues
            else OpenBimRuleStatus.PASSED,
            evaluated_count=1,
            issue_count=len(project_issues),
            summary="IFC4 project cardinality and length-unit check",
        )
    )
    issues.extend(project_issues)

    roots = list(candidate.by_type("IfcRoot"))
    identity_issues: list[OpenBimIssue] = []
    guid_entities: dict[str, list[Any]] = defaultdict(list)
    for root in roots:
        guid = entity_global_id(root)
        if not guid:
            identity_issues.append(
                _issue(
                    rule_id="IFC-02",
                    scope=OpenBimScope.IFC_SCHEMA,
                    severity=OpenBimSeverity.ERROR,
                    message="IfcRoot has an empty GlobalId.",
                    hashes=hashes,
                    entities=[root],
                    expected="non-empty GlobalId",
                    actual="",
                    field="GlobalId",
                )
            )
        else:
            guid_entities[guid].append(root)
    for guid, entities in sorted(guid_entities.items()):
        if len(entities) > 1:
            identity_issues.append(
                _issue(
                    rule_id="IFC-02",
                    scope=OpenBimScope.IFC_SCHEMA,
                    severity=OpenBimSeverity.ERROR,
                    message="GlobalId is duplicated within the candidate IFC.",
                    hashes=hashes,
                    entities=entities,
                    expected="unique GlobalId",
                    actual={"global_id": guid, "count": len(entities)},
                    field="GlobalId",
                )
            )
    results.append(
        _result(
            "IFC-02",
            OpenBimScope.IFC_SCHEMA,
            OpenBimRuleStatus.FAILED if identity_issues else OpenBimRuleStatus.PASSED,
            evaluated_count=len(roots),
            issue_count=len(identity_issues),
            summary="GlobalId presence and uniqueness check",
        )
    )
    issues.extend(identity_issues)

    products = [
        entity
        for entity in candidate.by_type("IfcProduct")
        if any(entity.is_a(ifc_class) for ifc_class in profile.applicable_entities)
    ]
    if len(products) > profile.max_products:
        raise ValueError("IFC candidate exceeds the registered product limit")
    containment_issues: list[OpenBimIssue] = []
    for product in products:
        container = entity_container(product)
        if container is None or not any(
            container.is_a(ifc_class) for ifc_class in profile.required_container_types
        ):
            containment_issues.append(
                _issue(
                    rule_id="IFC-03",
                    scope=OpenBimScope.IFC_SCHEMA,
                    severity=OpenBimSeverity.ERROR,
                    message="Product is not assigned to a required spatial container.",
                    hashes=hashes,
                    entities=[product],
                    field="container",
                    expected=profile.required_container_types,
                    actual=container.is_a() if container is not None else None,
                )
            )
    results.append(
        _result(
            "IFC-03",
            OpenBimScope.IFC_SCHEMA,
            OpenBimRuleStatus.FAILED if containment_issues else OpenBimRuleStatus.PASSED,
            evaluated_count=len(products),
            issue_count=len(containment_issues),
            summary="Required spatial containment check",
        )
    )
    issues.extend(containment_issues)

    asset_key_entities: dict[str, list[Any]] = defaultdict(list)
    for product in products:
        value = property_value(product, profile.asset_key_path)
        if value not in (None, ""):
            asset_key_entities[str(value)].append(product)
    duplicate_asset_issues: list[OpenBimIssue] = []
    for asset_key, entities in sorted(asset_key_entities.items()):
        if len(entities) > 1:
            duplicate_asset_issues.append(
                _issue(
                    rule_id="REV-01",
                    scope=OpenBimScope.PROJECT_REVISION_RULE,
                    severity=OpenBimSeverity.ERROR,
                    message="AssetKey is duplicated; revision matching is ambiguous.",
                    hashes=hashes,
                    entities=entities,
                    field=profile.asset_key_path,
                    expected="unique AssetKey",
                    actual={"asset_key": asset_key, "count": len(entities)},
                )
            )
    results.append(
        _result(
            "REV-01",
            OpenBimScope.PROJECT_REVISION_RULE,
            OpenBimRuleStatus.AMBIGUOUS if duplicate_asset_issues else OpenBimRuleStatus.PASSED,
            evaluated_count=len(asset_key_entities),
            issue_count=len(duplicate_asset_issues),
            summary="AssetKey uniqueness check for revision matching",
        )
    )
    issues.extend(duplicate_asset_issues)
    return results, issues, bool(identity_issues or duplicate_asset_issues)


def _asset_index(model: Any, profile: OpenBimProfile) -> tuple[dict[str, Any], set[str]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for entity in model.by_type("IfcProduct"):
        if not any(entity.is_a(ifc_class) for ifc_class in profile.applicable_entities):
            continue
        value = property_value(entity, profile.asset_key_path)
        if value not in (None, ""):
            grouped[str(value)].append(entity)
    ambiguous = {key for key, entities in grouped.items() if len(entities) != 1}
    return {key: entities[0] for key, entities in grouped.items() if len(entities) == 1}, ambiguous


def _is_authorized(
    authorizations: list[OpenBimAuthorization],
    *,
    asset_key: str,
    field: str,
    before: Any,
    after: Any,
) -> OpenBimAuthorization | None:
    for authorization in authorizations:
        if authorization.asset_key != asset_key or authorization.field != field:
            continue
        if authorization.before is not None and normalized_scalar(authorization.before) != before:
            continue
        if authorization.after is not None and normalized_scalar(authorization.after) != after:
            continue
        return authorization
    return None


def _locked_value_is_valid(field: str, value: Any) -> bool:
    if value in (None, ""):
        return False
    if field == "DG_Identity.AssetTag":
        return bool(re.fullmatch(r"VF-[A-Z]{2}-[0-9]{3}", str(value)))
    if field == "DG_VFabUtility.UtilityType":
        return str(value) in {"PCW", "CDA", "VAC", "EXH"}
    if field == "DG_VFabUtility.SystemCode":
        return bool(str(value).strip())
    if field == "container":
        return bool(str(value).strip())
    return True


def _ambiguous_global_id_steps(model: Any) -> set[int]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    ambiguous: set[int] = set()
    for entity in model.by_type("IfcRoot"):
        guid = entity_global_id(entity)
        if not guid:
            ambiguous.add(entity_step_id(entity))
        else:
            grouped[guid].append(entity)
    for entities in grouped.values():
        if len(entities) > 1:
            ambiguous.update(entity_step_id(entity) for entity in entities)
    return ambiguous


def validate_revision(
    baseline: Any,
    candidate: Any,
    profile: OpenBimProfile,
    hashes: OpenBimSourceHashes,
    *,
    candidate_identity_ambiguous: bool,
) -> tuple[list[OpenBimRuleResult], list[OpenBimIssue]]:
    baseline_index, baseline_ambiguous = _asset_index(baseline, profile)
    candidate_index, candidate_ambiguous = _asset_index(candidate, profile)
    all_ambiguous = baseline_ambiguous | candidate_ambiguous
    baseline_ambiguous_steps = _ambiguous_global_id_steps(baseline)
    candidate_ambiguous_steps = _ambiguous_global_id_steps(candidate)
    common_keys = [
        asset_key
        for asset_key in sorted(set(baseline_index) & set(candidate_index) - all_ambiguous)
        if entity_step_id(baseline_index[asset_key]) not in baseline_ambiguous_steps
        and entity_step_id(candidate_index[asset_key]) not in candidate_ambiguous_steps
    ]

    guid_issues: list[OpenBimIssue] = []
    locked_issues: list[OpenBimIssue] = []
    for asset_key in common_keys:
        before_entity = baseline_index[asset_key]
        after_entity = candidate_index[asset_key]
        before_guid = entity_global_id(before_entity)
        after_guid = entity_global_id(after_entity)
        if before_guid != after_guid:
            authorization = _is_authorized(
                profile.authorized_changes,
                asset_key=asset_key,
                field="GlobalId",
                before=before_guid,
                after=after_guid,
            )
            if authorization is None:
                guid_issues.append(
                    _issue(
                        rule_id="REV-02",
                        scope=OpenBimScope.PROJECT_REVISION_RULE,
                        severity=OpenBimSeverity.ERROR,
                        message="GlobalId changed for a stable AssetKey without authorization.",
                        hashes=hashes,
                        entities=[after_entity],
                        field="GlobalId",
                        expected=before_guid,
                        actual=after_guid,
                        raw={"asset_key": asset_key, "authorization": None},
                        key_parts=(asset_key,),
                    )
                )
        for field in profile.locked_fields:
            if field == "container":
                before_value = entity_container_id(before_entity)
                after_value = entity_container_id(after_entity)
            else:
                before_value = normalized_scalar(property_value(before_entity, field))
                after_value = normalized_scalar(property_value(after_entity, field))
            if before_value == after_value:
                continue
            # The project contract protects valid-to-valid changes. Missing or
            # invalid values are owned by IDS/integrity rules and are skipped
            # here to avoid cascading duplicate alerts from one mutation.
            if not _locked_value_is_valid(field, before_value) or not _locked_value_is_valid(
                field, after_value
            ):
                continue
            authorization = _is_authorized(
                profile.authorized_changes,
                asset_key=asset_key,
                field=field,
                before=before_value,
                after=after_value,
            )
            if authorization is not None:
                continue
            locked_issues.append(
                _issue(
                    rule_id="REV-03",
                    scope=OpenBimScope.PROJECT_REVISION_RULE,
                    severity=OpenBimSeverity.ERROR,
                    message="Locked revision field changed without authorization.",
                    hashes=hashes,
                    entities=[after_entity],
                    field=field,
                    expected=before_value,
                    actual=after_value,
                    raw={"asset_key": asset_key, "authorization": None},
                    key_parts=(asset_key,),
                )
            )

    ambiguous = candidate_identity_ambiguous or bool(all_ambiguous)
    results = [
        _result(
            "REV-02",
            OpenBimScope.PROJECT_REVISION_RULE,
            OpenBimRuleStatus.FAILED
            if guid_issues
            else OpenBimRuleStatus.AMBIGUOUS
            if ambiguous
            else OpenBimRuleStatus.PASSED,
            evaluated_count=len(common_keys),
            issue_count=len(guid_issues),
            summary="GlobalId persistence under the project revision contract",
        ),
        _result(
            "REV-03",
            OpenBimScope.PROJECT_REVISION_RULE,
            OpenBimRuleStatus.FAILED
            if locked_issues
            else OpenBimRuleStatus.AMBIGUOUS
            if ambiguous
            else OpenBimRuleStatus.PASSED,
            evaluated_count=len(common_keys) * len(profile.locked_fields),
            issue_count=len(locked_issues),
            summary="Locked property and container revision check",
        ),
    ]
    return results, guid_issues + locked_issues


def validate_clearance(
    candidate: Any,
    profile: OpenBimProfile,
    hashes: OpenBimSourceHashes,
) -> tuple[list[OpenBimRuleResult], list[OpenBimIssue]]:
    tools = [
        entity
        for entity in candidate.by_type("IfcBuildingElementProxy")
        if str(getattr(entity, "ObjectType", "") or "") == profile.tool_object_type
    ]
    obstacles: list[Any] = []
    seen_steps: set[int] = set()
    for ifc_class in profile.obstacle_entities:
        for entity in candidate.by_type(ifc_class):
            step_id = entity_step_id(entity)
            if step_id not in seen_steps:
                seen_steps.add(step_id)
                obstacles.append(entity)

    unit_scale = project_unit_scale_to_m(candidate)
    issues: list[OpenBimIssue] = []
    not_evaluable = False
    geometry_vertex_count = 0
    obstacle_bounds: dict[int, tuple[tuple[float, float, float], tuple[float, float, float]]] = {}
    for obstacle in obstacles:
        bounds = world_aabb(obstacle)
        if bounds is None:
            not_evaluable = True
            issues.append(
                _issue(
                    rule_id="GEO-01",
                    scope=OpenBimScope.PROJECT_GEOMETRY_RULE,
                    severity=OpenBimSeverity.WARNING,
                    message="Obstacle geometry could not be evaluated.",
                    hashes=hashes,
                    entities=[obstacle],
                    expected="represented geometry",
                    actual=None,
                )
            )
            continue
        geometry_vertex_count += bounds[2]
        obstacle_bounds[entity_step_id(obstacle)] = (bounds[0], bounds[1])

    evaluated_pairs = 0
    for tool in tools:
        tool_bounds = world_aabb(tool)
        if tool_bounds is None or unit_scale is None:
            not_evaluable = True
            issues.append(
                _issue(
                    rule_id="GEO-01",
                    scope=OpenBimScope.PROJECT_GEOMETRY_RULE,
                    severity=OpenBimSeverity.WARNING,
                    message="FAB tool geometry or project unit could not be evaluated.",
                    hashes=hashes,
                    entities=[tool],
                    expected="represented geometry with a declared length unit",
                    actual=None,
                )
            )
            continue
        geometry_vertex_count += tool_bounds[2]
        service_side = str(property_value(tool, "DG_VFabClearance.ServiceSide") or "")
        if service_side not in profile.allowed_service_sides:
            not_evaluable = True
            issues.append(
                _issue(
                    rule_id="GEO-01",
                    scope=OpenBimScope.PROJECT_GEOMETRY_RULE,
                    severity=OpenBimSeverity.WARNING,
                    message="ServiceSide is missing or unsupported for clearance screening.",
                    hashes=hashes,
                    entities=[tool],
                    field="DG_VFabClearance.ServiceSide",
                    expected=profile.allowed_service_sides,
                    actual=service_side or None,
                )
            )
            continue
        world_side = orthogonal_world_side(tool, service_side)
        if world_side is None:
            not_evaluable = True
            issues.append(
                _issue(
                    rule_id="GEO-01",
                    scope=OpenBimScope.PROJECT_GEOMETRY_RULE,
                    severity=OpenBimSeverity.WARNING,
                    message="Tool placement is outside the supported orthogonal rotations.",
                    hashes=hashes,
                    entities=[tool],
                    expected="0/90/180/270 degree horizontal rotation",
                    actual="unsupported placement",
                )
            )
            continue
        raw_depth = property_value(tool, "DG_VFabClearance.ServiceDepth")
        try:
            depth_m = (
                float(raw_depth) * unit_scale
                if raw_depth is not None
                else profile.default_service_depth_m
            )
        except (TypeError, ValueError):
            depth_m = 0.0
        if depth_m <= 0:
            not_evaluable = True
            issues.append(
                _issue(
                    rule_id="GEO-01",
                    scope=OpenBimScope.PROJECT_GEOMETRY_RULE,
                    severity=OpenBimSeverity.WARNING,
                    message="ServiceDepth is not a positive length.",
                    hashes=hashes,
                    entities=[tool],
                    field="DG_VFabClearance.ServiceDepth",
                    expected="> 0",
                    actual=raw_depth,
                )
            )
            continue
        envelope = service_envelope(
            (tool_bounds[0], tool_bounds[1]), world_side=world_side, depth_m=depth_m
        )
        for obstacle in obstacles:
            obstacle_aabb = obstacle_bounds.get(entity_step_id(obstacle))
            if obstacle_aabb is None:
                continue
            evaluated_pairs += 1
            overlap = aabb_positive_overlap(
                envelope, obstacle_aabb, epsilon=profile.clearance_epsilon_m
            )
            if overlap is None:
                continue
            pair = sorted([entity_stable_id(tool), entity_stable_id(obstacle)])
            issues.append(
                _issue(
                    rule_id="GEO-01",
                    scope=OpenBimScope.PROJECT_GEOMETRY_RULE,
                    severity=OpenBimSeverity.ERROR,
                    message=(
                        "Utility geometry positively overlaps the maintenance service envelope."
                    ),
                    hashes=hashes,
                    entities=[tool, obstacle],
                    entity_pair=pair,
                    expected={"positive_overlap_m": 0.0, "boundary_contact": "pass"},
                    actual={"overlap_depths_m": [round(value, 9) for value in overlap[0]]},
                    location=overlap[1],
                )
            )
    if geometry_vertex_count > profile.max_geometry_vertices:
        raise ValueError("IFC candidate exceeds the registered geometry vertex limit")

    error_count = sum(issue.severity == OpenBimSeverity.ERROR for issue in issues)
    status = (
        OpenBimRuleStatus.FAILED
        if error_count
        else OpenBimRuleStatus.NOT_EVALUABLE
        if not_evaluable
        else OpenBimRuleStatus.PASSED
    )
    result = _result(
        "GEO-01",
        OpenBimScope.PROJECT_GEOMETRY_RULE,
        status,
        evaluated_count=evaluated_pairs,
        issue_count=len(issues),
        summary="World-coordinate AABB maintenance-clearance screening",
    )
    return [result], issues


def sort_openbim_results(
    results: list[OpenBimRuleResult], issues: list[OpenBimIssue]
) -> tuple[list[OpenBimRuleResult], list[OpenBimIssue]]:
    return (
        sorted(results, key=lambda item: (item.scope.value, item.rule_id)),
        sorted(
            issues,
            key=lambda item: (
                item.scope.value,
                item.rule_id,
                item.issue_key,
            ),
        ),
    )


__all__ = [
    "sort_openbim_results",
    "validate_clearance",
    "validate_ids_requirements",
    "validate_ifc_integrity",
    "validate_revision",
]
