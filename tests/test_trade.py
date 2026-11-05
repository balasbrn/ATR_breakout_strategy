import pandas as pd
import pytest

from atr_breakout.core.bars import build_bars
from atr_breakout.core.costs import cost_basis_points
from atr_breakout.core.indicators import add_indicators
from atr_breakout.core.signal import crypto_entry_eligible, signal_directions
from atr_breakout.core.trade import simulate_trades
from synthetic.generate import PLANTED_SIGNALS, generate_frame


@pytest.fixture
def bars():
    frame = pd.DataFrame({
        "symbol": "SYNTHETIC", "open": 102.0, "high": 104.0, "low": 101.0,
        "close": 103.0, "overnight": False,
    }, index=range(45))
    frame.loc[0, ["open", "high", "low", "close"]] = [99, 103, 98, 102]
    return frame


def run(bars, signals=None, cost_bp=0):
    directions = pd.Series(0, index=bars.index)
    for index, direction in (signals or {0: 1}).items():
        directions.loc[index] = direction
    return simulate_trades(bars, directions, cost_bp=cost_bp)


@pytest.mark.parametrize(("direction", "opened"), [(1, 98), (1, 97), (-1, 103), (-1, 104)])
def test_cancels_entry_at_or_beyond_stop_s5(bars, direction, opened):
    bars.loc[1, ["open", "high", "low", "close"]] = [opened, opened, opened, opened]
    result, = run(bars, {0: direction})
    assert result.status == "SKIPPED_GAP"
    assert result.trade is None


def test_entry_bar_stop_is_checked_s5(bars):
    bars.loc[1, "low"] = 98
    trade = run(bars)[0].trade
    assert (trade.entry_bar, trade.exit_bar, trade.exit_reason) == (1, 1, "STOP")
    assert trade.entry_price == 102
    assert trade.one_r_price == 4
    assert trade.r_net == -1


def test_bar_five_exit_at_entry_equality_s5(bars):
    bars.loc[5, "close"] = 102
    trade = run(bars)[0].trade
    assert (trade.exit_bar, trade.exit_price, trade.exit_reason) == (5, 102, "BAR5_EXIT")


def test_initial_stop_has_precedence_on_bar_five_s5(bars):
    bars.loc[5, "low"] = 98
    trade = run(bars)[0].trade
    assert (trade.exit_bar, trade.exit_price, trade.exit_reason) == (5, 98, "STOP")


def test_moved_stop_activates_on_bar_six_and_cost_changes_path_s5_s6(bars):
    bars.loc[6:20, ["open", "low"]] = [103, 102.02]
    gross = run(bars, cost_bp=cost_basis_points("US", "gross"))[0].trade
    net = run(bars, cost_bp=cost_basis_points("US", "base"))[0].trade
    assert (gross.exit_bar, gross.exit_reason) == (20, "MAX_HOLD")
    assert (net.exit_bar, net.exit_reason) == (6, "BREAKEVEN_STOP")
    assert net.exit_price == pytest.approx(102 + 102 * 4.9 / 10_000)
    assert net.r_net == pytest.approx(0)


def test_later_stop_gap_reports_open_fill_diagnostic_s5_s6(bars):
    bars.loc[2, ["open", "low"]] = [97, 96]
    trade = run(bars, cost_bp=4.9)[0].trade
    assert (trade.exit_price, trade.gap_open_price) == (98, 97)
    assert trade.r_gross == -1
    assert trade.gap_open_r_net == pytest.approx(trade.r_net - 1 / 4)


def test_short_returns_use_direction_and_cost_s5_s6(bars):
    bars.loc[1:, ["open", "high", "low", "close"]] = [100, 99, 95, 96]
    bars.loc[1:5, "high"] = 101
    bars.loc[6:, "open"] = 98
    trade = run(bars, {0: -1}, cost_bp=10)[0].trade
    assert (trade.exit_bar, trade.exit_reason) == (20, "MAX_HOLD")
    assert trade.one_r_price == 3
    assert trade.r_gross == pytest.approx(4 / 3)
    assert trade.r_net == pytest.approx(3.9 / 3)


def test_busy_during_trade_and_signal_at_exit_close_s5(bars):
    bars.loc[3, "low"] = 98
    results = run(bars, {0: 1, 2: 1, 3: 1})
    assert [result.status for result in results] == ["TAKEN", "SKIPPED_BUSY", "TAKEN"]
    assert results[-1].trade.entry_bar == 4


def test_overnight_counts_only_after_entry_s5_s7(bars):
    bars.loc[1, "overnight"] = True
    assert not run(bars)[0].trade.crosses_overnight
    bars.loc[6, "overnight"] = True
    assert run(bars)[0].trade.crosses_overnight


def test_truncated_permitted_window_is_skipped_s8(bars):
    assert run(bars.iloc[:20])[0].status == "SKIPPED_BOUNDARY"
    assert run(bars.iloc[:21])[0].status == "TAKEN"


@pytest.mark.parametrize(("market", "base", "stress"), [
    ("US", 4.9, 9.9), ("NSE", 10.6, 15.6),
    ("CRYPTO", 12.0, 23.0), ("FX_GOLD", 1.5, 3.0),
])
def test_cost_case_selection_s6(market, base, stress):
    assert cost_basis_points(market, "gross") == 0
    assert cost_basis_points(market, "base") == base
    assert cost_basis_points(market, "stress") == stress


def test_planted_trades_through_the_production_modules_s4_s5_s6():
    bars = add_indicators(build_bars(generate_frame(), "CRYPTO"))
    directions = signal_directions(bars).where(crypto_entry_eligible(bars), 0)
    gross = simulate_trades(bars, directions, cost_bp=cost_basis_points("CRYPTO", "gross"))
    base = simulate_trades(bars, directions, cost_bp=cost_basis_points("CRYPTO", "base"))

    assert {result.signal_bar: result.direction for result in gross} == PLANTED_SIGNALS
    for stage_a, stage_b in zip(gross, base, strict=True):
        assert stage_a.status == stage_b.status == "TAKEN"
        assert stage_a.trade.exit_reason == stage_b.trade.exit_reason == "MAX_HOLD"
        assert stage_a.trade.r_gross > stage_b.trade.r_net > 0
