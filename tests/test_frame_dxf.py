from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import ezdxf
import pytest
from ezdxf import units
from ezdxf.document import Drawing
from ezdxf.entities.line import Line
from ezdxf.filemanagement import read

from datumguard.frame_dxf import (
    FRAME_DXF_DATUM,
    FRAME_DXF_LAYERS,
    FRAME_XDATA_APP_ID,
    generate_frame_dxf,
    verify_frame_dxf,
)
from datumguard.frame_rhino_adapter import adapt_rhino_frame_exchange
from datumguard.models import RunStatus

FIXTURE = Path("fixtures/examples/frame_rhino_exchange.json")


@pytest.fixture
def contract() -> Any:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    result = adapt_rhino_frame_exchange(payload)
    assert result.structural_contract is not None
    return result.structural_contract


def serialize(document: Drawing) -> bytes:
    stream = io.StringIO(newline="\n")
    document.write(stream, fmt="asc")
    return stream.getvalue().encode("utf-8")


def codes(result: Any) -> set[str]:
    return {item.code for item in result.violations}


def xdata(entity: Any) -> dict[str, str]:
    return {
        str(tag.value).split("=", 1)[0]: str(tag.value).split("=", 1)[1]
        for tag in entity.get_xdata(FRAME_XDATA_APP_ID)
        if tag.code == 1000 and "=" in str(tag.value)
    }


def test_frame_dxf_is_deterministic_r2013_mm_with_exact_layers_and_xdata(
    contract: Any,
) -> None:
    first = generate_frame_dxf(contract)
    second = generate_frame_dxf(contract)
    assert first == second
    document = read(io.StringIO(first.decode("utf-8")))
    assert document.dxfversion == "AC1027"
    assert document.units == units.MM
    assert set(FRAME_DXF_LAYERS) <= {layer.dxf.name for layer in document.layers}
    required = {
        "contract_hash",
        "entity_id",
        "entity_type",
        "revision",
        "datum",
        "unit",
        "design_kind",
    }
    for entity in document.modelspace():
        metadata = xdata(entity)
        assert required <= set(metadata)
        assert metadata["contract_hash"] == contract.contract_hash
        assert metadata["datum"] == FRAME_DXF_DATUM
        assert metadata["unit"] == "mm"
        assert metadata["design_kind"] == "structural_frame"


def test_independent_reopen_verifier_approves_exact_artifact(contract: Any) -> None:
    dxf_bytes = generate_frame_dxf(contract)
    result = verify_frame_dxf(contract, dxf_bytes)
    assert result.status is RunStatus.PASSED
    assert result.summary["approved"] is True
    assert result.summary["max_deviation_mm"] == 0.0
    assert not result.violations
    assert all(item.passed for item in result.measurements)


def test_tampered_member_endpoint_blocks_official_pass(contract: Any) -> None:
    document = read(io.StringIO(generate_frame_dxf(contract).decode("utf-8")))
    member = next(
        entity
        for entity in document.modelspace()
        if isinstance(entity, Line) and entity.dxf.layer == "S-FRAME"
    )
    end = member.dxf.end
    member.dxf.end = (float(end.x) + 0.002, float(end.y), float(end.z))
    result = verify_frame_dxf(contract, serialize(document))
    assert result.status is RunStatus.FAILED
    assert result.summary["approved"] is False
    assert "DG_FRAME_DXF_ENDPOINT_DEVIATION" in codes(result)


def test_out_of_plane_endpoint_is_measured_and_rejected(contract: Any) -> None:
    document = read(io.StringIO(generate_frame_dxf(contract).decode("utf-8")))
    member = next(entity for entity in document.modelspace() if isinstance(entity, Line))
    end = member.dxf.end
    member.dxf.end = (float(end.x), float(end.y), 0.002)
    result = verify_frame_dxf(contract, serialize(document))
    assert result.status is RunStatus.FAILED
    assert "DG_FRAME_DXF_ENDPOINT_DEVIATION" in codes(result)


def test_missing_xdata_is_rejected(contract: Any) -> None:
    document = read(io.StringIO(generate_frame_dxf(contract).decode("utf-8")))
    next(iter(document.modelspace())).discard_xdata(FRAME_XDATA_APP_ID)
    result = verify_frame_dxf(contract, serialize(document))
    assert result.status is RunStatus.FAILED
    assert "DG_FRAME_DXF_XDATA_MISSING" in codes(result)
    assert "DG_FRAME_DXF_ENTITY_MISSING" in codes(result)


def test_wrong_insunits_is_rejected(contract: Any) -> None:
    document = read(io.StringIO(generate_frame_dxf(contract).decode("utf-8")))
    document.units = units.IN
    result = verify_frame_dxf(contract, serialize(document))
    assert result.status is RunStatus.FAILED
    assert "DG_FRAME_DXF_INSUNITS_INVALID" in codes(result)


def test_tampered_datum_xdata_is_rejected(contract: Any) -> None:
    document = read(io.StringIO(generate_frame_dxf(contract).decode("utf-8")))
    entity = next(iter(document.modelspace()))
    tags = entity.get_xdata(FRAME_XDATA_APP_ID)
    entity.set_xdata(
        FRAME_XDATA_APP_ID,
        [
            (tag.code, "datum=origin:1,0,0;x:1,0,0;y:0,1,0;z:0,0,1")
            if tag.code == 1000 and str(tag.value).startswith("datum=")
            else (tag.code, tag.value)
            for tag in tags
        ],
    )
    result = verify_frame_dxf(contract, serialize(document))
    assert result.status is RunStatus.FAILED
    assert "DG_FRAME_DXF_DATUM_MISMATCH" in codes(result)


def test_hash_mismatch_is_rejected(contract: Any) -> None:
    result = verify_frame_dxf(
        contract,
        generate_frame_dxf(contract),
        expected_contract_hash="sha256:" + "0" * 64,
    )
    assert result.status is RunStatus.FAILED
    assert "DG_FRAME_DXF_HASH_MISMATCH" in codes(result)


def test_duplicate_member_geometry_is_rejected(contract: Any) -> None:
    document = read(io.StringIO(generate_frame_dxf(contract).decode("utf-8")))
    original = next(
        entity
        for entity in document.modelspace()
        if isinstance(entity, Line) and entity.dxf.layer == "S-FRAME"
    )
    duplicate = document.modelspace().add_line(
        original.dxf.start, original.dxf.end, dxfattribs={"layer": "S-FRAME"}
    )
    metadata = xdata(original)
    metadata["entity_id"] = "tampered-duplicate"
    duplicate.set_xdata(
        FRAME_XDATA_APP_ID,
        [(1000, f"{key}={value}") for key, value in metadata.items()],
    )
    result = verify_frame_dxf(contract, serialize(document))
    assert result.status is RunStatus.FAILED
    assert "DG_FRAME_DXF_DUPLICATE_GEOMETRY" in codes(result)
    assert "DG_FRAME_DXF_ENTITY_COUNT_MISMATCH" in codes(result)


def test_invalid_serialized_bytes_fail_closed(contract: Any) -> None:
    result = verify_frame_dxf(contract, b"not a DXF")
    assert result.status is RunStatus.FAILED
    assert codes(result) == {"DG_FRAME_DXF_PARSE_FAILED"}
    assert result.summary["approved"] is False


def test_wrong_dxf_version_is_rejected(contract: Any) -> None:
    source = read(io.StringIO(generate_frame_dxf(contract).decode("utf-8")))
    downgraded = ezdxf.new("R2010")
    downgraded.units = units.MM
    for layer in FRAME_DXF_LAYERS:
        if layer not in downgraded.layers:
            downgraded.layers.add(layer)
    # It is enough to prove the independent version gate; missing evidence is also expected.
    result = verify_frame_dxf(contract, serialize(downgraded))
    assert result.status is RunStatus.FAILED
    assert "DG_FRAME_DXF_VERSION_INVALID" in codes(result)
    assert source.dxfversion == "AC1027"
