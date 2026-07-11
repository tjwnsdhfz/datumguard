from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContractStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_CONFIRMATION = "needs_confirmation"
    UNDER_CONSTRAINED = "under_constrained"
    READY = "ready"
    INFEASIBLE = "infeasible"


class RunStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed_verification"
    REPAIRABLE = "repairable"
    REPAIR_EXHAUSTED = "repair_exhausted"
    CROSS_KERNEL_MISMATCH = "cross_kernel_mismatch"


class ArtifactStatus(StrEnum):
    GENERATED_UNVERIFIED = "generated_unverified"


class Datum(StrictModel):
    id: str = "datum-main"
    origin: tuple[float, float] = (0.0, 0.0)
    x_axis: tuple[float, float] = (1.0, 0.0)
    y_axis: tuple[float, float] = (0.0, 1.0)
    plane: Literal["XY"] = "XY"
    locked: Literal[True] = True

    @model_validator(mode="after")
    def validate_axes(self) -> Datum:
        dot = self.x_axis[0] * self.y_axis[0] + self.x_axis[1] * self.y_axis[1]
        x_len = self.x_axis[0] ** 2 + self.x_axis[1] ** 2
        y_len = self.y_axis[0] ** 2 + self.y_axis[1] ** 2
        if abs(dot) > 1e-9 or abs(x_len - 1.0) > 1e-9 or abs(y_len - 1.0) > 1e-9:
            raise ValueError("datum axes must be orthonormal unit vectors")
        return self


class RectangleOutline(StrictModel):
    id: str = "outline-plate"
    type: Literal["rectangle"] = "rectangle"
    origin: tuple[float, float] = (0.0, 0.0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class PolygonOutline(StrictModel):
    id: str = "outline-plate"
    type: Literal["polygon"] = "polygon"
    points: list[tuple[float, float]] = Field(min_length=3)


Outline = Annotated[RectangleOutline | PolygonOutline, Field(discriminator="type")]


class CircularHole(StrictModel):
    id: str
    type: Literal["circular_hole"] = "circular_hole"
    center: tuple[float, float]
    diameter: float = Field(gt=0)


class Slot(StrictModel):
    id: str
    type: Literal["slot"] = "slot"
    center: tuple[float, float]
    length: float = Field(gt=0)
    width: float = Field(gt=0)
    angle_deg: float = 0.0

    @model_validator(mode="after")
    def validate_length(self) -> Slot:
        if self.length < self.width:
            raise ValueError("slot length must be greater than or equal to width")
        return self


class RectangularCutout(StrictModel):
    id: str
    type: Literal["rectangular_cutout"] = "rectangular_cutout"
    origin: tuple[float, float]
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    corner_radius: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def validate_radius(self) -> RectangularCutout:
        if self.corner_radius * 2 > min(self.width, self.height):
            raise ValueError("corner radius is too large")
        return self


class LinearPattern(StrictModel):
    id: str
    type: Literal["linear_pattern"] = "linear_pattern"
    source_feature_id: str
    count: int = Field(ge=2, le=200)
    direction: tuple[float, float]
    spacing: float = Field(gt=0)

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, value: tuple[float, float]) -> tuple[float, float]:
        length = (value[0] ** 2 + value[1] ** 2) ** 0.5
        if length <= 1e-12:
            raise ValueError("pattern direction must be non-zero")
        return (value[0] / length, value[1] / length)


class CircularPattern(StrictModel):
    id: str
    type: Literal["circular_pattern"] = "circular_pattern"
    source_feature_id: str
    center: tuple[float, float]
    count: int = Field(ge=2, le=200)
    angle_step_deg: float


Feature = Annotated[
    CircularHole | Slot | RectangularCutout | LinearPattern | CircularPattern,
    Field(discriminator="type"),
]


class DimensionSource(StrictModel):
    kind: Literal["form", "intent_text"]
    ref: str


class Dimension(StrictModel):
    id: str
    path: str
    target: float
    tolerance_lower: float = Field(le=0)
    tolerance_upper: float = Field(ge=0)
    locked: bool = True
    source: DimensionSource


class Constraint(StrictModel):
    id: str
    type: Literal[
        "symmetry",
        "alignment",
        "equal_spacing",
        "non_overlap",
        "features_inside_outline",
        "minimum_edge_distance",
        "minimum_ligament",
    ]
    entity_ids: list[str] = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    required: bool = True


class FreeParameter(StrictModel):
    id: str
    path: str
    minimum: float
    maximum: float
    step: float = Field(gt=0)
    unit: Literal["mm", "inch"] = "mm"

    @model_validator(mode="after")
    def validate_range(self) -> FreeParameter:
        if self.minimum > self.maximum:
            raise ValueError("free parameter minimum exceeds maximum")
        return self


class ManufacturingProfile(StrictModel):
    id: str = "profile-custom"
    process: Literal["laser", "cnc", "manual", "custom"] = "custom"
    kerf: float = Field(default=0.0, ge=0)
    tool_diameter: float | None = Field(default=None, gt=0)
    minimum_feature: float = Field(default=1.0, ge=0)
    minimum_ligament: float = Field(default=1.0, ge=0)
    confirmed_by_user: bool = True


class ContractMetadata(StrictModel):
    project_name: str = Field(min_length=1, max_length=120)
    revision: str = Field(default="A", min_length=1, max_length=16)
    notes: str = Field(default="", max_length=1000)


class DesignContract(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    units: Literal["mm", "inch"] = "mm"
    datum: Datum = Field(default_factory=Datum)
    outline: Outline
    features: list[Feature] = Field(default_factory=list, max_length=250)
    dimensions: list[Dimension] = Field(default_factory=list, max_length=250)
    constraints: list[Constraint] = Field(default_factory=list, max_length=250)
    free_parameters: list[FreeParameter] = Field(default_factory=list, max_length=100)
    manufacturing_profile: ManufacturingProfile = Field(default_factory=ManufacturingProfile)
    metadata: ContractMetadata
    contract_hash: str | None = None
    intent_text: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_ids_and_paths(self) -> DesignContract:
        ids = [self.outline.id]
        ids.extend(feature.id for feature in self.features)
        ids.extend(dimension.id for dimension in self.dimensions)
        ids.extend(constraint.id for constraint in self.constraints)
        ids.extend(parameter.id for parameter in self.free_parameters)
        if len(ids) != len(set(ids)):
            raise ValueError("all entity identifiers must be unique")
        feature_ids = {feature.id for feature in self.features}
        for feature in self.features:
            if isinstance(feature, (LinearPattern, CircularPattern)):
                if feature.source_feature_id not in feature_ids:
                    raise ValueError(f"unknown pattern source: {feature.source_feature_id}")
                if feature.source_feature_id == feature.id:
                    raise ValueError("pattern cannot reference itself")
        locked_paths = {d.path for d in self.dimensions if d.locked}
        free_paths = {p.path for p in self.free_parameters}
        if locked_paths & free_paths:
            raise ValueError("a locked dimension cannot also be a free parameter")
        return self


class Evidence(StrictModel):
    type: str
    source: str
    locator: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class Violation(StrictModel):
    code: str
    message: str
    entity_ids: list[str] = Field(default_factory=list)
    constraint_id: str | None = None
    repairable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class Measurement(StrictModel):
    measurement_id: str
    dimension_id: str
    target: float
    actual: float
    deviation: float
    tolerance_lower: float
    tolerance_upper: float
    unit: Literal["mm"] = "mm"
    passed: bool
    evidence: dict[str, Any]


class ErrorInfo(StrictModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str


class RunResponse(StrictModel):
    status: RunStatus
    contract_hash: str
    artifact_hash: str | None = None
    measurements: list[Measurement] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    preview_svg: str
    bundle_base64: str | None = None
    error: ErrorInfo | None = None


class ContractValidationResponse(StrictModel):
    status: ContractStatus
    contract_hash: str
    artifact_hash: None = None
    measurements: list[Measurement] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    normalized_contract: DesignContract | None = None
    error: ErrorInfo | None = None


class GenerationResponse(StrictModel):
    status: ArtifactStatus = ArtifactStatus.GENERATED_UNVERIFIED
    contract_hash: str
    artifact_hash: str
    measurements: list[Measurement] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    preview_svg: str
    dxf_base64: str
    error: ErrorInfo | None = None


class RepairChange(StrictModel):
    path: str
    before: float
    after: float
    reason: str
    constraint_id: str | None = None


class RepairProposal(StrictModel):
    proposal_id: str
    contract_hash: str
    iteration: int = Field(ge=1, le=3)
    status: Literal["proposed", "not_repairable", "exhausted"]
    changes: list[RepairChange] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)
