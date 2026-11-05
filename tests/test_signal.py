import pandas as pd
import pytest

from atr_breakout.core.bars import build_bars
from atr_breakout.core.indicators import add_indicators
from atr_breakout.core.signal import crypto_entry_eligible, signal_directions
from synthetic.generate import PLANTED_SIGNALS, generate_frame


def test_exact_planted_signals_s4():
    bars = add_indicators(build_bars(generate_frame(), "CRYPTO"))
    directions = signal_directions(bars)
    assert directions[directions.ne(0)].to_dict() == PLANTED_SIGNALS
    assert crypto_entry_eligible(bars)[directions.ne(0)].all()


@pytest.fixture
def signal_bars():
    bars = pd.DataFrame({
        "ts_utc": pd.date_range("2021-01-01", periods=27, freq="15min", tz="UTC"),
        "open": 100.0,
        "high": 102.0,
        "low": 98.0,
        "close": 100.0,
        "atr": 2.5,
        "atr_rank_30d": 100.0,
        "filled_minutes": 0,
        "missing_minutes": 0,
    })
    bars.loc[19, "atr_rank_30d"] = 20
    bars.loc[20, ["high", "close", "atr"]] = [104, 103, 10]
    return bars


def test_breakout_uses_previous_atr_and_inclusive_thresholds_s4(signal_bars):
    assert signal_directions(signal_bars).iloc[20] == 1
    signal_bars.loc[20, ["low", "high", "close"]] = [96, 102, 97]
    assert signal_directions(signal_bars).iloc[20] == -1


@pytest.mark.parametrize(("column", "row", "value"), [
    ("close", 20, 102),      # Equality at the prior high.
    ("high", 0, 103),        # The oldest prior bar still counts.
    ("open", 20, 100.01),    # The close breaks out but the body is too small.
    ("atr_rank_30d", 19, 20.01),
    ("atr_rank_30d", 19, float("nan")),
    ("atr", 19, float("nan")),
])
def test_near_misses_do_not_signal_s4(signal_bars, column, row, value):
    signal_bars.loc[row, column] = value
    assert signal_directions(signal_bars).iloc[20] == 0


def test_short_must_close_strictly_below_prior_low_s4(signal_bars):
    signal_bars.loc[20, ["open", "high", "low", "close"]] = [101, 102, 97, 98]
    assert signal_directions(signal_bars).iloc[20] == 0


def test_requires_twenty_prior_bars_s4(signal_bars):
    assert signal_directions(signal_bars.iloc[1:]).loc[20] == 0


def test_benchmark_only_removes_compression_s9(signal_bars):
    signal_bars.loc[19, "atr_rank_30d"] = 21
    assert signal_directions(signal_bars).loc[20] == 0
    assert signal_directions(signal_bars, require_compression=False).loc[20] == 1
    signal_bars.loc[19, "atr"] = 3
    assert signal_directions(signal_bars, require_compression=False).loc[20] == 0


@pytest.mark.parametrize("bar", range(20, 26))
def test_crypto_purity_checks_signal_and_first_five_bars_s12(signal_bars, bar):
    signal_bars.loc[bar, ["filled_minutes", "missing_minutes"]] = [1, 2]
    assert crypto_entry_eligible(signal_bars).loc[20]
    signal_bars.loc[bar, "missing_minutes"] = 3
    assert not crypto_entry_eligible(signal_bars).loc[20]


def test_crypto_purity_counts_impure_lookback_bars_s12(signal_bars):
    signal_bars.loc[[0, 19], "missing_minutes"] = 4
    assert crypto_entry_eligible(signal_bars).loc[20]
    signal_bars.loc[1, "filled_minutes"] = 4
    assert not crypto_entry_eligible(signal_bars).loc[20]


def test_crypto_purity_detects_ten_unfilled_minutes_s12():
    minutes = generate_frame()
    first_signal = min(PLANTED_SIGNALS)
    start = (first_signal + 1) * 15
    minutes = minutes.drop(index=range(start, start + 10))
    bars = build_bars(minutes, "CRYPTO")
    assert bars.loc[first_signal + 1, ["filled_minutes", "missing_minutes"]].tolist() == [0, 10]
    assert not crypto_entry_eligible(bars).loc[first_signal]


def test_crypto_purity_counts_missing_buckets_s12(signal_bars):
    assert crypto_entry_eligible(signal_bars.drop(index=[1, 2])).loc[20]
    assert not crypto_entry_eligible(signal_bars.drop(index=[1, 2, 3])).loc[20]
    assert not crypto_entry_eligible(signal_bars.drop(index=21)).loc[20]


def test_crypto_purity_requires_all_five_future_slots_s12(signal_bars):
    signal_bars.loc[26, "missing_minutes"] = 10
    assert crypto_entry_eligible(signal_bars).loc[20]
    assert not crypto_entry_eligible(signal_bars.iloc[:25]).loc[20]
