# ruff: noqa: E402
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("torch_geometric")

from torch_geometric.data import Batch, Data

from datumguard.frame_dataset import (
    _contract_to_record,
    generate_frame_dataset,
    generate_pipe_rack_contract,
)
from datumguard.frame_gnn import (
    FrameGNN,
    build_graphsage_artifact,
    fit_normalization,
    predict_members,
    record_to_pyg,
    records_to_batch,
    topology_holdout_partitions,
    train_architecture_ensemble,
    write_json,
)
from datumguard.frame_surrogate import predict_frame_surrogate


def test_records_become_real_pyg_data_and_batch() -> None:
    dataset = generate_frame_dataset(cases=12, seed=901)
    stats = fit_normalization(dataset.records[:8])
    data = record_to_pyg(dataset.records[0], stats)
    batch = records_to_batch(dataset.records[:3], stats)
    assert isinstance(data, Data)
    assert isinstance(batch, Batch)
    assert data.x.shape[1] == 8
    assert data.edge_attr.shape[1] == 8
    assert data.edge_index.shape[0] == 2
    assert batch.num_graphs == 3


def test_split_has_topology_test_holdout_and_no_identifier_leakage() -> None:
    records = generate_frame_dataset(cases=30, seed=902).records
    split = topology_holdout_partitions(records, split_seed=77)
    assert split.test_groups == ["pipe_rack_4_bay"]
    assert "pipe_rack_4_bay" not in split.train_groups
    partitions = (split.train, split.validation, split.test)
    for i, left in enumerate(partitions):
        for right in partitions[i + 1 :]:
            assert not ({record.case_id for record in left} & {record.case_id for record in right})
            assert not (
                {record.contract_hash for record in left}
                & {record.contract_hash for record in right}
            )


def test_graphsage_and_gat_forward_return_two_log_targets() -> None:
    records = generate_frame_dataset(cases=9, seed=903).records
    stats = fit_normalization(records)
    batch = records_to_batch(records[:2], stats)
    for architecture in ("graphsage", "gat"):
        model = FrameGNN(architecture, hidden_channels=8)
        output = model(batch)
        assert output.shape == (2, 2)
        assert torch.isfinite(output).all()


def test_exported_numpy_graphsage_matches_pyg_ensemble(tmp_path: Path) -> None:
    records = generate_frame_dataset(cases=30, seed=904).records
    partitions = topology_holdout_partitions(records, split_seed=88)
    members, stats, report = train_architecture_ensemble(
        "graphsage",
        partitions,
        seeds=[3, 5],
        epochs=10,
        hidden_channels=8,
    )
    contract = generate_pipe_rack_contract(bays=2, seed=12345)
    record = _contract_to_record(
        contract,
        case_id="parity-case",
        topology_group="pipe_rack_2_bay",
    )
    expected = np.mean(predict_members(members, [record], stats), axis=0)[0]
    artifact = build_graphsage_artifact(
        members,
        stats,
        report["uncertainty_calibration"],
        partitions.train,
    )
    path = tmp_path / "portable.json"
    write_json(path, artifact)
    actual = predict_frame_surrogate(contract, model_path=path)
    assert actual.max_displacement_mm == pytest.approx(expected[0], rel=2e-5, abs=2e-5)
    assert actual.max_utilization == pytest.approx(expected[1], rel=2e-5, abs=2e-5)
