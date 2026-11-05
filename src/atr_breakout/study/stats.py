"""Per-market trade statistics over taken trades on a common R basis."""

import math

import pandas as pd


def mean_r(returns: pd.Series) -> float | None:
    return float(returns.mean()) if not returns.empty else None


def without_best_symbol(trades: pd.DataFrame) -> float | None:
    """Drop the largest total-R contributor, breaking ties by symbol."""
    if trades.empty:
        return None
    best = trades.groupby("symbol", sort=True)["r"].sum().idxmax()
    return mean_r(trades.loc[trades["symbol"].ne(best), "r"])


def clustered_t(trades: pd.DataFrame) -> float | None:
    """Intercept-only t with date-clustered SE and G/(G-1) correction."""
    center = mean_r(trades["r"])
    if center is None:
        return None
    scores = (trades["r"] - center).groupby(trades["trading_date"]).sum()
    clusters = len(scores)
    if clusters < 2:
        return None
    variance = clusters / (clusters - 1) * float(scores.pow(2).sum()) / len(trades)**2
    return center / math.sqrt(variance) if variance > 0 else None
