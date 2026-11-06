"""Evaluate the v1 pass rule and write per-market stage artifacts."""

from collections.abc import Callable
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from atr_breakout.contract_v1 import MIN_CLUSTERED_T, STUDY_WINDOWS
from atr_breakout.core.costs import CostCase
from atr_breakout.study.stats import clustered_t, mean_r, without_best_symbol


@dataclass(frozen=True)
class WindowVerdict:
    count: int
    mean_r: float | None
    random_mean_r: float | None
    mean_without_best: float | None

    @property
    def passed(self) -> bool:
        return (
            self.mean_r is not None and self.mean_r > 0
            and self.random_mean_r is not None and self.mean_r > self.random_mean_r
            and self.mean_without_best is not None and self.mean_without_best > 0
        )


@dataclass(frozen=True)
class StageVerdict:
    dev: WindowVerdict
    oos: WindowVerdict
    clustered_t: float | None

    @property
    def passed(self) -> bool:
        return (
            self.dev.passed and self.oos.passed
            and self.clustered_t is not None and self.clustered_t >= MIN_CLUSTERED_T
        )


def _window_verdict(trades: pd.DataFrame, random_mean: float | None) -> WindowVerdict:
    if trades[["r", "symbol", "trading_date"]].isna().any().any():
        raise ValueError("Taken trades require R, symbol, and trading date")
    if not np.isfinite(trades["r"].to_numpy(dtype=float)).all():
        raise ValueError("Taken trade returns must be finite")
    if random_mean is not None and not np.isfinite(random_mean):
        raise ValueError("Random benchmark mean must be finite")
    return WindowVerdict(len(trades), mean_r(trades["r"]), random_mean, without_best_symbol(trades))


def evaluate_stage(
    dev: pd.DataFrame, oos: pd.DataFrame, *,
    dev_random_mean: float | None, oos_random_mean: float | None,
) -> StageVerdict:
    """Evaluate one market and cost case using taken trades' signed R."""
    return StageVerdict(
        _window_verdict(dev, dev_random_mean),
        _window_verdict(oos, oos_random_mean),
        clustered_t(pd.concat([dev, oos], ignore_index=True)),
    )


def _write_json(path: Path, record: dict) -> str:
    contents = (json.dumps(record, indent=2, allow_nan=False) + "\n").encode()
    with path.open("xb") as output:
        output.write(contents)
    return hashlib.sha256(contents).hexdigest()


def write_stage_a(directory: Path, provenance: dict, gross: StageVerdict) -> None:
    """Record the gross verdict before base or stress is evaluated."""
    if provenance["market"] not in STUDY_WINDOWS:
        raise ValueError("Unknown market")
    directory.mkdir(mode=0o700)
    _write_json(directory / "stage_a.json", {
        **provenance, "gross": asdict(gross), "passed": gross.passed,
    })


def read_stage_a(directory: Path, provenance: dict) -> tuple[bool, str]:
    payload = (directory / "stage_a.json").read_bytes()
    record = json.loads(payload)
    if any(record.get(key) != value for key, value in provenance.items()):
        raise ValueError("Stage A provenance differs from Stage B inputs")
    gross = record["gross"]
    verdict = StageVerdict(
        WindowVerdict(**gross["dev"]), WindowVerdict(**gross["oos"]), gross["clustered_t"],
    )
    if record["passed"] is not verdict.passed:
        raise ValueError("Stage A verdict is inconsistent")
    return verdict.passed, hashlib.sha256(payload).hexdigest()


def write_stage_b(
    directory: Path, provenance: dict, evaluate: Callable[[CostCase], StageVerdict],
) -> bool:
    """Check recorded gross evidence before invoking either net evaluation."""
    gross_passed, gross_hash = read_stage_a(directory, provenance)
    if (directory / "stage_b.json").exists() or (directory / "pass.json").exists():
        raise FileExistsError("Stage B output already exists")
    # Claim before net evaluation to exclude concurrent calls.
    with (directory / ".stage_b.claim").open("x"):
        pass
    base = evaluate("base")
    stress = evaluate("stress")
    net_hash = _write_json(directory / "stage_b.json", {
        **provenance, "base": asdict(base), "stress": asdict(stress), "passed": base.passed,
    })
    _write_json(directory / "pass.json", {
        **provenance,
        "stage_a_passed": gross_passed, "stage_b_passed": base.passed,
        "stage_a_sha256": gross_hash, "stage_b_sha256": net_hash,
    })
    return gross_passed and base.passed


def write_stage_run(
    directory: Path, market: str, evaluate: Callable[[CostCase], StageVerdict],
) -> bool:
    """Run one market in a new directory and write holdout eligibility last."""
    if directory.exists():
        raise FileExistsError(directory)
    provenance = {"contract": "v1", "market": market}
    write_stage_a(directory, provenance, evaluate("gross"))
    return write_stage_b(directory, provenance, evaluate)


def holdout_passed(gross_mean: float | None, base_mean: float | None) -> bool:
    return all(value is not None and np.isfinite(value) and value > 0
               for value in (gross_mean, base_mean))
