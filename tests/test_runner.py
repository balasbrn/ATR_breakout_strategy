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


@pytest.fixture
def cloud(monkeypatch):
    from io import BytesIO
    from pathlib import Path
    import subprocess
    from types import SimpleNamespace

    from atr_breakout import archive

    state = SimpleNamespace(objects={}, calls=[], fail_upload=False, fail_read=False, fail_list=False)

    def upload(argv, *, check):
        assert argv[:4] == ["gcloud", "storage", "cp", "--no-clobber"]
        assert check
        local, remote = argv[4:]
        state.calls.append(("upload", remote))
        if state.fail_upload:
            raise subprocess.CalledProcessError(1, argv)
        state.objects.setdefault(remote, Path(local).read_bytes())

    class Download:
        def __init__(self, argv, *, stdout):
            assert argv[:3] == ["gcloud", "storage", "cat"] and stdout == subprocess.PIPE
            target = argv[3]
            state.calls.append(("check", target))
            self.stdout = BytesIO(state.objects[target])

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.stdout.close()

        def wait(self):
            return int(state.fail_read)

    original = subprocess.run

    def run(argv, **kwargs):
        if argv[:3] == ["gcloud", "storage", "ls"]:
            assert kwargs == {"capture_output": True, "text": True}
            target = argv[3]
            state.calls.append(("list", target))
            if state.fail_list:
                return SimpleNamespace(returncode=1, stderr="Permission denied")
            if target in state.objects:
                return SimpleNamespace(returncode=0, stderr="")
            return SimpleNamespace(returncode=1, stderr="ERROR: One or more URLs matched no objects.")
        if argv[0] == "gcloud":
            return upload(argv, **kwargs)
        return original(argv, **kwargs)

    monkeypatch.setattr(archive, "subprocess", SimpleNamespace(
        run=run, Popen=Download, PIPE=subprocess.PIPE, CalledProcessError=subprocess.CalledProcessError,
    ))
    return state


ARCHIVE = "gs://test-fixture/private"


@pytest.mark.parametrize("action", ["stage-a", "stage-b", "holdout", "cards"])
def test_real_cli_requires_archive_before_price_io_s8(tmp_path, monkeypatch, action):
    path = tmp_path / "minutes.json"
    path.write_text(json.dumps({"market": "US", "synthetic": False, "partitions": []}))
    monkeypatch.setattr("atr_breakout.cli.iter_minute_partitions", lambda *a, **kw: pytest.fail("unexpected price I/O"))
    args = [action, "--market", "US", "--data", str(path), "--out", str(tmp_path / "run")]
    if action == "cards":
        args += ["--schema", "unused.json"]
    with pytest.raises(SystemExit, match="2"):
        main(args)


def test_archives_stage_outputs_under_same_run_id_and_redacts_uri_s6(tmp_path, cloud):
    manifest = write_study_fixture(tmp_path / "fixture")
    run = tmp_path / "run"
    args = ["--data", str(manifest), "--market", "CRYPTO", "--out", str(run), "--archive", ARCHIVE]
    assert main(["stage-a", *args]) == 0
    first = dict(cloud.objects)
    assert f"{ARCHIVE}/run/stage_a.json" in first
    assert main(["stage-b", *args]) == 0
    assert f"{ARCHIVE}/run/pass.json" in cloud.objects
    assert all(cloud.objects[key] == value for key, value in first.items())
    for file in run.iterdir():
        assert cloud.objects[f"{ARCHIVE}/run/{file.name}"] == file.read_bytes()
        assert ARCHIVE.encode() not in file.read_bytes()


def test_cards_archive_preserves_nested_paths(tmp_path, cloud, monkeypatch):
    manifest = write_study_fixture(tmp_path / "fixture")

    def write_fake_cards(directory, *_args, **_kwargs):
        partition = directory / "public" / "entry" / "day_key=1" / "part-00000.parquet"
        partition.parent.mkdir(parents=True)
        partition.write_bytes(b"synthetic card partition")
        (directory / "public" / "manifest.json").write_text("{}")
        (directory / "event_map.parquet").write_bytes(b"synthetic private map")

    monkeypatch.setattr("atr_breakout.cli.write_cards", write_fake_cards)
    assert main([
        "cards", "--data", str(manifest), "--market", "CRYPTO", "--schema", "unused.json",
        "--out", str(tmp_path / "card-run"), f"--archive={ARCHIVE}",
    ]) == 0
    assert cloud.objects == {
        f"{ARCHIVE}/card-run/event_map.parquet": b"synthetic private map",
        f"{ARCHIVE}/card-run/public/manifest.json": b"{}",
        f"{ARCHIVE}/card-run/public/entry/day_key=1/part-00000.parquet": b"synthetic card partition",
    }


def test_holdout_archive_evidence_verified_before_any_partition_read_s8_s10(tmp_path, monkeypatch, cloud):
    dataset = _dataset(tmp_path, [("2021-01-04", "2021-01-04"), ("2023-01-03", "2023-01-03")])
    run = tmp_path / "run"
    _pass(run, dataset)
    monkeypatch.setattr("atr_breakout.cli._code_commit", lambda **_: COMMIT)
    read_partition = partitions._read_partition

    def checked_read(*args):
        fixed = f"{ARCHIVE}/holdout-claims/v1-US-{dataset.sha256}.claim"
        assert ("check", fixed) in cloud.calls
        assert cloud.objects[fixed] == cloud.objects[f"{ARCHIVE}/run/.v1-US-holdout.claim"]
        for name in (".v1-US-holdout.claim", "stage_a.json", "stage_b.json", "pass.json"):
            assert ("check", f"{ARCHIVE}/run/{name}") in cloud.calls
        return read_partition(*args)

    monkeypatch.setattr(partitions, "_read_partition", checked_read)
    assert main([
        "holdout", "--market", "US", "--data", str(dataset.manifest),
        "--out", str(run), "--archive", ARCHIVE,
    ]) == 0
    assert f"{ARCHIVE}/run/holdout.json" in cloud.objects


@pytest.mark.parametrize("failure", ["upload", "read", "size", "hash", "list", "identical_claim"])
def test_failed_holdout_archive_spends_claim_without_reading_prices_s8_s10(
    tmp_path, monkeypatch, cloud, failure,
):
    dataset = _dataset(tmp_path, [("2023-01-03", "2023-01-03")])
    run = tmp_path / "run"
    _pass(run, dataset)
    monkeypatch.setattr("atr_breakout.cli._code_commit", lambda **_: COMMIT)
    monkeypatch.setattr(partitions, "_read_partition", lambda *a: pytest.fail("unexpected price I/O"))
    if failure == "upload":
        cloud.fail_upload = True
    elif failure == "read":
        cloud.fail_read = True
    elif failure == "size":
        cloud.objects[f"{ARCHIVE}/run/stage_a.json"] = b"wrong"
    elif failure == "hash":
        payload = (run / "stage_a.json").read_bytes()
        cloud.objects[f"{ARCHIVE}/run/stage_a.json"] = b"x" + payload[1:]
    elif failure == "list":
        cloud.fail_list = True
    else:
        create_claim = partitions.claim_holdout

        def restore_existing_remote_claim(*args):
            claim = create_claim(*args)
            cloud.objects[f"{ARCHIVE}/run/{claim.name}"] = claim.read_bytes()
            return claim

        monkeypatch.setattr(partitions, "claim_holdout", restore_existing_remote_claim)
    with pytest.raises(SystemExit, match="2"):
        main([
            "holdout", "--market", "US", "--data", str(dataset.manifest),
            "--out", str(run), "--archive", ARCHIVE,
        ])
    claim = dataset.manifest.parent / ".v1-US-holdout.claim"
    record = json.loads(claim.read_bytes())
    assert record["attempt_id"]
    assert record["claimed_at_utc"].endswith("+00:00")
    if failure in ("list", "identical_claim"):
        expected = [("list", f"{ARCHIVE}/holdout-claims/v1-US-{dataset.sha256}.claim")]
        if failure == "identical_claim":
            expected.append(("list", f"{ARCHIVE}/run/{claim.name}"))
        assert cloud.calls == expected
    assert not (run / "holdout.json").exists()


def test_failed_final_archive_exits_with_error(tmp_path, cloud, monkeypatch):
    dataset = _dataset(tmp_path, [("2021-01-04", "2021-01-04")])
    run = tmp_path / "run"
    window = WindowVerdict(0, None, None, None)
    monkeypatch.setattr("atr_breakout.cli.study_case", lambda *a: (StageVerdict(window, window, None), {}))
    cloud.fail_upload = True
    with pytest.raises(SystemExit, match="2"):
        main([
            "stage-a", "--market", "US", "--data", str(dataset.manifest),
            "--out", str(run), "--archive", ARCHIVE,
        ])
    assert (run / "stage_a.json").is_file()


def test_fixed_remote_claim_blocks_new_output_directory_before_price_io_s8(tmp_path, monkeypatch, cloud, capsys):
    dataset = _dataset(tmp_path, [("2023-01-03", "2023-01-03")])
    run = tmp_path / "different-run"
    _pass(run, dataset)
    fixed = f"{ARCHIVE}/holdout-claims/v1-US-{dataset.sha256}.claim"
    cloud.objects[fixed] = b"claim from the original run"
    monkeypatch.setattr("atr_breakout.cli._code_commit", lambda **_: COMMIT)
    monkeypatch.setattr(partitions, "_read_partition", lambda *a: pytest.fail("unexpected price I/O"))

    with pytest.raises(SystemExit, match="2"):
        main([
            "holdout", "--market", "US", "--data", str(dataset.manifest),
            "--out", str(run), "--archive", ARCHIVE,
        ])
    assert "remote holdout claim already exists" in capsys.readouterr().err
    assert cloud.calls == [("list", fixed)]
    assert not (run / "holdout.json").exists()
