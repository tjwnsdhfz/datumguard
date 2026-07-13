from __future__ import annotations

import math
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .models import (
    ContractMetadata,
    ContractStatus,
    ErrorInfo,
    Evidence,
    Measurement,
    RepairProposal,
    RunStatus,
    StrictModel,
    Violation,
)


def _finite_pair(value: tuple[float, float]) -> tuple[float, float]:
    if not all(math.isfinite(item) for item in value):
        raise ValueError("frame coordinates must be finite")
    return value


class FrameNode(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    point: tuple[float, float]
    locked: bool = True

    _validate_point = field_validator("point")(_finite_pair)


class FrameMember(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    start_node_id: str = Field(min_length=1, max_length=80)
    end_node_id: str = Field(min_length=1, max_length=80)
    area_mm2: float = Field(gt=0, allow_inf_nan=False)
    inertia_mm4: float = Field(gt=0, allow_inf_nan=False)
    elastic_modulus_mpa: float = Field(default=200_000.0, gt=0, allow_inf_nan=False)
    section_depth_mm: float = Field(gt=0, allow_inf_nan=False)
    allowable_stress_mpa: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    locked: bool = True


class FrameNodalLoad(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    node_id: str = Field(min_length=1, max_length=80)
    fx_n: float = 0.0
    fy_n: float = 0.0
    mz_nmm: float = 0.0

    @field_validator("fx_n", "fy_n", "mz_nmm")
    @classmethod
    def validate_finite_load(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("frame loads must be finite")
        return value


class FrameSupport(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    node_id: str = Field(min_length=1, max_length=80)
    ux: bool = False
    uy: bool = False
    rz: bool = False


class FrameSourceObject(StrictModel):
    """Stable mapping from a normalized frame entity back to its Rhino object."""

    entity_type: Literal["member", "support", "load"]
    entity_id: str = Field(min_length=1, max_length=80)
    source_object_id: UUID


class FrameSourceProvenance(StrictModel):
    source_system: Literal["rhino_grasshopper"] = "rhino_grasshopper"
    source_document_id: str = Field(min_length=1, max_length=200)
    exchange_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    objects: list[FrameSourceObject] = Field(min_length=1, max_length=480)
    complete: bool

    @model_validator(mode="after")
    def validate_source_mapping(self) -> FrameSourceProvenance:
        identities = [(item.entity_type, item.entity_id) for item in self.objects]
        if len(identities) != len(set(identities)):
            raise ValueError("frame provenance entity mappings must be unique")
        source_ids = [item.source_object_id for item in self.objects]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Rhino source object identifiers must be unique")
        return self


class FrameAnalysisLimits(StrictModel):
    max_displacement_mm: float = Field(gt=0, allow_inf_nan=False)
    allowable_stress_mpa: float = Field(gt=0, allow_inf_nan=False)


class FrameFreeParameter(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    path: str = Field(min_length=1, max_length=200)
    minimum: float = Field(gt=0, allow_inf_nan=False)
    maximum: float = Field(gt=0, allow_inf_nan=False)
    step: float = Field(gt=0, allow_inf_nan=False)
    unit: Literal["mm2", "mm4"]

    @model_validator(mode="after")
    def validate_range_and_path(self) -> FrameFreeParameter:
        if self.minimum > self.maximum:
            raise ValueError("free parameter minimum exceeds maximum")
        parts = self.path.split(".")
        if (
            len(parts) != 3
            or parts[0] != "members"
            or parts[2]
            not in {
                "area_mm2",
                "inertia_mm4",
            }
        ):
            raise ValueError(
                "frame free parameters may only target members.<id>.area_mm2 or inertia_mm4"
            )
        expected_unit = "mm2" if parts[2] == "area_mm2" else "mm4"
        if self.unit != expected_unit:
            raise ValueError(f"{parts[2]} requires unit {expected_unit}")
        return self


class StructuralFrameContract(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    design_kind: Literal["structural_frame"] = "structural_frame"
    units: Literal["mm"] = "mm"
    nodes: list[FrameNode] = Field(min_length=2, max_length=120)
    members: list[FrameMember] = Field(min_length=1, max_length=240)
    loads: list[FrameNodalLoad] = Field(default_factory=list, max_length=120)
    supports: list[FrameSupport] = Field(default_factory=list, max_length=120)
    limits: FrameAnalysisLimits
    free_parameters: list[FrameFreeParameter] = Field(default_factory=list, max_length=50)
    metadata: ContractMetadata
    provenance: FrameSourceProvenance | None = None
    contract_hash: str | None = Field(default=None, max_length=80)
    intent_text: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_identifiers(self) -> StructuralFrameContract:
        identifiers = [item.id for item in self.nodes]
        identifiers.extend(item.id for item in self.members)
        identifiers.extend(item.id for item in self.loads)
        identifiers.extend(item.id for item in self.supports)
        identifiers.extend(item.id for item in self.free_parameters)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("all structural frame entity identifiers must be unique")
        if self.provenance is not None:
            expected = {
                *(("member", item.id) for item in self.members),
                *(("support", item.id) for item in self.supports),
                *(("load", item.id) for item in self.loads),
            }
            actual = {(item.entity_type, item.entity_id) for item in self.provenance.objects}
            missing = sorted(expected - actual)
            unexpected = sorted(actual - expected)
            if unexpected or (self.provenance.complete and missing):
                raise ValueError(
                    "frame provenance contains invalid or incomplete entity mappings; "
                    f"missing={missing}, unexpected={unexpected}"
                )
        return self


class FrameNodeResult(StrictModel):
    node_id: str
    ux_mm: float
    uy_mm: float
    rz_rad: float
    translation_mm: float
    reaction_fx_n: float
    reaction_fy_n: float
    reaction_mz_nmm: float


class FrameMemberResult(StrictModel):
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
    strain_energy_nmm: float


class FrameAnalysisResult(StrictModel):
    solver: Literal["datumguard_numpy_2d_frame_v1"] = "datumguard_numpy_2d_frame_v1"
    node_results: list[FrameNodeResult]
    member_results: list[FrameMemberResult]
    max_displacement_mm: float
    max_displacement_node_id: str
    displacement_utilization: float
    max_member_utilization: float
    critical_member_id: str | None = None
    condition_number: float
    equilibrium_residual_n: float


class FrameContractValidationResponse(StrictModel):
    status: ContractStatus
    contract_hash: str
    artifact_hash: None = None
    measurements: list[Measurement] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    normalized_contract: StructuralFrameContract | None = None
    error: ErrorInfo | None = None


class FrameRunResponse(StrictModel):
    status: RunStatus
    contract_hash: str
    artifact_hash: str | None = None
    measurements: list[Measurement] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    preview_svg: str
    repair_proposals: list[RepairProposal] = Field(default_factory=list)
    error: ErrorInfo | None = None


__all__ = [
    "FrameAnalysisLimits",
    "FrameAnalysisResult",
    "FrameContractValidationResponse",
    "FrameFreeParameter",
    "FrameMember",
    "FrameMemberResult",
    "FrameNodalLoad",
    "FrameNode",
    "FrameNodeResult",
    "FrameRunResponse",
    "FrameSourceObject",
    "FrameSourceProvenance",
    "FrameSupport",
    "StructuralFrameContract",
]
