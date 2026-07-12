from __future__ import annotations

import math
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .frame_models import (
    FrameAnalysisResult,
    FrameMember,
    FrameMemberResult,
    FrameNodeResult,
    StructuralFrameContract,
)

FloatArray = NDArray[np.float64]


class FrameSolverError(ValueError):
    """Fail-closed structural solver error with a stable public error code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        entity_ids: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.entity_ids = entity_ids or []
        self.details = details or {}


def _member_matrices(
    member: FrameMember,
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[float, FloatArray, FloatArray]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        raise FrameSolverError(
            "DG_FRAME_ZERO_LENGTH",
            "A frame member has zero length in model coordinates.",
            entity_ids=[member.id, member.start_node_id, member.end_node_id],
            details={"length_mm": length},
        )
    c = dx / length
    s = dy / length
    ea_l = member.elastic_modulus_mpa * member.area_mm2 / length
    ei = member.elastic_modulus_mpa * member.inertia_mm4
    twelve_ei_l3 = 12.0 * ei / length**3
    six_ei_l2 = 6.0 * ei / length**2
    four_ei_l = 4.0 * ei / length
    two_ei_l = 2.0 * ei / length
    local = np.array(
        [
            [ea_l, 0.0, 0.0, -ea_l, 0.0, 0.0],
            [0.0, twelve_ei_l3, six_ei_l2, 0.0, -twelve_ei_l3, six_ei_l2],
            [0.0, six_ei_l2, four_ei_l, 0.0, -six_ei_l2, two_ei_l],
            [-ea_l, 0.0, 0.0, ea_l, 0.0, 0.0],
            [0.0, -twelve_ei_l3, -six_ei_l2, 0.0, twelve_ei_l3, -six_ei_l2],
            [0.0, six_ei_l2, two_ei_l, 0.0, -six_ei_l2, four_ei_l],
        ],
        dtype=np.float64,
    )
    transform = np.array(
        [
            [c, s, 0.0, 0.0, 0.0, 0.0],
            [-s, c, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, c, s, 0.0],
            [0.0, 0.0, 0.0, -s, c, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    return length, local, transform


def _validate_references(contract: StructuralFrameContract) -> None:
    node_ids = {node.id for node in contract.nodes}
    unknown: set[str] = set()
    owners: set[str] = set()
    for member in contract.members:
        for node_id in (member.start_node_id, member.end_node_id):
            if node_id not in node_ids:
                unknown.add(node_id)
                owners.add(member.id)
    for load in contract.loads:
        if load.node_id not in node_ids:
            unknown.add(load.node_id)
            owners.add(load.id)
    for support in contract.supports:
        if support.node_id not in node_ids:
            unknown.add(support.node_id)
            owners.add(support.id)
    if unknown:
        raise FrameSolverError(
            "DG_FRAME_UNKNOWN_NODE",
            "A frame member, load, or support references an unknown node.",
            entity_ids=sorted([*unknown, *owners]),
            details={"unknown_node_ids": sorted(unknown), "referencing_entity_ids": sorted(owners)},
        )


def _validate_connected(contract: StructuralFrameContract) -> None:
    adjacency: dict[str, set[str]] = {node.id: set() for node in contract.nodes}
    for member in contract.members:
        adjacency[member.start_node_id].add(member.end_node_id)
        adjacency[member.end_node_id].add(member.start_node_id)
    start = min(adjacency)
    visited = {start}
    pending = [start]
    while pending:
        node_id = pending.pop()
        for neighbour in sorted(adjacency[node_id] - visited):
            visited.add(neighbour)
            pending.append(neighbour)
    missing = sorted(set(adjacency) - visited)
    if missing:
        raise FrameSolverError(
            "DG_FRAME_DISCONNECTED",
            "The structural frame contains disconnected nodes or sub-frames.",
            entity_ids=missing,
            details={"disconnected_node_ids": missing},
        )


def solve_frame(contract: StructuralFrameContract) -> FrameAnalysisResult:
    """Solve a 2D Euler-Bernoulli frame in the mm-N-MPa unit system.

    The implementation intentionally uses a deterministic dense assembly for the
    bounded MVP model size. It is the official screening result; future learned
    surrogates must be compared with, and may not replace, this calculation.
    """

    _validate_references(contract)
    _validate_connected(contract)
    nodes = sorted(contract.nodes, key=lambda item: item.id)
    members = sorted(contract.members, key=lambda item: item.id)
    node_index = {node.id: index for index, node in enumerate(nodes)}
    points = {node.id: node.point for node in nodes}
    dof_count = len(nodes) * 3
    stiffness = np.zeros((dof_count, dof_count), dtype=np.float64)
    force = np.zeros(dof_count, dtype=np.float64)
    member_cache: dict[str, tuple[float, FloatArray, FloatArray, list[int]]] = {}

    for member in members:
        length, local, transform = _member_matrices(
            member,
            points[member.start_node_id],
            points[member.end_node_id],
        )
        start_index = node_index[member.start_node_id] * 3
        end_index = node_index[member.end_node_id] * 3
        indices = [
            start_index,
            start_index + 1,
            start_index + 2,
            end_index,
            end_index + 1,
            end_index + 2,
        ]
        global_member = transform.T @ local @ transform
        stiffness[np.ix_(indices, indices)] += global_member
        member_cache[member.id] = (length, local, transform, indices)

    for load in sorted(contract.loads, key=lambda item: item.id):
        start = node_index[load.node_id] * 3
        force[start : start + 3] += (load.fx_n, load.fy_n, load.mz_nmm)

    restrained: set[int] = set()
    for support in contract.supports:
        start = node_index[support.node_id] * 3
        if support.ux:
            restrained.add(start)
        if support.uy:
            restrained.add(start + 1)
        if support.rz:
            restrained.add(start + 2)
    free = np.array(sorted(set(range(dof_count)) - restrained), dtype=np.int64)
    displacement = np.zeros(dof_count, dtype=np.float64)
    condition_number = 1.0
    if free.size:
        reduced = stiffness[np.ix_(free, free)]
        diagonal_scale = np.sqrt(np.abs(np.diag(reduced)))
        if np.any(diagonal_scale <= np.finfo(np.float64).eps):
            raise FrameSolverError(
                "DG_FRAME_SINGULAR",
                "The frame has an unrestrained degree of freedom with zero stiffness.",
                details={"free_dof_count": int(free.size)},
            )
        scaled = reduced / np.outer(diagonal_scale, diagonal_scale)
        singular_values = np.linalg.svd(scaled, compute_uv=False)
        largest = float(singular_values[0]) if singular_values.size else 0.0
        smallest = float(singular_values[-1]) if singular_values.size else 0.0
        rank_tolerance = max(scaled.shape) * np.finfo(np.float64).eps * max(largest, 1.0)
        if smallest <= rank_tolerance:
            raise FrameSolverError(
                "DG_FRAME_SINGULAR",
                "The frame stiffness matrix is singular or under-constrained.",
                details={
                    "free_dof_count": int(free.size),
                    "smallest_scaled_singular_value": smallest,
                    "rank_tolerance": rank_tolerance,
                },
            )
        condition_number = largest / smallest
        if not math.isfinite(condition_number) or condition_number > 1.0e12:
            raise FrameSolverError(
                "DG_FRAME_SINGULAR",
                "The frame stiffness matrix is too ill-conditioned for a reliable result.",
                details={"scaled_condition_number": condition_number},
            )
        scaled_force = force[free] / diagonal_scale
        try:
            scaled_displacement = np.linalg.solve(scaled, scaled_force)
        except np.linalg.LinAlgError as exc:
            raise FrameSolverError(
                "DG_FRAME_SINGULAR",
                "The frame stiffness matrix could not be solved.",
                details={"reason": str(exc)},
            ) from exc
        displacement[free] = scaled_displacement / diagonal_scale

    if not np.all(np.isfinite(displacement)):
        raise FrameSolverError(
            "DG_FRAME_SINGULAR",
            "The frame solution contains non-finite displacement values.",
        )

    residual = stiffness @ displacement - force
    free_translation_dofs = [index for index in free.tolist() if index % 3 != 2]
    equilibrium_residual = (
        float(np.max(np.abs(residual[free_translation_dofs]))) if free_translation_dofs else 0.0
    )
    node_results: list[FrameNodeResult] = []
    for node in nodes:
        start = node_index[node.id] * 3
        ux, uy, rz = (float(item) for item in displacement[start : start + 3])
        node_results.append(
            FrameNodeResult(
                node_id=node.id,
                ux_mm=ux,
                uy_mm=uy,
                rz_rad=rz,
                translation_mm=math.hypot(ux, uy),
                reaction_fx_n=float(residual[start]),
                reaction_fy_n=float(residual[start + 1]),
                reaction_mz_nmm=float(residual[start + 2]),
            )
        )

    member_results: list[FrameMemberResult] = []
    for member in members:
        length, local, transform, indices = member_cache[member.id]
        local_displacement = transform @ displacement[indices]
        end_force = local @ local_displacement
        axial = max(abs(float(end_force[0])), abs(float(end_force[3])))
        moment = max(abs(float(end_force[2])), abs(float(end_force[5])))
        extreme_fibre = member.section_depth_mm / 2.0
        stress = axial / member.area_mm2 + moment * extreme_fibre / member.inertia_mm4
        allowable = member.allowable_stress_mpa or contract.limits.allowable_stress_mpa
        member_results.append(
            FrameMemberResult(
                member_id=member.id,
                length_mm=length,
                start_axial_n=float(end_force[0]),
                start_shear_n=float(end_force[1]),
                start_moment_nmm=float(end_force[2]),
                end_axial_n=float(end_force[3]),
                end_shear_n=float(end_force[4]),
                end_moment_nmm=float(end_force[5]),
                max_combined_stress_mpa=stress,
                allowable_stress_mpa=allowable,
                utilization=stress / allowable,
                strain_energy_nmm=max(
                    0.0,
                    float(0.5 * local_displacement.T @ local @ local_displacement),
                ),
            )
        )

    max_node = max(node_results, key=lambda item: (item.translation_mm, item.node_id))
    critical_member = max(
        member_results,
        key=lambda item: (item.utilization, item.member_id),
        default=None,
    )
    return FrameAnalysisResult(
        node_results=node_results,
        member_results=member_results,
        max_displacement_mm=max_node.translation_mm,
        max_displacement_node_id=max_node.node_id,
        displacement_utilization=(max_node.translation_mm / contract.limits.max_displacement_mm),
        max_member_utilization=critical_member.utilization if critical_member else 0.0,
        critical_member_id=critical_member.member_id if critical_member else None,
        condition_number=condition_number,
        equilibrium_residual_n=equilibrium_residual,
    )


__all__ = ["FrameSolverError", "solve_frame"]
