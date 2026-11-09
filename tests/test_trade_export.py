import hashlib
import json
import stat

import pyarrow.parquet as pq
import pytest

from atr_breakout import cli
from atr_breakout.trade_export import RETURN_COLUMNS, TRADE_SCHEMA
from synthetic.generate import write_study_fixture


def test_stage_trade_rows_reconcile_with_verdicts_and_metrics_s6_s7_s9(tmp_path, monkeypatch):
    manifest = write_study_fixture(tmp_path / "fixture", symbols=("SYNTHETIC", "OTHER"))
    run = tmp_path / "run"
    monkeypatch.setattr(cli, "_code_commit", lambda **_: "a" * 40)
    options = ["--market", "CRYPTO", "--data", str(manifest), "--out", str(run)]
    assert cli.main(["stage-a", *options]) == 0
    parquet = run / "trades.parquet"
    assert stat.S_IMODE(parquet.stat().st_mode) == 0o600
    stage_a = pq.read_table(parquet)
    assert stage_a.schema.equals(TRADE_SCHEMA)
    assert set(stage_a["case"].to_pylist()) == {"gross"}
    assert not (run / "stage_b.json").exists()
    gross_metrics = json.loads((run / "gross_metrics.json").read_bytes())
    assert gross_metrics["trades_sha256"] == hashlib.sha256(parquet.read_bytes()).hexdigest()
    assert cli.main(["stage-b", *options]) == 0

    net_metrics = json.loads((run / "net_metrics.json").read_bytes())
    assert net_metrics["trades_sha256"] == hashlib.sha256(parquet.read_bytes()).hexdigest()
    all_rows = pq.read_table(parquet).to_pandas()
    assert all_rows["trade_id"].is_unique
    assert pq.read_table(parquet).slice(0, len(stage_a)).equals(stage_a)
    assert set(all_rows["case"]) == {"gross", "base", "stress"}
    assert set(all_rows["window"]) == {"dev", "oos"}
    assert all_rows.loc[all_rows["status"].ne("TAKEN"), [
        "entry_ts_utc", "exit_ts_utc", "exit_reason", "one_r_price", *RETURN_COLUMNS.values(),
    ]].isna().all().all()

    for case, column in RETURN_COLUMNS.items():
        verdict_file = "stage_a.json" if case == "gross" else "stage_b.json"
        verdict = json.loads((run / verdict_file).read_bytes())[case]
        metrics = (gross_metrics if case == "gross" else net_metrics)[case]
        for window in ("dev", "oos"):
            scoped = all_rows.loc[all_rows["case"].eq(case) & all_rows["window"].eq(window)]
            strategy = scoped.loc[scoped["benchmark"].isna()]
            taken = strategy.loc[strategy["status"].eq("TAKEN")]
            assert strategy["status"].value_counts().to_dict() == metrics[window]["statuses"]
            assert len(taken) == metrics[window]["count"]
            assert taken[column].mean() == pytest.approx(verdict[window]["mean_r"])
            assert taken[column].mean() == pytest.approx(metrics[window]["mean_r"])
            other_columns = set(RETURN_COLUMNS.values()) - {column}
            assert taken[list(other_columns)].isna().all().all()

            draws = scoped.loc[scoped["benchmark"].eq("RANDOM")]
            assert draws["status"].eq("SKIPPED_GAP").sum() == metrics[window]["random_skipped_gap"]
            random_taken = draws.loc[draws["status"].eq("TAKEN")]
            assert random_taken.groupby("seed").size().to_dict() == dict.fromkeys(range(1, 101), len(taken))
            assert random_taken.groupby("seed")[column].mean().mean() == pytest.approx(metrics[window]["random_mean_r"])
            no_compression = scoped.loc[
                scoped["benchmark"].eq("NO_COMPRESSION") & scoped["status"].eq("TAKEN")
            ]
            assert no_compression[column].mean() == pytest.approx(metrics[window]["no_compression_mean_r"])
