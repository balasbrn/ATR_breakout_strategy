"""Command line for the pre-run v1 study and holdout review."""

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

import pyarrow.fs as arrow_fs

from atr_breakout.archive import archive_destination, archive_directory, archive_holdout_evidence
from atr_breakout.cards.anonymise import CardKeys
from atr_breakout.cards.entry import CardContext
from atr_breakout.cards.outcome import build_cards
from atr_breakout.cards.writer import write_cards
from atr_breakout.contract_v1 import STUDY_WINDOWS
from atr_breakout.data.partitions import iter_minute_partitions, open_dataset
from atr_breakout.data.sessions import CALENDARS, session_schedule
from atr_breakout.data.validated import convert_validated
from atr_breakout.data.windows import claim_holdout, require_holdout_pass
from atr_breakout.runner import holdout_case, prepare_partitioned_bars, strategy, study_case
from atr_breakout.study.passrule import holdout_passed, read_stage_a, write_stage_a, write_stage_b
from atr_breakout.core.costs import cost_basis_points
from atr_breakout.trade_export import trade_digest, write_trade_export


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


def _convert(args):
    if not args.source.startswith("gs://"):
        raise ValueError("Conversion requires a runtime GCS source prefix")
    if args.out.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        raise ValueError("Write canonical market data outside the source checkout")

    study = authorize = None
    if args.phase == "holdout":
        if not all((args.study_data, args.run, args.archive)):
            raise ValueError("Holdout conversion requires --study-data, --run, and --archive")
        study = open_dataset(args.study_data, args.market)
        commit = _code_commit(require_clean=True)
        provenance = study.provenance(commit)
        require_holdout_pass(args.run, provenance)
        destination = archive_destination(args.archive, args.run)
        purpose = "holdout-conversion"

        def authorize():
            require_holdout_pass(args.run, provenance)
            claim = claim_holdout(study.manifest, study.market, provenance, purpose=purpose)
            archive_holdout_evidence(
                args.run, claim, destination, market=study.market, manifest_sha256=study.sha256,
                purpose=purpose,
            )
    elif args.study_data or args.run or args.archive:
        raise ValueError("--study-data, --run, and --archive apply only to holdout conversion")

    filesystem, root = arrow_fs.FileSystem.from_uri(args.source)
    manifest = convert_validated(
        filesystem, root, args.out, market=args.market, study=study, authorize_holdout=authorize,
    )
    print(manifest)


def _verify_trade_snapshot(directory, metrics_file):
    expected = json.loads((directory / metrics_file).read_bytes())["trades_sha256"]
    if trade_digest(directory) != expected:
        raise ValueError("trades.parquet checksum differs from the recorded snapshot")


def _run(args, command):
    if args.action == "sessions":
        _write(args.out, session_schedule(args.market))
        return
    if args.action == "convert":
        _convert(args)
        return
    dataset = open_dataset(args.data, args.market)
    if not dataset.synthetic and not args.archive:
        raise ValueError("Real runs require --archive")
    destination = archive_destination(args.archive, args.out) if args.archive else None
    commit = _code_commit(require_clean=not dataset.synthetic)
    provenance = dataset.provenance(commit)
    if args.action == "stage-b":
        read_stage_a(args.out, provenance)
        _verify_trade_snapshot(args.out, "gross_metrics.json")
    holdout_run = args.out if args.action == "holdout" else None
    if holdout_run and any((holdout_run / name).exists() for name in ("holdout_gross.json", "holdout.json")):
        raise ValueError("Holdout output already exists")
    if holdout_run and (not dataset.synthetic or (args.out / "net_metrics.json").is_file()):
        _verify_trade_snapshot(args.out, "net_metrics.json")

    def archive_claim(claim: Path) -> None:
        archive_holdout_evidence(
            holdout_run, claim, destination, market=dataset.market, manifest_sha256=dataset.sha256,
        )

    sessions = None
    if args.action == "cards" and args.sessions:
        sessions = json.loads(args.sessions.read_text())
        if isinstance(sessions, dict):
            if sessions["market"] != args.market:
                raise ValueError("Session schedule market does not match the cards market")
            sessions = sessions["sessions"]
    partitions = iter_minute_partitions(
        dataset, commit=commit, holdout_run=holdout_run,
        archive_claim=archive_claim if holdout_run and destination else None,
        holdout_data=open_dataset(args.holdout_data, args.market)
        if holdout_run and getattr(args, "holdout_data", None) else None,
    )
    frames, higher, checksums = prepare_partitioned_bars(
        partitions, args.market, cards=args.action == "cards", sessions=sessions,
    )
    provenance["input_sha256"] = checksums
    execution = {
        "command": command,
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    if args.action == "stage-a":
        with write_trade_export(args.out, args.market, append=False) as export:
            verdict, metrics = study_case(frames, args.market, "gross", record=export.record)
            write_stage_a(args.out, provenance, verdict)
        _write(args.out / "gross_metrics.json", {
            **provenance, **execution, "gross": metrics, "trades_sha256": trade_digest(args.out),
        })
    elif args.action == "stage-b":
        cases = {}
        with ExitStack() as stack:
            export = stack.enter_context(write_trade_export(args.out, args.market, append=True))

            def evaluate(case):
                verdict, metrics = study_case(frames, args.market, case, record=export.record)
                cases[case] = metrics
                return verdict

            passed = write_stage_b(args.out, provenance, evaluate, before_publish=stack.close)
        _write(args.out / "net_metrics.json", {
            **provenance, **execution, **cases, "passed": passed, "trades_sha256": trade_digest(args.out),
        })
    elif args.action == "holdout":
        with write_trade_export(args.out, args.market, append=True) as export:
            gross = holdout_case(frames, args.market, "gross", record=export.record)
            _write(args.out / "holdout_gross.json", {**provenance, **execution, "gross": gross})
            base = holdout_case(frames, args.market, "base", record=export.record)
        _write(args.out / "holdout.json", {
            **provenance, **execution, "gross": gross, "base": base,
            "passed": holdout_passed(gross["mean_r"], base["mean_r"]),
            "trades_sha256": trade_digest(args.out),
        })
    else:
        keys = CardKeys({args.market: min(bars["trading_date"].min() for bars in frames.values())})
        tables = {name: [] for name in ("entry", "exit", "outcome", "event_map")}
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
        trade_phase = args.action if args.action in ("stage-a", "stage-b", "holdout") else None
        archive_directory(args.out, destination, trade_phase=trade_phase)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="atr-bo")
    actions = parser.add_subparsers(dest="action", required=True)
    sessions = actions.add_parser("sessions", help="Generate the DEV/OOS cash-session schedule")
    sessions.add_argument("--market", required=True, choices=CALENDARS)
    sessions.add_argument("--out", required=True, type=Path, help="New schedule JSON file")
    convert = actions.add_parser("convert", help="Convert Trade555 validated symbol files")
    convert.add_argument("--source", required=True, help="Runtime gs:// validated-layer prefix")
    convert.add_argument("--market", required=True, choices=STUDY_WINDOWS)
    convert.add_argument("--phase", required=True, choices=("study", "holdout"))
    convert.add_argument("--out", required=True, type=Path, help="Fresh canonical output directory")
    convert.add_argument("--study-data", type=Path, help="Study manifest for holdout conversion")
    convert.add_argument("--run", type=Path, help="Study stage evidence directory for holdout conversion")
    convert.add_argument("--archive", help="Private archive prefix for the holdout conversion claim")
    for name in ("stage-a", "stage-b", "holdout", "cards"):
        action = actions.add_parser(name, allow_abbrev=False)
        action.add_argument("--data", required=True, type=Path, help="Canonical minute manifest")
        action.add_argument("--market", required=True, choices=STUDY_WINDOWS)
        action.add_argument("--out", required=True, type=Path, help="Run directory or private card destination")
        action.add_argument("--archive", help="Archive destination prefix (required for real runs)")
        if name == "holdout":
            action.add_argument("--holdout-data", type=Path, help="Separately converted holdout manifest")
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
