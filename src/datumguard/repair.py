from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from ortools.sat.python import cp_model

from .core import compute_contract_hash, get_numeric_path, set_numeric_path
from .models import DesignContract, RepairChange, RepairProposal, Violation

MICRONS_PER_MM = 1000


class RepairRejected(ValueError):
    """Raised when a proposal violates locked/free repair policy."""


def _to_microns(value: float) -> int:
    return int(round(value * MICRONS_PER_MM))


def _solve_nearest(
    *,
    minimum: float,
    maximum: float,
    step: float,
    desired: float,
) -> float | None:
    minimum_um = _to_microns(minimum)
    maximum_um = _to_microns(maximum)
    step_um = max(_to_microns(step), 1)
    count = max((maximum_um - minimum_um) // step_um, 0)
    model = cp_model.CpModel()
    index = model.new_int_var(0, count, "step_index")
    value = model.new_int_var(minimum_um, minimum_um + count * step_um, "value_um")
    model.add(value == minimum_um + index * step_um)
    distance = model.new_int_var(0, max(abs(maximum_um), abs(minimum_um)) * 2 + 1, "distance")
    model.add_abs_equality(distance, value - _to_microns(desired))
    model.minimize(distance)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 0.25
    solver.parameters.num_search_workers = 1
    status = solver.solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        return None
    return solver.value(value) / MICRONS_PER_MM


def _desired_from_violation(
    contract: DesignContract,
    path: str,
    violation: Violation,
    iteration: int,
) -> float | None:
    current = get_numeric_path(contract, path)
    if violation.code == "DG_TOLERANCE_EXCEEDED":
        target = violation.details.get("target")
        return float(target) if isinstance(target, int | float) else None
    if violation.code in {
        "DG_EDGE_DISTANCE",
        "DG_FEATURE_OUTSIDE_OUTLINE",
        "DG_FEATURE_OVERLAP",
        "DG_LIGAMENT",
    }:
        actual = float(
            violation.details.get(
                "actual_edge_distance",
                violation.details.get("actual_ligament", 0.0),
            )
        )
        required = float(
            violation.details.get(
                "required_edge_distance",
                violation.details.get("required_ligament", 0.0),
            )
        )
        delta = max(required - actual + 0.001, 1.0) * iteration
        return current + delta
    return None


def propose_repair(
    contract: DesignContract,
    violations: list[Violation],
    *,
    iteration: int,
) -> RepairProposal:
    contract_hash = compute_contract_hash(contract)
    if iteration > 3:
        return RepairProposal(
            proposal_id=f"repair-{contract_hash[7:19]}-{iteration}",
            contract_hash=contract_hash,
            iteration=3,
            status="exhausted",
            violations=violations,
        )

    free_by_path = {parameter.path: parameter for parameter in contract.free_parameters}
    locked_paths = {dimension.path for dimension in contract.dimensions if dimension.locked}
    changes: list[RepairChange] = []
    changed_paths: set[str] = set()
    for violation in violations:
        if not violation.repairable:
            continue
        explicit_path = violation.details.get("path")
        candidate_paths: list[str] = []
        if isinstance(explicit_path, str):
            candidate_paths.append(explicit_path)
        for entity_id in violation.entity_ids:
            candidate_paths.extend(
                path for path in free_by_path if path.startswith(f"features.{entity_id}.")
            )
        for path in candidate_paths:
            if path in changed_paths or path in locked_paths or path not in free_by_path:
                continue
            parameter = free_by_path[path]
            before = get_numeric_path(contract, path)
            desired = _desired_from_violation(contract, path, violation, iteration)
            if desired is None:
                continue
            after = _solve_nearest(
                minimum=parameter.minimum,
                maximum=parameter.maximum,
                step=parameter.step,
                desired=desired,
            )
            if after is None or math.isclose(before, after, abs_tol=1e-12):
                continue
            changes.append(
                RepairChange(
                    path=path,
                    before=before,
                    after=after,
                    reason=violation.code,
                    constraint_id=violation.constraint_id,
                )
            )
            changed_paths.add(path)
            break

    proposal_payload = json.dumps(
        [change.model_dump(mode="json") for change in changes],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    proposal_digest = hashlib.sha256(proposal_payload).hexdigest()[:12]
    return RepairProposal(
        proposal_id=f"repair-{proposal_digest}-{iteration}",
        contract_hash=contract_hash,
        iteration=iteration,
        status="proposed" if changes else "not_repairable",
        changes=changes,
        violations=violations,
    )


def apply_repair(contract: DesignContract, proposal: RepairProposal) -> DesignContract:
    if proposal.contract_hash != compute_contract_hash(contract):
        raise RepairRejected("proposal contract hash does not match")
    if proposal.status != "proposed" or not proposal.changes:
        raise RepairRejected("proposal has no applicable changes")
    free_by_path = {parameter.path: parameter for parameter in contract.free_parameters}
    locked_paths = {dimension.path for dimension in contract.dimensions if dimension.locked}
    result = contract
    for change in proposal.changes:
        if change.path in locked_paths or change.path not in free_by_path:
            raise RepairRejected(f"path is not repairable: {change.path}")
        actual_before = get_numeric_path(result, change.path)
        if not math.isclose(actual_before, change.before, abs_tol=1e-9):
            raise RepairRejected(f"stale before value: {change.path}")
        parameter = free_by_path[change.path]
        if not parameter.minimum <= change.after <= parameter.maximum:
            raise RepairRejected(f"repair value is outside the declared range: {change.path}")
        result = set_numeric_path(result, change.path, change.after)

    for path in locked_paths:
        if not math.isclose(
            get_numeric_path(contract, path),
            get_numeric_path(result, path),
            abs_tol=1e-12,
        ):
            raise RepairRejected(f"locked dimension changed: {path}")
    return result


def compare_contracts(baseline: DesignContract, candidate: DesignContract) -> dict[str, Any]:
    paths = sorted(
        {dimension.path for dimension in baseline.dimensions}
        | {dimension.path for dimension in candidate.dimensions}
        | {parameter.path for parameter in baseline.free_parameters}
        | {parameter.path for parameter in candidate.free_parameters}
    )
    changes: list[dict[str, Any]] = []
    for path in paths:
        try:
            before = get_numeric_path(baseline, path)
            after = get_numeric_path(candidate, path)
        except KeyError:
            changes.append({"path": path, "change": "missing_in_one_contract"})
            continue
        if not math.isclose(before, after, abs_tol=1e-12):
            changes.append({"path": path, "before": before, "after": after})
    return {
        "baseline_hash": compute_contract_hash(baseline),
        "candidate_hash": compute_contract_hash(candidate),
        "changes": changes,
        "feature_ids_added": sorted(
            {feature.id for feature in candidate.features}
            - {feature.id for feature in baseline.features}
        ),
        "feature_ids_removed": sorted(
            {feature.id for feature in baseline.features}
            - {feature.id for feature in candidate.features}
        ),
    }
