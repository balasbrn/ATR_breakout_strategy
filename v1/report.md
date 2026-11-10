# ATR_breakout_strategy v1 — Results

**Status: CLOSED.** Study closed by the owner on 2026-11-10 after US and NSE failed both stages; FX/gold and crypto were not run.

The frozen [contract](contract.md) and [HTML scorecard](report.html) accompany this report.

## Provenance

| Item | Value |
|---|---|
| Contract | `v1/contract.md`, frozen 2026-11-05, commit: `f968fff3c67fc550a7f82241ed93eefcd95ee7d8` |
| Code | US [`a05c0e4e22bfe475d359a08765aa2ecda3bb39ae`](https://github.com/balasbrn/ATR_breakout_strategy/commit/a05c0e4e22bfe475d359a08765aa2ecda3bb39ae) · NSE [`1cd4dd5ab809f95321e981a0abfa41d4efc702e0`](https://github.com/balasbrn/ATR_breakout_strategy/commit/1cd4dd5ab809f95321e981a0abfa41d4efc702e0) |
| Script and command | US Stage A `atr-bo stage-a --market US --data /home/ubuntu/data/atr/us-study/minutes.json --out /home/ubuntu/data/atr/runs/us-v1 --archive '<runtime-uri>'`<br>US Stage B `atr-bo stage-b --market US --data /home/ubuntu/data/atr/us-study/minutes.json --out /home/ubuntu/data/atr/runs/us-v1 --archive '<runtime-uri>'`<br>NSE Stage A `atr-bo stage-a --market NSE --data /home/ubuntu/data/atr/nse-study/minutes.json --out /home/ubuntu/data/atr/runs/nse-v1 --archive '<runtime-uri>'`<br>NSE Stage B `atr-bo stage-b --market NSE --data /home/ubuntu/data/atr/nse-study/minutes.json --out /home/ubuntu/data/atr/runs/nse-v1 --archive '<runtime-uri>'` |
| Data checksums | US manifest SHA-256 `0d375f201e14eaacf95bd35ee7d2a31367ba8945f99a3f4889e3f30288e07939`<br>NSE manifest SHA-256 `f557f91f31bf80482d819722ae4b7a84465d173e1efe397aee1697d37591739f`<br>Per-date SHA-256 values are recorded in the source files’ `input_sha256` maps. |
| Run date (UTC) | US Stage A `2026-11-09T20:29:55.405866+00:00`<br>US Stage B `2026-11-09T20:53:12.764421+00:00`<br>NSE Stage A `2026-11-10T17:23:37.170830+00:00`<br>NSE Stage B `2026-11-10T17:57:45.815216+00:00` |
| Costs | §6 of the contract: base and stress, per market |

Provenance for crypto and FX/gold: not run.

## 1. Stage A — gross (no costs)

Written down before Stage B is computed.

| Rule | US dev | US OOS | NSE dev | NSE OOS | Crypto dev | Crypto OOS | FX/gold dev | FX/gold OOS |
|---|---|---|---|---|---|---|---|---|
| 1 · Mean R > 0 | pass · 0.09694180261076392 | pass · 0.015691553032018357 | pass · 0.025473504852672708 | pass · 0.0579243658365287 | not run | not run | not run | not run |
| 2 · Mean R > random entry | fail · 0.09694180261076392 vs 0.2614028176513953 | fail · 0.015691553032018357 vs 0.21503534889253523 | fail · 0.025473504852672708 vs 0.19206341770740057 | fail · 0.0579243658365287 vs 0.15701600232300955 | not run | not run | not run | not run |
| 3 · Mean R > 0 without best symbol | pass · 0.08508541463169829 | pass · 0.005291040449486489 | pass · 0.01969897246616931 | pass · 0.05122381571367225 | not run | not run | not run | not run |
| 4 · t ≥ 2 (dev + OOS, clustered by date) | pass · 2.700401043401606 | | pass · 3.1389516650488285 | | not run | | not run | |
| **Verdict** | fail | | fail | | not run | | not run | |

## 2. Stage B — net (base costs; stress reported)

| Rule | US dev | US OOS | NSE dev | NSE OOS | Crypto dev | Crypto OOS | FX/gold dev | FX/gold OOS |
|---|---|---|---|---|---|---|---|---|
| 1 · Mean R > 0 | pass · 0.017157127606902887 | fail · -0.04781729074996655 | fail · -0.12827607633775673 | fail · -0.08371071520628426 | not run | not run | not run | not run |
| 2 · Mean R > random entry | pass · 0.017157127606902887 vs -0.7652737051222398 | pass · -0.04781729074996655 vs -0.5839583841534874 | pass · -0.12827607633775673 vs -1.0378597052439074 | pass · -0.08371071520628426 vs -1.2040382274424473 | not run | not run | not run | not run |
| 3 · Mean R > 0 without best symbol | pass · 0.005724696566125945 | fail · -0.05842531654744106 | fail · -0.13353301929952216 | fail · -0.08983424355110683 | not run | not run | not run | not run |
| 4 · t ≥ 2 (dev + OOS, clustered by date) | fail · -0.09530392945837304 | | fail · -10.53076159337139 | | not run | | not run | |
| **Verdict** | fail | | fail | | not run | | not run | |

## 3. Metrics per market

One table per market (US stocks, NSE, crypto, FX and gold), columns development, out-of-sample and
holdout (holdout stays **locked** unless both stages pass):

### US

| Metric | Development | Out-of-sample | Holdout |
|---|---|---|---|
| Trades | gross 6401 · base 6405 · stress 6409 | gross 2785 · base 2786 · stress 2790 | locked (Stage A failed) |
| Mean gross R | 0.09694180261076392 | 0.015691553032018357 | locked (Stage A failed) |
| Mean net R, base | 0.017157127606902887 | -0.04781729074996655 | locked (Stage A failed) |
| Mean net R, stress | -0.061398920688818824 | -0.11090614487079416 | locked (Stage A failed) |
| Hit rate | gross 0.2363693172941728 · base 0.33817330210772834 · stress 0.32922452800748947 | gross 0.21831238779174147 · base 0.3435032304379038 · stress 0.34444444444444444 | locked (Stage A failed) |
| Average win R / average loss R | gross 1.9541315641888573 / -0.676927434977178 · base 1.2775676653833432 / -0.6270222182392894 · stress 1.2283015627908742 / -0.6943991579863653 | gross 1.7161016383774494 / -0.6731911252116621 · base 1.0245360279165776 / -0.608911946826447 · stress 0.9609511095556409 / -0.674454135925868 | locked (Stage A failed) |
| `skipped_gap` / `skipped_busy` | gross 215 / 735 · base 215 / 731 · stress 215 / 727 | gross 63 / 253 · base 63 / 252 · stress 63 / 248 | locked (Stage A failed) |
| Share crossing overnight (cash markets) | gross 0.11310732698015935 · base 0.11209992193598751 · stress 0.11015759088781402 | gross 0.1066427289048474 · base 0.10624551328068917 · stress 0.10501792114695341 | locked (Stage A failed) |
| Mean R without best symbol | gross 0.08508541463169829 · base 0.005724696566125945 · stress -0.07267862805739161 | gross 0.005291040449486489 · base -0.05842531654744106 · stress -0.12172292258936213 | locked (Stage A failed) |
| Random entry, mean R | gross 0.2614028176513953 · base -0.7652737051222398 · stress -1.813031437603064 | gross 0.21503534889253523 · base -0.5839583841534874 · stress -1.405706414507447 | locked (Stage A failed) |
| Breakout without compression, mean R | gross 0.04559395392407353 · base -0.02482344760799811 · stress -0.09522918905384908 | gross 0.020487730417346275 · base -0.03483396243999071 · stress -0.09160665311163216 | locked (Stage A failed) |
| Buy-and-hold (context only) | 56.012841003357735 | -23.97059951478181 | locked (Stage A failed) |
| Filled 1-min bars (crypto only) | not computed | not computed | locked (Stage A failed) |

### NSE

| Metric | Development | Out-of-sample | Holdout |
|---|---|---|---|
| Trades | gross 63636 · base 63901 · stress 64031 | gross 24461 · base 24553 · stress 24614 | locked (Stage A failed) |
| Mean gross R | 0.025473504852672708 | 0.0579243658365287 | locked (Stage A failed) |
| Mean net R, base | -0.12827607633775673 | -0.08371071520628426 | locked (Stage A failed) |
| Mean net R, stress | -0.20086768378035533 | -0.1521103219641777 | locked (Stage A failed) |
| Hit rate | gross 0.1824910428059589 · base 0.286599583731084 · stress 0.2787712201902204 | gross 0.18977147295695188 · base 0.29515741457255734 · stress 0.2871130251076623 | locked (Stage A failed) |
| Average win R / average loss R | gross 2.4179607497512117 / -0.7269685193992784 · base 1.3591474382746256 / -0.7260526131398083 · stress 1.3098062081385102 / -0.7854065420295671 | gross 2.333629357619553 / -0.6914245531900894 · base 1.3136619507979355 / -0.669411135085157 · stress 1.2536803112298145 / -0.7189027050129688 | locked (Stage A failed) |
| `skipped_gap` / `skipped_busy` | gross 1213 / 9613 · base 1216 / 9345 · stress 1218 / 9213 | gross 322 / 3255 · base 323 / 3162 · stress 323 / 3101 | locked (Stage A failed) |
| Share crossing overnight (cash markets) | gross 0.31078320447545416 · base 0.3034694292734073 · stress 0.29983914041636084 | gross 0.2787702873962634 · base 0.27092412332505195 · stress 0.2664743641829853 | locked (Stage A failed) |
| Mean R without best symbol | gross 0.01969897246616931 · base -0.13353301929952216 · stress -0.20580952614780734 | gross 0.05122381571367225 · base -0.08983424355110683 · stress -0.15807246473490383 | locked (Stage A failed) |
| Random entry, mean R | gross 0.19206341770740057 · base -1.0378597052439074 · stress -1.6138957142610186 | gross 0.15701600232300955 · base -1.2040382274424473 · stress -1.8465457819681068 | locked (Stage A failed) |
| Breakout without compression, mean R | gross 0.02011342946885269 · base -0.10566668421888764 · stress -0.1647617809200611 | gross 0.029291436456715364 · base -0.0901462155520234 · stress -0.14754739460219285 | locked (Stage A failed) |
| Buy-and-hold (context only) | 144.79582232388552 | 68.94103398546373 | locked (Stage A failed) |
| Filled 1-min bars (crypto only) | not computed | not computed | locked (Stage A failed) |

### Crypto

| Metric | Development | Out-of-sample | Holdout |
|---|---|---|---|
| Trades | not run | not run | not run |
| Mean gross R | not run | not run | not run |
| Mean net R, base | not run | not run | not run |
| Mean net R, stress | not run | not run | not run |
| Hit rate | not run | not run | not run |
| Average win R / average loss R | not run | not run | not run |
| `skipped_gap` / `skipped_busy` | not run | not run | not run |
| Share crossing overnight (cash markets) | not run | not run | not run |
| Mean R without best symbol | not run | not run | not run |
| Random entry, mean R | not run | not run | not run |
| Breakout without compression, mean R | not run | not run | not run |
| Buy-and-hold (context only) | not run | not run | not run |
| Filled 1-min bars (crypto only) | not run | not run | not run |

### FX/gold

| Metric | Development | Out-of-sample | Holdout |
|---|---|---|---|
| Trades | not run | not run | not run |
| Mean gross R | not run | not run | not run |
| Mean net R, base | not run | not run | not run |
| Mean net R, stress | not run | not run | not run |
| Hit rate | not run | not run | not run |
| Average win R / average loss R | not run | not run | not run |
| `skipped_gap` / `skipped_busy` | not run | not run | not run |
| Share crossing overnight (cash markets) | not run | not run | not run |
| Mean R without best symbol | not run | not run | not run |
| Random entry, mean R | not run | not run | not run |
| Breakout without compression, mean R | not run | not run | not run |
| Buy-and-hold (context only) | not run | not run | not run |
| Filled 1-min bars (crypto only) | not run | not run | not run |

### Mean R by calendar year

| Market | Window | Year | Gross | Base | Stress |
|---|---|---|---:|---:|---:|
| US | dev | 2019 | 0.1248533697849646 | 0.012985120432805872 | -0.1001971440000759 |
| US | dev | 2020 | 0.1463846344182708 | 0.08066247495864817 | 0.011793035490779199 |
| US | dev | 2021 | 0.04636121660153229 | -0.03975550313926445 | -0.12013361827482215 |
| US | oos | 2022 | 0.015691553032018357 | -0.04781729074996655 | -0.11090614487079416 |
| US | Holdout | locked (Stage A failed) | locked (Stage A failed) | locked (Stage A failed) | locked (Stage A failed) |
| NSE | dev | 2015 | 0.08388983256893369 | -0.07078693013753033 | -0.14214056263424293 |
| NSE | dev | 2016 | 0.036592094524739445 | -0.12701508667663935 | -0.20478660811334565 |
| NSE | dev | 2017 | -0.02343465258275826 | -0.21379138355476845 | -0.30539838676328973 |
| NSE | dev | 2018 | -0.006163536417512974 | -0.1603334645220307 | -0.23153172731680252 |
| NSE | dev | 2019 | 0.014972337636181044 | -0.1379759623686551 | -0.2111487780861807 |
| NSE | dev | 2020 | 0.05609877313583293 | -0.05815023799538029 | -0.11174282817846638 |
| NSE | oos | 2021 | 0.044837396986018074 | -0.09159618758528497 | -0.15797341153913572 |
| NSE | oos | 2022 | 0.07037348066919773 | -0.07621061834485233 | -0.14653171750932395 |
| NSE | Holdout | locked (Stage A failed) | locked (Stage A failed) | locked (Stage A failed) | locked (Stage A failed) |
| Crypto | not run | not run | not run | not run | not run |
| FX/gold | not run | not run | not run | not run | not run |

Crypto secondary development row (from 2019-01-01): not run.

Hit rate and overnight share are fractions as stored in the metrics. Buy-and-hold is stored in percent.

## 4. Caveats carried on every result

- US list chosen by 2026 popularity; crypto list omits coins that died (survivorship).
- NSE point-in-time index membership not applied.
- Crypto prices are spot; costs model perpetuals; basis and funding not modelled.
- Crypto may keep only 1–3 coins after the completeness rule: low power, never pooled.
- t ≥ 2 is a first bar, not proof (see REFERENCES.md, Harvey, Liu and Zhu 2016).

- The random-entry benchmark draws tight 1R stops, which inflates its gross R and
  deepens its net losses. The gross result below random partly reflects stop width.
- NSE data starts on 2015-01-09, versus the registered 2015-01-01 start.
- The NSE universe includes about 20 indices. The with/without-indices split was not computed.

## 5. Verdict

v1 failed both Stage A and Stage B in US and NSE. No holdout opened. Crypto and
FX/gold were not run.
