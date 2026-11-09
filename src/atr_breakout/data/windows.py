"""Verify stage evidence and authorize market trading dates before input I/O."""

from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from uuid import uuid4

from atr_breakout.contract_v1 import STUDY_WINDOWS
from atr_breakout.study.passrule import StageVerdict, WindowVerdict


class HoldoutLocked(ValueError):
    """The supplied run cannot authorize a holdout read."""


def allowed_dates(market: str, *, holdout: bool) -> tuple[date | None, date]:
    dev, oos, reserved = STUDY_WINDOWS[market]
    return reserved if holdout else (dev[0], oos[1])


def _passed(record: dict) -> bool:
    for name in ("dev", "oos"):
        window = record[name]
        if type(window["count"]) is not int or window["count"] <= 0:
            return False
        if any(
            type(window[key]) not in (int, float) or not math.isfinite(window[key])
            for key in ("mean_r", "random_mean_r", "mean_without_best")
        ):
            return False
    t = record["clustered_t"]
    if type(t) not in (int, float) or not math.isfinite(t):
        return False
    verdict = StageVerdict(
        WindowVerdict(**record["dev"]), WindowVerdict(**record["oos"]), record["clustered_t"],
    )
    return verdict.passed


def require_holdout_pass(run: Path, provenance: dict) -> None:
    """Fail closed on missing, mismatched, or failed DEV/OOS evidence."""
    try:
        gate = json.loads((run / "pass.json").read_bytes())
        if any(gate[key] != value for key, value in provenance.items()):
            raise HoldoutLocked("Holdout pass does not match this input, code, and market")
        checksums = None
        for stage, case in (("a", "gross"), ("b", "base")):
            payload = (run / f"stage_{stage}.json").read_bytes()
            if gate[f"stage_{stage}_sha256"] != hashlib.sha256(payload).hexdigest():
                raise HoldoutLocked("Holdout stage artifact checksum does not match")
            record = json.loads(payload)
            if any(record[key] != value for key, value in provenance.items()):
                raise HoldoutLocked("Holdout stage provenance does not match")
            if stage == "a":
                checksums = record["input_sha256"]
            elif record["input_sha256"] != checksums:
                raise HoldoutLocked("Stage input checksums disagree")
            if (
                gate[f"stage_{stage}_passed"] is not True
                or record["passed"] is not True
                or not _passed(record[case])
            ):
                raise HoldoutLocked("Holdout requires both gross and base stages to pass")
    except (OSError, KeyError, TypeError, AttributeError, json.JSONDecodeError) as error:
        raise HoldoutLocked("Holdout requires valid Stage A, Stage B, and pass files") from error


def claim_holdout(
    manifest: Path, market: str, provenance: dict, *, purpose: str = "holdout",
) -> Path:
    """Reserve the single v1 holdout attempt for this dataset and market."""
    claim = manifest.parent / f".v1-{market}-{purpose}.claim"
    try:
        with claim.open("x") as output:
            json.dump({
                **provenance,
                "attempt_id": str(uuid4()),
                "claimed_at_utc": datetime.now(timezone.utc).isoformat(),
            }, output)
    except FileExistsError as error:
        raise HoldoutLocked("This dataset and market already claimed its v1 holdout") from error
    return claim
