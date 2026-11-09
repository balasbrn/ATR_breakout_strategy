"""One-symbol trade simulation for a single v1 cost case."""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from atr_breakout.contract_v1 import ENTRY_OFFSET_BARS, MAX_HOLD_BARS, STOP_REVIEW_BAR
from atr_breakout.core.costs import round_trip_cost, trade_returns

Status = Literal["TAKEN", "SKIPPED_BUSY", "SKIPPED_GAP", "SKIPPED_BOUNDARY", "SKIPPED_PURITY"]
ExitReason = Literal["STOP", "BAR5_EXIT", "BREAKEVEN_STOP", "MAX_HOLD"]


@dataclass(frozen=True)
class Trade:
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    exit_reason: ExitReason
    one_r_price: float
    r_gross: float
    r_net: float
    crosses_overnight: bool
    gap_open_price: float | None
    gap_open_r_net: float | None


@dataclass(frozen=True)
class SignalResult:
    signal_bar: int
    direction: int
    status: Status
    trade: Trade | None = None


def _resolve_exit(
    prices: np.ndarray, signal_bar: int, direction: int, entry: float, stop: float, cost: float
) -> tuple[int, float, ExitReason, float | None]:
    stop_moved = False
    last_bar = signal_bar + MAX_HOLD_BARS
    for index in range(signal_bar + ENTRY_OFFSET_BARS, last_bar + 1):
        opened, high, low, close = prices[index]
        extreme = low if direction == 1 else high
        if direction * (extreme - stop) <= 0:
            reason = "BREAKEVEN_STOP" if stop_moved else "STOP"
            gap_open = float(opened) if direction * (opened - stop) < 0 else None
            return index, stop, reason, gap_open
        if index == signal_bar + STOP_REVIEW_BAR:
            if direction * (close - entry) <= 0:
                return index, float(close), "BAR5_EXIT", None
            stop = entry + direction * cost
            stop_moved = True
    return last_bar, float(prices[last_bar, 3]), "MAX_HOLD", None


def simulate_trades(
    bars: pd.DataFrame, directions: pd.Series, *, cost_bp: float, independent: bool = False,
    purity: pd.Series | None = None,
) -> list[SignalResult]:
    """Simulate one cost case on a single symbol's permitted bars.

    Directions are indexed like bars, with values -1, 0 or 1. Pass the
    scoped directions and only bars the study is allowed to read. Optional
    purity preserves blocked signals without simulating them.
    A signal needs the full trade window even if it would have exited early.
    All result bar references are integer positions in the supplied frame.
    Independent benchmark draws may overlap.
    """
    if not bars.index.equals(directions.index) or not directions.isin([-1, 0, 1]).all():
        raise ValueError("Directions must align with bars and be -1, 0 or 1")
    if purity is not None and not bars.index.equals(purity.index):
        raise ValueError("Purity must align with bars")
    if bars["symbol"].nunique() > 1:
        raise ValueError("Trades require a single symbol")

    prices = bars[["open", "high", "low", "close"]].to_numpy(dtype=float)
    overnight = bars["overnight"].to_numpy(dtype=bool)
    signals = directions.to_numpy()
    results = []
    last_exit = -1
    for index in np.flatnonzero(signals):
        signal_bar = int(index)
        direction = int(signals[index])
        if purity is not None and not purity.iloc[signal_bar]:
            results.append(SignalResult(signal_bar, direction, "SKIPPED_PURITY"))
            continue
        if signal_bar + MAX_HOLD_BARS >= len(bars):
            results.append(SignalResult(signal_bar, direction, "SKIPPED_BOUNDARY"))
            continue
        if not independent and signal_bar < last_exit:
            results.append(SignalResult(signal_bar, direction, "SKIPPED_BUSY"))
            continue

        entry_bar = signal_bar + ENTRY_OFFSET_BARS
        entry = float(prices[entry_bar, 0])
        stop = float(prices[signal_bar, 2 if direction == 1 else 1])
        one_r = direction * (entry - stop)
        if one_r <= 0:
            results.append(SignalResult(signal_bar, direction, "SKIPPED_GAP"))
            continue

        cost = round_trip_cost(entry, cost_bp)
        last_exit, exit_price, reason, gap_open = _resolve_exit(
            prices, signal_bar, direction, entry, stop, cost
        )
        gross, net = trade_returns(direction, entry, exit_price, one_r, cost)
        gap_net = None
        if gap_open is not None:
            _, gap_net = trade_returns(direction, entry, gap_open, one_r, cost)
        trade = Trade(
            entry_bar=entry_bar,
            exit_bar=last_exit,
            entry_price=entry,
            exit_price=exit_price,
            exit_reason=reason,
            one_r_price=one_r,
            r_gross=gross,
            r_net=net,
            crosses_overnight=bool(overnight[entry_bar + 1:last_exit + 1].any()),
            gap_open_price=gap_open,
            gap_open_r_net=gap_net,
        )
        results.append(SignalResult(signal_bar, direction, "TAKEN", trade))
    return results
