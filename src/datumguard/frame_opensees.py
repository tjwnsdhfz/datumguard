from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import math
import platform as platform_module
import sys
import threading
from collections.abc import Iterable, Sequence
from importlib import resources
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, Protocol, cast

from pydantic import Field

from .frame_dataset import generate_pipe_rack_contract
from .frame_models import (
    FrameAnalysisResult,
    FrameMemberResult,
    FrameNodeResult,
    StructuralFrameContract,
)
from .frame_service import validate_frame_contract
from .frame_solver import FrameSolverError, solve_frame
from .models import StrictModel

NUMPY_SOLVER_ID: Literal["datumguard_numpy_2d_frame_v1"] = "datumguard_numpy_2d_frame_v1"
OPENSEES_SOLVER_ID: Literal["openseespy_elastic_beam_column_2d_v1"] = (
    "openseespy_elastic_beam_column_2d_v1"
)
_OPENSEES_LOCK = threading.RLock()


class _OpenSeesAPI(Protocol):
    def wipe(self) -> None: ...
    def model(self, *args: object) -> None: ...
    def node(self, *args: object) -> None: ...
    def fix(self, *args: object) -> None: ...
    def geomTransf(self, *args: object) -> None: ...
    def element(self, *args: object) -> None: ...
    def timeSeries(self, *args: object) -> None: ...
    def pattern(self, *args: object) -> None: ...
    def load(self, *args: object) -> None: ...
    def constraints(self, *args: object) -> None: ...
    def numberer(self, *args: object) -> None: ...
    def system(self, *args: object) -> None: ...
    def integrator(self, *args: object) -> None: ...
    def algorithm(self, *args: object) -> None: ...
    def analysis(self, *args: object) -> None: ...
    def analyze(self, *args: object) -> int: ...
    def reactions(self, *args: object) -> None: ...
    def nodeDisp(self, *args: object) -> Sequence[float]: ...
    def nodeReaction(self, *args: object) -> Sequence[float]: ...
    def eleResponse(self, *args: object) -> Sequence[float]: ...
    def version(self) -> str: ...


class OpenSeesParityError(RuntimeError):
    """Fail-closed OpenSees adapter or parity error with a stable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class OpenSeesAvailability(StrictModel):
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    package: Literal["openseespy"] = "openseespy"
    package_version: str | None = None
    engine_version: str | None = None
    runtime: str
    reason: str | None = None

    @property
    def available(self) -> bool:
        return self.status == "AVAILABLE"


class ParityTolerances(StrictModel):
    displacement_abs_mm: float = Field(default=1.0e-7, gt=0)
    rotation_abs_rad: float = Field(default=1.0e-10, gt=0)
    force_abs_n: float = Field(default=1.0e-5, gt=0)
    moment_abs_nmm: float = Field(default=1.0e-2, gt=0)
    stress_abs_mpa: float = Field(default=1.0e-8, gt=0)
    utilization_abs: float = Field(default=1.0e-10, gt=0)
    relative: float = Field(default=1.0e-7, gt=0)


class OpenSeesNodeResult(StrictModel):
    node_id: str
    ux_mm: float
    uy_mm: float
    rz_rad: float
    translation_mm: float
    reaction_fx_n: float
    reaction_fy_n: float
    reaction_mz_nmm: float


class OpenSeesMemberResult(StrictModel):
    member_id: str
    length_mm: float
    start_axial_n: float
    start_shear_n: float
    start_moment_nmm: float
    end_axial_n: float
    end_shear_n: float
    end_moment_nmm: float
    max_combined_stress_mpa: float
    allowable_stress_mpa: float
    utilization: float


class OpenSeesFrameAnalysis(StrictModel):
    solver: Literal["openseespy_elastic_beam_column_2d_v1"] = OPENSEES_SOLVER_ID
    engine_version: str
    analyze_return_code: int
    node_results: list[OpenSeesNodeResult]
    member_results: list[OpenSeesMemberResult]
    max_displacement_mm: float
    max_displacement_node_id: str
    max_member_utilization: float
    critical_member_id: str | None
    equilibrium_force_residual_n: float
    equilibrium_moment_residual_nmm: float
    node_tags: dict[str, int]
    member_tags: dict[str, int]
    local_force_convention: str = (
        "OpenSees localForce resisting vector [N_i,V_i,M_i,N_j,V_j,M_j], "
        "local x from start node to end node and local y counter-clockwise normal; "
        "this maps directly to DatumGuard k_local @ u_local."
    )


class ParityMetricEvidence(StrictModel):
    metric: str
    unit: str
    sample_count: int = Field(ge=1)
    absolute_tolerance: float
    relative_tolerance: float
    max_absolute_error: float
    max_relative_error: float
    worst_entity_dof: str
    passed: bool


class ParityErrorEvidence(StrictModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ParityCaseEvidence(StrictModel):
    case_id: str
    status: Literal["PASSED", "FAILED", "SKIPPED"]
    contract_hash: str
    expected_screening_status: Literal["PASS", "FAIL"]
    numpy_screening_status: Literal["PASS", "FAIL"] | None = None
    opensees_screening_status: Literal["PASS", "FAIL"] | None = None
    metrics: list[ParityMetricEvidence] = Field(default_factory=list)
    equilibrium: dict[str, float] = Field(default_factory=dict)
    tag_mapping: dict[str, dict[str, int]] = Field(default_factory=dict)
    errors: list[ParityErrorEvidence] = Field(default_factory=list)


class ParityBenchmarkCase(StrictModel):
    case_id: str
    contract: StructuralFrameContract
    expected_screening_status: Literal["PASS", "FAIL"]


class OpenSeesParityReport(StrictModel):
    report_kind: Literal["frame_opensees_parity_v1"] = "frame_opensees_parity_v1"
    schema_version: Literal["frame-opensees-parity-v1"] = "frame-opensees-parity-v1"
    status: Literal["PASSED", "FAILED", "UNAVAILABLE"]
    benchmark_id: Literal["datumguard-frame-opensees-parity"] = "datumguard-frame-opensees-parity"
    contract_hash: str
    versions: dict[str, str | None]
    platform: dict[str, str]
    tolerances: ParityTolerances
    availability: OpenSeesAvailability
    cases: list[ParityCaseEvidence]
    summary: dict[str, int | bool | str]
    claims: list[str] = Field(
        default_factory=lambda: [
            "Independent solver parity benchmark, not a structural safety certification.",
            (
                "Any unavailable engine, solver failure, entity mismatch, or tolerance "
                "mismatch fails closed."
            ),
            (
                "OpenSees parity does not add code compliance, nonlinear, buckling, fatigue, "
                "or seismic checks."
            ),
        ]
    )


def _load_opensees() -> _OpenSeesAPI:
    module: ModuleType = importlib.import_module("openseespy.opensees")
    return cast(_OpenSeesAPI, module)


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def probe_opensees() -> OpenSeesAvailability:
    runtime = f"{platform_module.python_implementation()} {platform_module.python_version()}"
    try:
        ops = _load_opensees()
        engine_version = str(ops.version())
    except Exception as exc:
        return OpenSeesAvailability(
            status="UNAVAILABLE",
            package_version=_distribution_version("openseespy"),
            runtime=runtime,
            reason=f"{type(exc).__name__}: {exc}",
        )
    return OpenSeesAvailability(
        status="AVAILABLE",
        package_version=_distribution_version("openseespy"),
        engine_version=engine_version,
        runtime=runtime,
    )


def _check_finite(values: Sequence[float], *, owner: str) -> list[float]:
    result = [float(value) for value in values]
    if not all(math.isfinite(value) for value in result):
        raise OpenSeesParityError(
            "DG_FRAME_OPENSEES_NONFINITE",
            "OpenSees returned a non-finite response.",
            details={"owner": owner, "values": result},
        )
    return result


def _equilibrium_from_nodes(
    contract: StructuralFrameContract,
    node_results: Iterable[OpenSeesNodeResult | FrameNodeResult],
) -> tuple[float, float]:
    points = {node.id: node.point for node in contract.nodes}
    fx = sum(load.fx_n for load in contract.loads)
    fy = sum(load.fy_n for load in contract.loads)
    moment = sum(
        load.mz_nmm + points[load.node_id][0] * load.fy_n - points[load.node_id][1] * load.fx_n
        for load in contract.loads
    )
    for result in node_results:
        x, y = points[result.node_id]
        fx += result.reaction_fx_n
        fy += result.reaction_fy_n
        moment += result.reaction_mz_nmm + x * result.reaction_fy_n - y * result.reaction_fx_n
    return max(abs(fx), abs(fy)), abs(moment)


def solve_frame_opensees(contract: StructuralFrameContract) -> OpenSeesFrameAnalysis:
    """Solve the same mm-N 2D elastic frame with a genuine OpenSeesPy model.

    OpenSees uses process-global state, so model creation, analysis, extraction,
    and cleanup are serialized. Any non-zero ``analyze`` code fails closed.
    """

    availability = probe_opensees()
    if not availability.available:
        raise OpenSeesParityError(
            "DG_FRAME_OPENSEES_UNAVAILABLE",
            "OpenSeesPy is unavailable; parity cannot be asserted.",
            details=availability.model_dump(mode="json"),
        )
    try:
        ops = _load_opensees()
    except Exception as exc:
        raise OpenSeesParityError(
            "DG_FRAME_OPENSEES_UNAVAILABLE",
            "OpenSeesPy became unavailable before model construction.",
            details={"exception_type": type(exc).__name__, "reason": str(exc)},
        ) from exc
    nodes = sorted(contract.nodes, key=lambda item: item.id)
    members = sorted(contract.members, key=lambda item: item.id)
    node_tags = {node.id: index + 1 for index, node in enumerate(nodes)}
    member_tags = {member.id: index + 1 for index, member in enumerate(members)}
    restraint_by_node = {node.id: [False, False, False] for node in nodes}
    for support in sorted(contract.supports, key=lambda item: item.id):
        restraint = restraint_by_node.get(support.node_id)
        if restraint is None:
            raise OpenSeesParityError(
                "DG_FRAME_OPENSEES_UNKNOWN_NODE",
                "A support references an unknown node.",
                details={"support_id": support.id, "node_id": support.node_id},
            )
        restraint[0] = restraint[0] or support.ux
        restraint[1] = restraint[1] or support.uy
        restraint[2] = restraint[2] or support.rz
    load_by_node = {node.id: [0.0, 0.0, 0.0] for node in nodes}
    for load in sorted(contract.loads, key=lambda item: item.id):
        combined = load_by_node.get(load.node_id)
        if combined is None:
            raise OpenSeesParityError(
                "DG_FRAME_OPENSEES_UNKNOWN_NODE",
                "A load references an unknown node.",
                details={"load_id": load.id, "node_id": load.node_id},
            )
        combined[0] += load.fx_n
        combined[1] += load.fy_n
        combined[2] += load.mz_nmm

    with _OPENSEES_LOCK:
        ops.wipe()
        try:
            ops.model("basic", "-ndm", 2, "-ndf", 3)
            for node in nodes:
                ops.node(node_tags[node.id], node.point[0], node.point[1])
            for node in nodes:
                fixity = restraint_by_node[node.id]
                if any(fixity):
                    ops.fix(node_tags[node.id], *(int(value) for value in fixity))
            transform_tag = 1
            ops.geomTransf("Linear", transform_tag)
            for member in members:
                if member.start_node_id not in node_tags or member.end_node_id not in node_tags:
                    raise OpenSeesParityError(
                        "DG_FRAME_OPENSEES_UNKNOWN_NODE",
                        "A member references an unknown node.",
                        details={
                            "member_id": member.id,
                            "start_node_id": member.start_node_id,
                            "end_node_id": member.end_node_id,
                        },
                    )
                ops.element(
                    "elasticBeamColumn",
                    member_tags[member.id],
                    node_tags[member.start_node_id],
                    node_tags[member.end_node_id],
                    member.area_mm2,
                    member.elastic_modulus_mpa,
                    member.inertia_mm4,
                    transform_tag,
                )
            ops.timeSeries("Linear", 1)
            ops.pattern("Plain", 1, 1)
            for node in nodes:
                values = load_by_node[node.id]
                if any(value != 0.0 for value in values):
                    ops.load(node_tags[node.id], *values)
            ops.constraints("Plain")
            ops.numberer("Plain")
            ops.system("BandGeneral")
            ops.integrator("LoadControl", 1.0)
            ops.algorithm("Linear")
            ops.analysis("Static")
            analyze_code = int(ops.analyze(1))
            if analyze_code != 0:
                raise OpenSeesParityError(
                    "DG_FRAME_OPENSEES_ANALYSIS_FAILED",
                    "OpenSees static analysis returned a non-zero code.",
                    details={"analyze_return_code": analyze_code},
                )
            ops.reactions()
            node_results: list[OpenSeesNodeResult] = []
            for node in nodes:
                displacement = _check_finite(
                    ops.nodeDisp(node_tags[node.id]), owner=f"node:{node.id}:displacement"
                )
                reaction = _check_finite(
                    ops.nodeReaction(node_tags[node.id]), owner=f"node:{node.id}:reaction"
                )
                if len(displacement) != 3 or len(reaction) != 3:
                    raise OpenSeesParityError(
                        "DG_FRAME_OPENSEES_RESPONSE_SHAPE",
                        "OpenSees returned an unexpected 2D node response shape.",
                        details={
                            "node_id": node.id,
                            "displacement_count": len(displacement),
                            "reaction_count": len(reaction),
                        },
                    )
                node_results.append(
                    OpenSeesNodeResult(
                        node_id=node.id,
                        ux_mm=displacement[0],
                        uy_mm=displacement[1],
                        rz_rad=displacement[2],
                        translation_mm=math.hypot(displacement[0], displacement[1]),
                        reaction_fx_n=reaction[0],
                        reaction_fy_n=reaction[1],
                        reaction_mz_nmm=reaction[2],
                    )
                )

            points = {node.id: node.point for node in nodes}
            member_results: list[OpenSeesMemberResult] = []
            for member in members:
                response = _check_finite(
                    ops.eleResponse(member_tags[member.id], "localForce"),
                    owner=f"member:{member.id}:localForce",
                )
                if len(response) != 6:
                    raise OpenSeesParityError(
                        "DG_FRAME_OPENSEES_RESPONSE_SHAPE",
                        "OpenSees localForce must contain six 2D end actions.",
                        details={"member_id": member.id, "response_count": len(response)},
                    )
                start = points[member.start_node_id]
                end = points[member.end_node_id]
                length = math.hypot(end[0] - start[0], end[1] - start[1])
                axial = max(abs(response[0]), abs(response[3]))
                moment = max(abs(response[2]), abs(response[5]))
                stress = (
                    axial / member.area_mm2
                    + moment * (member.section_depth_mm / 2.0) / member.inertia_mm4
                )
                allowable = member.allowable_stress_mpa or contract.limits.allowable_stress_mpa
                member_results.append(
                    OpenSeesMemberResult(
                        member_id=member.id,
                        length_mm=length,
                        start_axial_n=response[0],
                        start_shear_n=response[1],
                        start_moment_nmm=response[2],
                        end_axial_n=response[3],
                        end_shear_n=response[4],
                        end_moment_nmm=response[5],
                        max_combined_stress_mpa=stress,
                        allowable_stress_mpa=allowable,
                        utilization=stress / allowable,
                    )
                )
            max_node = max(node_results, key=lambda item: (item.translation_mm, item.node_id))
            critical = max(
                member_results,
                key=lambda item: (item.utilization, item.member_id),
                default=None,
            )
            force_residual, moment_residual = _equilibrium_from_nodes(contract, node_results)
            return OpenSeesFrameAnalysis(
                engine_version=availability.engine_version or "unknown",
                analyze_return_code=analyze_code,
                node_results=node_results,
                member_results=member_results,
                max_displacement_mm=max_node.translation_mm,
                max_displacement_node_id=max_node.node_id,
                max_member_utilization=critical.utilization if critical else 0.0,
                critical_member_id=critical.member_id if critical else None,
                equilibrium_force_residual_n=force_residual,
                equilibrium_moment_residual_nmm=moment_residual,
                node_tags=node_tags,
                member_tags=member_tags,
            )
        except OpenSeesParityError:
            raise
        except Exception as exc:
            raise OpenSeesParityError(
                "DG_FRAME_OPENSEES_RUNTIME_ERROR",
                "OpenSees raised an exception while building, solving, or extracting the model.",
                details={"exception_type": type(exc).__name__, "reason": str(exc)},
            ) from exc
        finally:
            ops.wipe()


def _metric_evidence(
    *,
    metric: str,
    unit: str,
    samples: list[tuple[str, float, float]],
    absolute_tolerance: float,
    relative_tolerance: float,
) -> ParityMetricEvidence:
    if not samples:
        raise ValueError(f"parity metric {metric} requires at least one sample")
    evaluated: list[tuple[str, float, float, bool]] = []
    for identity, expected, actual in samples:
        absolute_error = abs(actual - expected)
        denominator = max(abs(expected), abs(actual), absolute_tolerance)
        relative_error = absolute_error / denominator
        limit = absolute_tolerance + relative_tolerance * max(abs(expected), abs(actual))
        evaluated.append((identity, absolute_error, relative_error, absolute_error <= limit))
    worst = max(evaluated, key=lambda item: (item[1], item[0]))
    return ParityMetricEvidence(
        metric=metric,
        unit=unit,
        sample_count=len(evaluated),
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
        max_absolute_error=worst[1],
        max_relative_error=max(item[2] for item in evaluated),
        worst_entity_dof=worst[0],
        passed=all(item[3] for item in evaluated),
    )


def _screening_status(
    contract: StructuralFrameContract,
    *,
    max_displacement_mm: float,
    max_member_utilization: float,
) -> Literal["PASS", "FAIL"]:
    return (
        "PASS"
        if max_displacement_mm <= contract.limits.max_displacement_mm
        and max_member_utilization <= 1.0
        else "FAIL"
    )


def compare_frame_analyses(
    case_id: str,
    contract_hash: str,
    contract: StructuralFrameContract,
    numpy_result: FrameAnalysisResult,
    opensees_result: OpenSeesFrameAnalysis,
    *,
    expected_screening_status: Literal["PASS", "FAIL"],
    tolerances: ParityTolerances | None = None,
) -> ParityCaseEvidence:
    """Compare complete result maps. Missing entities and mismatches fail closed."""

    tolerance = tolerances or ParityTolerances()
    errors: list[ParityErrorEvidence] = []
    numpy_nodes = {item.node_id: item for item in numpy_result.node_results}
    opensees_nodes = {item.node_id: item for item in opensees_result.node_results}
    numpy_members = {item.member_id: item for item in numpy_result.member_results}
    opensees_members = {item.member_id: item for item in opensees_result.member_results}
    if set(numpy_nodes) != set(opensees_nodes) or set(numpy_members) != set(opensees_members):
        errors.append(
            ParityErrorEvidence(
                code="DG_FRAME_PARITY_ENTITY_MISMATCH",
                message="Solver result entity identifiers do not match.",
                details={
                    "numpy_only_nodes": sorted(set(numpy_nodes) - set(opensees_nodes)),
                    "opensees_only_nodes": sorted(set(opensees_nodes) - set(numpy_nodes)),
                    "numpy_only_members": sorted(set(numpy_members) - set(opensees_members)),
                    "opensees_only_members": sorted(set(opensees_members) - set(numpy_members)),
                },
            )
        )
        return ParityCaseEvidence(
            case_id=case_id,
            status="FAILED",
            contract_hash=contract_hash,
            expected_screening_status=expected_screening_status,
            errors=errors,
            tag_mapping={
                "nodes": opensees_result.node_tags,
                "members": opensees_result.member_tags,
            },
        )

    displacement_samples: list[tuple[str, float, float]] = []
    rotation_samples: list[tuple[str, float, float]] = []
    reaction_force_samples: list[tuple[str, float, float]] = []
    reaction_moment_samples: list[tuple[str, float, float]] = []
    for node_id in sorted(numpy_nodes):
        expected = numpy_nodes[node_id]
        actual = opensees_nodes[node_id]
        displacement_samples.extend(
            [
                (f"{node_id}.ux", expected.ux_mm, actual.ux_mm),
                (f"{node_id}.uy", expected.uy_mm, actual.uy_mm),
            ]
        )
        rotation_samples.append((f"{node_id}.rz", expected.rz_rad, actual.rz_rad))
        reaction_force_samples.extend(
            [
                (
                    f"{node_id}.reaction_fx",
                    expected.reaction_fx_n,
                    actual.reaction_fx_n,
                ),
                (
                    f"{node_id}.reaction_fy",
                    expected.reaction_fy_n,
                    actual.reaction_fy_n,
                ),
            ]
        )
        reaction_moment_samples.append(
            (
                f"{node_id}.reaction_mz",
                expected.reaction_mz_nmm,
                actual.reaction_mz_nmm,
            )
        )
    member_force_samples: list[tuple[str, float, float]] = []
    member_moment_samples: list[tuple[str, float, float]] = []
    stress_samples: list[tuple[str, float, float]] = []
    utilization_samples: list[tuple[str, float, float]] = []
    force_fields = ("start_axial_n", "start_shear_n", "end_axial_n", "end_shear_n")
    moment_fields = ("start_moment_nmm", "end_moment_nmm")
    for member_id in sorted(numpy_members):
        expected_member: FrameMemberResult = numpy_members[member_id]
        actual_member = opensees_members[member_id]
        member_force_samples.extend(
            (
                f"{member_id}.{field}",
                float(getattr(expected_member, field)),
                float(getattr(actual_member, field)),
            )
            for field in force_fields
        )
        member_moment_samples.extend(
            (
                f"{member_id}.{field}",
                float(getattr(expected_member, field)),
                float(getattr(actual_member, field)),
            )
            for field in moment_fields
        )
        stress_samples.append(
            (
                f"{member_id}.max_combined_stress",
                expected_member.max_combined_stress_mpa,
                actual_member.max_combined_stress_mpa,
            )
        )
        utilization_samples.append(
            (
                f"{member_id}.utilization",
                expected_member.utilization,
                actual_member.utilization,
            )
        )
    metrics = [
        _metric_evidence(
            metric="node_displacement",
            unit="mm",
            samples=displacement_samples,
            absolute_tolerance=tolerance.displacement_abs_mm,
            relative_tolerance=tolerance.relative,
        ),
        _metric_evidence(
            metric="node_rotation",
            unit="rad",
            samples=rotation_samples,
            absolute_tolerance=tolerance.rotation_abs_rad,
            relative_tolerance=tolerance.relative,
        ),
        _metric_evidence(
            metric="node_reaction_force",
            unit="N",
            samples=reaction_force_samples,
            absolute_tolerance=tolerance.force_abs_n,
            relative_tolerance=tolerance.relative,
        ),
        _metric_evidence(
            metric="node_reaction_moment",
            unit="N*mm",
            samples=reaction_moment_samples,
            absolute_tolerance=tolerance.moment_abs_nmm,
            relative_tolerance=tolerance.relative,
        ),
        _metric_evidence(
            metric="member_local_axial_shear",
            unit="N",
            samples=member_force_samples,
            absolute_tolerance=tolerance.force_abs_n,
            relative_tolerance=tolerance.relative,
        ),
        _metric_evidence(
            metric="member_local_moment",
            unit="N*mm",
            samples=member_moment_samples,
            absolute_tolerance=tolerance.moment_abs_nmm,
            relative_tolerance=tolerance.relative,
        ),
        _metric_evidence(
            metric="member_combined_stress",
            unit="MPa",
            samples=stress_samples,
            absolute_tolerance=tolerance.stress_abs_mpa,
            relative_tolerance=tolerance.relative,
        ),
        _metric_evidence(
            metric="member_utilization",
            unit="ratio",
            samples=utilization_samples,
            absolute_tolerance=tolerance.utilization_abs,
            relative_tolerance=tolerance.relative,
        ),
    ]
    numpy_screening = _screening_status(
        contract,
        max_displacement_mm=numpy_result.max_displacement_mm,
        max_member_utilization=numpy_result.max_member_utilization,
    )
    opensees_screening = _screening_status(
        contract,
        max_displacement_mm=opensees_result.max_displacement_mm,
        max_member_utilization=opensees_result.max_member_utilization,
    )
    if numpy_screening != expected_screening_status:
        errors.append(
            ParityErrorEvidence(
                code="DG_FRAME_PARITY_EXPECTED_SCREENING_MISMATCH",
                message="NumPy screening status differs from the benchmark expectation.",
                details={
                    "expected": expected_screening_status,
                    "actual": numpy_screening,
                },
            )
        )
    if opensees_screening != numpy_screening:
        errors.append(
            ParityErrorEvidence(
                code="DG_FRAME_PARITY_SCREENING_MISMATCH",
                message="OpenSees and NumPy screening statuses differ.",
                details={"numpy": numpy_screening, "opensees": opensees_screening},
            )
        )
    numpy_force_residual, numpy_moment_residual = _equilibrium_from_nodes(
        contract, numpy_result.node_results
    )
    equilibrium = {
        "numpy_force_residual_n": numpy_force_residual,
        "numpy_moment_residual_nmm": numpy_moment_residual,
        "opensees_force_residual_n": opensees_result.equilibrium_force_residual_n,
        "opensees_moment_residual_nmm": opensees_result.equilibrium_moment_residual_nmm,
    }
    equilibrium_passed = (
        numpy_force_residual <= tolerance.force_abs_n
        and opensees_result.equilibrium_force_residual_n <= tolerance.force_abs_n
        and numpy_moment_residual <= tolerance.moment_abs_nmm
        and opensees_result.equilibrium_moment_residual_nmm <= tolerance.moment_abs_nmm
    )
    if not equilibrium_passed:
        errors.append(
            ParityErrorEvidence(
                code="DG_FRAME_PARITY_EQUILIBRIUM_FAILED",
                message="At least one solver exceeds the global equilibrium tolerance.",
                details=equilibrium,
            )
        )
    passed = all(metric.passed for metric in metrics) and not errors
    if not all(metric.passed for metric in metrics):
        errors.append(
            ParityErrorEvidence(
                code="DG_FRAME_PARITY_TOLERANCE_EXCEEDED",
                message="One or more solver result categories exceed parity tolerance.",
                details={
                    "failed_metrics": [metric.metric for metric in metrics if not metric.passed]
                },
            )
        )
    return ParityCaseEvidence(
        case_id=case_id,
        status="PASSED" if passed else "FAILED",
        contract_hash=contract_hash,
        expected_screening_status=expected_screening_status,
        numpy_screening_status=numpy_screening,
        opensees_screening_status=opensees_screening,
        metrics=metrics,
        equilibrium=equilibrium,
        tag_mapping={"nodes": opensees_result.node_tags, "members": opensees_result.member_tags},
        errors=errors,
    )


def _cantilever_contract() -> StructuralFrameContract:
    return StructuralFrameContract.model_validate(
        {
            "design_kind": "structural_frame",
            "nodes": [
                {"id": "fixed", "point": [0, 0]},
                {"id": "tip", "point": [3000, 0]},
            ],
            "members": [
                {
                    "id": "cantilever",
                    "start_node_id": "fixed",
                    "end_node_id": "tip",
                    "area_mm2": 2000,
                    "inertia_mm4": 8_000_000,
                    "elastic_modulus_mpa": 200_000,
                    "section_depth_mm": 200,
                }
            ],
            "loads": [{"id": "tip-load", "node_id": "tip", "fy_n": -1000}],
            "supports": [
                {
                    "id": "fixed-support",
                    "node_id": "fixed",
                    "ux": True,
                    "uy": True,
                    "rz": True,
                }
            ],
            "limits": {"max_displacement_mm": 10, "allowable_stress_mpa": 250},
            "metadata": {"project_name": "OpenSees parity cantilever"},
        }
    )


def _portal_contract() -> StructuralFrameContract:
    common = {
        "area_mm2": 4200,
        "inertia_mm4": 85_000_000,
        "elastic_modulus_mpa": 200_000,
        "section_depth_mm": 320,
    }
    return StructuralFrameContract.model_validate(
        {
            "design_kind": "structural_frame",
            "nodes": [
                {"id": "base-left", "point": [0, 0]},
                {"id": "base-right", "point": [6000, 0]},
                {"id": "eave-left", "point": [0, 4000]},
                {"id": "eave-right", "point": [6000, 4000]},
            ],
            "members": [
                {
                    "id": "column-left",
                    "start_node_id": "base-left",
                    "end_node_id": "eave-left",
                    **common,
                },
                {
                    "id": "column-right",
                    "start_node_id": "base-right",
                    "end_node_id": "eave-right",
                    **common,
                },
                {
                    "id": "beam",
                    "start_node_id": "eave-left",
                    "end_node_id": "eave-right",
                    **common,
                },
            ],
            "loads": [
                {"id": "lateral", "node_id": "eave-left", "fx_n": 15_000},
                {
                    "id": "gravity-moment",
                    "node_id": "eave-right",
                    "fy_n": -40_000,
                    "mz_nmm": 1_250_000,
                },
            ],
            "supports": [
                {
                    "id": "support-left",
                    "node_id": "base-left",
                    "ux": True,
                    "uy": True,
                    "rz": True,
                },
                {
                    "id": "support-right",
                    "node_id": "base-right",
                    "ux": True,
                    "uy": True,
                    "rz": True,
                },
            ],
            "limits": {"max_displacement_mm": 20, "allowable_stress_mpa": 250},
            "metadata": {"project_name": "OpenSees parity portal"},
        }
    )


def _failure_fixture_contract() -> StructuralFrameContract:
    repository_fixture = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "examples"
        / "frame_pipe_rack_failure.json"
    )
    if repository_fixture.is_file():
        return StructuralFrameContract.model_validate_json(
            repository_fixture.read_text(encoding="utf-8")
        )
    base = generate_pipe_rack_contract(bays=2, seed=7302)
    data = base.model_dump(mode="python", exclude={"contract_hash"})
    data["limits"] = {"max_displacement_mm": 0.01, "allowable_stress_mpa": 0.01}
    data["metadata"] = {
        "project_name": "Embedded failure fixture fallback",
        "revision": "FAIL-FALLBACK",
        "notes": "Used only when the source fixture is not packaged.",
    }
    return StructuralFrameContract.model_validate(data)


def build_default_parity_cases() -> list[ParityBenchmarkCase]:
    return [
        ParityBenchmarkCase(
            case_id="cantilever",
            contract=_cantilever_contract(),
            expected_screening_status="PASS",
        ),
        ParityBenchmarkCase(
            case_id="portal",
            contract=_portal_contract(),
            expected_screening_status="PASS",
        ),
        *[
            ParityBenchmarkCase(
                case_id=f"pipe-rack-{bays}-bay",
                contract=generate_pipe_rack_contract(bays=bays, seed=8100 + bays),
                expected_screening_status="PASS",
            )
            for bays in (2, 3, 4)
        ],
        ParityBenchmarkCase(
            case_id="failure-fixture",
            contract=_failure_fixture_contract(),
            expected_screening_status="FAIL",
        ),
    ]


def _suite_hash(cases: Sequence[ParityBenchmarkCase]) -> str:
    values = []
    for case in cases:
        validation = validate_frame_contract(case.contract)
        values.append(
            {
                "case_id": case.case_id,
                "contract_hash": validation.contract_hash,
                "expected_screening_status": case.expected_screening_status,
            }
        )
    payload = json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _platform_evidence() -> dict[str, str]:
    return {
        "python": platform_module.python_version(),
        "python_implementation": platform_module.python_implementation(),
        "executable": Path(sys.executable).name,
        "system": platform_module.system(),
        "release": platform_module.release(),
        "machine": platform_module.machine(),
        "platform": platform_module.platform(),
    }


def run_opensees_parity_benchmark(
    cases: Sequence[ParityBenchmarkCase] | None = None,
    *,
    tolerances: ParityTolerances | None = None,
) -> OpenSeesParityReport:
    selected = list(cases or build_default_parity_cases())
    if not selected:
        raise ValueError("at least one OpenSees parity case is required")
    tolerance = tolerances or ParityTolerances()
    availability = probe_opensees()
    suite_hash = _suite_hash(selected)
    versions = {
        "datumguard": _distribution_version("datumguard"),
        "numpy": _distribution_version("numpy"),
        "openseespy": availability.package_version,
        "openseespywin": _distribution_version("openseespywin"),
        "opensees_engine": availability.engine_version,
        "numpy_solver": NUMPY_SOLVER_ID,
        "opensees_adapter": OPENSEES_SOLVER_ID,
    }
    if not availability.available:
        skipped = []
        for case in selected:
            contract_hash = validate_frame_contract(case.contract).contract_hash
            skipped.append(
                ParityCaseEvidence(
                    case_id=case.case_id,
                    status="SKIPPED",
                    contract_hash=contract_hash,
                    expected_screening_status=case.expected_screening_status,
                    errors=[
                        ParityErrorEvidence(
                            code="DG_FRAME_OPENSEES_UNAVAILABLE",
                            message="OpenSeesPy is unavailable; no parity claim was made.",
                            details={"reason": availability.reason},
                        )
                    ],
                )
            )
        return OpenSeesParityReport(
            status="UNAVAILABLE",
            contract_hash=suite_hash,
            versions=versions,
            platform=_platform_evidence(),
            tolerances=tolerance,
            availability=availability,
            cases=skipped,
            summary={
                "case_count": len(skipped),
                "passed_count": 0,
                "failed_count": 0,
                "skipped_count": len(skipped),
                "fail_closed": True,
            },
        )

    evidence: list[ParityCaseEvidence] = []
    for case in selected:
        validation = validate_frame_contract(case.contract)
        contract_hash = validation.contract_hash
        try:
            numpy_result = solve_frame(case.contract)
            opensees_result = solve_frame_opensees(case.contract)
            result = compare_frame_analyses(
                case.case_id,
                contract_hash,
                case.contract,
                numpy_result,
                opensees_result,
                expected_screening_status=case.expected_screening_status,
                tolerances=tolerance,
            )
        except (FrameSolverError, OpenSeesParityError) as exc:
            code = getattr(exc, "code", "DG_FRAME_PARITY_SOLVER_ERROR")
            details = getattr(exc, "details", {})
            result = ParityCaseEvidence(
                case_id=case.case_id,
                status="FAILED",
                contract_hash=contract_hash,
                expected_screening_status=case.expected_screening_status,
                errors=[
                    ParityErrorEvidence(
                        code=code,
                        message=str(exc),
                        details=cast(dict[str, Any], details),
                    )
                ],
            )
        evidence.append(result)
    passed_count = sum(item.status == "PASSED" for item in evidence)
    failed_count = sum(item.status == "FAILED" for item in evidence)
    skipped_count = sum(item.status == "SKIPPED" for item in evidence)
    status: Literal["PASSED", "FAILED", "UNAVAILABLE"] = (
        "PASSED" if passed_count == len(evidence) else "FAILED"
    )
    return OpenSeesParityReport(
        status=status,
        contract_hash=suite_hash,
        versions=versions,
        platform=_platform_evidence(),
        tolerances=tolerance,
        availability=availability,
        cases=evidence,
        summary={
            "case_count": len(evidence),
            "passed_count": passed_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "fail_closed": True,
        },
    )


def load_packaged_parity_report() -> OpenSeesParityReport | None:
    """Load the latest audited static report shipped with the package, if present."""

    try:
        report_file = resources.files("datumguard").joinpath("data/frame_opensees_parity.json")
        return OpenSeesParityReport.model_validate_json(report_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError, ValueError):
        return None


__all__ = [
    "OpenSeesAvailability",
    "OpenSeesFrameAnalysis",
    "OpenSeesMemberResult",
    "OpenSeesNodeResult",
    "OpenSeesParityError",
    "OpenSeesParityReport",
    "ParityBenchmarkCase",
    "ParityCaseEvidence",
    "ParityErrorEvidence",
    "ParityMetricEvidence",
    "ParityTolerances",
    "build_default_parity_cases",
    "compare_frame_analyses",
    "load_packaged_parity_report",
    "probe_opensees",
    "run_opensees_parity_benchmark",
    "solve_frame_opensees",
]
