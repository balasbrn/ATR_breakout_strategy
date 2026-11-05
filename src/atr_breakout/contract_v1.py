"""Constants for the frozen v1 contract and approved implementation decisions."""

from datetime import date

# §3–4: bars, volatility compression, and breakout.
BAR_MINUTES = 15
ATR_PERIOD = 14
ATR_RANK_DAYS = 30
MAX_COMPRESSION_RANK = 20
BREAKOUT_LOOKBACK = 20
MIN_IMPULSE_ATR = 1.2

# §5: per-symbol position and exit rules.
MAX_OPEN_POSITIONS_PER_SYMBOL = 1
ENTRY_OFFSET_BARS = 1
STOP_REVIEW_BAR = 5
MAX_HOLD_BARS = 20

# §6: round-trip costs in basis points, (base, stress).
GROSS_COST_BP = 0.0
ROUND_TRIP_COSTS_BP = {
    "US": (4.9, 9.9),
    "NSE": (10.6, 15.6),
    "CRYPTO": (12.0, 23.0),
    "FX_GOLD": (1.5, 3.0),
}

# §8: inclusive (start, end) dates for dev, OOS, and holdout.
# Crypto development starts on each coin's first usable date.
STUDY_WINDOWS = {
    "US": (
        (date(2019, 10, 1), date(2021, 12, 31)),
        (date(2022, 1, 1), date(2022, 12, 31)),
        (date(2023, 1, 1), date(2026, 9, 30)),
    ),
    "NSE": (
        (date(2015, 1, 1), date(2020, 12, 31)),
        (date(2021, 1, 1), date(2022, 12, 31)),
        (date(2023, 1, 1), date(2026, 9, 30)),
    ),
    "CRYPTO": (
        (None, date(2021, 12, 31)),
        (date(2022, 1, 1), date(2022, 12, 31)),
        (date(2023, 1, 1), date(2024, 12, 31)),
    ),
    "FX_GOLD": (
        (date(2011, 1, 1), date(2020, 12, 31)),
        (date(2021, 1, 1), date(2022, 12, 31)),
        (date(2023, 1, 1), date(2026, 9, 30)),
    ),
}

# §9 and approved decisions §3: random-entry repetitions.
RANDOM_BENCHMARK_SEEDS = range(1, 101)

# §10: clustered t-statistic threshold.
MIN_CLUSTERED_T = 2.0

# §12 O5 and approved decisions §4: crypto minute coverage and purity.
CRYPTO_MIN_ANNUAL_COMPLETENESS = 0.90
CRYPTO_MAX_FILL_GAP_MINUTES = 3
CRYPTO_MAX_FILLED_MINUTES_PER_BAR = 3
CRYPTO_MAX_IMPURE_LOOKBACK_BARS = 2
CRYPTO_SECONDARY_DEV_START = date(2019, 1, 1)
