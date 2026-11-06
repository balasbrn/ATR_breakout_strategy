"""Command line for the pre-run v1 study and holdout review."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

from atr_breakout.archive import archive_destination, archive_directory, archive_holdout_evidence
from atr_breakout.cards.anonymise import CardKeys
from atr_breakout.cards.context import higher_timeframes
from atr_breakout.cards.entry import CardContext
from atr_breakout.cards.outcome import build_cards
from atr_breakout.cards.writer import write_cards
from atr_breakout.contract_v1 import STUDY_WINDOWS
from atr_breakout.data.partitions import load_minutes, open_dataset
from atr_breakout.data.sessions import CALENDARS, session_schedule
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
    if args.action == "sessions":
        _write(args.out, session_schedule(args.market))
        return
    dataset = open_dataset(args.data, args.market)
    if not dataset.synthetic and not args.archive:
        raise ValueError("Real runs require --archive")
    destination = archive_destination(args.archive, args.out) if args.archive else None
    commit = _code_commit(require_clean=not dataset.synthetic)
    provenance = dataset.provenance(commit)
    if args.action == "stage-b":
        read_stage_a(args.out, provenance)
    holdout_run = args.out if args.action == "holdout" else None
    if holdout_run and any((holdout_run / name).exists() for name in ("holdout_gross.json", "holdout.json")):
        raise ValueError("Holdout output already exists")
    def archive_claim(claim: Path) -> None:
        archive_holdout_evidence(holdout_run, claim, destination)

    minutes, checksums = load_minutes(
        dataset, commit=commit, holdout_run=holdout_run,
        archive_claim=archive_claim if holdout_run and destination else None,
    )
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
        sessions = json.loads(args.sessions.read_text()) if args.sessions else None
        if isinstance(sessions, dict):
            if sessions["market"] != args.market:
                raise ValueError("Session schedule market does not match the cards market")
            sessions = sessions["sessions"]
        higher = higher_timeframes(minutes, args.market, sessions=sessions)
        for symbol, bars, directions, purity, actual in strategy(
            frames, args.market, cost_basis_points(args.market, "base"),
        ):
            cards = build_cards(
                bars, directions, actual, market=args.market, keys=keys, purity=purity,
                context=CardContext(higher=higher.get(symbol, {})),
            )
            for name in tables:
                tables[name].extend(cards[name])
        write_cards(
            args.out, tables, schema_path=args.schema, code_commit=commit, synthetic=dataset.synthetic,
        )
    if destination:
        archive_directory(args.out, destination)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="atr-bo")
    actions = parser.add_subparsers(dest="action", required=True)
    sessions = actions.add_parser("sessions", help="Generate the DEV/OOS cash-session schedule")
    sessions.add_argument("--market", required=True, choices=CALENDARS)
    sessions.add_argument("--out", required=True, type=Path, help="New schedule JSON file")
    for name in ("stage-a", "stage-b", "holdout", "cards"):
        action = actions.add_parser(name, allow_abbrev=False)
        action.add_argument("--data", required=True, type=Path, help="Canonical minute manifest")
        action.add_argument("--market", required=True, choices=STUDY_WINDOWS)
        action.add_argument("--out", required=True, type=Path, help="Run directory or private card destination")
        action.add_argument("--archive", help="Archive destination prefix (required for real runs)")
        if name == "cards":
            action.add_argument("--schema", required=True, type=Path, help="Pinned Trade555 schema")
            action.add_argument("--sessions", type=Path, help="Required US/NSE UTC session schedule JSON")
    argv = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(argv)
    try:
        archive = getattr(args, "archive", None)
        recorded = [
            item.replace(archive, "<runtime-uri>") if archive and item in (archive, f"--archive={archive}") else item
            for item in argv
        ]
        _run(args, shlex.join(["atr-bo", *recorded]))
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"atr-bo: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
