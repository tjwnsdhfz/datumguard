from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .models import ErrorInfo, Evidence, StrictModel, Violation

ArtifactFormat = Literal["dxf", "step", "ifc"]
AuditStatus = Literal["audited", "needs_confirmation", "failed_verification"]
DxfSupportLevel = Literal["MEASURED", "RENDER_ONLY", "UNSUPPORTED"]


class DxfEntitySupport(StrictModel):
    entity_type: str
    support_level: DxfSupportLevel
    entity_count: int = Field(ge=0)
    reason: str


class DxfCompleteness(StrictModel):
    support_matrix_version: str
    comparison_complete: bool
    render_eligible: bool
    analysis_truncated: bool = False
    modelspace_entity_count: int = Field(ge=0)
    block_definition_count: int = Field(ge=0)
    nested_block_entity_count: int = Field(ge=0)
    estimated_expanded_entity_count: int = Field(ge=0)
    insert_count: int = Field(ge=0)
    max_nesting_depth: int = Field(ge=0)
    cyclic_block_references: bool = False
    xref_names: list[str] = Field(default_factory=list)
    entity_support: list[DxfEntitySupport] = Field(default_factory=list)
    budget_exceeded: list[str] = Field(default_factory=list)
    budgets: dict[str, int] = Field(default_factory=dict)


class AuditIssue(StrictModel):
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    entity_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class ArtifactMetric(StrictModel):
    metric_id: str
    label: str
    value: float | int | str | bool | None
    unit: str | None = None
    source: str = "serialized_artifact"


class PreviewMesh(StrictModel):
    vertices: list[tuple[float, float, float]] = Field(default_factory=list)
    triangles: list[tuple[int, int, int]] = Field(default_factory=list)
    truncated: bool = False
    source_triangle_count: int = 0


class ArtifactAuditResponse(StrictModel):
    status: AuditStatus
    contract_hash: str = "sha256:not-applicable"
    artifact_hash: str | None
    measurements: list[ArtifactMetric] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    format: ArtifactFormat | None = None
    filename: str
    media_type: str
    byte_size: int
    approval_eligible: Literal[False] = False
    original_preserved: Literal[True] = True
    summary: dict[str, Any] = Field(default_factory=dict)
    issues: list[AuditIssue] = Field(default_factory=list)
    preview_svg: str | None = None
    preview_mesh: PreviewMesh | None = None
    dxf_completeness: DxfCompleteness | None = None
    error: ErrorInfo | None = None


class ArtifactComparisonResponse(StrictModel):
    status: AuditStatus
    contract_hash: str = "sha256:not-applicable"
    artifact_hash: str | None
    measurements: list[ArtifactMetric] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    format: ArtifactFormat | None = None
    baseline_hash: str
    candidate_hash: str
    same_artifact: bool
    support_matrix_version: str | None = None
    comparison_complete: bool | None = None
    comparison: dict[str, Any] = Field(default_factory=dict)
    baseline: ArtifactAuditResponse
    candidate: ArtifactAuditResponse
    error: ErrorInfo | None = None
