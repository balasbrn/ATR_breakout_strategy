# ATR_breakout_strategy

Pre-registered research on one trading idea: **after volatility has been unusually quiet, does a
strong 15-minute close beyond the last 20 bars' high or low keep moving far enough to pay for
itself?** It is tested first before costs (is there any edge?), then after costs (is it still
profitable?), separately for US stocks, NSE stocks, crypto, and FX and gold.

This repository holds the rules, the reports and the references. It contains **no market data**.

## Versions

Each version lives in its own folder. A version's `contract.md` is frozen on the date it states and
is **never edited** afterwards; any change to a rule, parameter, cost or date becomes the next
version, with a note saying what changed and why.

| Version | Frozen | Contract | Report | Status |
|---|---|---|---|---|
| v1 | 2026-11-05 | [v1/contract.md](v1/contract.md) | [v1/report.md](v1/report.md) · [v1/report.html](v1/report.html) | Pre-registered; results pending |

v1 was drafted under the working name "S1"; the contract text keeps that name as written when it was
frozen.

## How results are decided (v1)

1. **Stage A, gross:** no costs. Written down before Stage B is computed.
2. **Stage B, net:** base-case costs (stress case reported beside it).
3. **Pass rule, per market, on development and out-of-sample:** mean R > 0; mean R > a random-entry
   benchmark; mean R > 0 without the best symbol; t ≥ 2 with standard errors clustered by date.
4. **Holdout:** run once, only if both stages pass.

A result that fails is reported as failed. There is no re-tuning within a version.

## Rules for this repository

- Contracts are never edited after freezing. A new rule means a new version folder.
- Every report names its contract version and the code commit that produced it.
- Real market data is never committed (vendor licences). Results, counts and checksums are.
- Synthetic data, when added, is labelled as synthetic and used only to test the code.

## Coming next

- `synthetic/`: a small seeded generator of fake 1-minute price data with a few planted
  "compression, then breakout" patterns, to check the rules are implemented correctly.
- `notebooks/colab_quickstart.ipynb`: runs the v1 rules on the synthetic data in Google Colab.

## References

The research that inspired the idea and shaped the test design: [REFERENCES.md](REFERENCES.md).

## Disclaimer

Research only. Nothing here is investment advice or a recommendation to trade.
