# References

The sources below inspired the idea or shaped the test design. None of them tests this exact rule:
we did not find a peer-reviewed study of an intraday "volatility compression, then breakout" rule
across these markets, which is the gap this project tests. This list is kept separate from the
frozen contracts so that adding a reference never changes a contract.

## The breakout idea

- **Brock, W., Lakonishok, J. and LeBaron, B. (1992).** Simple Technical Trading Rules and the
  Stochastic Properties of Stock Returns. *Journal of Finance*, 47(5), 1731–1764.
  On the Dow Jones 1897–1986, buy signals from a "trading range break" (price above its recent
  high) were followed by higher returns than sell signals. *Used for:* the core rule, a close beyond
  the prior 20-bar high or low, tested here on 15-minute bars.
- **Gao, L., Han, Y., Li, S. Z. and Zhou, G. (2018).** Market Intraday Momentum. *Journal of
  Financial Economics*, 129(2), 394–414.
  The S&P 500's first half-hour return predicts its last half-hour return. *Used for:* support for
  intraday continuation over a few hours (20 bars ≈ 5 hours).
- **Zarattini, C., Barbon, A. and Aziz, A. (2024).** A Profitable Day Trading Strategy for the U.S.
  Equity Market. Swiss Finance Institute Research Paper No. 24-98 (working paper).
  An opening-range breakout on US stocks reported as profitable after costs. An independent,
  non-peer-reviewed replication found the gross effect but little left after spreads. *Used for:*
  the reason this project reports gross and net results separately.

## Why compression first

- **Bollerslev, T. (1986).** Generalized Autoregressive Conditional Heteroskedasticity. *Journal of
  Econometrics*, 31(3), 307–327.
  Volatility clusters and reverts towards its average. *Used for:* waiting for compression (ATR in
  the lowest 20% of its last 30 days) before a breakout.
- **Wilder, J. W. (1978).** *New Concepts in Technical Trading Systems.* Trend Research.
  Practitioner book; defines the Average True Range. *Used for:* ATR(14) with Wilder smoothing.
- **Crabel, T. (1990).** *Day Trading with Short Term Price Patterns and Opening Range Breakout.*
  Traders Press. Practitioner book on narrow ranges followed by expansion. *Used for:* the
  "contraction, then expansion" idea. Not peer-reviewed.

## Guard rails for the test

- **Sullivan, R., Timmermann, A. and White, H. (1999).** Data-Snooping, Technical Trading Rule
  Performance, and the Bootstrap. *Journal of Finance*, 54(5), 1647–1691.
  Re-tested technical rules allowing for the many rules tried; the best rules lost their edge in
  later data. *Used for:* frozen rules, out-of-sample testing and a holdout run once.
- **Park, C.-H. and Irwin, S. H. (2007).** What Do We Know About the Profitability of Technical
  Analysis? *Journal of Economic Surveys*, 21(4), 786–826.
  Many studies report profits, but many have data-snooping, cost or risk problems. *Used for:*
  costs, a random-entry benchmark and the best-symbol-removed check in the pass rule.
- **Harvey, C. R., Liu, Y. and Zhu, H. (2016).** … and the Cross-Section of Expected Returns.
  *Review of Financial Studies*, 29(1), 5–68.
  With many strategies tested, t = 2 is too low a bar; they argue for about 3. *Used for:* context
  for the t ≥ 2 rule: a pass near t = 2 is a first step, not proof.
- **Petersen, M. A. (2009).** Estimating Standard Errors in Finance Panel Data Sets: Comparing
  Approaches. *Review of Financial Studies*, 22(1), 435–480.
  Observations that share a common shock need clustered standard errors. *Used for:* standard
  errors clustered by calendar date, because breakouts bunch on volatile days.
