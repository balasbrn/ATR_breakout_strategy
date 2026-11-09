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

Use the Trade555 validated v1.1 root as a runtime GCS prefix. Keep the canonical
output outside the repository on atr-free.

```sh
atr-bo convert --market US --phase study --source "$validated_prefix" --out "$study_data"
```

The converter reads the audited symbol files, keeps valid and usable rows from
each symbol's audit start date, and writes one local Parquet partition per
trading date. US uses raw regular-session OHLC, ignores adjustment factors, and
keeps GOOGL as the sole Alphabet share class.
NSE keeps delivered adjusted OHLC. FX and gold use all eight symbols and drop
tick volume. The crypto screen reads only eligible timestamps and flag columns,
counts annual coverage before converting prices, and excludes 2025 onward.
The runner fills isolated crypto gaps in the canonical input.

Study price scans end at the frozen DEV/OOS boundary. Arrow filters at read,
then the reader masks each batch again before conversion sees it. A mixed row
group may be decoded internally, and the manifest records the number that
straddled the cutoff based only on footer timestamp bounds. Out-of-window
prices never enter conversion statistics, logs, or output partitions.
The manifest records source file sizes and modification times, audit checksums,
and the SHA-256 of each canonical partition. The GCS prefix is supplied only
at runtime.

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
   For validated-layer input, convert reserved prices to a separate directory
   only after both stages pass. The original study manifest stays byte-identical.

   ```sh
   atr-bo convert --market US --phase holdout --source "$validated_prefix" \
     --study-data "$study_data/minutes.json" --run "$run_dir" \
     --archive "$archive_prefix" --out "$reserved_data"
   atr-bo holdout --market US --data "$study_data/minutes.json" \
     --holdout-data "$reserved_data/minutes.json" --out "$run_dir" --archive "$archive_prefix"
   ```

   Conversion and simulation each have one claim. Conversion archives its
   claim under `holdout-conversion-claims/` before reading reserved source prices.
   Simulation verifies the study evidence and the linkage between manifests,
   then claims and archives the single execution before reading canonical prices.
4. The canonical dataset directory must be writable for the exclusive holdout
   claim. Before opening any price partition, the runner archives and verifies
   the claim plus `stage_a.json`, `stage_b.json`, and `pass.json`. The runner
   first checks both remote claim paths, which requires list access. It stores
   a claim at `<prefix>/holdout-claims/v1-<market>-<manifest_sha256>.claim`
   and a copy in the run archive. A failed check, upload, or verification
   stops the run and leaves the attempt spent. Preserve the claim in the
   canonical dataset directory. If the VM is replaced, restore the archived
   run files and claim. Keep the same archive prefix. The fixed claim blocks
   a new attempt for that manifest even if the local claim and run ID change.
5. For cards, use `atr-bo cards --schema <pinned-schema.json>` with the same data
   and market arguments and a fresh private output directory. Only DEV and OOS
   are used. For US or NSE, generate the DEV/OOS schedule with
   `atr-bo sessions --market US --out <schedule.json>` (use `NSE` for India),
   then pass `--sessions <schedule.json>` to the cards command. Keep the schedule
   beside the data. The JSON records the calendar version and UTC session times.
   Higher timeframes use the same authorized minutes. Publish only the export's
   `public/` directory. Liquidity and benchmark context are separate follow-ups.
6. Archive the metrics and checksums for the report. Include a reporting caveat
   that the frozen NSE universe includes indices such as INDIA_VIX and that
   equity costs may not apply to them. Show NSE results both with and without
   the indices, using the full universe for the primary verdict. Review moved-stop
   open-price diagnostics separately from overnight gaps, and the count of
   crypto exits after more than 20 UTC slots. This CLI produces JSON metrics.
   Private per-trade delivery and filling the frozen report template are
   follow-up integration tasks before publishing research results.

## Streaming and VM memory budget

The CLI verifies and aggregates one authorized trading-date partition at a
time. It releases the minute frame before opening the next file and retains
the 15-minute bars, plus H1, H4, and daily bars for cards. Crypto keeps one
observed minute per symbol from the previous partition so gaps of at most
three minutes can be filled across UTC midnight. Longer gaps stay missing.
The annual crypto completeness screen runs during validated-layer conversion.

These are planning estimates for DEV/OOS cards on atr-free (4 OCPU, 24 GB),
using dense bar counts and allowing for pandas aggregation, indicator frames,
and card export buffers. They are estimates of process peak memory, not VM
measurements. The numbers vary with coverage, eligible symbols, and card counts.

| Market | Estimated retained 15-minute rows | Expected peak memory |
|---|---:|---:|
| US | ~1.1 million (50 symbols) | 1–3 GiB |
| NSE | ~11.7 million (233 symbols) | 7–11 GiB |
| Crypto | up to ~1.1 million (3 coins, 10 years each) | 1–3 GiB |
| FX and gold | ~2.4 million (8 instruments assumed) | 2–4 GiB |

The acceptance target is below 12 GB peak RSS for NSE DEV/OOS cards.
Record the actual peak RSS on atr-free before treating that target as verified.

### Measure the synthetic NSE cards run on atr-free

On Linux, activate the editable environment from the repository root and supply
the pinned Trade555 card schema. The script generates a new synthetic fixture,
runs the actual cards CLI with GNU `/usr/bin/time -v`, and prints peak RSS.
It saves the full timing log as `cards.time.txt` and the card counts in
`cards/public/manifest.json`. The generator writes 233 synthetic symbols and
375 minutes per XBOM session from 09:15 to 15:30 Kolkata time by default.

```sh
scripts/nse_memory_check.sh "$(mktemp -d)" /path/to/event_card_v2.json
```

The default is one calendar year (2015). For a small functional check, add
`1 2` as the last two arguments. To measure the full 2015–2022 DEV/OOS span,
keep 233 symbols and set the year argument to `8`. Use a fresh output directory
and allow disk space for the larger fixture and card export.

```sh
scripts/nse_memory_check.sh "$(mktemp -d)" /path/to/event_card_v2.json 8
```

The eight-year fixture has about eight times as many retained bars as the
one-year fixture. The one-year RSS is a sizing check. Compare the measured
eight-year peak against 12,000,000,000 bytes (11,718,750 KiB) to verify the
target. Both commands use synthetic data and omit the bucket archive.
