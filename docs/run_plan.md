# v1 pre-run review

The CLI runs on canonical minute files. The dry run uses generated data only.
The reviewed commit, frozen contract, and manifest should be fixed before running
any vendor inputs. The historical report remains pending through this review.

## Reproduce the dry run

From an editable installation of this repository, run:

```sh
python -m pip install -e '.[test]'
python -m pytest -q
run_root=$(mktemp -d)
python -m synthetic.generate --out "$run_root/fixture"
atr-bo stage-a --data "$run_root/fixture/minutes.json" --market CRYPTO --out "$run_root/study"
atr-bo stage-b --data "$run_root/fixture/minutes.json" --market CRYPTO --out "$run_root/study"
atr-bo holdout --data "$run_root/fixture/minutes.json" --market CRYPTO --out "$run_root/study"
```

The last command must fail. The fixture has one symbol, so removing the top
contributor leaves no observations. The tests separately exercise an authorized
synthetic holdout and verify that a second attempt fails.

## Input handoff

Put the manifest and Parquet partitions outside the repository. Use one file per
market trading date. Each file uses the canonical minute schema and contains one
market's symbols for that date. The manifest lists the full set of partitions,
including reserved dates, using relative paths and SHA-256 checksums.

```json
{
  "market": "US",
  "synthetic": false,
  "partitions": [
    {"date": "2021-01-04", "path": "2021-01-04.parquet", "sha256": "<64 hex digits>"}
  ]
}
```

Vendor normalization and the symbol manifest are input prerequisites. The real
crypto command refuses to load prices pending the approved annual completeness
and isolated-gap adapter. Crypto coverage for holdout years must be gathered
from minute-count metadata. The coverage step must not open reserved prices.

## Sequence after owner review

Pass `--archive <gs://bucket/prefix>` to `stage-a`, `stage-b`, `holdout`, and
`cards`. It is required for real runs and optional for synthetic runs. Supply
the destination at runtime and use a private bucket because the card archive
includes the private event map. The output directory basename is the run ID.
Use the same archive prefix and run ID for both study stages and holdout, and
a separate run ID for cards. The recorded command redacts the destination.

After each command, the CLI copies the output tree to `<prefix>/<run-id>/` with
`gcloud storage cp --no-clobber`. It streams each stored object back to check its
byte count and SHA-256. Existing objects must match exactly. An upload or
verification failure exits with an error. Wait for successful verification
before advancing to the next step.

1. Run `stage-a` once per market with a new output directory. Save the gross verdict
   and metrics before any net computations. Record the command, code revision,
   manifest digest, and input checksums.
2. Run `stage-b` against the same manifest and directory. Stage B checks Stage A's
   provenance and input checksums, then runs base and stress separately even
   when gross fails. The random benchmark draws with replacement. Rules 1–3
   apply to each period and the combined t-statistic clusters by the signal's
   trading date. A one-symbol spoke cannot pass the best-symbol removal rule.
3. Review `stage_a.json`, `stage_b.json`, and `pass.json` before running
   `holdout`. The runner checks both verdicts and stage hashes against the
   manifest, market, and code commit before opening holdout price partitions.
   DEV and OOS bars then provide indicator warmup. Only holdout signals enter
   the holdout simulation. Crypto 2025+ is outside every permitted range.
4. The canonical dataset directory must be writable for the exclusive holdout
   claim. Before opening any price partition, the runner archives and verifies
   the claim plus `stage_a.json`, `stage_b.json`, and `pass.json`. An upload or
   verification failure stops the run and leaves the attempt spent. Preserve
   the claim in the canonical dataset directory. If the VM is replaced,
   restore the archived run files and claim to their original locations.
   Keep the same archive prefix and run ID so any existing remote claim
   blocks a new attempt even if the local claim was lost.
5. For cards, use `atr-bo cards --schema <pinned-schema.json>` with the same data
   and market arguments and a fresh private output directory. Only DEV and OOS
   are used. For US or NSE, generate the DEV/OOS schedule with
   `atr-bo sessions --market US --out <schedule.json>` (use `NSE` for India),
   then pass `--sessions <schedule.json>` to the cards command. Keep the schedule
   beside the data. The JSON records the calendar version and UTC session times.
   Higher timeframes use the same authorized minutes. Publish only the export's
   `public/` directory. Liquidity and benchmark context are separate follow-ups.
6. Archive the metrics and checksums for the report. Review moved-stop
   open-price diagnostics separately from overnight gaps, and the count of
   crypto exits after more than 20 UTC slots. This CLI produces JSON metrics.
   Private per-trade delivery and filling the frozen report template are
   follow-up integration tasks before publishing research results.
