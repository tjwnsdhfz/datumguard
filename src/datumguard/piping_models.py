from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

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


class PipingNode(StrictModel):
    id: str
    point: tuple[float, float]
    node_type: Literal["endpoint", "junction", "equipment_connection"] = "junction"
    locked: bool = True


class PipeSegment(StrictModel):
    id: str
    start_node_id: str
    end_node_id: str
    nominal_diameter: float = Field(gt=0)
    service_code: str = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_endpoints(self) -> PipeSegment:
        if self.start_node_id == self.end_node_id:
            raise ValueError("pipe segment endpoints must differ")
        return self


class Valve(StrictModel):
    id: str
    type: Literal["valve"] = "valve"
    segment_id: str
    offset: float = Field(ge=0)
    tag: str = Field(default="", max_length=80)
    valve_type: Literal["isolation", "check", "control"] = "isolation"


class Reducer(StrictModel):
    id: str
    type: Literal["reducer"] = "reducer"
    segment_id: str
    offset: float = Field(ge=0)
    tag: str = Field(default="", max_length=80)
    inlet_diameter: float = Field(gt=0)
    outlet_diameter: float = Field(gt=0)


class Instrument(StrictModel):
    id: str
    type: Literal["instrument"] = "instrument"
    segment_id: str
    offset: float = Field(ge=0)
    tag: str = Field(min_length=1, max_length=80)
    instrument_type: str = Field(default="sensor", min_length=1, max_length=80)


InlineComponent = Annotated[Valve | Reducer | Instrument, Field(discriminator="type")]


class PipeSupport(StrictModel):
    id: str
    type: Literal["hanger", "shoe", "guide", "anchor"] = "shoe"
    segment_id: str
    offset: float = Field(ge=0)


class RectangularEquipmentZone(StrictModel):
    id: str
    type: Literal["rectangle"] = "rectangle"
    zone_kind: Literal["equipment", "keepout"] = "equipment"
    origin: tuple[float, float]
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    minimum_clearance: float = Field(default=0.0, ge=0)


class CircularEquipmentZone(StrictModel):
    id: str
    type: Literal["circle"] = "circle"
    zone_kind: Literal["equipment", "keepout"] = "keepout"
    center: tuple[float, float]
    diameter: float = Field(gt=0)
    minimum_clearance: float = Field(default=0.0, ge=0)


EquipmentZone = Annotated[
    RectangularEquipmentZone | CircularEquipmentZone,
    Field(discriminator="type"),
]


class PipingDimension(StrictModel):
    id: str
    path: str
    target: float
    tolerance_lower: float = Field(default=0.0, le=0)
    tolerance_upper: float = Field(default=0.0, ge=0)
    locked: bool = True
    source: DimensionSource | None = None


class PipingConstraint(StrictModel):
    id: str
    type: Literal[
        "route_connected",
        "orthogonal",
        "endpoint_alignment",
        "inline_component_position",
        "maximum_support_spacing",
        "minimum_obstacle_clearance",
        "duplicate_geometry",
    ]
    entity_ids: list[str] = Field(default_factory=list, max_length=250)
    parameters: dict[str, Any] = Field(default_factory=dict)
    required: bool = True


class PipingFreeParameter(StrictModel):
    id: str
    path: str
    minimum: float
    maximum: float
    step: float = Field(gt=0)
    unit: Literal["mm", "inch"] = "mm"

    @model_validator(mode="after")
    def validate_range(self) -> PipingFreeParameter:
        if self.minimum > self.maximum:
            raise ValueError("free parameter minimum exceeds maximum")
        return self


class PipingDrawingProfile(StrictModel):
    id: str = "piping-profile-default"
    sheet_size: Literal["A4", "A3", "A2", "A1", "A0"] = "A3"
    scale_denominator: float = Field(default=50.0, gt=0)
    include_dimensions: bool = True
    include_node_labels: bool = True
    title_block: bool = True


class PipingPlanContract(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    design_kind: Literal["piping_plan"] = "piping_plan"
    units: Literal["mm", "inch"] = "mm"
    datum: Datum = Field(default_factory=Datum)
    nodes: list[PipingNode] = Field(min_length=2, max_length=250)
    segments: list[PipeSegment] = Field(min_length=1, max_length=250)
    components: list[InlineComponent] = Field(default_factory=list, max_length=250)
    supports: list[PipeSupport] = Field(default_factory=list, max_length=500)
    equipment_zones: list[EquipmentZone] = Field(default_factory=list, max_length=250)
    dimensions: list[PipingDimension] = Field(default_factory=list, max_length=250)
    constraints: list[PipingConstraint] = Field(default_factory=list, max_length=250)
    free_parameters: list[PipingFreeParameter] = Field(default_factory=list, max_length=100)
    drawing_profile: PipingDrawingProfile = Field(default_factory=PipingDrawingProfile)
    metadata: ContractMetadata
    contract_hash: str | None = None
    intent_text: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_identifiers_and_references(self) -> PipingPlanContract:
        entities = [
            *self.nodes,
            *self.segments,
            *self.components,
            *self.supports,
            *self.equipment_zones,
            *self.dimensions,
            *self.constraints,
            *self.free_parameters,
        ]
        ids = [item.id for item in entities]
        if len(ids) != len(set(ids)):
            raise ValueError("all piping entity identifiers must be unique")

        node_ids = {node.id for node in self.nodes}
        missing_nodes = sorted(
            {
                node_id
                for segment in self.segments
                for node_id in (segment.start_node_id, segment.end_node_id)
                if node_id not in node_ids
            }
        )
        if missing_nodes:
            raise ValueError(f"segments reference unknown nodes: {missing_nodes}")

        segment_ids = {segment.id for segment in self.segments}
        missing_segments = sorted(
            {
                item.segment_id
                for item in [*self.components, *self.supports]
                if item.segment_id not in segment_ids
            }
        )
        if missing_segments:
            raise ValueError(f"items reference unknown segments: {missing_segments}")

        locked_paths = {item.path for item in self.dimensions if item.locked}
        free_paths = {item.path for item in self.free_parameters}
        if locked_paths & free_paths:
            raise ValueError("a locked dimension cannot also be a free parameter")
        return self


class PipingRunResponse(StrictModel):
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


class PipingContractValidationResponse(StrictModel):
    status: ContractStatus
    contract_hash: str
    artifact_hash: None = None
    measurements: list[Measurement] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    normalized_contract: PipingPlanContract | None = None
    error: ErrorInfo | None = None


class PipingGenerationResponse(StrictModel):
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
    "CircularEquipmentZone",
    "EquipmentZone",
    "InlineComponent",
    "Instrument",
    "PipeSegment",
    "PipeSupport",
    "PipingConstraint",
    "PipingContractValidationResponse",
    "PipingDimension",
    "PipingDrawingProfile",
    "PipingFreeParameter",
    "PipingGenerationResponse",
    "PipingNode",
    "PipingPlanContract",
    "PipingRunResponse",
    "RectangularEquipmentZone",
    "Reducer",
    "Valve",
]
