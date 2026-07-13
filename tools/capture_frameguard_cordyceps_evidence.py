"""Create live Rhino/Grasshopper/DatumGuard round-trip evidence through Cordyceps.

Prerequisites:
* Rhino 8 and Grasshopper are running.
* The active Grasshopper canvas contains the Cordyceps component.
* Cordyceps answers at ``http://127.0.0.1:26929``.

The script deliberately uses Cordyceps tool calls for every Rhino and Grasshopper
mutation. DatumGuard then consumes the Grasshopper output and writes an evidence ZIP
only after exact screening and independent DXF reopen verification pass.
"""

from __future__ import annotations

import base64
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from datumguard.core import compute_artifact_hash  # noqa: E402
from datumguard.frame_roundtrip_service import run_frame_rhino_roundtrip  # noqa: E402
from datumguard.models import RunStatus  # noqa: E402

CORDYCEPS_ROOT = "http://127.0.0.1:26929"
CORDYCEPS_MCP = f"{CORDYCEPS_ROOT}/mcp"
PYTHON3_GUID = "719467e6-7cf5-4848-99b0-c5dd57e5442c"
EVIDENCE = ROOT / "docs" / "evidence"


def _request_json(request: urllib.request.Request, timeout: int = 180) -> dict[str, Any]:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Cordyceps returned a non-object response")
    return payload


def _health() -> dict[str, Any]:
    request = urllib.request.Request(f"{CORDYCEPS_ROOT}/health", method="GET")
    return _request_json(request, timeout=10)


def _call(tool: str, arguments: dict[str, Any], request_id: int) -> dict[str, Any]:
    envelope = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments},
    }
    request = urllib.request.Request(
        CORDYCEPS_MCP,
        data=json.dumps(envelope).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    payload = _request_json(request)
    if "error" in payload:
        raise RuntimeError(f"Cordyceps {tool} failed: {payload['error']}")
    try:
        text = payload["result"]["content"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Cordyceps {tool} response has no text payload") from exc
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {"success": True, "text": text}
    if isinstance(parsed, dict) and parsed.get("success") is False:
        raise RuntimeError(f"Cordyceps {tool} rejected the request: {parsed}")
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _output_value(outputs: dict[str, Any], name: str) -> str:
    records = outputs.get("outputs")
    if not isinstance(records, list):
        raise RuntimeError("Cordyceps output inspection did not return outputs")
    for record in records:
        if not isinstance(record, dict) or record.get("name") != name:
            continue
        preview = record.get("preview")
        if isinstance(preview, list) and preview and isinstance(preview[0], str):
            return preview[0]
    raise RuntimeError(f"Grasshopper output {name} is missing")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _portable_capture_record(payload: dict[str, Any]) -> dict[str, Any]:
    record = dict(payload)
    file_path = record.get("filePath")
    if isinstance(file_path, str):
        record["filePath"] = Path(file_path).name
    return record


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    health_before = _health()
    if health_before.get("status") != "ok":
        raise RuntimeError(f"Cordyceps is not healthy: {health_before}")

    request_id = 40_000

    def call(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        nonlocal request_id
        result = _call(tool, arguments, request_id)
        request_id += 1
        return result

    call("gh_document", {"action": "solver", "enabled": "false"})
    call("gh_document", {"action": "clear"})
    component = call(
        "gh_canvas",
        {
            "action": "add",
            "type": PYTHON3_GUID,
            "nickname": "DatumGuard_Rhino_Exchange",
            "x": 80,
            "y": 200,
        },
    )
    component_id = str(component["id"])
    component_code = (
        ROOT / "integrations" / "grasshopper" / "frameguard_cordyceps_exchange_component.py"
    ).read_text(encoding="utf-8")
    call(
        "gh_script",
        {
            "action": "configure",
            "id": component_id,
            "code": component_code,
            "inputs": "[]",
            "outputs": json.dumps(
                [
                    {"name": "ExchangeJSON", "type": "Text"},
                    {"name": "Status", "type": "Text"},
                ]
            ),
        },
    )
    call("gh_document", {"action": "solver", "enabled": "true"})
    call("gh_document", {"action": "recompute"})

    component_outputs = call("gh_inspect", {"action": "outputs", "id": component_id})
    grasshopper_status = _output_value(component_outputs, "Status")
    if not grasshopper_status.startswith("READY:"):
        raise RuntimeError(f"Grasshopper exchange component did not pass: {grasshopper_status}")
    exchange = json.loads(_output_value(component_outputs, "ExchangeJSON"))
    exchange_path = EVIDENCE / "frameguard-rhino-exchange.json"
    _write_json(exchange_path, exchange)

    result = run_frame_rhino_roundtrip(exchange)
    if (
        result.status is not RunStatus.PASSED
        or result.dxf_base64 is None
        or result.bundle_base64 is None
        or result.manifest is None
        or result.verification is None
    ):
        raise RuntimeError(
            "DatumGuard blocked the live round trip: "
            + json.dumps(
                [item.model_dump(mode="json") for item in result.violations],
                ensure_ascii=False,
            )
        )

    dxf_bytes = base64.b64decode(result.dxf_base64, validate=True)
    bundle_bytes = base64.b64decode(result.bundle_base64, validate=True)
    dxf_path = EVIDENCE / "frameguard-rhino-roundtrip.dxf"
    bundle_path = EVIDENCE / "frameguard-rhino-roundtrip.zip"
    dxf_path.write_bytes(dxf_bytes)
    bundle_path.write_bytes(bundle_bytes)

    source_objects = (
        result.normalized_contract.provenance.objects
        if (
            result.normalized_contract is not None
            and result.normalized_contract.provenance is not None
        )
        else []
    )
    result_record = {
        "schema_version": "1.0.0",
        "status": result.status.value,
        "exchange_hash": result.exchange_hash,
        "contract_hash": result.contract_hash,
        "artifact_hash": result.artifact_hash,
        "manifest_hash": result.manifest_hash,
        "bundle_hash": result.bundle_hash,
        "summary": result.summary,
        "violations": [item.model_dump(mode="json") for item in result.violations],
        "verification": result.verification.model_dump(mode="json"),
        "manifest": result.manifest.model_dump(mode="json"),
        "source_guid_mapping": [item.model_dump(mode="json") for item in source_objects],
        "artifacts": {
            "exchange": exchange_path.name,
            "dxf": {
                "name": dxf_path.name,
                "sha256": compute_artifact_hash(dxf_bytes),
            },
            "bundle": {
                "name": bundle_path.name,
                "sha256": compute_artifact_hash(bundle_bytes),
            },
        },
        "safety_boundary": {
            "screening_only": True,
            "safety_certification": False,
            "construction_approval": False,
        },
    }
    result_path = EVIDENCE / "frameguard-rhino-roundtrip-result.json"
    _write_json(result_path, result_record)

    source_panel = call(
        "gh_canvas",
        {
            "action": "add",
            "type": "Panel",
            "nickname": "01_RHINO_SOURCE",
            "x": -360,
            "y": 20,
            "value": (
                "01 RHINO 8 SOURCE\n"
                f"{len(exchange['members'])} members / {len(exchange['supports'])} supports / "
                f"{len(exchange['loads'])} load\n"
                f"{len(source_objects)} real Rhino GUIDs\nunits={exchange['document']['units']}"
            ),
        },
    )
    gate_panel = call(
        "gh_canvas",
        {
            "action": "add",
            "type": "Panel",
            "nickname": "02_DATUMGUARD_GATES",
            "x": 410,
            "y": 10,
            "value": (
                "02 DATUMGUARD GATES\n"
                "exact source hash: bound\n"
                "contract semantic XRECORD: matched\n"
                "DXF reopened: passed\n"
                f"artifact {str(result.artifact_hash)[:22]}..."
            ),
        },
    )
    boundary_panel = call(
        "gh_canvas",
        {
            "action": "add",
            "type": "Panel",
            "nickname": "03_SAFETY_BOUNDARY",
            "x": 410,
            "y": 260,
            "value": (
                "03 EVIDENCE BUNDLE\n"
                "screening_gate_status=passed\n"
                "artifact_role=geometry_evidence\n"
                "safety_certification=false"
            ),
        },
    )
    group_ids = [
        str(source_panel["id"]),
        component_id,
        str(gate_panel["id"]),
        str(boundary_panel["id"]),
    ]
    call(
        "gh_canvas",
        {
            "action": "group_create",
            "name": "FRAMEGUARD LIVE RHINO ROUND-TRIP",
            "ids": json.dumps(group_ids),
            "color": "#148568",
        },
    )
    call("gh_canvas", {"action": "zoom"})

    gh_path = EVIDENCE / "frameguard-rhino-roundtrip.gh"
    gh_canvas_path = EVIDENCE / "frameguard-rhino-roundtrip-grasshopper.png"
    rhino_view_path = EVIDENCE / "frameguard-rhino-roundtrip-rhino.png"
    for generated_path in (gh_path, gh_canvas_path, rhino_view_path):
        if generated_path.exists():
            generated_path.unlink()
    call("gh_document", {"action": "save", "path": str(gh_path)})
    canvas_capture = call(
        "gh_document",
        {
            "action": "capture_canvas",
            "path": str(gh_canvas_path),
            "fit": "true",
            "padding": 80,
        },
    )
    call("rhino_render", {"action": "display", "mode": "Shaded"})
    call("rhino_render", {"action": "camera", "preset": "top"})
    call("rhino_render", {"action": "zoom"})
    viewport_capture = call(
        "gh_document",
        {
            "action": "capture_viewport",
            "path": str(rhino_view_path),
            "view": "Top",
            "width": 1440,
            "height": 900,
            "transparent": "false",
        },
    )

    gh_status = call("gh_inspect", {"action": "status"})
    health_after = _health()
    session_record = {
        "cordyceps_health_before": health_before,
        "cordyceps_health_after": health_after,
        "rhino_scene_creation": "Grasshopper Python3 component via Cordyceps",
        "grasshopper_component_id": component_id,
        "grasshopper_output_status": grasshopper_status,
        "grasshopper_status": gh_status,
        "canvas_capture": _portable_capture_record(canvas_capture),
        "viewport_capture": _portable_capture_record(viewport_capture),
        "datumguard": {
            "status": result.status.value,
            "exchange_hash": result.exchange_hash,
            "contract_hash": result.contract_hash,
            "artifact_hash": result.artifact_hash,
            "bundle_hash": result.bundle_hash,
            "contract_record_verified": result.verification.summary.get("contract_record_verified"),
            "provenance_verified": result.verification.summary.get("provenance_verified"),
        },
    }
    _write_json(EVIDENCE / "frameguard-cordyceps-session.json", session_record)

    print(
        json.dumps(
            {
                "status": result.status.value,
                "exchange_hash": result.exchange_hash,
                "contract_hash": result.contract_hash,
                "artifact_hash": result.artifact_hash,
                "bundle_hash": result.bundle_hash,
                "source_guid_count": len(source_objects),
                "grasshopper_file": str(gh_path),
                "canvas_capture": str(gh_canvas_path),
                "viewport_capture": str(rhino_view_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
