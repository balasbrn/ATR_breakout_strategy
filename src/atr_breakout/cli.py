"""Command line for the pre-run v1 study and holdout review."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

from atr_breakout.cards.anonymise import CardKeys
from atr_breakout.cards.outcome import build_cards
from atr_breakout.cards.writer import write_cards
from atr_breakout.contract_v1 import STUDY_WINDOWS
from atr_breakout.data.partitions import load_minutes, open_dataset
from atr_breakout.runner import holdout_case, prepare_bars, strategy, study_case
from atr_breakout.study.passrule import holdout_passed, read_stage_a, write_stage_a, write_stage_b
from atr_breakout.core.costs import cost_basis_points


def _code_commit(*, require_clean: bool) -> str:
    source = Path(__file__).resolve().parent
    if require_clean:
        changed = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all", "--",
             ":/src", ":/pyproject.toml", ":/v1/contract.md"],
            check=True, capture_output=True, text=True, cwd=source,
        )
        if changed.stdout:
            raise ValueError("A real run requires clean committed code and contract files")
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
        cwd=source,
    )
    commit = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Could not identify the source checkout")
    return commit


def _write(path, record):
    payload = json.dumps(record, indent=2, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as output:
        output.write(payload)


def _run(args, command):
    dataset = open_dataset(args.data, args.market)
    commit = _code_commit(require_clean=not dataset.synthetic)
    provenance = dataset.provenance(commit)
    if args.action == "stage-b":
        read_stage_a(args.out, provenance)
    holdout_run = args.out if args.action == "holdout" else None
    if holdout_run and any((holdout_run / name).exists() for name in ("holdout_gross.json", "holdout.json")):
        raise ValueError("Holdout output already exists")
    minutes, checksums = load_minutes(dataset, commit=commit, holdout_run=holdout_run)
    frames = prepare_bars(minutes, args.market)
    provenance["input_sha256"] = checksums
    execution = {
        "command": command,
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    if args.action == "stage-a":
        verdict, metrics = study_case(frames, args.market, "gross")
        write_stage_a(args.out, provenance, verdict)
        _write(args.out / "gross_metrics.json", {**provenance, **execution, "gross": metrics})
    elif args.action == "stage-b":
        cases = {}

        def evaluate(case):
            verdict, metrics = study_case(frames, args.market, case)
            cases[case] = metrics
            return verdict

        passed = write_stage_b(args.out, provenance, evaluate)
        _write(args.out / "net_metrics.json", {**provenance, **execution, **cases, "passed": passed})
    elif args.action == "holdout":
        gross = holdout_case(frames, args.market, "gross")
        _write(args.out / "holdout_gross.json", {**provenance, **execution, "gross": gross})
        base = holdout_case(frames, args.market, "base")
        _write(args.out / "holdout.json", {
            **provenance, **execution, "gross": gross, "base": base,
            "passed": holdout_passed(gross["mean_r"], base["mean_r"]),
        })
    else:
        keys = CardKeys({args.market: min(bars["trading_date"].min() for bars in frames.values())})
        tables = {name: [] for name in ("entry", "exit", "outcome", "event_map")}
        for _, bars, directions, purity, actual in strategy(
            frames, args.market, cost_basis_points(args.market, "base"),
        ):
            cards = build_cards(bars, directions, actual, market=args.market, keys=keys, purity=purity)
            for name in tables:
                tables[name].extend(cards[name])
        write_cards(
            args.out, tables, schema_path=args.schema, code_commit=commit, synthetic=dataset.synthetic,
        )


def main(argv=None):
    parser = argparse.ArgumentParser(prog="atr-bo")
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("stage-a", "stage-b", "holdout", "cards"):
        action = actions.add_parser(name)
        action.add_argument("--data", required=True, type=Path, help="Canonical minute manifest")
        action.add_argument("--market", required=True, choices=STUDY_WINDOWS)
        action.add_argument("--out", required=True, type=Path, help="Run directory or private card destination")
        if name == "cards":
            action.add_argument("--schema", required=True, type=Path, help="Pinned Trade555 schema")
    argv = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(argv)
    try:
        _run(args, shlex.join(["atr-bo", *argv]))
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"atr-bo: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
