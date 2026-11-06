from datetime import date
import hashlib
import json

import pandas as pd
import pytest

from atr_breakout.cli import main
from atr_breakout.core.trade import simulate_trades
from atr_breakout.data import partitions
from atr_breakout.data.windows import HoldoutLocked
from atr_breakout.runner import _trade_row
from atr_breakout.study.passrule import StageVerdict, WindowVerdict, write_stage_a, write_stage_b
from synthetic.generate import generate_frame, write_study_fixture

COMMIT = "a" * 40


def _dataset(root, days):
    entries = []
    for declared, observed in days:
        frame = generate_frame().head(2).copy()
        frame["ts_utc"] = pd.date_range(f"{observed} 15:00", periods=2, freq="min", tz="UTC")
        path = root / f"{declared}.parquet"
        frame.to_parquet(path, index=False)
        entries.append({
            "date": declared, "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    manifest = root / "minutes.json"
    manifest.write_text(json.dumps({"market": "US", "synthetic": True, "partitions": entries}))
    return partitions.open_dataset(manifest, "US")


def _pass(directory, dataset, stage_t=2):
    provenance = {**dataset.provenance(COMMIT), "input_sha256": {"2021-01-04": "a" * 64}}
    window = WindowVerdict(2, 2, 1, 1)
    write_stage_a(directory, provenance, StageVerdict(window, window, stage_t))
    write_stage_b(directory, provenance, lambda _: StageVerdict(window, window, 2))


def test_dev_and_oos_never_open_reserved_paths_s8(tmp_path):
    dataset = _dataset(tmp_path, [("2021-01-04", "2021-01-04"), ("2023-01-03", "2023-01-03")])
    (tmp_path / "2023-01-03.parquet").unlink()
    _, hashes = partitions.load_minutes(dataset, commit=COMMIT)
    assert list(hashes) == ["2021-01-04"]


def test_bad_pass_evidence_is_refused_before_partition_io_s8_s10(tmp_path, monkeypatch):
    dataset = _dataset(tmp_path, [("2023-01-03", "2023-01-03")])
    monkeypatch.setattr(partitions, "_read_partition", lambda *args: pytest.fail("unexpected price I/O"))
    run = tmp_path / "run"
    with pytest.raises(HoldoutLocked):
        partitions.load_minutes(dataset, commit=COMMIT, holdout_run=run)
    _pass(run, dataset, stage_t=1)
    with pytest.raises(HoldoutLocked, match="both gross and base"):
        partitions.load_minutes(dataset, commit=COMMIT, holdout_run=run)
    passing = tmp_path / "passing"
    _pass(passing, dataset)
    with pytest.raises(HoldoutLocked, match="does not match"):
        partitions.load_minutes(dataset, commit="b" * 40, holdout_run=passing)
    stage = passing / "stage_a.json"
    stage.write_bytes(stage.read_bytes() + b"\n")
    with pytest.raises(HoldoutLocked, match="checksum"):
        partitions.load_minutes(dataset, commit=COMMIT, holdout_run=passing)


def test_valid_holdout_uses_warmup_and_claims_once_across_run_directories_s8_s10(tmp_path):
    dataset = _dataset(tmp_path, [("2021-01-04", "2021-01-04"), ("2023-01-03", "2023-01-03")])
    first, second = tmp_path / "first", tmp_path / "second"
    _pass(first, dataset)
    _pass(second, dataset)
    _, hashes = partitions.load_minutes(dataset, commit=COMMIT, holdout_run=first)
    assert list(hashes) == ["2021-01-04", "2023-01-03"]
    with pytest.raises(HoldoutLocked, match="already claimed"):
        partitions.load_minutes(dataset, commit=COMMIT, holdout_run=second)


def test_mislabelled_partition_is_rejected_before_ohlc_read_s8(tmp_path, monkeypatch):
    dataset = _dataset(tmp_path, [("2021-01-04", "2023-01-03")])
    original = partitions.pq.ParquetFile.read

    def timestamps_only(self, *, columns):
        assert columns == ["ts_utc"]
        return original(self, columns=columns)

    monkeypatch.setattr(partitions.pq.ParquetFile, "read", timestamps_only)
    with pytest.raises(ValueError, match="outside its declared"):
        partitions.load_minutes(dataset, commit=COMMIT)


def test_real_crypto_fails_closed_until_coverage_adapter_s12(tmp_path, monkeypatch):
    path = tmp_path / "minutes.json"
    path.write_text(json.dumps({"market": "CRYPTO", "synthetic": False, "partitions": []}))
    monkeypatch.setattr(partitions, "_read_partition", lambda *args: pytest.fail("unexpected price I/O"))
    with pytest.raises(ValueError, match="completeness"):
        partitions.load_minutes(partitions.open_dataset(path, "CRYPTO"), commit=COMMIT)


def test_synthetic_cli_runs_both_stages_and_leaves_holdout_locked_s6_s10(tmp_path, capsys):
    manifest = write_study_fixture(tmp_path / "fixture")
    run = tmp_path / "run"
    options = ["--data", str(manifest), "--market", "CRYPTO", "--out", str(run)]
    with pytest.raises(SystemExit, match="2"):
        main(["stage-b", *options])
    assert not run.exists()
    assert main(["stage-a", *options]) == 0
    assert not (run / "stage_b.json").exists()
    assert main(["stage-b", *options]) == 0
    gross = json.loads((run / "gross_metrics.json").read_text())
    net = json.loads((run / "net_metrics.json").read_text())
    assert gross["synthetic"] and gross["gross"]["dev"]["count"] == 2
    assert net["base"]["oos"]["count"] >= 2
    assert not json.loads((run / "pass.json").read_text())["stage_a_passed"]
    with pytest.raises(SystemExit, match="2"):
        main(["holdout", *options])
    assert "Holdout requires both gross and base" in capsys.readouterr().err
    assert not (run / "holdout.json").exists()


def test_cluster_date_comes_from_signal_before_overnight_entry_s10():
    days = [date(2021, 1, 4), *([date(2021, 1, 5)] * 20)]
    bars = pd.DataFrame({
        "symbol": "SYNTHETIC", "open": 100.0, "high": 103.0, "low": 99.0,
        "close": 102.0, "overnight": [False, True, *([False] * 19)],
        "ts_utc": pd.date_range("2021-01-04T20:45Z", periods=21, freq="15min"),
        "trading_date": days,
    })
    directions = pd.Series([1, *([0] * 20)])
    trade, = simulate_trades(bars, directions, cost_bp=0)
    assert trade.trade.entry_bar == 1
    assert _trade_row("SYNTHETIC", bars, trade)["trading_date"] == days[0]


def test_authorized_holdout_cli_writes_results_once_s8_s10(tmp_path, monkeypatch):
    dataset = _dataset(tmp_path, [("2021-01-04", "2021-01-04"), ("2023-01-03", "2023-01-03")])
    run = tmp_path / "run"
    _pass(run, dataset)
    monkeypatch.setattr("atr_breakout.cli._code_commit", lambda **_: COMMIT)
    args = ["holdout", "--market", "US", "--data", str(dataset.manifest), "--out", str(run)]
    assert main(args) == 0
    result = (run / "holdout.json").read_bytes()
    assert json.loads(result)["passed"] is False
    with pytest.raises(SystemExit, match="2"):
        main(args)
    assert (run / "holdout.json").read_bytes() == result
