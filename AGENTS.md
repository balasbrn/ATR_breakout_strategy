# AGENTS.md — rules for every coding agent in this repository

Read this file, then [INDEX.md](INDEX.md), before writing any code. They apply to Codex, Claude
and any other agent.

## 1. What we are building

One run over historical 1-minute data that does two jobs:

1. **Tests the frozen v1 contract** ([v1/contract.md](v1/contract.md)): Stage A (gross), then
   Stage B (net), the benchmarks and the pass rule, and fills in [v1/report.md](v1/report.md).
2. **Writes an event card for every v1 signal**, in the `event_card_v2` format described in
   [docs/event_cards.md](docs/event_cards.md). The cards are exported to a private location for a
   separate ML project. They are **never committed** here.

It also writes one **per-trade results file** (columns in [docs/outputs.md](docs/outputs.md)),
which a later Monte Carlo project reads. Nothing else links the projects.

## 2. Non-negotiable rules

1. **The contract is frozen.** Never edit anything in `v1/` except filling the "pending" cells of
   `v1/report.md` from a run. If code and contract disagree, the contract wins: stop and report.
   Do not "improve" a rule, parameter, cost or date. A change is a new version folder, decided by
   the owner.
2. **No market data, cards, keys or bucket names in the repository.** Real data stays outside the
   repo. Results, counts and checksums are committed; data is not. Paths to real data come from
   the command line or an environment variable, never from code.
3. **Holdout is locked.** The code must refuse to read any date inside a market's holdout window
   (contract §8) unless a pass file written by the Stage A and Stage B run exists and says both
   stages passed. No flag bypasses this in normal use. Crypto 2025+ is never read (contract §2).
4. **Stage A before Stage B.** Stage A results are written to their own file before Stage B is
   computed (contract §6).
5. **Tests use synthetic data only.** No test downloads anything or reads real data. Every test is
   deterministic (fixed seeds).
6. **Small, modular code.** Follow the layout in [INDEX.md](INDEX.md): one job per module, a
   module under about 300 lines, pure functions where possible, no module reaches into another's
   internals. A change should touch one module and its test, not the whole codebase.
7. **Every contract rule has a test** that names its section, e.g. `test_gap_rule_s5`. A rule
   without a test is not done.
8. **Every report names** the contract version, the code commit, the command, and the sha256 of
   each input file.

## 3. Workflow

1. Work on a branch (`codex/<topic>` or `claude/<topic>`), never directly on `main`.
2. Build in the order of [INDEX.md](INDEX.md) §3. One module (or one small group) per pull request
   keeps reviews short.
3. Before pushing: `python -m pytest -q` passes, and `git status` shows no data files.
4. Open a pull request with: what changed, which contract sections it implements, how it was
   tested, and what was **not** tested.
5. **Reviews arrive as pull-request comments.** Read them all, fix or answer each one, push, and
   reply in the thread with the commit. Do not merge your own pull request; the owner merges.

## 4. Stack

Python 3.11+, `numpy`, `pandas`, `pyarrow`, `pytest`. Nothing else without a reason in the pull
request. No notebooks in `src/`. Configuration constants from the contract live in one module
(`src/atr_breakout/contract_v1.py`), each with the contract section it comes from.

## 5. When in doubt

Ask in the pull request instead of guessing. Ambiguity in the contract is reported, not resolved
silently: list it under "Open questions" in the pull request.
