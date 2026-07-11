from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from .artifact_models import PreviewMesh
from .models import (
    ContractMetadata,
    ErrorInfo,
    Evidence,
    Measurement,
    RunStatus,
    StrictModel,
    Violation,
)


class SolidHole(StrictModel):
    id: str
    center: tuple[float, float]
    diameter: float = Field(gt=0)


class MountingPlateSolid(StrictModel):
    type: Literal["mounting_plate"] = "mounting_plate"
    width: float = Field(gt=0, le=5000)
    depth: float = Field(gt=0, le=5000)
    thickness: float = Field(gt=0, le=1000)
    corner_radius: float = Field(default=0, ge=0)
    holes: list[SolidHole] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_geometry(self) -> MountingPlateSolid:
        if self.corner_radius * 2 >= min(self.width, self.depth):
            raise ValueError("corner_radius must be less than half of the shortest side")
        for hole in self.holes:
            radius = hole.diameter / 2
            if abs(hole.center[0]) + radius >= self.width / 2:
                raise ValueError(f"hole {hole.id} exceeds the plate width")
            if abs(hole.center[1]) + radius >= self.depth / 2:
                raise ValueError(f"hole {hole.id} exceeds the plate depth")
        return self


class AngleBracketSolid(StrictModel):
    type: Literal["angle_bracket"] = "angle_bracket"
    width: float = Field(gt=0, le=5000)
    base_depth: float = Field(gt=0, le=5000)
    base_thickness: float = Field(gt=0, le=1000)
    vertical_height: float = Field(gt=0, le=5000)
    vertical_thickness: float = Field(gt=0, le=1000)
    base_holes: list[SolidHole] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_geometry(self) -> AngleBracketSolid:
        if self.vertical_thickness >= self.base_depth:
            raise ValueError("vertical_thickness must be less than base_depth")
        if self.vertical_height <= self.base_thickness:
            raise ValueError("vertical_height must exceed base_thickness")
        for hole in self.base_holes:
            radius = hole.diameter / 2
            if abs(hole.center[0]) + radius >= self.width / 2:
                raise ValueError(f"hole {hole.id} exceeds the bracket width")
            if abs(hole.center[1]) + radius >= self.base_depth / 2:
                raise ValueError(f"hole {hole.id} exceeds the bracket base")
        return self


class FlangeSolid(StrictModel):
    type: Literal["flange"] = "flange"
    outer_diameter: float = Field(gt=0, le=5000)
    inner_diameter: float = Field(gt=0, le=5000)
    thickness: float = Field(gt=0, le=1000)
    bolt_circle_diameter: float = Field(gt=0, le=5000)
    bolt_hole_diameter: float = Field(gt=0, le=500)
    bolt_hole_count: int = Field(ge=2, le=64)

    @model_validator(mode="after")
    def validate_geometry(self) -> FlangeSolid:
        if self.inner_diameter >= self.outer_diameter:
            raise ValueError("inner_diameter must be smaller than outer_diameter")
        if self.bolt_circle_diameter >= self.outer_diameter:
            raise ValueError("bolt_circle_diameter must be smaller than outer_diameter")
        if self.bolt_circle_diameter <= self.inner_diameter:
            raise ValueError("bolt_circle_diameter must exceed inner_diameter")
        radial_clearance = min(
            self.bolt_circle_diameter - self.inner_diameter,
            self.outer_diameter - self.bolt_circle_diameter,
        )
        if self.bolt_hole_diameter >= radial_clearance:
            raise ValueError("bolt holes overlap the flange bore or outer edge")
        return self


SolidGeometry = Annotated[
    MountingPlateSolid | AngleBracketSolid | FlangeSolid,
    Field(discriminator="type"),
]


class SolidPartContract(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    design_kind: Literal["solid_part"] = "solid_part"
    units: Literal["mm"] = "mm"
    geometry: SolidGeometry
    tolerance_mm: float = Field(default=0.001, gt=0, le=1.0)
    metadata: ContractMetadata
    contract_hash: str | None = None


class SolidRunResponse(StrictModel):
    status: RunStatus
    contract_hash: str
    artifact_hash: str | None = None
    measurements: list[Measurement] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    preview_mesh: PreviewMesh | None = None
    step_base64: str | None = None
    bundle_base64: str | None = None
    error: ErrorInfo | None = None
