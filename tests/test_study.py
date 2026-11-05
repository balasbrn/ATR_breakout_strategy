from datetime import date
import hashlib
import json

import pandas as pd
import pytest

from atr_breakout.core.trade import simulate_trades
from atr_breakout.study.benchmarks import buy_and_hold_pct, random_entry, without_compression
from atr_breakout.study.passrule import (
    StageVerdict,
    WindowVerdict,
    evaluate_stage,
    holdout_passed,
    write_stage_run,
)
from atr_breakout.study.stats import clustered_t, without_best_symbol


@pytest.fixture
def bars():
    return pd.DataFrame({
        "symbol": "SYNTHETIC", "open": 100.0, "high": 102.0, "low": 98.0,
        "close": 101.0, "atr": 2.0, "atr_rank_30d": 100.0, "overnight": False,
        "ts_utc": pd.date_range("2021-01-01", periods=42, freq="15min", tz="UTC"),
        "filled_minutes": 0, "missing_minutes": 0,
    })


def test_random_entry_replaces_gaps_with_same_direction_s9(bars):
    window = bars.iloc[:22].copy()
    window.loc[1, ["open", "low"]] = [98, 97]
    directions = pd.Series(0, index=window.index)
    directions.iloc[1] = 1
    trade = simulate_trades(window, directions, cost_bp=4.9)[0].trade

    benchmark = random_entry({"SYNTHETIC": window}, pd.Series([1, 1]), market="US", cost_bp=4.9)
    assert len(benchmark.draw_means) == 100
    assert benchmark.mean_r == pytest.approx(trade.r_net)
    assert benchmark.percentile_5_95 == pytest.approx((trade.r_net, trade.r_net))
    assert benchmark.skipped_gap > 0
    assert benchmark == random_entry(
        {"SYNTHETIC": window}, pd.Series([1, 1]), market="US", cost_bp=4.9
    )


def test_random_entry_matches_mix_and_allows_overlapping_trades_s9(bars):
    window = bars.iloc[:22].copy()
    window.loc[0, "atr_rank_30d"] = float("nan")
    returns = []
    for direction in (-1, 1):
        directions = pd.Series(0, index=window.index)
        directions.iloc[1] = direction
        returns.append(simulate_trades(window, directions, cost_bp=0)[0].trade.r_net)
    benchmark = random_entry(
        {"SYNTHETIC": window}, pd.Series([-1, 1, 1]), market="US", cost_bp=0
    )
    assert benchmark.mean_r == pytest.approx((returns[0] + 2 * returns[1]) / 3)
    assert benchmark.skipped_gap == 0
    adjacent = pd.Series(0, index=window.index)
    adjacent.iloc[:2] = 1
    window.loc[0, "low"] = 97
    dependent = simulate_trades(window, adjacent, cost_bp=0)
    assert dependent[1].status == "SKIPPED_BUSY"
    trades = simulate_trades(window, adjacent, cost_bp=0, independent=True)
    assert [trade.status for trade in trades] == ["TAKEN", "TAKEN"]


def test_random_entry_requires_purity_and_full_window_s9_s12(bars):
    window = bars.iloc[:41].copy()
    assert random_entry({"SYNTHETIC": window}, pd.Series([1]), market="CRYPTO", cost_bp=0).mean_r is not None
    window.loc[21, "missing_minutes"] = 10
    assert random_entry({"SYNTHETIC": window}, pd.Series([1]), market="CRYPTO", cost_bp=0).mean_r is None
    assert random_entry({"SYNTHETIC": bars.iloc[:20]}, pd.Series([1]), market="US", cost_bp=0).mean_r is None


def test_random_entry_undefined_when_every_draw_would_gap_s9(bars):
    window = bars.iloc[:21].copy()
    window.loc[1, ["open", "low"]] = [98, 97]
    result = random_entry({"SYNTHETIC": window}, pd.Series([1]), market="US", cost_bp=0)
    assert result.mean_r is None


def test_breakout_only_and_equal_weight_buy_hold_s9(bars):
    bars.loc[20, ["high", "close"]] = [104, 103]
    trades = without_compression(bars, market="US", cost_bp=0)
    assert len(trades) == 1 and trades[0].status == "TAKEN"
    first = pd.DataFrame({"close": [100, 120]})
    second = pd.DataFrame({"close": [10, 11, 13, 14]})
    assert buy_and_hold_pct({"A": first, "B": second}) == pytest.approx(30)


def make_trades(rows):
    return pd.DataFrame(rows, columns=["symbol", "trading_date", "r"])


def test_clustered_t_on_known_two_cluster_case_s10():
    trades = make_trades([
        ("A", date(2021, 1, 1), 1), ("B", date(2021, 1, 1), 1),
        ("A", date(2021, 1, 2), 3), ("B", date(2021, 1, 2), 3),
    ])
    assert clustered_t(trades) == pytest.approx(2)
    assert clustered_t(trades.iloc[:2]) is None
    assert clustered_t(trades.assign(r=1)) is None


def test_remove_largest_total_r_contributor_s10():
    trades = make_trades([("A", 1, 2), ("A", 2, 2), ("B", 1, 3)])
    assert without_best_symbol(trades) == 3
    assert without_best_symbol(trades.iloc[:2]) is None


def test_pass_requires_all_rules_per_window_and_combined_t_s10():
    dev = make_trades([("A", 1, 1), ("B", 1, 1)])
    oos = make_trades([("A", 2, 3), ("B", 2, 3)])
    assert evaluate_stage(dev, oos, dev_random_mean=0, oos_random_mean=0).passed
    assert not evaluate_stage(dev, oos, dev_random_mean=1, oos_random_mean=0).passed
    assert not evaluate_stage(dev.iloc[:1], oos, dev_random_mean=0, oos_random_mean=0).passed
    assert not evaluate_stage(dev, oos, dev_random_mean=0, oos_random_mean=None).passed
    assert not evaluate_stage(dev, oos.assign(r=4), dev_random_mean=0, oos_random_mean=0).passed
    assert holdout_passed(1, 0.01)
    assert not holdout_passed(1, 0)
    assert not holdout_passed(None, 1)


@pytest.mark.parametrize(("gross_pass", "base_pass"), [(True, True), (False, True), (True, False)])
def test_write_gross_before_net_and_gate_only_on_gross_and_base_s6_s10(
    tmp_path, gross_pass, base_pass,
):
    directory = tmp_path / "run"
    window = WindowVerdict(2, 2, 0, 1)
    calls = []

    def evaluate(case):
        calls.append(case)
        if case != "gross":
            assert (directory / "stage_a.json").is_file()
        assert not (directory / "pass.json").exists()
        passing = {"gross": gross_pass, "base": base_pass, "stress": False}[case]
        return StageVerdict(window, window, 2 if passing else 1)

    assert write_stage_run(directory, "US", evaluate) is (gross_pass and base_pass)
    assert calls == ["gross", "base", "stress"]
    verdict = json.loads((directory / "pass.json").read_text())
    assert verdict["stage_a_passed"] is gross_pass
    assert verdict["stage_b_passed"] is base_pass
    for stage in ("a", "b"):
        digest = hashlib.sha256((directory / f"stage_{stage}.json").read_bytes()).hexdigest()
        assert verdict[f"stage_{stage}_sha256"] == digest
    with pytest.raises(FileExistsError):
        write_stage_run(directory, "US", evaluate)


def test_incomplete_run_never_issues_pass_file_s10(tmp_path):
    directory = tmp_path / "run"
    window = WindowVerdict(2, 2, 0, 1)

    def evaluate(case):
        if case == "base":
            raise RuntimeError("net calculation failed")
        return StageVerdict(window, window, 2)

    with pytest.raises(RuntimeError, match="net calculation failed"):
        write_stage_run(directory, "US", evaluate)
    assert (directory / "stage_a.json").is_file()
    assert not (directory / "pass.json").exists()


def test_random_window_allows_prior_crypto_history_but_no_forward_overlap_s9():
    timestamps = pd.date_range("2021-01-01 19:00", periods=41, freq="15min", tz="UTC")
    bars = pd.DataFrame({
        "symbol": "SYNTHETIC", "open": 100.0, "high": 102.0, "low": 98.0,
        "close": 101.0, "atr": 2.0, "atr_rank_30d": 100.0, "overnight": False,
        "ts_utc": timestamps, "trading_date": timestamps.date,
        "filled_minutes": 0, "missing_minutes": 0,
    })
    second_day = date(2021, 1, 2)
    result = random_entry(
        {"SYNTHETIC": bars}, pd.Series([1]), market="CRYPTO", cost_bp=0,
        window=(second_day, second_day),
    )
    assert result.mean_r is not None
    first_day = date(2021, 1, 1)
    result = random_entry(
        {"SYNTHETIC": bars}, pd.Series([1]), market="US", cost_bp=0,
        window=(first_day, first_day),
    )
    assert result.mean_r is None
