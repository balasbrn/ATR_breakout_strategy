"""Benchmarks over preselected bars in one market and study window."""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from atr_breakout.contract_v1 import ENTRY_OFFSET_BARS, MAX_HOLD_BARS, RANDOM_BENCHMARK_SEEDS
from atr_breakout.core.signal import crypto_entry_eligible, signal_directions
from atr_breakout.core.trade import SignalResult, simulate_trades


@dataclass(frozen=True)
class RandomBenchmark:
    draw_means: tuple[float, ...]
    skipped_gap: int

    @property
    def mean_r(self) -> float | None:
        return float(np.mean(self.draw_means)) if self.draw_means else None

    @property
    def percentile_5_95(self) -> tuple[float, float] | None:
        if not self.draw_means:
            return None
        lower, upper = np.percentile(self.draw_means, [5, 95])
        return float(lower), float(upper)


def _eligible_positions(
    bars: pd.DataFrame, market: str, window: tuple[date, date] | None,
) -> np.ndarray:
    eligible = bars["atr"].notna() & bars["atr_rank_30d"].notna()
    if market == "CRYPTO":
        eligible &= crypto_entry_eligible(bars)
    if window is not None:
        start, end = window
        dates = bars["trading_date"]
        eligible &= dates.ge(start) & dates.shift(-MAX_HOLD_BARS).le(end)
    return np.flatnonzero(eligible.to_numpy()[:max(0, len(bars) - MAX_HOLD_BARS)])


def _draw(rng, valid: np.ndarray, count: int) -> tuple[np.ndarray, int]:
    picks = rng.integers(len(valid), size=count)
    rejected = ~valid[picks]
    skipped = int(rejected.sum())
    while rejected.any():
        picks[rejected] = rng.integers(len(valid), size=int(rejected.sum()))
        rejected = ~valid[picks]
        skipped += int(rejected.sum())
    return picks, skipped


def random_entry(
    bars_by_symbol: dict[str, pd.DataFrame], taken_directions: pd.Series,
    *, market: str, cost_bp: float, window: tuple[date, date] | None = None,
) -> RandomBenchmark:
    """Draw uniformly over eligible symbol/bar pairs with replacement.

    If supplied, the inclusive trading-date window bounds the signal and
    its full forward horizon while allowing earlier bars for purity. With
    no window, the supplied bars define its boundaries. The strategy's
    taken long and short counts are matched exactly in every draw.
    """
    if not taken_directions.isin([-1, 1]).all():
        raise ValueError("Benchmark directions must be taken longs or shorts")
    if taken_directions.empty:
        return RandomBenchmark((), 0)

    if window is not None and window[0] > window[1]:
        raise ValueError("Benchmark window must be in chronological order")

    frames = [bars_by_symbol[symbol] for symbol in sorted(bars_by_symbol)]
    positions = [_eligible_positions(bars, market, window) for bars in frames]
    sizes = [len(indices) for indices in positions]
    if not sum(sizes):
        return RandomBenchmark((), 0)
    offsets = np.cumsum([0, *sizes])
    candidates = np.concatenate(positions)
    counts = taken_directions.value_counts().sort_index()
    generators = [np.random.default_rng(seed) for seed in RANDOM_BENCHMARK_SEEDS]
    draw_sums = np.zeros(len(RANDOM_BENCHMARK_SEEDS))
    skipped_gap = 0

    for direction, count in counts.items():
        stop_column = "low" if direction == 1 else "high"
        valid = np.concatenate([
            direction * (
                bars["open"].to_numpy()[indices + ENTRY_OFFSET_BARS]
                - bars[stop_column].to_numpy()[indices]
            ) > 0
            for bars, indices in zip(frames, positions)
        ])
        if not valid.any():
            return RandomBenchmark((), 0)

        samples = []
        for rng in generators:
            picks, rejected = _draw(rng, valid, int(count))
            samples.append(picks)
            skipped_gap += rejected
        draws = np.stack(samples)
        picked, inverse = np.unique(draws, return_inverse=True)
        values = np.empty(len(picked))
        for index, bars in enumerate(frames):
            start, end = picked.searchsorted(offsets[index:index + 2])
            indices = candidates[picked[start:end]]
            if not len(indices):
                continue
            directions = pd.Series(0, index=bars.index, dtype="int8")
            directions.iloc[indices] = direction
            trades = simulate_trades(bars, directions, cost_bp=cost_bp, independent=True)
            values[start:end] = [result.trade.r_net for result in trades]
        draw_sums += values[inverse.reshape(draws.shape)].sum(axis=1)

    return RandomBenchmark(tuple((draw_sums / len(taken_directions)).tolist()), skipped_gap)


def without_compression(
    bars: pd.DataFrame, *, market: str, cost_bp: float,
) -> list[SignalResult]:
    directions = signal_directions(bars, require_compression=False)
    if market == "CRYPTO":
        directions = directions.where(crypto_entry_eligible(bars), 0)
    return simulate_trades(bars, directions, cost_bp=cost_bp)


def buy_and_hold_pct(bars_by_symbol: dict[str, pd.DataFrame]) -> float | None:
    """Equal-weight each symbol's return over the supplied window."""
    returns = [
        100 * (bars["close"].iloc[-1] / bars["close"].iloc[0] - 1)
        for bars in bars_by_symbol.values()
        if not bars.empty
    ]
    return float(np.mean(returns)) if returns else None
