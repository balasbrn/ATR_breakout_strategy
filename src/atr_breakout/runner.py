"""Connect authorized canonical bars to study and card modules."""

from collections import Counter
from datetime import date

import pandas as pd

from atr_breakout.contract_v1 import MAX_HOLD_BARS, STUDY_WINDOWS
from atr_breakout.core.bars import BAR_SIZE, build_bars
from atr_breakout.core.costs import cost_basis_points
from atr_breakout.core.indicators import add_indicators
from atr_breakout.core.signal import crypto_entry_eligible, signal_directions
from atr_breakout.core.trade import simulate_trades
from atr_breakout.study.benchmarks import buy_and_hold_pct, random_entry, without_compression
from atr_breakout.study.passrule import evaluate_stage
from atr_breakout.study.stats import mean_r


def prepare_bars(minutes, market):
    bars = build_bars(minutes, market)
    return {
        symbol: add_indicators(frame.reset_index(drop=True))
        for symbol, frame in bars.groupby("symbol", sort=True)
    }


def _between(days, window):
    start, end = window
    return days.le(end) & (days.ge(start) if start is not None else True)


def strategy(frames, market, bp, window=None):
    """Simulate per symbol and keep raw directions for the card builder."""
    for symbol, bars in frames.items():
        directions = signal_directions(bars)
        purity = crypto_entry_eligible(bars) if market == "CRYPTO" else None
        eligible = directions if purity is None else directions.where(purity, 0)
        if window is not None:
            eligible = eligible.where(_between(bars["trading_date"], window), 0)
        yield symbol, bars, directions, purity, simulate_trades(bars, eligible, cost_bp=bp)


def _trade_row(symbol, bars, result):
    signal = bars.iloc[result.signal_bar]
    trade = result.trade
    exit_bar = bars.iloc[trade.exit_bar] if trade else None
    return {
        "symbol": symbol, "trading_date": signal.trading_date,
        "signal_ts_utc": signal.ts_utc + BAR_SIZE, "direction": result.direction,
        "status": result.status, "r": trade.r_net if trade else None,
        "crosses_overnight": trade.crosses_overnight if trade else False,
        "gap_open_r": trade.gap_open_r_net if trade else None,
        "moved_stop_gap": bool(trade and trade.exit_reason == "BREAKEVEN_STOP" and trade.gap_open_price is not None),
        "extended_utc_horizon": bool(trade and exit_bar.ts_utc - signal.ts_utc > MAX_HOLD_BARS * BAR_SIZE),
    }


def _metrics(rows, market):
    taken = rows.loc[rows["status"].eq("TAKEN")]
    returns = taken["r"]
    gap = taken.loc[taken["gap_open_r"].notna()]
    moved = gap.loc[gap["moved_stop_gap"]]
    overnight_gap = gap.loc[gap["crosses_overnight"] & ~gap["moved_stop_gap"]]
    return {
        "count": len(taken),
        "statuses": dict(Counter(rows["status"])),
        "mean_r": mean_r(returns),
        "hit_rate": float(returns.gt(0).mean()) if len(returns) else None,
        "mean_win_r": mean_r(returns[returns.gt(0)]),
        "mean_loss_r": mean_r(returns[returns.lt(0)]),
        "overnight_share": float(taken["crosses_overnight"].mean()) if market in ("US", "NSE") and len(taken) else None,
        "moved_stop_gap_count": len(moved),
        "moved_stop_gap_mean_open_r": mean_r(moved["gap_open_r"]),
        "overnight_gap_count_excluding_moved_stops": len(overnight_gap),
        "overnight_gap_mean_open_r": mean_r(overnight_gap["gap_open_r"]),
        "crypto_exits_after_20_slots": int(taken["extended_utc_horizon"].sum()) if market == "CRYPTO" else None,
        "mean_r_by_year": {
            str(year): mean_r(group["r"])
            for year, group in taken.groupby(taken["trading_date"].map(lambda day: day.year))
        },
    }


TRADE_COLUMNS = [
    "symbol", "trading_date", "signal_ts_utc", "direction", "status", "r",
    "crosses_overnight", "gap_open_r", "moved_stop_gap", "extended_utc_horizon",
]


def study_case(frames, market, case):
    bp = cost_basis_points(market, case)
    rows = []
    breakout = []
    for symbol, bars, _, _, results in strategy(frames, market, bp):
        rows.extend(_trade_row(symbol, bars, result) for result in results)
        breakout.extend(
            _trade_row(symbol, bars, result)
            for result in without_compression(bars, market=market, cost_bp=bp)
        )
    results = pd.DataFrame(rows, columns=TRADE_COLUMNS)
    breakout = pd.DataFrame(breakout, columns=TRADE_COLUMNS)
    dev, oos, _ = STUDY_WINDOWS[market]
    taken_frames, random_means = [], []
    metrics = {}
    for name, window in (("dev", dev), ("oos", oos)):
        scoped = results.loc[_between(results["trading_date"], window)]
        taken = scoped.loc[scoped["status"].eq("TAKEN")]
        start = window[0] or date.min
        benchmark = random_entry(frames, taken["direction"], market=market, cost_bp=bp, window=(start, window[1]))
        no_compression = breakout.loc[
            _between(breakout["trading_date"], window) & breakout["status"].eq("TAKEN"), "r"
        ]
        buy_hold_bars = {
            symbol: bars.loc[_between(bars["trading_date"], window)]
            for symbol, bars in frames.items()
        }
        taken_frames.append(taken)
        random_means.append(benchmark.mean_r)
        metrics[name] = {
            **_metrics(scoped, market),
            "random_mean_r": benchmark.mean_r,
            "random_percentile_5_95": benchmark.percentile_5_95,
            "random_skipped_gap": benchmark.skipped_gap,
            "no_compression_mean_r": mean_r(no_compression),
            "buy_and_hold_pct": buy_and_hold_pct(buy_hold_bars),
            "filled_minutes": sum(int(bars["filled_minutes"].sum()) for bars in buy_hold_bars.values()) if market == "CRYPTO" else None,
        }
    verdict = evaluate_stage(
        *taken_frames, dev_random_mean=random_means[0], oos_random_mean=random_means[1],
    )
    return verdict, metrics


def holdout_case(frames, market, case):
    window = STUDY_WINDOWS[market][2]
    rows = [
        _trade_row(symbol, bars, result)
        for symbol, bars, _, _, results in strategy(
            frames, market, cost_basis_points(market, case), window,
        )
        for result in results
    ]
    return _metrics(pd.DataFrame(rows, columns=TRADE_COLUMNS), market)
