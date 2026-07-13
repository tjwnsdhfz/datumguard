from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .models import StrictModel


class OpenBimScope(StrEnum):
    IFC_SCHEMA = "IFC_SCHEMA"
    IDS_REQUIREMENT = "IDS_REQUIREMENT"
    PROJECT_GEOMETRY_RULE = "PROJECT_GEOMETRY_RULE"
    PROJECT_REVISION_RULE = "PROJECT_REVISION_RULE"


class OpenBimRuleStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"
    AMBIGUOUS = "ambiguous"


class OpenBimSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class OpenBimAuthorization(StrictModel):
    asset_key: str = Field(min_length=1, max_length=200)
    field: str = Field(min_length=1, max_length=200)
    before: Any | None = None
    after: Any | None = None
    reason: str = Field(min_length=1, max_length=1000)


class OpenBimProfile(StrictModel):
    profile_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")
    version: str = Field(min_length=1, max_length=40)
    ifc_schema: Literal["IFC4"] = "IFC4"
    applicable_entities: list[str] = Field(min_length=1, max_length=32)
    tool_object_type: str = Field(default="FAB_TOOL", min_length=1, max_length=100)
    obstacle_entities: list[str] = Field(min_length=1, max_length=32)
    required_container_types: list[str] = Field(min_length=1, max_length=16)
    asset_key_path: str = Field(default="DG_Identity.AssetKey", pattern=r"^[^.]+\.[^.]+$")
    locked_fields: list[str] = Field(min_length=1, max_length=32)
    allowed_service_sides: list[str] = Field(min_length=1, max_length=16)
    default_service_depth_m: float = Field(default=0.6, gt=0.0, le=20.0)
    clearance_epsilon_m: float = Field(default=1e-9, ge=0.0, le=0.01)
    authorized_changes: list[OpenBimAuthorization] = Field(default_factory=list, max_length=1000)
    max_products: int = Field(default=500, ge=1, le=10_000)
    max_geometry_vertices: int = Field(default=2_000_000, ge=8, le=20_000_000)
    max_bcf_topics: int = Field(default=1000, ge=1, le=5000)

    @field_validator(
        "applicable_entities",
        "obstacle_entities",
        "required_container_types",
        "locked_fields",
        "allowed_service_sides",
    )
    @classmethod
    def values_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("profile list values must be unique")
        return value


class OpenBimSourceHashes(StrictModel):
    baseline: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    candidate: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    ids: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    profile: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class OpenBimIssue(StrictModel):
    issue_key: str = Field(min_length=1, max_length=128)
    rule_id: str = Field(min_length=1, max_length=80)
    scope: OpenBimScope
    severity: OpenBimSeverity
    message: str = Field(min_length=1, max_length=4000)
    entity_ids: list[str] = Field(default_factory=list, max_length=100)
    entity_pair: list[str] | None = Field(default=None, min_length=2, max_length=2)
    step_ids: list[int] = Field(default_factory=list, max_length=100)
    field: str | None = Field(default=None, max_length=200)
    expected: Any | None = None
    actual: Any | None = None
    location: tuple[float, float, float] | None = None
    source_hashes: OpenBimSourceHashes
    raw: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_entity_pair(self) -> OpenBimIssue:
        if self.entity_pair is not None and self.entity_pair != sorted(self.entity_pair):
            raise ValueError("entity_pair must use deterministic sorted order")
        return self


class OpenBimRuleResult(StrictModel):
    rule_id: str = Field(min_length=1, max_length=80)
    scope: OpenBimScope
    status: OpenBimRuleStatus
    severity: OpenBimSeverity
    evaluated_count: int = Field(ge=0)
    issue_count: int = Field(ge=0)
    summary: str = Field(min_length=1, max_length=1000)


class OpenBimReportArtifact(StrictModel):
    kind: Literal["evidence_json", "html", "bcf", "bcfzip", "manifest"]
    filename: str = Field(min_length=1, max_length=200)
    media_type: str = Field(min_length=1, max_length=200)
    artifact_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)
    content_base64: str = Field(min_length=1)


class OpenBimEvidenceReport(StrictModel):
    schema_version: Literal["openbim-evidence-1.0"] = "openbim-evidence-1.0"
    status: Literal["passed", "failed_verification", "needs_confirmation"]
    profile_id: str
    baseline_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    candidate_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    ids_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    profile_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    research_validation_only: Literal[True] = True
    approval_eligible: Literal[False] = False
    rule_results: list[OpenBimRuleResult]
    issues: list[OpenBimIssue]
    timings_ms: dict[str, float] = Field(default_factory=dict)
    reports: list[OpenBimReportArtifact] = Field(default_factory=list)
    error: dict[str, Any] | None = None


DEFAULT_VIRTUAL_FAB_PROFILE = OpenBimProfile(
    profile_id="virtual-fab-v1",
    version="1.0.0",
    applicable_entities=[
        "IfcBuildingElementProxy",
        "IfcPipeSegment",
        "IfcPipeFitting",
        "IfcValve",
    ],
    tool_object_type="FAB_TOOL",
    obstacle_entities=["IfcPipeSegment", "IfcPipeFitting", "IfcValve"],
    required_container_types=["IfcBuildingStorey", "IfcSpace"],
    asset_key_path="DG_Identity.AssetKey",
    locked_fields=[
        "DG_Identity.AssetTag",
        "DG_VFabUtility.UtilityType",
        "DG_VFabUtility.SystemCode",
        "container",
    ],
    allowed_service_sides=["+X", "-X", "+Y", "-Y"],
    authorized_changes=[
        OpenBimAuthorization(
            asset_key=f"L{layout}-PS-001",
            field="DG_VFabUtility.SystemCode",
            before="SYS-PCW-A",
            after="SYS-PCW-B",
            reason="Synthetic approved utility routing revision for research control.",
        )
        for layout in (1, 2, 3)
    ],
)


REGISTERED_OPENBIM_PROFILES: dict[str, OpenBimProfile] = {
    DEFAULT_VIRTUAL_FAB_PROFILE.profile_id: DEFAULT_VIRTUAL_FAB_PROFILE,
}


__all__ = [
    "DEFAULT_VIRTUAL_FAB_PROFILE",
    "REGISTERED_OPENBIM_PROFILES",
    "OpenBimAuthorization",
    "OpenBimEvidenceReport",
    "OpenBimIssue",
    "OpenBimProfile",
    "OpenBimReportArtifact",
    "OpenBimRuleResult",
    "OpenBimRuleStatus",
    "OpenBimScope",
    "OpenBimSeverity",
    "OpenBimSourceHashes",
]
