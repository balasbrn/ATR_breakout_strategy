from datetime import date

from atr_breakout import contract_v1 as contract


def test_bar_and_atr_settings_s3():
    assert contract.BAR_MINUTES == 15
    assert contract.ATR_PERIOD == 14
    assert contract.ATR_RANK_DAYS == 30


def test_breakout_settings_s4():
    assert contract.MAX_COMPRESSION_RANK == 20
    assert contract.BREAKOUT_LOOKBACK == 20
    assert contract.MIN_IMPULSE_ATR == 1.2


def test_trade_settings_s5():
    assert contract.MAX_OPEN_POSITIONS_PER_SYMBOL == 1
    assert contract.ENTRY_OFFSET_BARS == 1
    assert contract.STOP_REVIEW_BAR == 5
    assert contract.MAX_HOLD_BARS == 20


def test_round_trip_costs_s6():
    assert contract.GROSS_COST_BP == 0
    assert contract.ROUND_TRIP_COSTS_BP == {
        "US": (4.9, 9.9),
        "NSE": (10.6, 15.6),
        "CRYPTO": (12.0, 23.0),
        "FX_GOLD": (1.5, 3.0),
    }


def test_study_windows_s8():
    actual = {
        market: tuple(
            (start.isoformat() if start else None, end.isoformat())
            for start, end in windows
        )
        for market, windows in contract.STUDY_WINDOWS.items()
    }
    assert actual == {
        "US": (
            ("2019-10-01", "2021-12-31"),
            ("2022-01-01", "2022-12-31"),
            ("2023-01-01", "2026-09-30"),
        ),
        "NSE": (
            ("2015-01-01", "2020-12-31"),
            ("2021-01-01", "2022-12-31"),
            ("2023-01-01", "2026-09-30"),
        ),
        "CRYPTO": (
            (None, "2021-12-31"),
            ("2022-01-01", "2022-12-31"),
            ("2023-01-01", "2024-12-31"),
        ),
        "FX_GOLD": (
            ("2011-01-01", "2020-12-31"),
            ("2021-01-01", "2022-12-31"),
            ("2023-01-01", "2026-09-30"),
        ),
    }


def test_random_benchmark_seeds_s9():
    assert list(contract.RANDOM_BENCHMARK_SEEDS) == list(range(1, 101))


def test_clustered_t_threshold_s10():
    assert contract.MIN_CLUSTERED_T == 2.0


def test_crypto_coverage_and_purity_settings_s12():
    assert contract.CRYPTO_MIN_ANNUAL_COMPLETENESS == 0.90
    assert contract.CRYPTO_MAX_FILL_GAP_MINUTES == 3
    assert contract.CRYPTO_MAX_FILLED_MINUTES_PER_BAR == 3
    assert contract.CRYPTO_MAX_IMPURE_LOOKBACK_BARS == 2
    assert contract.CRYPTO_SECONDARY_DEV_START == date(2019, 1, 1)
