"""Build plan and bot outcome tracks for permitted DEV/OOS signals."""

from dataclasses import dataclass

import pandas as pd

from atr_breakout.contract_v1 import STUDY_WINDOWS
from atr_breakout.core.bars import BAR_SIZE, CASH_SESSIONS
from atr_breakout.core.costs import cost_basis_points
from atr_breakout.core.trade import SignalResult

from .anonymise import CardKeys
from .entry import CARD_VERSION, MARKET_CLASS, PLAN, CardContext, snapshot

COST_MODEL = "atr_bo_v1_base"
BOT_REASONS = {
    "STOP": "INITIAL_STOP", "BAR5_EXIT": "TIME_STOP",
    "BREAKEVEN_STOP": "BE_STOP", "MAX_HOLD": "TIME",
}
ACTIONS = {
    "TAKEN": "SIGNAL_ACCEPTED", "SKIPPED_BUSY": "SYMBOL_ALREADY_OPEN",
    "SKIPPED_GAP": "ORDER_UNFILLED", "SKIPPED_BOUNDARY": "TIME_FILTER_VETO",
    "SKIPPED_PURITY": "ATR_VETO",
}


@dataclass(frozen=True)
class PlanExit:
    bar: int
    result: str
    reason: str
    price: float
    ambiguity: bool = False
    gap: str = "none"


def _plan_exit(bars, index, direction, market):
    signal = bars.iloc[index]
    entry, atr = float(signal.close), float(signal.atr)
    if not atr > 0:
        return None
    stop = entry - direction * atr * PLAN["stop_atr"]
    target = entry + direction * atr * PLAN["target_atr"]
    last = index + PLAN["max_bars"]

    for position in range(index, min(len(bars), last + 1)):
        bar = bars.iloc[position]
        if market in CASH_SESSIONS:
            if bar.trading_date != signal.trading_date:
                prior = bars.iloc[position - 1]
                return PlanExit(position - 1, "SESSION_CLOSE", "SESSION_CLOSE", float(prior.close))

        if position > index:
            adverse = bar.low if direction == 1 else bar.high
            favorable = bar.high if direction == 1 else bar.low
            if direction * (adverse - stop) <= 0:
                collision = direction * (favorable - target) >= 0
                gap = direction * (bar.open - stop) < 0
                reason = "SAME_BAR_COLLISION_STOP_FIRST" if collision else "STOP"
                return PlanExit(
                    position, "STOP", reason, float(bar.open) if gap else stop,
                    collision, "adverse_stop_gap_open_fill" if gap else "none",
                )
            if direction * (favorable - target) >= 0:
                gap = direction * (bar.open - target) > 0
                return PlanExit(position, "TARGET", "TARGET", target, gap="favorable_target_gap_capped" if gap else "none")

        if market in CASH_SESSIONS:
            zone, _, closing = CASH_SESSIONS[market]
            local_end = (bar.ts_utc + BAR_SIZE).tz_convert(zone)
            if local_end.hour * 60 + local_end.minute == closing:
                return PlanExit(position, "SESSION_CLOSE", "SESSION_CLOSE", float(bar.close))
        if position == last:
            return PlanExit(position, "TIME", "TIME", float(bar.close))
    return None


def _costs(move, entry, atr, bp):
    if move is None:
        return {}
    gross_bp = 10_000 * move / entry
    gross_atr = move / atr
    return {
        "gross_bp": gross_bp, "net_bp": gross_bp - bp,
        "gross_atr": gross_atr, "net_atr": (move - bp * entry / 10_000) / atr,
        "cost_source_version": COST_MODEL,
    }


def build_cards(
    bars: pd.DataFrame, directions: pd.Series, actual: list[SignalResult],
    *, market: str, keys: CardKeys, context: CardContext | None = None,
    purity: pd.Series | None = None,
) -> dict[str, list[dict]]:
    """Build one symbol's public tables and private map from base-case results.

    Bars must end by OOS. Optional purity identifies why a raw crypto
    signal has no result from the trade simulator.
    """
    dev, oos, _ = STUDY_WINDOWS[market]
    if bars["trading_date"].gt(oos[1]).any():
        raise ValueError("Card inputs must end by the market's OOS cutoff")
    if bars["symbol"].nunique() > 1 or not directions.index.equals(bars.index):
        raise ValueError("Cards require aligned directions and one symbol")
    if purity is not None and not purity.index.equals(bars.index):
        raise ValueError("Purity must align with bars")

    tables = {name: [] for name in ("entry", "exit", "outcome", "event_map")}
    actual_by_index = {result.signal_bar: result for result in actual}
    bp = cost_basis_points(market, "base")
    context = context or CardContext()
    for index, direction in enumerate(directions):
        if direction == 0:
            continue
        bar = bars.iloc[index]
        if dev[0] is not None and bar.trading_date < dev[0]:
            continue
        result = actual_by_index.get(index)
        if result is None:
            if market != "CRYPTO" or purity is None or bool(purity.iloc[index]):
                raise ValueError("An eligible raw signal is missing its base-case trade result")
            status, trade = "SKIPPED_PURITY", None
        else:
            if result.direction != direction:
                raise ValueError("Base-case trade direction disagrees with signal")
            status, trade = result.status, result.trade

        symbol = str(bar.symbol)
        asset = "COMMODITY_CFD" if market == "FX_GOLD" and symbol == "XAUUSD" else MARKET_CLASS[market]
        at = bar.ts_utc + BAR_SIZE
        identity = keys.identify(market, symbol, asset, at, bar.trading_date)
        prior = bars.iloc[index - 1]
        trigger = {"name": "atr_breakout_v1", "values": {
            "atr_rank_prev": float(prior.atr_rank_30d),
            "impulse_atr": float(direction * (bar.close - bar.open) / prior.atr),
        }}
        common = {
            "card_version": CARD_VERSION, "asset_class": asset,
            "direction": "LONG" if direction == 1 else "SHORT", "timeframe": "15m",
            "trigger": trigger, "plan": PLAN.copy(),
        }
        tables["entry"].append({**identity, **common, **snapshot(bars, index, market, context, cost_bp=bp)})

        plan = _plan_exit(bars, index, direction, market)
        atr = float(bar.atr)
        plan_status = "COMPLETE" if plan else "INCOMPLETE_DATA"
        plan_move = float(direction * (plan.price - bar.close)) if plan else None
        plan_costs = _costs(plan_move, float(bar.close), atr, bp)
        bot_move = direction * (trade.exit_price - trade.entry_price) if trade else None
        bot_costs = _costs(bot_move, trade.entry_price, atr, bp) if trade else {}
        bot_reason = BOT_REASONS[trade.exit_reason] if trade else None
        plan_bars = plan.bar - index if plan else None
        bot_bars = trade.exit_bar - trade.entry_bar + 1 if trade else None
        tables["outcome"].append({
            "event_id": identity["event_id"], "card_version": CARD_VERSION, "day_key": identity["day_key"],
            "label_end_day_key": keys.day_key(market, bars.iloc[plan.bar].trading_date) if plan else None,
            "bot_label_end_day_key": keys.day_key(market, bars.iloc[trade.exit_bar].trading_date) if trade else None,
            "status": plan_status, "action": "TAKEN" if trade else "BLOCKED",
            "action_reason": ACTIONS[status], "cost_model_version": COST_MODEL,
            "target_after_stop": True if plan and plan.ambiguity else None, "failure_type": None,
            "card_plan": {
                "status": plan_status, "plan_result": plan.result if plan else None,
                "exit_reason": plan.reason if plan else None, "plan_r": plan_costs.get("gross_atr"),
                "plan_bars": plan_bars, "bars_held": plan_bars,
                "ambiguity": bool(plan and plan.ambiguity),
                "gap_status": plan.gap if plan else "horizon_incomplete",
                "gross_mid_to_mid_bp": plan_costs.get("gross_bp"),
                "gross_mid_to_mid_atr": plan_costs.get("gross_atr"), "costs": plan_costs,
            },
            "bot_actual": {
                "action_status": "TAKEN" if trade else "BLOCKED",
                "exit_reason": bot_reason, "bot_exit_reason": bot_reason,
                "bars_held": bot_bars, "bot_bars": bot_bars,
                "gross_bp": bot_costs.get("gross_bp"), "net_bp": bot_costs.get("net_bp"),
                "bot_net_bp": bot_costs.get("net_bp"),
                "cost_source": "MODELLED_FIXED" if trade else None,
                "result_source": "MODELLED_FIXED" if trade else None,
            },
            "bot_actual_costs": bot_costs,
        })

        tracks = []
        if plan:
            tracks.append(("CARD_PLAN", plan.bar, plan.reason, plan_bars))
        if trade:
            tracks.append(("BOT_ACTUAL", trade.exit_bar, bot_reason, bot_bars))
        for track, position, reason, held in tracks:
            end = bars.iloc[position]
            end_at = end.ts_utc + BAR_SIZE
            exit_identity = keys.identify(market, symbol, asset, end_at, end.trading_date)
            exit_identity["event_id"] = identity["event_id"]
            tables["exit"].append({
                **exit_identity, **common, **snapshot(bars, position, market, context, cost_bp=bp),
                "exit_track": track, "exit_reason": reason,
                "bot_exit_reason": bot_reason if track == "BOT_ACTUAL" else None,
                "bars_held": held, "move_since_entry_atr": float(direction * (end.close - bar.close) / atr),
            })

        tables["event_map"].append({
            **identity, "market": market, "symbol": symbol, "signal_time": at.isoformat(),
            "trading_date": bar.trading_date.isoformat(), "status": status,
            "bot_exit_reason": trade.exit_reason if trade else None,
            "bot_gross_r": trade.r_gross if trade else None, "bot_net_r": trade.r_net if trade else None,
        })
    return tables
