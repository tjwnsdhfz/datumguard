from __future__ import annotations

from collections.abc import Callable

import pytest

import datumguard.frame_opensees as frame_opensees
from datumguard.frame_opensees import (
    OpenSeesFrameAnalysis,
    build_default_parity_cases,
    compare_frame_analyses,
    load_packaged_parity_report,
    probe_opensees,
    run_opensees_parity_benchmark,
    solve_frame_opensees,
)
from datumguard.frame_service import validate_frame_contract
from datumguard.frame_solver import solve_frame

AVAILABILITY = probe_opensees()
requires_opensees = pytest.mark.skipif(
    not AVAILABILITY.available,
    reason=f"genuine OpenSeesPy unavailable: {AVAILABILITY.reason}",
)


def _case(case_id: str) -> frame_opensees.ParityBenchmarkCase:
    return next(item for item in build_default_parity_cases() if item.case_id == case_id)


def test_unavailable_is_structured_skipped_and_never_fake_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable() -> None:
        raise ImportError("deliberate missing OpenSees test")

    monkeypatch.setattr(frame_opensees, "_load_opensees", unavailable)
    report = run_opensees_parity_benchmark([_case("cantilever")])
    assert report.status == "UNAVAILABLE"
    assert report.availability.status == "UNAVAILABLE"
    assert report.summary == {
        "case_count": 1,
        "passed_count": 0,
        "failed_count": 0,
        "skipped_count": 1,
        "fail_closed": True,
    }
    assert report.cases[0].status == "SKIPPED"
    assert report.cases[0].errors[0].code == "DG_FRAME_OPENSEES_UNAVAILABLE"


@requires_opensees
def test_genuine_opensees_cantilever_maps_displacements_reactions_and_local_forces() -> None:
    case = _case("cantilever")
    numpy_result = solve_frame(case.contract)
    opensees_result = solve_frame_opensees(case.contract)
    contract_hash = validate_frame_contract(case.contract).contract_hash
    evidence = compare_frame_analyses(
        case.case_id,
        contract_hash,
        case.contract,
        numpy_result,
        opensees_result,
        expected_screening_status="PASS",
    )
    assert opensees_result.engine_version == AVAILABILITY.engine_version
    assert opensees_result.analyze_return_code == 0
    assert evidence.status == "PASSED"
    assert evidence.errors == []
    assert all(metric.passed for metric in evidence.metrics)
    member = opensees_result.member_results[0]
    assert member.start_shear_n == pytest.approx(1000.0)
    assert member.end_shear_n == pytest.approx(-1000.0)
    assert member.start_moment_nmm == pytest.approx(3_000_000.0)
    assert member.end_moment_nmm == pytest.approx(0.0, abs=1.0e-6)
    assert "[N_i,V_i,M_i,N_j,V_j,M_j]" in opensees_result.local_force_convention


@requires_opensees
def test_opensees_tags_are_deterministic_across_repeated_runs() -> None:
    contract = _case("portal").contract
    first = solve_frame_opensees(contract)
    second = solve_frame_opensees(contract)
    assert first.node_tags == second.node_tags
    assert first.member_tags == second.member_tags
    assert list(first.node_tags) == sorted(first.node_tags)
    assert list(first.member_tags) == sorted(first.member_tags)


@requires_opensees
def test_deliberate_displacement_mismatch_fails_closed() -> None:
    case = _case("cantilever")
    numpy_result = solve_frame(case.contract)
    genuine = solve_frame_opensees(case.contract)
    perturbed_nodes = []
    for node in genuine.node_results:
        if node.node_id == "tip":
            perturbed_nodes.append(node.model_copy(update={"uy_mm": node.uy_mm + 0.01}))
        else:
            perturbed_nodes.append(node)
    mismatched = genuine.model_copy(update={"node_results": perturbed_nodes})
    evidence = compare_frame_analyses(
        case.case_id,
        validate_frame_contract(case.contract).contract_hash,
        case.contract,
        numpy_result,
        mismatched,
        expected_screening_status="PASS",
    )
    assert evidence.status == "FAILED"
    assert "node_displacement" in {
        metric.metric for metric in evidence.metrics if not metric.passed
    }
    assert "DG_FRAME_PARITY_TOLERANCE_EXCEEDED" in {error.code for error in evidence.errors}


@requires_opensees
def test_default_suite_runs_all_required_cases_and_failure_fixture_is_parity_pass() -> None:
    report = run_opensees_parity_benchmark()
    assert report.status == "PASSED"
    assert report.summary["case_count"] == 6
    assert report.summary["passed_count"] == 6
    assert {item.case_id for item in report.cases} == {
        "cantilever",
        "portal",
        "pipe-rack-2-bay",
        "pipe-rack-3-bay",
        "pipe-rack-4-bay",
        "failure-fixture",
    }
    failure = next(item for item in report.cases if item.case_id == "failure-fixture")
    assert failure.status == "PASSED"
    assert failure.expected_screening_status == "FAIL"
    assert failure.numpy_screening_status == "FAIL"
    assert failure.opensees_screening_status == "FAIL"
    assert all(item.contract_hash.startswith("sha256:") for item in report.cases)
    assert report.contract_hash.startswith("sha256:")


@requires_opensees
def test_solver_exception_is_a_failed_case(monkeypatch: pytest.MonkeyPatch) -> None:
    original: Callable[..., OpenSeesFrameAnalysis] = frame_opensees.solve_frame_opensees

    def fail_solver(*args: object, **kwargs: object) -> OpenSeesFrameAnalysis:
        del args, kwargs
        raise frame_opensees.OpenSeesParityError(
            "DG_FRAME_OPENSEES_TEST_FAILURE", "deliberate solver failure"
        )

    monkeypatch.setattr(frame_opensees, "solve_frame_opensees", fail_solver)
    report = run_opensees_parity_benchmark([_case("portal")])
    monkeypatch.setattr(frame_opensees, "solve_frame_opensees", original)
    assert report.status == "FAILED"
    assert report.cases[0].status == "FAILED"
    assert report.cases[0].errors[0].code == "DG_FRAME_OPENSEES_TEST_FAILURE"


def test_packaged_report_is_schema_valid_when_present() -> None:
    report = load_packaged_parity_report()
    if report is None:
        pytest.skip("packaged benchmark report has not been generated")
    assert report.schema_version == "frame-opensees-parity-v1"
    assert report.summary["fail_closed"] is True
