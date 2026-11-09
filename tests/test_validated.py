import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pyarrow.fs as fs
import pytest

from atr_breakout import cli
from atr_breakout.data.partitions import iter_minute_partitions, open_dataset
from atr_breakout.data.validated import _crypto_coverage
from atr_breakout.study.passrule import StageVerdict, WindowVerdict, write_stage_a, write_stage_b

COMMIT = "a" * 40


def _source(root, *, dataset="us_stocks", symbol="FAKE", rows=None, usable_from="2022-12-30"):
    path = root / dataset / f"symbol={symbol}"
    path.mkdir(parents=True)
    (path / "audit.json").write_text(json.dumps({
        "symbol": symbol, "completeness": {"usable_from": usable_from},
    }))
    rows = rows or [
        ("2022-12-29T15:00Z", 9, True, True, True),
        ("2022-12-30T14:30Z", 10, True, True, True),
        ("2022-12-30T14:31Z", 20, True, False, True),
        ("2022-12-30T14:32Z", 30, False, True, True),
        ("2022-12-30T14:33Z", 40, True, True, False),
        ("2023-01-03T14:30Z", 50, True, True, True),
    ]
    frame = pd.DataFrame(rows, columns=["ts", "open", "valid", "usable", "in_session"])
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True).astype("datetime64[us, UTC]")
    for name in ("high", "low", "close"):
        frame[name] = frame["open"]
    frame["volume"] = 100
    frame["session"] = frame["ts"].dt.date
    frame["split_factor"] = 0.5
    frame["total_factor"] = 0.4
    frame.to_parquet(path / "bars.parquet", index=False, row_group_size=len(frame))
    return path


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / "validated"
    _source(root)
    opened = []

    def from_uri(uri):
        assert uri.startswith("gs://")
        opened.append(uri)
        return fs.LocalFileSystem(), str(root)

    monkeypatch.setattr(cli, "arrow_fs", SimpleNamespace(FileSystem=SimpleNamespace(from_uri=from_uri)))
    monkeypatch.setattr(cli, "_code_commit", lambda **_: COMMIT)
    return root, opened


def _convert(tmp_path, phase, **options):
    out = tmp_path / phase
    args = [
        "convert", "--source", "gs://synthetic-fixture/validated", "--market", "US",
        "--phase", phase, "--out", str(out),
    ]
    for key, value in options.items():
        args += ["--" + key.replace("_", "-"), str(value)]
    assert cli.main(args) == 0
    return open_dataset(out / "minutes.json", "US")


def test_convert_study_drops_reserved_rows_and_uses_raw_us_prices_s2_s8(tmp_path, source):
    study = _convert(tmp_path, "study")
    assert list(study.partitions) == [pd.Timestamp("2022-12-30").date()]
    assert study.conversion["straddling_row_groups"] == 1
    assert study.conversion["cutoff_utc"] == "2023-01-01T00:00:00+00:00"
    assert "gs://" not in study.manifest.read_text()
    _, minutes, _ = next(iter_minute_partitions(study, commit=COMMIT))
    assert minutes["open"].tolist() == [10]
    assert minutes["volume"].tolist() == [100]
    assert len(source[1]) == 1


def test_convert_holdout_requires_pass_then_archives_before_price_read_s8_s10(tmp_path, source, monkeypatch):
    study = _convert(tmp_path, "study")
    run = tmp_path / "run"
    archive = "gs://synthetic-fixture/archive"
    options = dict(study_data=study.manifest, run=run, archive=archive)
    with pytest.raises(SystemExit, match="2"):
        _convert(tmp_path, "holdout", **options)
    assert len(source[1]) == 1

    verdict = StageVerdict(WindowVerdict(2, 2, 1, 1), WindowVerdict(2, 2, 1, 1), 2)
    provenance = {**study.provenance(COMMIT), "input_sha256": {
        day.isoformat(): checksum for day, (_, checksum) in study.partitions.items()
    }}
    write_stage_a(run, provenance, verdict)
    write_stage_b(run, provenance, lambda _: verdict)
    archives = []

    def archive_evidence(run_path, claim, destination, **kwargs):
        assert run_path == run and claim.is_file()
        assert destination.endswith("/run")
        archives.append(kwargs.get("purpose", "holdout"))

    from atr_breakout.data import validated
    scan = validated.price_batches

    def checked_scan(*args, **kwargs):
        assert archives == ["holdout-conversion"]
        yield from scan(*args, **kwargs)

    monkeypatch.setattr(cli, "archive_holdout_evidence", archive_evidence)
    monkeypatch.setattr(validated, "price_batches", checked_scan)
    holdout = _convert(tmp_path, "holdout", **options)
    assert list(holdout.partitions) == [pd.Timestamp("2023-01-03").date()]
    assert holdout.conversion["study_manifest_sha256"] == study.sha256

    def archive_execution(claim: Path):
        assert claim.is_file()
        archives.append("holdout")

    partitions = list(iter_minute_partitions(
        study, commit=COMMIT, holdout_run=run, archive_claim=archive_execution, holdout_data=holdout,
    ))
    assert [frame["open"].tolist() for _, frame, _ in partitions] == [[10], [50]]
    assert archives == ["holdout-conversion", "holdout"]


def test_crypto_coverage_counts_only_eligible_metadata_and_seals_2025_s12(monkeypatch):
    from atr_breakout.data import validated
    import pyarrow as pa

    def scan(_fragment, *, columns, predicate, cutoff):
        assert columns == ["ts"] and cutoff.year == 2025
        assert "usable" in str(predicate) and "valid" in str(predicate)
        yield pa.record_batch({"ts": pd.date_range("2022-12-31", periods=2, freq="min", tz="UTC")})

    monkeypatch.setattr(validated, "price_batches", scan)
    result = _crypto_coverage(None, "2022-12-31")
    assert result["years"]["2022"] == {"observed": 2, "expected": 1440, "required": False}
    assert result["years"]["2023"]["required"]
    assert result["years"]["2024"]["required"]
    assert not result["passed"]


@pytest.mark.parametrize(("market", "dataset", "symbol_count"), [
    ("NSE", "nse", 1), ("FX_GOLD", "fx_gold", 8),
])
def test_convert_uses_nse_as_delivered_and_omits_fx_tick_volume_s2(tmp_path, market, dataset, symbol_count):
    from atr_breakout.data.validated import convert_validated

    root = tmp_path / "validated"
    for index in range(symbol_count):
        _source(root, dataset=dataset, symbol=f"FAKE{index}", rows=[
            ("2022-12-30T04:00Z", 12, True, True, False),
        ])
    path = convert_validated(fs.LocalFileSystem(), str(root), tmp_path / "out", market=market, synthetic=True)
    canonical = open_dataset(path, market)
    _, frame, _ = next(iter_minute_partitions(canonical, commit=COMMIT))
    assert frame["open"].tolist() == [12] * symbol_count
    if market == "FX_GOLD":
        assert frame["volume"].isna().all()
    else:
        assert frame["volume"].tolist() == [100]


def test_crypto_completeness_is_per_required_year_s12(monkeypatch):
    from atr_breakout.data import validated
    import pyarrow as pa

    def scan(_fragment, **_kwargs):
        # 2021's one-day development tail and both holdout years meet 90%.
        for start, minutes in [
            ("2021-12-31", 1296), ("2023-01-01", 473040), ("2024-01-01", 474336),
        ]:
            yield pa.record_batch({"ts": pd.date_range(start, periods=minutes, freq="min", tz="UTC")})

    monkeypatch.setattr(validated, "price_batches", scan)
    result = _crypto_coverage(None, "2021-12-31")
    assert result["passed"]
    assert result["years"]["2022"]["observed"] == 0
    assert not result["years"]["2022"]["required"]
