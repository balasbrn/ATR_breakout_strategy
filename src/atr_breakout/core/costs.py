"""Round-trip transaction costs and signed returns under contract §6."""

from typing import Literal

from atr_breakout.contract_v1 import GROSS_COST_BP, ROUND_TRIP_COSTS_BP

CostCase = Literal["gross", "base", "stress"]
BASIS_POINTS_PER_UNIT = 10_000


def cost_basis_points(market: str, case: CostCase) -> float:
    base, stress = ROUND_TRIP_COSTS_BP[market]
    return {"gross": GROSS_COST_BP, "base": base, "stress": stress}[case]


def round_trip_cost(entry_price: float, cost_bp: float) -> float:
    return entry_price * cost_bp / BASIS_POINTS_PER_UNIT


def trade_returns(
    direction: int, entry: float, exit_price: float, one_r: float, cost: float
) -> tuple[float, float]:
    """Return gross and net R for a single simulation path."""
    gross = direction * (exit_price - entry) / one_r
    return gross, gross - cost / one_r
