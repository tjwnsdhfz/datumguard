from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import pytest

from datumguard.frame_rhino_adapter import (
    RhinoFrameExchange,
    adapt_rhino_frame_exchange,
)
from datumguard.models import ContractStatus

FIXTURE = Path("fixtures/examples/frame_rhino_exchange.json")


@pytest.fixture
def exchange_payload() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def violation_codes(result: Any) -> set[str]:
    return {item.code for item in result.violations}


def test_versioned_exchange_schema_is_strict(exchange_payload: dict[str, Any]) -> None:
    exchange = RhinoFrameExchange.model_validate(exchange_payload)
    assert exchange.schema_version == "1.0.0"
    assert exchange.design_kind == "structural_frame_exchange"
    invalid = copy.deepcopy(exchange_payload)
    invalid["schema_version"] = "2.0.0"
    result = adapt_rhino_frame_exchange(invalid)
    assert result.status is ContractStatus.INFEASIBLE
    assert violation_codes(result) == {"DG_FRAME_RHINO_SCHEMA_INVALID"}


def test_inch_exchange_normalizes_geometry_section_and_moment_to_mm(
    exchange_payload: dict[str, Any],
) -> None:
    exchange_payload["loads"][0]["mz_n_document_unit"] = 2.0
    result = adapt_rhino_frame_exchange(exchange_payload)
    assert result.status is ContractStatus.READY
    assert result.structural_contract is not None
    contract = result.structural_contract
    assert contract.units == "mm"
    assert sorted(node.point for node in contract.nodes) == [
        (0.0, 0.0),
        (0.0, 3048.0),
        (6096.0, 0.0),
        (6096.0, 3048.0),
    ]
    member = next(item for item in contract.members if item.id == "beam-top")
    assert member.area_mm2 == pytest.approx(10.0 * 25.4**2)
    assert member.inertia_mm4 == pytest.approx(300.0 * 25.4**4, abs=0.001)
    assert member.section_depth_mm == pytest.approx(304.8)
    assert contract.loads[0].mz_nmm == pytest.approx(50.8)
    assert contract.limits.max_displacement_mm == pytest.approx(25.4)
    assert result.contract_hash == contract.contract_hash


@pytest.mark.parametrize(
    ("unit", "factor"),
    [("mm", 1.0), ("cm", 10.0), ("m", 1000.0), ("in", 25.4), ("ft", 304.8)],
)
def test_every_supported_rhino_unit_has_an_explicit_mm_scale(
    exchange_payload: dict[str, Any], unit: str, factor: float
) -> None:
    exchange_payload["document"]["units"] = unit
    result = adapt_rhino_frame_exchange(exchange_payload)
    assert result.status is ContractStatus.READY
    assert result.structural_contract is not None
    member = next(item for item in result.structural_contract.members if item.id == "beam-top")
    nodes = {item.id: item for item in result.structural_contract.nodes}
    start = nodes[member.start_node_id].point
    end = nodes[member.end_node_id].point
    assert math.dist(start, end) == pytest.approx(240.0 * factor, abs=0.001)


@pytest.mark.parametrize("unit", ["unset", "unknown", "yards", ""])
def test_unknown_or_unset_units_never_infer(exchange_payload: dict[str, Any], unit: str) -> None:
    exchange_payload["document"]["units"] = unit
    result = adapt_rhino_frame_exchange(exchange_payload)
    expected = ContractStatus.NEEDS_CONFIRMATION if unit else ContractStatus.INFEASIBLE
    assert result.status is expected
    assert result.structural_contract is None
    if unit:
        assert violation_codes(result) == {"DG_FRAME_RHINO_UNIT_CONFIRMATION_REQUIRED"}


def test_nonfinite_section_value_is_rejected_before_normalization(
    exchange_payload: dict[str, Any],
) -> None:
    exchange_payload["sections"][0]["area"] = float("inf")

    result = adapt_rhino_frame_exchange(exchange_payload)

    assert result.status is ContractStatus.INFEASIBLE
    assert result.structural_contract is None
    assert violation_codes(result) == {"DG_FRAME_RHINO_SCHEMA_INVALID"}


@pytest.mark.parametrize("datum", [None, {}])
def test_missing_or_empty_datum_never_defaults_to_world_xy(
    exchange_payload: dict[str, Any], datum: dict[str, Any] | None
) -> None:
    if datum is None:
        del exchange_payload["document"]["datum"]
    else:
        exchange_payload["document"]["datum"] = datum

    result = adapt_rhino_frame_exchange(exchange_payload)

    assert result.status is ContractStatus.INFEASIBLE
    assert result.structural_contract is None
    assert violation_codes(result) == {"DG_FRAME_RHINO_SCHEMA_INVALID"}


def test_in_plane_rotated_orthonormal_datum_is_supported(
    exchange_payload: dict[str, Any],
) -> None:
    angle = math.radians(30.0)
    exchange_payload["document"]["datum"].update(
        {
            "x_axis": [math.cos(angle), math.sin(angle), 0.0],
            "y_axis": [-math.sin(angle), math.cos(angle), 0.0],
            "z_axis": [0.0, 0.0, 1.0],
        }
    )
    result = adapt_rhino_frame_exchange(exchange_payload)
    assert result.status is ContractStatus.READY


def test_tilted_or_nonorthogonal_datum_is_rejected(
    exchange_payload: dict[str, Any],
) -> None:
    tilted = copy.deepcopy(exchange_payload)
    angle = math.radians(5.0)
    tilted["document"]["datum"].update(
        {
            "y_axis": [0.0, math.cos(angle), math.sin(angle)],
            "z_axis": [0.0, -math.sin(angle), math.cos(angle)],
        }
    )
    tilted_result = adapt_rhino_frame_exchange(tilted)
    assert tilted_result.status is ContractStatus.INFEASIBLE
    assert violation_codes(tilted_result) == {"DG_FRAME_RHINO_DATUM_NOT_XY"}

    nonorthogonal = copy.deepcopy(exchange_payload)
    nonorthogonal["document"]["datum"]["y_axis"] = [0.1, 1.0, 0.0]
    nonorthogonal_result = adapt_rhino_frame_exchange(nonorthogonal)
    assert nonorthogonal_result.status is ContractStatus.INFEASIBLE
    assert violation_codes(nonorthogonal_result) == {"DG_FRAME_RHINO_DATUM_NONORTHONORMAL"}


def test_out_of_plane_geometry_above_one_micron_fails_closed(
    exchange_payload: dict[str, Any],
) -> None:
    exchange_payload["members"][0]["end"][2] = 0.001 / 25.4 + 0.000001
    result = adapt_rhino_frame_exchange(exchange_payload)
    assert result.status is ContractStatus.INFEASIBLE
    assert violation_codes(result) == {"DG_FRAME_RHINO_OUT_OF_PLANE"}
    assert result.structural_contract is None


def test_support_or_load_requires_explicit_node_match(
    exchange_payload: dict[str, Any],
) -> None:
    exchange_payload["loads"][0]["point"][0] += 0.01
    exchange_payload["node_merge_tolerance"] = 0.0
    result = adapt_rhino_frame_exchange(exchange_payload)
    assert result.status is ContractStatus.INFEASIBLE
    assert violation_codes(result) == {"DG_FRAME_RHINO_POINT_NOT_ON_NODE"}


def test_member_order_does_not_change_node_ids_or_contract_hash(
    exchange_payload: dict[str, Any],
) -> None:
    first = adapt_rhino_frame_exchange(exchange_payload)
    reordered = copy.deepcopy(exchange_payload)
    reordered["members"].reverse()
    reordered["supports"].reverse()
    second = adapt_rhino_frame_exchange(reordered)
    assert first.status is ContractStatus.READY
    assert second.status is ContractStatus.READY
    assert first.contract_hash == second.contract_hash
    assert first.exchange_hash == second.exchange_hash
    assert first.structural_contract is not None
    assert second.structural_contract is not None
    assert {item.id for item in first.structural_contract.nodes} == {
        item.id for item in second.structural_contract.nodes
    }


def test_distinct_points_that_quantize_together_are_not_silently_merged(
    exchange_payload: dict[str, Any],
) -> None:
    exchange_payload["document"]["units"] = "mm"
    exchange_payload["document"]["datum"]["origin"] = [0.0, 0.0, 0.0]
    exchange_payload["node_merge_tolerance"] = 0.0
    exchange_payload["members"][0]["start"] = [0.0, 0.0, 0.0]
    exchange_payload["members"][0]["end"] = [0.0004, 0.0, 0.0]
    exchange_payload["members"][1]["start"] = [1.0, 0.0, 0.0]
    exchange_payload["members"][1]["end"] = [2.0, 0.0, 0.0]
    exchange_payload["members"][2]["start"] = [2.0, 0.0, 0.0]
    exchange_payload["members"][2]["end"] = [3.0, 0.0, 0.0]
    exchange_payload["supports"] = []
    exchange_payload["loads"] = []
    result = adapt_rhino_frame_exchange(exchange_payload)
    assert result.status is ContractStatus.INFEASIBLE
    assert violation_codes(result) == {"DG_FRAME_RHINO_QUANTIZATION_COLLISION"}
