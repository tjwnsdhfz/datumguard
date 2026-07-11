from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, field_validator, model_validator

from .models import (
    ArtifactStatus,
    ContractMetadata,
    ContractStatus,
    Datum,
    DimensionSource,
    ErrorInfo,
    Evidence,
    Measurement,
    RunStatus,
    StrictModel,
    Violation,
)


class ArchitecturalGrid(StrictModel):
    id: str
    label: str
    start: tuple[float, float]
    end: tuple[float, float]
    axis: Literal["x", "y", "custom"] = "custom"
    offset: float | None = None
    locked: bool = True

    @model_validator(mode="after")
    def validate_extent(self) -> ArchitecturalGrid:
        if self.start == self.end:
            raise ValueError("grid start and end must differ")
        if self.offset is not None:
            coordinates = (
                (self.start[0], self.end[0]) if self.axis == "x" else (self.start[1], self.end[1])
            )
            if self.axis != "custom" and any(
                abs(coordinate - self.offset) > 1e-6 for coordinate in coordinates
            ):
                raise ValueError("grid offset must match its constant axis coordinate")
        return self


class ArchitecturalWall(StrictModel):
    id: str
    start: tuple[float, float]
    end: tuple[float, float]
    thickness: float = Field(gt=0)
    wall_type: Literal["exterior", "interior", "partition", "custom"] = "custom"
    locked: bool = True

    @model_validator(mode="after")
    def validate_extent(self) -> ArchitecturalWall:
        if self.start == self.end:
            raise ValueError("wall start and end must differ")
        return self


class ArchitecturalOpening(StrictModel):
    id: str
    type: Literal["door", "window", "opening"] = "opening"
    wall_id: str
    offset: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float | None = Field(default=None, gt=0)
    sill_height: float | None = Field(default=None, ge=0)
    swing: Literal["left", "right", "double", "none"] = "none"


class RectangularColumn(StrictModel):
    id: str
    type: Literal["rectangular_column"] = "rectangular_column"
    center: tuple[float, float]
    width: float = Field(gt=0)
    depth: float = Field(gt=0)
    rotation_deg: float = 0.0


class CircularColumn(StrictModel):
    id: str
    type: Literal["circular_column"] = "circular_column"
    center: tuple[float, float]
    diameter: float = Field(gt=0)


ArchitecturalColumn = Annotated[
    RectangularColumn | CircularColumn,
    Field(discriminator="type"),
]


class RoomSeed(StrictModel):
    id: str
    name: str = Field(min_length=1, max_length=120)
    point: tuple[float, float]
    expected_area: float | None = Field(default=None, gt=0)


class ArchitecturalDimension(StrictModel):
    id: str
    path: str
    target: float
    tolerance_lower: float = Field(default=0.0, le=0)
    tolerance_upper: float = Field(default=0.0, ge=0)
    locked: bool = True
    source: DimensionSource | None = None


class ArchitecturalConstraint(StrictModel):
    id: str
    type: Literal[
        "exterior_closed_loop",
        "walls_connected",
        "openings_inside_walls",
        "openings_non_overlap",
        "columns_clear_of_openings",
        "column_grid_alignment",
        "room_seed_enclosed",
        "room_resolved",
        "duplicate_geometry",
        "non_overlap",
        "alignment",
        "orthogonal",
        "minimum_clearance",
    ]
    entity_ids: list[str] = Field(default_factory=list, max_length=250)
    parameters: dict[str, Any] = Field(default_factory=dict)
    required: bool = True


class ArchitecturalFreeParameter(StrictModel):
    id: str
    path: str
    minimum: float
    maximum: float
    step: float = Field(gt=0)
    unit: Literal["mm", "inch"] = "mm"

    @model_validator(mode="after")
    def validate_range(self) -> ArchitecturalFreeParameter:
        if self.minimum > self.maximum:
            raise ValueError("free parameter minimum exceeds maximum")
        return self


class ArchitecturalDrawingProfile(StrictModel):
    id: str = "architecture-profile-default"
    sheet_size: Literal["A4", "A3", "A2", "A1", "A0"] = "A3"
    scale_denominator: float = Field(default=100.0, gt=0)
    include_dimensions: bool = True
    include_room_labels: bool = True
    title_block: bool = True


class ArchitecturalPlanContract(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    design_kind: Literal["architectural_plan"] = "architectural_plan"
    units: Literal["mm", "inch"] = "mm"
    datum: Datum = Field(default_factory=Datum)
    grids: list[ArchitecturalGrid] = Field(default_factory=list, max_length=250)
    walls: list[ArchitecturalWall] = Field(min_length=1, max_length=250)
    openings: list[ArchitecturalOpening] = Field(default_factory=list, max_length=250)
    columns: list[ArchitecturalColumn] = Field(default_factory=list, max_length=250)
    room_seeds: list[RoomSeed] = Field(default_factory=list, max_length=250)
    dimensions: list[ArchitecturalDimension] = Field(default_factory=list, max_length=250)
    constraints: list[ArchitecturalConstraint] = Field(default_factory=list, max_length=250)
    free_parameters: list[ArchitecturalFreeParameter] = Field(default_factory=list, max_length=100)
    drawing_profile: ArchitecturalDrawingProfile = Field(
        default_factory=ArchitecturalDrawingProfile
    )
    metadata: ContractMetadata
    contract_hash: str | None = None
    intent_text: str | None = Field(default=None, max_length=2000)

    @field_validator("grids", "walls", "openings", "columns", "room_seeds")
    @classmethod
    def validate_collection_ids(cls, value: list[Any]) -> list[Any]:
        ids = [item.id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("identifiers must be unique within each collection")
        return value

    @model_validator(mode="after")
    def validate_references_and_locks(self) -> ArchitecturalPlanContract:
        entities = [*self.grids, *self.walls, *self.openings, *self.columns, *self.room_seeds]
        ids = [item.id for item in entities]
        ids.extend(item.id for item in self.dimensions)
        ids.extend(item.id for item in self.constraints)
        ids.extend(item.id for item in self.free_parameters)
        if len(ids) != len(set(ids)):
            raise ValueError("all architectural entity identifiers must be unique")
        wall_ids = {wall.id for wall in self.walls}
        unknown_walls = sorted(
            {opening.wall_id for opening in self.openings if opening.wall_id not in wall_ids}
        )
        if unknown_walls:
            raise ValueError(f"openings reference unknown walls: {unknown_walls}")
        locked_paths = {item.path for item in self.dimensions if item.locked}
        free_paths = {item.path for item in self.free_parameters}
        if locked_paths & free_paths:
            raise ValueError("a locked dimension cannot also be a free parameter")
        return self


class ArchitecturalRunResponse(StrictModel):
    status: RunStatus
    contract_hash: str
    artifact_hash: str | None = None
    measurements: list[Measurement] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    preview_svg: str
    bundle_base64: str | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    error: ErrorInfo | None = None


class ArchitecturalContractValidationResponse(StrictModel):
    status: ContractStatus
    contract_hash: str
    artifact_hash: None = None
    measurements: list[Measurement] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    normalized_contract: ArchitecturalPlanContract | None = None
    error: ErrorInfo | None = None


class ArchitecturalGenerationResponse(StrictModel):
    status: ArtifactStatus = ArtifactStatus.GENERATED_UNVERIFIED
    contract_hash: str
    artifact_hash: str
    measurements: list[Measurement] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    preview_svg: str
    dxf_base64: str
    error: ErrorInfo | None = None


__all__ = [
    "ArchitecturalColumn",
    "ArchitecturalConstraint",
    "ArchitecturalContractValidationResponse",
    "ArchitecturalDimension",
    "ArchitecturalDrawingProfile",
    "ArchitecturalFreeParameter",
    "ArchitecturalGrid",
    "ArchitecturalGenerationResponse",
    "ArchitecturalOpening",
    "ArchitecturalPlanContract",
    "ArchitecturalRunResponse",
    "ArchitecturalWall",
    "CircularColumn",
    "RectangularColumn",
    "RoomSeed",
]
