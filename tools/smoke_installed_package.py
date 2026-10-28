"""Exercise a built wheel from an isolated interpreter outside the source checkout.

Pass an explicit plate contract fixture path. This script deliberately never changes
sys.path: an editable install or an import from the checkout must fail the smoke test.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import sys
import zipfile
from importlib import metadata, resources
from pathlib import Path

from ezdxf.entities.lwpolyline import LWPolyline
from ezdxf.filemanagement import read

import datumguard
from datumguard.frame_research_evidence import (
    load_gnn_benchmark,
    load_opensees_parity_report,
)
from datumguard.mcp_server import mcp
from datumguard.models import DesignContract, RunStatus
from datumguard.service import run_design, verify_only


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def installed_origin() -> tuple[Path, list[str]]:
    checkout = Path(__file__).resolve().parents[1]
    require(sys.flags.isolated == 1, "Run this smoke test with python -I.")
    require(
        not Path.cwd().resolve().is_relative_to(checkout),
        "The smoke test must run outside the source checkout.",
    )
    require(datumguard.__file__ is not None, "datumguard must have a concrete installed origin.")
    origin = Path(str(datumguard.__file__)).resolve()
    require(not origin.is_relative_to(checkout), f"Imported source checkout: {origin}")
    distribution = metadata.distribution("datumguard")
    installed = Path(str(distribution.locate_file("datumguard/__init__.py"))).resolve()
    require(
        origin == installed, f"Imported module is not from the installed distribution: {origin}"
    )
    direct_url = distribution.read_text("direct_url.json")
    if direct_url is not None:
        require(
            not json.loads(direct_url).get("dir_info", {}).get("editable", False),
            "An editable install does not test the wheel.",
        )
    entry_points = {
        entry.name: entry for entry in distribution.entry_points if entry.group == "console_scripts"
    }
    expected = {
        "datumguard-api": "datumguard.api:main",
        "datumguard-mcp": "datumguard.mcp_server:main",
    }
    for name, target in expected.items():
        require(name in entry_points, f"Missing installed entry point: {name}")
        require(entry_points[name].value == target, f"Unexpected entry point target: {name}")
        require(callable(entry_points[name].load()), f"Entry point cannot be loaded: {name}")
    return origin, sorted(expected)


def packaged_data() -> list[str]:
    require(bool(load_opensees_parity_report()), "Packaged OpenSees evidence is empty.")
    require(bool(load_gnn_benchmark()), "Packaged GNN benchmark is empty.")
    names = [
        "frame_opensees_parity.json",
        "frame_gnn_benchmark.json",
        "frame_graphsage_ensemble_v1.json",
    ]
    for name in names:
        payload = json.loads(
            resources.files("datumguard").joinpath("data", name).read_text("utf-8")
        )
        require(isinstance(payload, dict) and bool(payload), f"Invalid packaged JSON: {name}")
    return names


def tamper_outline(dxf_bytes: bytes) -> bytes:
    document = read(io.StringIO(dxf_bytes.decode("utf-8")))
    outlines = [
        entity
        for entity in document.modelspace()
        if isinstance(entity, LWPolyline) and entity.dxf.layer == "OUTLINE"
    ]
    require(len(outlines) == 1, "The smoke fixture must contain one rectangle outline.")
    outline = outlines[0]
    points = list(outline.get_points("xy"))
    max_x = max(float(point[0]) for point in points)
    outline.set_points(
        [(float(x) + (1.0 if float(x) == max_x else 0.0), float(y)) for x, y in points],
        format="xy",
    )
    output = io.StringIO(newline="\n")
    document.write(output)
    return output.getvalue().encode("utf-8")


async def smoke(fixture: Path) -> None:
    origin, entry_points = installed_origin()
    data_files = packaged_data()
    contract = DesignContract.model_validate_json(fixture.read_text(encoding="utf-8"))
    result = run_design(contract, auto_repair=False)
    require(result.status == RunStatus.PASSED, f"Fixture did not pass: {result.violations}")
    require(bool(result.measurements), "A passing run must include actual measurements.")
    require(
        all(item.passed for item in result.measurements), "A passing run has failed measurements."
    )
    require(result.bundle_base64 is not None, "A passing run did not produce an approved bundle.")
    with zipfile.ZipFile(
        io.BytesIO(base64.b64decode(str(result.bundle_base64), validate=True))
    ) as bundle:
        dxf_bytes = bundle.read("drawing.dxf")
        verification = json.loads(bundle.read("verification.json"))
        require(verification["status"] == "passed", "Bundle verification is not approved.")
        require(
            verification["contract_hash"] == result.contract_hash,
            "Bundle verification is for a different contract.",
        )
    tampered = verify_only(contract, tamper_outline(dxf_bytes))
    require(tampered.status == RunStatus.FAILED, "Independent verifier accepted tampered DXF.")
    codes = sorted({violation.code for violation in tampered.violations})
    require(
        "DG_TOLERANCE_EXCEEDED" in codes, "Tampered geometry did not fail dimension verification."
    )
    require(
        tampered.artifact_hash != result.artifact_hash,
        "Tampered serialized DXF must have a different artifact hash.",
    )
    tool_names = {tool.name for tool in await mcp.list_tools()}
    expected_tools = {
        "design_contract_draft",
        "design_contract_validate",
        "drawing_generate",
        "drawing_verify",
        "repair_propose",
        "repair_apply",
        "drawing_compare",
        "export_bundle",
        "rhino_preview",
    }
    require(
        expected_tools <= tool_names, f"Missing MCP tools: {sorted(expected_tools - tool_names)}"
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "installed_origin": str(origin),
                "entry_points": entry_points,
                "packaged_data": data_files,
                "contract_hash": result.contract_hash,
                "measurements": len(result.measurements),
                "tampered_dxf_status": tampered.status.value,
                "tampered_dxf_violation_codes": codes,
                "mcp_tool_count": len(tool_names),
            },
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path, help="Absolute path to a passing plate contract JSON")
    arguments = parser.parse_args()
    require(arguments.fixture.is_absolute(), "The fixture path must be absolute.")
    asyncio.run(smoke(arguments.fixture))


if __name__ == "__main__":
    main()
