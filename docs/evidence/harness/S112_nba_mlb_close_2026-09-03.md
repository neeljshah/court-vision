# S112 -- a real market close for the NBA and MLB gate corpora, and what it does to every "vs Elo" pregame result (2026-09-03)

Row: `docs/evidence/HARNESS_GAPS_2026-09-03.md` S112 (data).
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q (self-checked in section 6).
Calibration language only. An uncharged screen is a NON-FINDING. **NOT VERIFIED** -- this is
the lane's own report; no independent verifier has re-run it.

---

## VERDICT

**Both sports reach a close (nba 952 events, mlb 894 -- both well over the 300 bar), and the
headline is not about a model at all: on NBA the market close beats the gate corpus's Elo
incumbent by +0.025606 Brier, on MLB by +0.007269, both with the declared-cluster CI excluding
zero.** Every prior pregame result on those two sports was scored against a reference that is
this far behind the market, so "vs Elo" was never evidence about the market and is now measured
rather than asserted.

Re-scored on the SCREEN side against that close:

- **S108's full-feature elastic net and HGB, with `logit(p_close)` as the offset: NULL on both
  sports, and NEGATIVE.** nba `-0.040888` / `-0.007784`, mlb `-0.022663` / `-0.005575` against the
  `+0.004` bar. 0 of 4 arms clear.
- **The top-5 vs-Elo single-term screens: the NBA `+0.005221` VANISHES, exactly as the row
  predicted, and it vanishes on BOTH axes.** S85's best screen
  (`nba_player_value_features.continuity` / `z_vs_league`) was `+0.005221` vs Elo on S85's last-800
  window; on the 492 close-covered screen rows it is **`-0.000660` vs the SAME Elo incumbent**, and
  **`-0.003272` vs `p_close`**. All 5 NBA screens and all 5 MLB screens are negative vs the close.

**No prereg DRAFT is written**: no arm beats `p_close` by `>= +0.004` with a CI excluding zero;
every one is on the wrong side of zero. Uncharged: no prereg sealed, no ledger read, no ledger
write, `_charge_ledger` never called, `data/cache/eval_gate/backtest_fwer.jsonl` never opened
(still **18 rows**, md5 `a4ae7c13995672e478d59770591b83ba`, byte-identical to what S79, S85, S108
and S81 recorded). `data/registry/` untouched, no flag flipped, no bar moved
(`IMPROVEMENT_BAR == 0.004`, asserted by the per-file test). The VERDICT partition was never
built and never read. Nothing was read or written under `src/`, `kernel/` (except the existing
`devig2` import), `api/`, `intel/`, `scripts/team_system/`; nothing under `foundry/` was edited
(S111 owns it) -- `screen_predictor` and `tiers` are imported only.

**The LIVE `data/cache/combo/gate_corpus_{nba,mlb}.parquet` the pod runner (pid 480752) reads
were NOT modified.** Verified by sha256 before and after the build: nba
`716f6f5f3f2181051e352936efa60d616c9de029a026b85cc585d6ed20cb0aaf`, mlb
`ac60c9cb18958c20ff53d7d0b698700375b6a0ce15e7ef0ecd20fb730e0903bd`, identical across the run.
The close lands in NEW files beside them.

---

## 0. STEP 0 -- the premise, measured before anything was built (Q8)

### 0.1 NBA -- can the corpus reach a close, and from where?

The register row names three candidates. All three were measured; two of the three claims in the
row needed correcting, and the correction does not stop the row.

| candidate | rows / games | dates | what it actually is | joins to `gate_corpus_nba` | verdict |
|---|---|---|---|---|---|
| `nba_checkpoints_full.parquet` first traded tick | 465,249 rows / **1,593 games**, all polymarket, all `traded = True` | 2024-10-22 .. 2026-06-13 | **not pregame.** 1,591 of 1,593 first ticks are period 1, median **21 s AFTER tip** (5th-95th pct 0 .. 52 s), 899 of 1,593 at score 0-0. Zero rows before tip -- S81's premise finding, reproduced here. | bridged 1,331 / 1,593 (83.6 pct) by `nba_mechanism_ladder.build_crosswalk`; **965 rows / 960 unique** land in the 1,814-row gate corpus | **USABLE**, labelled `first_inplay_tick` |
| `nba_close_corpus.parquet` | **663 rows / 663 games**, all polymarket, `close_kind = last_tick_before_commence` | 2023-02-23 .. 2026-04-03 | **a genuine PREGAME close.** `seconds_before_tip` median 44 s (min 2, max 74). One close per game, `validation_only = True`. | **220** games overlap the gate corpus (the corpus is 2024-25 + 2025-26 only, this file starts in 2023) | **USABLE but under the bar alone** |
| `nba_price_series.parquet` | 8,399,632 rows / 2,572 events | -- | keys carry a DATE and no clock, so no tick can be certified pre-tip (S81) | 0 certified | CLOSED AT LIMIT |

The row's "~21 s after tip, 1,593 games" and "663 closes" are both **CONFIRMED**. What the row
does not say, and what decides the shape of the build: **the 663-row pregame file overlaps the
gate corpus on only 220 games, which is under the 300 bar on its own.** So a pure-pregame NBA
close is CLOSED AT LIMIT, and the row's coverage is reached only by ranking the pregame close
first and falling back to the first in-play tick. Both are carried, both are labelled, and
section 3.3 shows the two sources agree on the headline.

**The join key.** `gate_corpus_nba.event_id` is the NBA-stats `game_id` (`0022400061`).
`nba_close_corpus.game_id` is the same alphabet -- a direct join.
`nba_checkpoints_full.game_id` is an ESPN id (`401704627`) and needs the S84/S98 bridge:
`nba_mechanism_ladder.build_crosswalk` (market-ticker tricode pair + date within +/-1 day, kept
only when the venue outcome agrees with `games.parquet` `home_win`). That bridge is imported, not
rewritten.

**Achievable NBA coverage, funnel with every drop named:**

| step | games |
|---|---|
| priced games in `nba_checkpoints_full` (traded) | 1,593 |
| first tick in period 1 | 1,591 (2 dropped, `first_tick_not_period_1`) |
| bridged to an NBA-stats game_id | 1,331 (262 dropped, `unbridged_game` -- `games.parquet` ends 2026-04-12, so 2026-04/05/06 is unbridgeable, per S98) |
| minus 5 ambiguous bridges (2 venue games naming 1 corpus game) | 1,321 (10 rows dropped) |
| minus the exactly-0.500 placeholder | 1,315 (6 dropped) |
| **+ the 663-row pregame file**, minus its **154** exactly-0.500 rows | 509 pregame closes |
| union, pregame ranked first, restricted to the gate corpus | **952 of 1,814 = 52.48 pct** |

**>= 300: MET.** 220 of the 952 carry a genuinely pregame close, 732 the first in-play tick.
523 of the 952 are within 30 s of tip.

### 0.2 MLB -- the Kalshi last pre-first-pitch two-sided traded quote

| fact | measured |
|---|---|
| `mlb_price_series.parquet` | 13,473,591 rows; 4,212,676 kalshi (`traded` is a Kalshi-only column: 1,771,989 True / 2,440,687 False), 12,817,077 moneyline |
| Kalshi moneyline TRADED events | **972 event_keys** |
| the first-pitch clock | the ticker `KXMLBGAME-<yy><MON><dd><hhmm><away><home>`, `hhmm` in ET -- the only local one, already certified by `close_join_mlb` |
| `close_join_mlb` (S10) DEVIG_TWO_SIDED, joined to the spine | **913** -- the existing 8.17 pct source (913 / 11,179 modern spine rows) |
| S81's "935 two-sided traded" | the pre-spine-join count; after the spine join it is the same 913 |
| minus the exactly-0.500 devigged placeholder | **894** |
| joined to `gate_corpus_mlb` (39,162 rows) | **894 = 2.28 pct of the whole corpus, 8.00 pct of the 11,179-row `era_2022_2026` unit** |
| dates | **2026-04-26 .. 2026-07-08** -- 74 days, one venue, one season |

**>= 300: MET**, and **SINGLE-WINDOW under Q5** -- one `corpus_unit`, one venue, 74 days. The
join key is `event_id` recovered from (`date`, `home_team`, `away_team`) against
`games_current.parquet`, exactly as `close_join_mlb` does it; 22 events found no spine match and
are counted, not dropped silently.

### 0.3 The placeholder-0.500 rule, and why it is not cosmetic

S81 established that the untraded Kalshi listing quote sits at exactly 0.500 on 87.1 pct of first
ticks, and that scoring against it is the degenerate denominator B9 forbids. Measured here at the
CLOSE rather than the open:

| corpus | rows at exactly 0.500 | share |
|---|---|---|
| mlb devigged two-sided pre-first-pitch closes | **19 of 913** | 2.08 pct |
| nba first traded tick | **6 of 1,321** | 0.45 pct |
| **nba pregame `nba_close_corpus.parquet`** | **154 of 663** | **23.2 pct** |

The NBA pregame file is where the rule earns its keep: nearly a quarter of its closes are the
venue's listing placeholder, not a price. All 179 are excluded and counted.

---

## 1. THE CLOSE RULES, STATED

**mlb -- `close_source = pre_first_pitch_two_sided`, `close_kind = DEVIG_TWO_SIDED`.** The LAST
TRADED two-sided Kalshi quote with `ts_utc < start_utc`, devigged by feeding `1/prob` as a decimal
price through the EXISTING `close_join.close_column` (one `devig2`, never two) -- the same call
`close_join_mlb` makes. Strictly pregame by construction. `close_ts` is that quote's own epoch
timestamp; `close_sec_after_tip` is negative on every row (it is seconds relative to first pitch).

**nba -- two sources, ranked, both `close_kind = VENUE_PROB_ONE_SIDED`.**
1. `pregame_last_tick_before_commence`: `nba_close_corpus.close_prob_home`, the polymarket last
   tick before `commence_time`. `close_sec_after_tip = -seconds_before_tip`, so negative.
2. `first_inplay_tick`: the earliest TRADED tick of `nba_checkpoints_full` for that game.
   `close_sec_after_tip = 720 - game_clock_s` (period 1 only), so positive.
   **`close_within_30s` = |close_sec_after_tip| <= 30** -- the WITHIN-30-S-OF-TIP rule is written
   as a column the reader filters on, never applied as a hidden default. 523 of 952 pass it.

Both NBA sources are a **single venue probability**: polymarket serves one number, there is no
second side, so **nothing is devigged on the NBA side and it is never called a fair close** -- it
carries whatever the venue's own spread was. Where a devig is possible (mlb) it is done; where it
is not (nba) the row says so in `close_kind`.

**Ranking.** A genuinely pregame close outranks a first in-play tick for the same event. 218 of
the 220 pregame-covered events also had an in-play tick; the pregame number wins on all of them.

---

## 2. THE NEW CORPORA, AND THE PARITY CHECKS

`scripts/platformkit/eval_gate/close_join_nba_mlb.py` (298 LOC) writes:

| file | rows | corpus_sha256 |
|---|---|---|
| `data/cache/combo/gate_corpus_nba_close.parquet` | 1,814 | `cf40f90bf547d960ed604ffa557a87fcc3f2a0ed397825b2b56da115110a6dc3` |
| `data/cache/combo/gate_corpus_nba_close.sources.json` | sidecar | -- |
| `data/cache/combo/gate_corpus_mlb_close.parquet` | 39,162 | `70c04c4074efac746c9b025c31534a4574cb505962d9c7fe8f33dc4f973b3490` |
| `data/cache/combo/gate_corpus_mlb_close.sources.json` | sidecar | -- |

Six columns are APPENDED and nothing else changes: `p_close, close_ts, close_source, close_kind,
close_sec_after_tip, close_within_30s`.

| parity check | result |
|---|---|
| **live corpora untouched** | sha256 of `gate_corpus_{nba,mlb}.parquet` identical before and after the build (section VERDICT) |
| **every live column carried through byte-for-byte** | `base[cols].equals(new[cols])` = **True** for both sports; row counts identical (1,814 / 39,162); the added columns are exactly the six above (B2) |
| **column ORDER preserved** | asserted in code: the build raises if the first `len(base.columns)` columns are not the live corpus's, in order |
| **sidecar is build_gate_corpus-compatible** | same keys (`sport`, `built_at`, `n_rows`, `corpus_sha256`, `sources`, `provenance`), sources recorded through `corpus_cache._source_manifest` so the keys are repo-relative and travel |
| **portable=True loads on a host without the domain sources** | `load_close_corpus(sport, portable=True)` returns 1,814 / 39,162 rows via `corpus_cache.load_gate_corpus`, i.e. it verifies the parquet against the sidecar's own `corpus_sha256` (the S68 path) |
| **deterministic rebuild** | a second `build_close_corpus` run produced byte-identical parquets (both sha256 unchanged) |
| **mlb close == S81's close, event for event** | 894 common events, **max abs diff exactly 0.0**; S81 carries 19 events this lane does not, and **all 19 are exactly 0.500** -- the placeholder rule is the whole difference |
| **mlb close set == `close_join_mlb`'s DEVIG_TWO_SIDED set** | `set(S10 two-sided, 913) == set(mine, 894) | set(the 19 placeholders)` = **True** |

---

## 3. THE RE-SCORE (SCREEN SIDE ONLY)

`scripts/platformkit/eval_gate/s112_rescore_vs_close.py` (239 LOC). Rows are
`s108_features.build(sport)` -> `tiers.partition_corpus(seed = 20260903)`, **SCREEN side only**,
then restricted to events carrying a `p_close`. The VERDICT side was never built.

**The screen SHA-256 is byte-equal to the S58c / S79 / S85 / S108 artifacts'** -- nba
`1a32541d44aa7fcb...`, mlb `ad743c924c7c4547...`, basis `iso_week` on both. The partition is
computed over the FULL state list exactly as before and only then filtered to close-covered rows,
so the partition itself is unchanged; what changes is the scored subset, and its size is stated
everywhere below.

| sport | n states | n SCREEN | n screen WITH a close | n SCORED (outer test folds) | outer folds |
|---|---|---|---|---|---|
| nba | 1,814 | 867 | **492** | **351** | 5 (k = 6, S108's default) |
| mlb | 39,162 | 19,589 | **442** | **276** | 5 (k = 7, see below) |

**One documented deviation from S108, and it does not move a bar.** S108's design requires
`>= 5` outer folds. On mlb's 442 close-covered screen rows S108's default `k = 6` forms only
FOUR (`MIN_TRAIN = 120` eats the first). That minimum was **not lowered**; `k` was raised to the
smallest value that satisfies it, `k = 7`, and both values are written into the artifact
(`outer_folds_requested`, `s108_outer_folds`). nba runs at S108's own `k = 6`.

### 3.1 The headline: the close vs the corpus's Elo incumbent

`close_minus_elo = mean(loss_elo) - mean(loss_close)`; positive = the close is better.

| sport | n scored | Brier Elo (`p_base`) | Brier `p_close` | close - Elo | corpus_unit CI95 | declared-cluster CI95 (team) | clusters |
|---|---|---|---|---|---|---|---|
| nba | 351 | 0.211728 | **0.186122** | **+0.025606** | [-0.024861, +0.076073] (2 units) | **[+0.015252, +0.035960]**, p = 2.16e-05 | 30 |
| mlb | 276 | 0.251444 | **0.244175** | **+0.007269** | undefined (1 unit) | **[+0.000066, +0.014473]**, p = 0.0481 | 26 |

The `corpus_unit` CI is not the binding one on either sport: nba has two units (2024-25 /
2025-26) and mlb's close-covered rows are a single unit (`era_2022_2026`), so the DECLARED cluster
key (`team`, the SF-10 key for both sports) carries the interval. Both declared CIs exclude zero.

**This is the row's real finding.** It is a statement about the REFERENCE, not about a model: the
Elo baseline the nba and mlb gate corpora ship as `p_base` trails a real market close by
0.0256 / 0.0073 Brier. Every "improvement vs `p_base`" ever measured on those two corpora was
measured against that.

### 3.2 Arm (a) -- S108's full-feature model with `logit(p_close)` as the OFFSET

S108's `folds`, `_prep`, `enet_logistic`, `hgb_offset` and `_grid_oof` are imported unchanged, so
the leak contract (nested inner walk-forward for the penalty, expanding outer folds, a blanket
2-day purge/embargo gap, train-fold median imputation + standardisation) is the one S108 was
scored under. Because the close is now the offset, Elo is no longer a copy of it and enters as a
plain FEATURE (`logit_p_base`) -- the same rule S108 applies to soccer and tennis.

`improvement_vs_close = Brier(p_close) - Brier(model)`; positive = the model is better. Bar
`+0.004` with the CI excluding zero.

| sport | arm | p | Brier `p_close` | Brier model | improvement vs close | unit CI95 | declared CI95 (team) | clears bar |
|---|---|---|---|---|---|---|---|---|
| nba | elastic_net | 179 | 0.186122 | 0.227010 | **-0.040888** | [-0.663415, +0.581639] | [-0.060623, -0.021153] | **NO** |
| nba | hgb_offset | 179 | 0.186122 | 0.193907 | **-0.007784** | [-0.048434, +0.032865] | [-0.015267, -0.000302] | **NO** |
| mlb | elastic_net | 23 | 0.244175 | 0.266837 | **-0.022663** | undefined (1 unit) | [-0.037101, -0.008224] | **NO** |
| mlb | hgb_offset | 23 | 0.244175 | 0.249750 | **-0.005575** | undefined (1 unit) | [-0.011502, +0.000351] | **NO** |

**0 of 4 arms clear. Three of the four have a declared CI entirely BELOW zero** -- adding the
feature set to the close measurably hurts.

What the penalty grid chose, reproducing S108's own signature:

| sport | fold | n_train | n_test | lambda | nonzero coefs |
|---|---|---|---|---|---|
| nba | 0 / 1 / 2 / 3 / 4 | 129 / 204 / 279 / 339 / 408 | 70 / 70 / 70 / 71 / 70 | 0.001 / 0.3 / 0.3 / 0.3 / 0.3 | **105 / 0 / 0 / 0 / 0** |
| mlb | 0 / 1 / 2 / 3 / 4 | 141 / 204 / 271 / 311 / 366 | 55 / 55 / 56 / 55 / 55 | 0.001 / 0.3 / 0.003 / 0.3 / 0.3 | 7 / 0 / 7 / 0 / 0 |

**The elastic net's large negative is one fold, and it is honest to say so.** nba fold 0 is the
only fold where the inner walk-forward picked the loosest penalty (105 of 179 coefficients
nonzero on 129 training rows) and its out-of-fold Brier is **0.414440** against the close's
0.213129; folds 1-4 chose `lambda = 0.3`, drove every coefficient to zero, and tracked the close
(0.203242 / 0.203433 / 0.177002 / 0.137649 vs 0.202185 / 0.202604 / 0.177083 / 0.135740). The mlb
picture is the same shape (fold 2 at 0.335994 vs 0.238604). **The reading is not "the model is
0.04 worse"; it is "with 179 columns and a real close as the offset, the only thing that does not
blow up is choosing none of them"** -- S108's finding, now against a market reference instead of
Elo. The HGB arm, which cannot select its way to zero, lands a few thousandths behind the close in
both sports.

### 3.3 The robustness check the two NBA close sources allow

The NBA `p_close` mixes a genuinely pregame close with a first in-play tick that already knows a
median 21 s of basketball. If the headline were an artifact of that head start, the two sources
would disagree. They do not:

| close source | n scored | Brier `p_close` | Brier Elo | close - Elo |
|---|---|---|---|---|
| `first_inplay_tick` (median 21 s after tip) | 220 | 0.180911 | 0.206540 | **+0.025629** |
| `pregame_last_tick_before_commence` (median 44 s BEFORE tip) | 131 | 0.194874 | 0.220442 | **+0.025567** |
| the `close_within_30s` subset | 163 | 0.197986 | 0.216983 | +0.018997 |

The genuinely pregame subset gives **+0.025567**, within 0.00007 of the in-play-tick subset's
+0.025629. The finding is not the tick's head start.

### 3.4 Arm (b) -- the top-5 vs-Elo screens, re-run vs `p_close`

The top-5 T1 screens per sport by published S85 improvement, re-run through the SAME walk-forward
single-term screen (`foundry.screen_predictor.ScreenBinder` + `RealScreenPredictor`, purge +
embargo from `eval_gate.walkforward`), on **identical rows**, once with Elo as `p_ref` and once
with `p_close` as `p_ref`. The incumbent is swapped by rewriting `devig_close_prob` on a COPY of
the states; nothing under `foundry/` was edited.

**nba (492 rows, 30 team clusters):**

| feature / transform | S85 vs Elo (last-800 window) | **here vs Elo** (492 close-covered rows) | **here vs `p_close`** | CI95 vs close | p |
|---|---|---|---|---|---|
| `continuity` / `z_vs_league` | **+0.005221** | **-0.000660** | **-0.003272** | [-0.006699, +0.000155] | 0.0606 |
| `continuity` / `raw` | +0.005172 | +0.000844 | -0.001836 | [-0.004964, +0.001291] | 0.2395 |
| `roster_value_asof` / `rank_in_league` | +0.004037 | +0.001616 | -0.002699 | [-0.007195, +0.001798] | 0.2296 |
| `top_heavy` / `z_vs_league` | +0.003049 | -0.002742 | -0.003725 | [-0.006804, -0.000647] | 0.0194 |
| `roster_value_asof` / `raw` | +0.003043 | +0.000562 | -0.004236 | [-0.008858, +0.000387] | 0.0710 |

**mlb (442 rows, 29 team clusters):** all five are `mlb_bullpen_relief_chains.battersFaced`, and
all five were already negative in S85.

| feature / transform | S85 vs Elo | here vs Elo | **here vs `p_close`** | CI95 vs close | p |
|---|---|---|---|---|---|
| `battersFaced` / `delta_vs_prior` | -0.003090 | -0.005938 | -0.006792 | [-0.014113, +0.000530] | 0.0677 |
| `battersFaced` / `ew` h=20 | -0.003405 | -0.007429 | -0.007707 | [-0.015401, -0.000013] | 0.0496 |
| `battersFaced` / `ew` h=10 | -0.003531 | -0.007445 | -0.007718 | [-0.015424, -0.000012] | 0.0497 |
| `battersFaced` / `ew` h=5 | -0.003620 | -0.007474 | -0.007740 | [-0.015474, -0.000006] | 0.0498 |
| `battersFaced` / `ew` h=3 | -0.003794 | -0.007502 | -0.007766 | [-0.015544, +0.000012] | 0.0503 |

**10 of 10 screens are negative against the close.**

**The decomposition matters more than the sign.** S85's one nominal NBA winner loses its
`+0.005221` in TWO independent steps, and the first is not about the market at all:

1. **the WINDOW** -- moving from S85's last-800 screen rows to the 492 close-covered screen rows
   takes `continuity` / `z_vs_league` from **+0.005221 to -0.000660 against the SAME Elo
   incumbent**. Four fifths of the effect was window-specific before any close was involved. That
   is the concrete form of S85's own warning ("one nominal hit out of 344 looks, against Elo, on
   one window").
2. **the REFERENCE** -- swapping Elo for `p_close` on those same 492 rows takes it a further
   -0.0026, to **-0.003272**.

The row predicted "the +0.005 vs-Elo NBA screens vanish". They vanish, and the measurement says
the window carried most of the disappearance.

---

## 4. WHAT THIS DOES AND DOES NOT LICENSE

- It **does** make NBA and MLB pregame results market-relative for the first time, on 952 and 894
  events. Anything measured against `p_base` on those corpora may now be re-measured against a
  real close, and the gap between the two references is itself measured (+0.0256 / +0.0073).
- It **does not** license any claim of beating a close. Every arm is behind it. The close is
  reported as the reference, never as something beaten.
- **MLB is SINGLE-WINDOW (Q5):** one `corpus_unit`, one venue (Kalshi), one season, a 74-day
  window (2026-04-26 .. 2026-07-08). It could not carry an AHEAD even if an arm had cleared.
- **NBA's close is not a devigged fair close.** It is a single polymarket probability and carries
  the venue's own spread. 732 of 952 are a tick ~21 s after tip, not a pregame price. Section 3.3
  shows the headline survives restricting to the 131 genuinely pregame scored rows, but a
  pure-pregame NBA corpus is only 220 events -- **CLOSE AT LIMIT below the 300 bar**, and the named
  acquisition is extending `nba_close_corpus`'s `commence_time` recovery to
  `nba_price_series.parquet` (S81's section 5 names the same one).
- The nba screen comparison in 3.4 is on 492 rows, **not** S85's 800; the two numbers are not
  interchangeable and both windows are printed side by side above.

---

## 5. ARTIFACTS

| path | what |
|---|---|
| `scripts/platformkit/eval_gate/close_join_nba_mlb.py` | the close attach (298 LOC) |
| `scripts/platformkit/eval_gate/s112_rescore_vs_close.py` | the re-score (239 LOC) |
| `tests/platformkit/eval_gate/test_close_join_nba_mlb.py` | per-file test, **8 passed in 1.88 s** |
| `data/cache/combo/gate_corpus_nba_close.parquet` + `.sources.json` | 1,814 rows, 952 with a close |
| `data/cache/combo/gate_corpus_mlb_close.parquet` + `.sources.json` | 39,162 rows, 894 with a close |
| `data/cache/eval_gate/s112_rescore_2026-09-03.json` | both sports, both arms, all folds, all screens |
| `data/cache/eval_gate/s112_rescore_2026-09-03_nba_fullmodel.csv` | 351 per-event rows (Q9) |
| `data/cache/eval_gate/s112_rescore_2026-09-03_mlb_fullmodel.csv` | 276 per-event rows (Q9) |

Reproduce:

    python -m scripts.platformkit.eval_gate.close_join_nba_mlb --sports nba,mlb
    python -m scripts.platformkit.eval_gate.s112_rescore_vs_close --sports nba,mlb
    python -m pytest tests/platformkit/eval_gate/test_close_join_nba_mlb.py -q

---

## 6. SELF-CHECK against VERIFIER_CONTRACT sections B and Q

| rule | self-check |
|---|---|
| B1 circular metric | No row is excluded by the metric. Every denominator is the FULL gate corpus (1,814 / 39,162) and every drop is named and counted in `drops` (`placeholder_half`, `ambiguous_event_id`, `unbridged_game`, `first_tick_not_period_1`, `no_spine_match`, `not_in_gate_corpus`), reprinted in section 0.1/0.2. |
| B2 non-additive schema | Six columns APPENDED to a NEW file; zero renamed, zero removed. `base[cols].equals(new[cols])` is True on both sports and the build RAISES if the live column order is not preserved. No existing module was edited, so no reader changed behaviour. |
| B3 fall-through loss | Missing != bad: an event with no close keeps its row with `p_close = NaN` and is simply not scored; it is never marked failed. S108's median + `__isna` indicator handling is inherited unchanged. |
| B4 re-claim loop | Not a queue; no claimable item exists. |
| B5 pre-verification deploy | **Nothing copied to the pod.** Local only. The orchestrator section below states what a deploy would ship; it has not happened. |
| B6 orphans | Nothing moved or retired. Two new modules, one new test, zero deletions. |
| B7 head-slice evidence | The scored rows are the 5 walk-forward outer TEST folds spanning the corpus tail (nba 2024-10-22 .. 2026-04-06; mlb 2026-04-26 .. 2026-07-05), fold sizes 70-71 and 55-56, even by construction -- not a head slice. |
| B8 self-fit as independent | Every reported number is out-of-fold. The penalty is chosen by an INNER walk-forward inside the outer train window and never sees a test row. The single-term screens are `walk_forward` with purge + embargo, `select_inside = True`. |
| B9 degenerate denominator | The placeholder-0.500 quote is the degenerate case here and it is excluded and counted in all three sources (19 mlb, 6 nba tick, **154 nba pregame**). Every scored unit is a distinct event: 351 rows / 351 unique event_ids (nba), 276 / 276 (mlb) -- verified from the archived CSVs. |
| B10 / Q3 moved bar | `IMPROVEMENT_BAR == 0.004`, imported from S108 so there is exactly one definition, asserted by `test_bar_is_not_moved`. S108's `>= 5 outer folds` minimum was NOT lowered; `k` was raised from 6 to 7 on mlb to satisfy it, and both numbers are in the artifact. The 300-event coverage bar was met on both sports, not lowered. The pure-pregame NBA arm is reported CLOSE AT LIMIT at 220 rather than scored against a lowered bar. |
| Q1 prereg sealed | No scored CLAIM is made, so no seal is required and none is asserted. This is a SCREEN and a NON-FINDING; no arm reaches the prereg-DRAFT condition. |
| Q2 ledger charged | Nothing charged. `backtest_fwer.jsonl` never opened; **18 rows**, md5 `a4ae7c13995672e478d59770591b83ba`, unchanged. `_charge_ledger` never called (`tiers.charge_tier` never reached: `_run_screen`/`run_tier` are not used, the screen goes straight through `walk_forward`). |
| Q4 leak contract | Arm (a) runs S108's imported nested walk-forward with the 2-day purge/embargo gap. Arm (b) runs `eval_gate.walkforward.walk_forward` (48 h same-team purge, 3-day same-matchup embargo, `select_inside=True`). Feature names pass `screen_predictor.check_feature_name`, so a same-game column is refused BY NAME before any value is read. `p_close` is the OFFSET, never a feature. |
| Q5 two corpora | No AHEAD is claimed anywhere -- 0 of 4 model arms and 0 of 10 screens are on the good side of zero. The **mlb close corpus is labelled SINGLE-WINDOW** (1 corpus_unit, 1 venue, 74 days) here and in the register row. The nba close spans 2 corpus_units. |
| Q6 calibration language | Calibration only. No dollar / ROI / profit / edge word. None of +18.38, 0.119, +54, 78.11, 8.94, 54.57 appears. |
| Q7 sampling rail | Every scored metric is SAMPLED with n >= 30 (351, 276, 492, 442). The premise tables in 0.1/0.2 are CONSTRUCT: every local NBA and MLB price corpus on disk is enumerated. |
| Q8 premise first | Done before any code. The row's three NBA facts (21 s after tip / 1,593 games / 663 closes) are CONFIRMED; the row's implicit assumption that 663 closes means 663 usable ones is **CORRECTED** -- only 220 overlap the gate corpus and 154 of the 663 are exactly-0.500 placeholders. S81's "935" is the pre-spine-join count and reconciles to `close_join_mlb`'s 913. |
| Q9 archive the differential | `s112_rescore_2026-09-03_{nba,mlb}_fullmodel.csv` carry per-event `event_id, event_date, corpus_unit, cluster_id, fold, y, p_close, p_elo, p_enet, p_hgb` and all four loss columns plus the paired differentials `d_elastic_net` / `d_hgb_offset`. **A2 reproduction from the CSVs alone: `close_minus_elo` recomputes to +0.025606 (nba) and +0.007269 (mlb), and the declared-cluster CIs to the printed digits.** The per-screen differentials of arm (b) ride in the summary JSON. |

---

## 7. ORCHESTRATOR SECTION

### 7.1 Files to ship to the pod

Ship ONLY after an ACCEPT (B5 -- nothing has been copied):

| file | why |
|---|---|
| `scripts/platformkit/eval_gate/close_join_nba_mlb.py` | the attach; imports `close_join_mlb`, `corpus_cache` and `nba_mechanism_ladder`, all already on the pod |
| `scripts/platformkit/eval_gate/s112_rescore_vs_close.py` | the re-score; imports `s108_*`, `screen_predictor`, `tiers`, `walkforward`, `dm_test`, all already on the pod |
| `tests/platformkit/eval_gate/test_close_join_nba_mlb.py` | the per-file test (synthetic fixtures, no real data needed) |
| `docs/evidence/harness/S112_nba_mlb_close_2026-09-03.md` | this memo |

**Do NOT ship the two new parquets to run the ATTACH on the pod.** The pod has no
`nba_checkpoints_full.parquet`, no `nba_close_corpus.parquet` and no `mlb_price_series.parquet`,
so `build_close_corpus` cannot run there. If the pod needs to READ a close corpus, ship the built
pair as data:

    data/cache/combo/gate_corpus_nba_close.parquet   + .sources.json
    data/cache/combo/gate_corpus_mlb_close.parquet   + .sources.json

and read them with `load_close_corpus(sport, portable=True)` (or `FOUNDRY_PORTABLE_CORPUS=1`),
which verifies the parquet against the sidecar's `corpus_sha256` -- the S68 path, already
exercised locally. The two shas to check on arrival are in section 2.

### 7.2 Should the LIVE corpora be swapped?

**NO. Recommendation: do not swap, and there is nothing to swap to.**

1. The live `gate_corpus_{nba,mlb}.parquet` were not modified and the new files are strictly
   additive supersets, so a swap buys nothing a `_close` read does not already buy.
2. A swap would change `screen_predictor.INCUMBENT` semantics for nba/mlb, which is
   `foundry/`-owned and currently held by the S111 lane. Any incumbent change belongs in that
   lane's file, not in a corpus swap done underneath it.
3. Coverage forbids it as a default: mlb's close covers **2.28 pct** of the corpus (894 of
   39,162). Making the close the incumbent would silently drop 97.7 pct of the MLB corpus from
   every screen. NBA at 52.5 pct would drop nearly half.
4. The pod runner (pid 480752) reads the live files through the S68 sidecars. Overwriting them
   mid-run is exactly the hazard the lane rails name.

**What to do instead:** treat `gate_corpus_<sport>_close.parquet` as an OPT-IN second reference.
The right follow-up row is a `screen_predictor` change that lets a caller ask for
`incumbent = "p_close"` on nba/mlb and reports the close-covered denominator beside the full one
-- that is an S111-adjacent edit and is NOT made here.

### 7.3 Register row text

See the lane report.
