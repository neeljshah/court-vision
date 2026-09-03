# S111 -- the pregame factory's coverage acquisitions, taken off disk

**Row:** S111 (data) in `docs/evidence/HARNESS_GAPS_2026-09-03.md`.
**Parent:** S85 (`docs/evidence/harness/S85_refused_families_2026-09-03.md`), sections 2.3 and 2.4.
**Verdict:** **LANDED -- coverage acquired, screen NULL.** Four families crossed the frozen 0.8
coverage floor and produced their first screens ever (478 new T1 screens); every one of them is
NULL. Two tennis families stay CLOSED AT LIMIT with a different, unbuilt acquisition named.

A SCREEN IS A NON-FINDING. Calibration language only -- no dollar, ROI, profit or edge claim
appears here, and none of the retracted figures is quoted.

---

## 0. Premise (Q8), measured before any change

| the row's premise | measured | verdict |
|---|---|---|
| (a) five tennis families sit at 58 pct because the WTA half of the served window has no as-of tables | `tennis_features` 466/800, `tennis_return` 466/800, `tennis_meta` 469/800, `tennis_schedule_density` 469/800, `tennis_travel_scouting` 454/800 -- reproduced S85's numbers exactly | **HOLDS** |
| the WTA siblings already exist under other names | `data/domains/tennis/` held `asof_hold_wta.parquet` and `asof_setdetail_wta.parquet` and **no** `asof_features_wta` / `asof_return_wta` / `asof_meta_wta`. `foundry/catalogue.py` had already NAMED all three as absent (`catalogue.absent()` returned five paths) | **NOT falsified** |
| (b) `nba_quarter_shape` at 35.2 pct | 282-283 of 800 depending on the member (`diff_*` 282, `home_*`/`away_*` 283) -- reproduced | **HOLDS** |
| (c) a supplied column with 0 non-null on the served window passes both guards | reproduced directly: with `nba_quarter_shape` keyed on the ESPN `event_id` (the S85 defect) the supply returned a series with **0 non-null of the served 800** and raised nothing | **HOLDS** |

**How the existing `_wta` siblings were built.** `domains/tennis/asof_hold_wta.py` does not re-implement
the walk: it imports `asof_hold`'s own primitives and runs them against the WTA spine
`wta_matches.parquet` (11,270 rows: `event_id, date, tour, tourney_id, round, match_num, p1_id, p2_id,
surface, ...`) joined to the `-wta-`-tagged rows of the MIXED `match_stats.parquet` sidecar
(59,312 rows total, 28,696 WTA-tagged, **11,270 / 11,270** event_id overlap with the spine).
The strictly-before rule is the shared one: snapshot BEFORE this match's own values enter the
player's history, debut -> NaN.

**Sources measured on disk.** `data/domains/basketball_nba/linescores_2024_25.parquet` = 1,321 rows,
`event_id home_abbr home_q1..q4 away_abbr away_q1..q4 date`, 2024-10-22 .. 2025-06-22, keyed by the
ESPN `event_id`. `espn_nba_game_bridge.parquet` = 1,299 rows, all `match_confidence == "exact"`,
carrying `event_id -> game_id` (1,225 rows for season 2024-25, 74 for 2025-26); 1,225 of the 1,321
2024-25 linescores rows are bridged. `asof_quarter_shape.parquet` before the change: 1,313 rows,
1,156 with an NBA `game_id`, built from `linescores.parquet` (2025-26) alone.

---

## 1. What changed

### 1.1 (a) The three WTA sibling tables -- the SAME builders, not copies

`domains/tennis/asof_wta_siblings.py` (113 LOC). `build_asof_features` and `build_asof_return` were
**already parametrised** by `(match_stats, matches, out_path)`, so the WTA table is those exact
functions called with the WTA spine and the WTA half of the sidecar -- there is no second copy of the
walk-forward pass to keep in step. `build_asof_meta` reads raw Sackmann year CSVs by glob, so it took
one additive keyword, `pattern` (default `"atp_matches_*.csv"`, unchanged); the WTA run passes
`"wta_matches_*.csv"`. All 11,270 spine keys `(tourney_id, match_num)` were confirmed present in the
raw WTA CSVs before the build.

Written through `scripts/platformkit/ops/safe_parquet_write.write_parquet_atomic` (atomic replace,
refuse-to-shrink).

| table | rows | sha256[:16] | bytes | leak check |
|---|---|---|---|---|
| `data/domains/tennis/asof_features_wta.parquet` | 11,270 (100 pct `-wta-`) | `08618f4d5286cbc6` | 1,676,961 | 306 debut rows (`p1_n_prior == 0`), **0** with a non-NaN as-of value |
| `data/domains/tennis/asof_return_wta.parquet` | 11,270 (100 pct) | `4da5642b62ec5223` | 1,331,005 | 306 debut rows, **0** non-NaN |
| `data/domains/tennis/asof_meta_wta.parquet` | 11,270 (100 pct) | `81454e9b999c384c` | 509,374 | 1,397 debut rows, **0** non-NaN `minutes_prior_asof` |

**A NEW TABLE, NOT A WIDER SPINE.** The ATP parquets are frozen inputs of already-screened families;
appending WTA rows to them would move a screened family's source. A sibling cannot.

### 1.2 (a) Registration -- and why it is `asof_supply`, not the family's `sources`

`tennis_hold` and `tennis_setdetail` carry BOTH the ATP and the `_wta` parquet in their frozen
`sources` tuple, and `screen_predictor.source_column`'s family-source path already concatenates over
that tuple. **That route was rejected here.** The family partition is frozen in
`docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md` and pinned by `git hash-object` inside
`family_bars.load_families`; editing it to add a source would move the pin and the `spec_version`,
which is the S14 tamper-evidence condition and is not this row's business. `foundry/asof_supply.py`
is the additive route S85 built for exactly this: it is consulted only for the pairs it lists.

Three registry entries, rule `event` on the frozen `event_id` key (both tables are already one row per
event and already as-of by construction, so no side or prior aggregation is involved -- the "p1/p2
side rule" the gap row suggested is not the right rule here and would have re-derived values that the
tables already carry):

```
"tennis_features": Supply(ATP_WTA.format("features"), "event", TENNIS_FEATURES, loader="glob"),
"tennis_return":   Supply(ATP_WTA.format("return"),   "event", TENNIS_RETURN,   loader="glob"),
"tennis_meta":     Supply(ATP_WTA.format("meta"),     "event", TENNIS_META,     loader="glob"),
```

`_load_glob` now splits its pattern on a **comma**: the ATP table and its `_wta` sibling are two
frozen files and a single glob wide enough to catch both (`asof_features*.parquet`) would also catch
the unrelated `asof_features_ext2026.parquet` corpus. Existing entries carry no comma, so their
behaviour is byte-identical. Declared columns are exactly the frozen family's members (15 / 18 / 12);
`test_registry_is_additive_and_well_formed` still asserts `columns <= members` for all 13 entries and
now globs each comma part.

`asof_supply.py` was at 296 lines and the change would have pushed it past the 300-line cap, so the
closed column tuples (`_NBA_QUARTER`, `_PIT`, `_STYLE` plus the three new tennis ones) moved verbatim
into `scripts/platformkit/foundry/asof_supply_columns.py` -- a pure-data module, no logic, no
behaviour change; the names are private and had no reader outside `asof_supply.py`.
`asof_supply.py` is 298 lines, `screen_predictor.py` is unchanged at 300.

### 1.3 (b) Folding the 2024-25 shard into `asof_quarter_shape`

`domains/basketball_nba/asof_quarter_shape_full.py` (108 LOC) unions both linescores shards, dedups on
the ESPN `event_id`, sorts by date and hands the union to the FROZEN `build_asof_quarter_shape`
unchanged -- one chronological as-of pass over both seasons, so a 2025-26 game's trailing quarter
shape now reads the team's 2024-25 games as prior rows. Then the key: `espn_nba_game_bridge.parquet`
is applied FIRST (an exact per-event id map) and the builder's own `(date, canonical abbr)` join fills
only what the bridge does not carry. A row with neither stays NaN -- never guessed.

`asof_quarter_shape.parquet`: **1,313 -> 2,634 rows**, `game_id` non-null **1,156 -> 2,386**,
sha256[:16] `61ad557a4d51ae85`. 16 debut rows (`home_n_prior == 0`), **0** with a non-NaN as-of value.
Written through the same refuse-to-shrink atomic writer.

**HONEST NOTE:** the 2025-26 rows' as-of VALUES move -- they now have real prior history where they
previously had none. That costs no landed number: `nba_quarter_shape` has never produced a screen (it
was UNCOVERED at T0 in S85 and silently all-NaN before that). The three families S85 did screen are
re-run below as the regression check and reproduce to the sixth decimal.

### 1.4 (c) The all-NaN guard

`asof_supply._refuse_all_nan`, called on every declared supply's return value. `ScreenBinder` puts the
served window on the context frame (`self.frame.attrs.update(sport=sport, served_rows=self.rows)` --
the same `attrs` channel S85's MLB alias already uses), so the guard checks the window the screen will
actually SCORE, not the whole screen side. Zero non-null there raises
`SupplyUnavailable("all-NaN on the served window")`, which `source_column` already converts to
`ScreenRefused("unavailable: all-NaN on the served window")` -- so the family is REFUSED and counted
among the refusals, instead of drifting to a silent UNCOVERED.

Measured on the exact historical defect: re-registering `nba_quarter_shape` with `key="event_id"`
(the ESPN key S85 filed) and asking for `home_q1_margin_asof` on the real corpus now prints
`REFUSED: all-NaN on the served window`, where before it returned a series with 0 non-null of 800.
Synthetic coverage: `test_all_nan_on_the_served_window_is_refused_as_unavailable` builds a table whose
only value sits outside the served window and asserts both directions (served, refused; unserved,
returned).

Refusal counts in the (d) run: **86 refusals of 828 seeded** -- 68 `ratio_to_opponent needs a
home_/away_ or p1_/p2_ twin`, 9 `year is neither an asof_ column nor a gate-corpus column`, 9 `is_p1`
(both identifiers), and **0 `all-NaN on the served window`**, because (a) and (b) removed the only
family that would have triggered it.

---

## 2. (d) The local factory screen -- coverage before -> after

`python -m scripts.platformkit.eval_gate.s111_screen --out-dir <scratch>` (the run is a committed
script so it is re-runnable; S85's equivalent was ad hoc). Scratch sqlite, scratch trials dir, a ledger
path that is **never created**, `allow_charge=False`. 828 hypotheses seeded from the FROZEN
`FWER_FAMILIES_SPEC` grammar over the five S111 tennis families + `nba_quarter_shape` + the three NBA
families S85 already screened. 5 passes, **275.4 s** wall, **0 charges**.

Partition and window are the harness's own and unmoved: seed 20260903, SCREEN side only, last 800
states, coverage floor 0.8, purge 48 h + embargo 3 d inside `walk_forward`. Screen-partition shas
recomputed here are **byte-equal** to S58c / S79 / S85 / S108: nba `1a32541d44aa7fcb`, tennis
`c8dde4f3a44c8e58`.

Result rows: **1,420** = 742 T0 (678 COVERED, 64 UNCOVERED) + **678 T1 SCREEN** (was 200 for these
nine families -- **478 screens that had never existed**).

| family | best filled/800 BEFORE | AFTER | T0 rows | COVERED before -> after | T1 screens before -> after |
|---|---|---|---|---|---|
| `tennis_features` | 466 (58.2 pct) | **797 (99.6 pct)** | 125 | 0 -> **125** | 0 -> **125** |
| `tennis_return` | 466 (58.2 pct) | **797 (99.6 pct)** | 152 | 0 -> **150** | 0 -> **150** |
| `tennis_meta` | 469 (58.6 pct) | **800 (100 pct)** | 100 | 0 -> **78** | 0 -> **78** |
| `nba_quarter_shape` | 282 (35.2 pct) | **800 (100 pct)** | 125 | 0 -> **125** | 0 -> **125** |
| `tennis_schedule_density` | 469 (58.6 pct) | 469 (58.6 pct) | 24 | 0 -> 0 | 0 -> 0 |
| `tennis_travel_scouting` | 454 (56.8 pct) | 454 (56.8 pct) | 16 | 0 -> 0 | 0 -> 0 |
| `nba_opp_allowed` | 800 | 800 | 120 | 120 -> 120 | 120 -> 120 |
| `nba_player_adv` | 800 | 800 | 48 | 48 -> 48 | 48 -> 48 |
| `nba_player_value_features` | 800 | 800 | 32 | 32 -> 32 | 32 -> 32 |

**THE FLOOR WAS NOT MOVED (Q3).** It is still `_COVERAGE_FLOOR = 0.8` in `foundry/tiers.py`, byte
-identical to master. `tennis_meta` reaching 78 COVERED of 100 rather than 100 is the floor doing its
job on four members whose SOURCE is sparse, not a coverage bug: `p1_seed` 325/800 and `p2_seed`
304/800 (only seeded players carry a seed), `p2_ht` 638/800 and `diff_ht` 613/800 (Sackmann height is
12.4 pct null in the raw WTA CSVs). Those members stay honestly UNCOVERED.

**Two families remain CLOSED AT LIMIT.** `tennis_schedule_density` and `tennis_travel_scouting` sit at
58.6 / 56.8 pct for the same ATP/WTA reason, but their acquisition is a different one that S85 named
separately -- extend `schedule_density.parquet` and `travel_scouting.parquet` to the WTA half, which
is a different builder from the three this row scoped and is not attempted here.
`schedule_density_wta.parquet` is still one of the two paths `catalogue.absent()` names (down from
five).

---

## 3. (d) The screen table -- NULL

Improvement = `Brier incumbent - Brier model`; positive is better. The CI is the cluster-robust
95 pct interval on the paired loss difference, **recomputed from the archived per-event differential**
in the documented direction (`d = loss_incumbent - loss_model`), never quoted from the stored
`dm_stat` -- S79 filed that `tiers._run_screen` passes the sign mirror and that finding is unrepaired.

| family | screens | best member / transform | incumbent | Brier incumbent | Brier model | improvement | DM CI 95 | screen p | clusters |
|---|---|---|---|---|---|---|---|---|---|
| `tennis_features` | 125 | `p1_ace_rate_asof` / `delta_vs_prior` | **devigged close** | 0.197611 | 0.199522 | **-0.001911** | [-0.005899, +0.002077] | 0.3487 | 233 |
| `tennis_return` | 150 | `p1_break_pct_clay_asof` / `ratio_to_opponent` | **devigged close** | 0.197611 | 0.199176 | **-0.001565** | [-0.005141, +0.002011] | 0.3919 | 233 |
| `tennis_meta` | 78 | `p2_rank_points` / `delta_vs_prior` | **devigged close** | 0.197611 | 0.197423 | **+0.000188** | [-0.007000, +0.007377] | 0.9591 | 233 |
| `nba_quarter_shape` | 125 | `home_q1_margin_asof` / `ratio_to_opponent` | p_base (**Elo**, not a close) | 0.205118 | 0.203591 | **+0.001527** | [-0.004355, +0.007408] | 0.6148 | 30 |
| `nba_opp_allowed` | 120 | `opp_fg3m_allowed_vs_league` / `ew` | p_base (**Elo**) | 0.205118 | 0.203259 | +0.001858 | [-0.001921, +0.005638] | 0.3432 | 30 |
| `nba_player_adv` | 48 | `usagepercentage_asof` / `rank_in_league` | p_base (**Elo**) | 0.205118 | 0.204065 | +0.001053 | [-0.002813, +0.004919] | 0.5976 | 30 |
| `nba_player_value_features` | 32 | `continuity` / `z_vs_league` | p_base (**Elo**) | 0.205118 | 0.199897 | +0.005221 | [+0.000451, +0.009992] | 0.0404 | 30 |

**Multiplicity.** 2 of 678 screens have a recomputed CI lower bound above zero, against ~16.9 expected
by chance at the 2.5 pct tail -- FEWER than chance. Both are the same column (`continuity`, `raw` and
`z_vs_league`) in the same already-known family, and both are scored against **Elo, not a close**.
256 of 678 (37.8 pct) improve at all. **NULL.**

**NO PREREG DRAFTED.** The bar for one was a close-relative screen clearing +0.004 with a CI excluding
zero. Every close-relative screen here (the three tennis families, incumbent = the devigged close) is
negative or spans zero; the only interval excluding zero is vs Elo and is the S85 result, not a new
close-relative one. The market is efficient on these families; we do not match the close with them.

**REGRESSION CHECK (the point of re-screening the three NBA families S85 already ran).** Their
improvements reproduce to the sixth decimal -- `nba_player_value_features` +0.005221 (S85 +0.005221),
`nba_opp_allowed` +0.001858 (S85 +0.001858), `nba_player_adv` +0.001053 (S85 +0.001053), with the same
best member and transform each time. The bridge moved no already-screened family's values.
*One disclosed difference:* my recomputed interval for `nba_player_value_features` is
[+0.000451, +0.009992] against S85's published [+0.000244, +0.010199]. The point estimate is identical;
the interval differs in the fourth decimal because the two recomputations use different small-sample
cluster-variance corrections. Both exclude zero, and neither is a close-relative claim.

---

## 4. Self-check against `docs/evidence/tracking/VERIFIER_CONTRACT.md` (B + Q)

- **B1** no metric is computed after excluding rows that would fail it. Coverage is measured over the
  whole frozen 800-row served window; the UNCOVERED members are named with their counts.
- **B2** additive schema. `build_asof_meta` gained a keyword with its existing behaviour as the
  default; `_load_glob` gained comma handling that no existing pattern uses; `asof_quarter_shape.parquet`
  keeps every column and gains rows. `asof_supply_columns.py` is a verbatim move of private names with
  no reader outside the module (grepped). Readers of `asof_quarter_shape.parquet` re-tested below.
- **B3** no gate quarantines on absent evidence: a row the bridge cannot key stays NaN and drops out of
  the alignment, exactly as before.
- **B5** nothing was copied to the pod.
- **B6** no module moved or retired; no orphaned import or `-m` reference. The one renamed test
  function (`..._exactly_the_five_s11_named` -> `..._exactly_the_two_still_unbuilt`) is referenced
  nowhere else.
- **B7** no head slices: T0's vintage sample is the harness's own even `[::step]` sample and every one
  of the 800 served rows is scored.
- **B10 / Q3** no bar moved. `_COVERAGE_FLOOR = 0.8`, seed 20260903, 800-row window, ridge 1e-3, purge
  48 h, embargo 3 d, `IMPROVEMENT_BAR` -- all untouched; the two families that could not reach the
  floor are reported CLOSED AT LIMIT, not lowered to.
- **Q1** no scored comparison is claimed, so no seal is required and none is asserted. A SCREEN is a
  non-finding.
- **Q2** no charge. `tiers.charge_tier` was never reached (`allow_charge=False`), `_charge_ledger` was
  never called, the scratch ledger path was never created, and
  `data/cache/eval_gate/backtest_fwer.jsonl` is **18 rows** before and after.
- **Q4** every screen runs inside `eval_gate.walk_forward` with purging and the symmetric embargo,
  `select_inside` only; no meta-learner is involved.
- **Q5** no AHEAD is claimed, so the two-corpora rule is not engaged.
- **Q6** calibration language only; no dollar / ROI / profit / edge word, and none of the retracted
  figures appears.
- **Q7** the coverage numbers are SAMPLED metrics at n = 800 and the screen table is n = 678 screens.
- **Q8** the premise was re-measured first (section 0) and holds; part of it -- "the siblings may
  already exist under other names" -- was checked and is NOT falsified.
- **Q9** each T1 trial's JSON carries its full per-event differential (`event_id`, timestamp, cluster,
  `loss_model`, `loss_close`), and every CI in section 3 was recomputed from those rows alone by
  `s111_screen.dm_ci`; the model side is the archived per-refit fit state in the same JSON.

**Human-gated trees untouched:** nothing under `src/`, `kernel/`, `api/`, `intel/`,
`scripts/team_system/` was read for writing or edited. `data/registry/` untouched. No feature flag
flipped. `scripts/platformkit/eval_gate/s81_market_move.py` (the S81 lane's file) untouched.

---

## 5. Tests

Per-file only:

```
python -m pytest domains/tennis/test_asof_wta_siblings.py -q               3 passed in 0.20s
python -m pytest domains/basketball_nba/test_asof_quarter_shape_full.py -q 3 passed in 0.72s
python -m pytest tests/platformkit/foundry/test_asof_supply.py -q          5 passed in 2.35s
python -m pytest tests/platformkit/foundry/test_catalogue.py -q           13 passed in 1.38s
```

Readers of the touched artifacts, re-run unchanged (A5):
`tests/platformkit/test_asof_quarter_shape.py` 6 passed - `tests/platformkit/test_gate_test_quarter_shape.py`
5 passed - `tests/platformkit/foundry/test_screen_predictor.py` 3 passed -
`tests/platformkit/foundry/test_tiers.py` 12 passed - `tests/platformkit/foundry/test_family_combo_screen.py`
3 passed - `tests/platformkit/foundry/test_foundry_runner_s16.py` 7 passed -
`scripts/platformkit/test_foundry_runner.py` 1 passed - `domains/tennis/test_asof_meta.py` 6 passed -
`scripts/platformkit/data_frontier/test_utilization_audit.py` 4 passed -
`scripts/platformkit/interaction_factory/test_builders_ingame_state.py` 6 passed -
`tests/platformkit/eval_gate/test_s108_pregame_full_model.py` 8 passed -
`scripts/platformkit/eval_gate/test_catalog_rescreen.py` 8 passed -
`scripts/platformkit/ops/test_safe_parquet_write.py` 6 passed.

## 6. Files

| file | LOC | what |
|---|---|---|
| `domains/tennis/asof_wta_siblings.py` | 113 | new - runs the three frozen ATP builders against the WTA spine |
| `domains/tennis/test_asof_wta_siblings.py` | 55 | new - strictly-before on a synthetic spine + the two wiring checks |
| `domains/tennis/asof_meta.py` | 234 | + additive `pattern` keyword (default unchanged) |
| `domains/basketball_nba/asof_quarter_shape_full.py` | 108 | new - both linescores shards, one as-of pass, bridge key |
| `domains/basketball_nba/test_asof_quarter_shape_full.py` | 60 | new - union/dedup, cross-shard prior history, bridge key |
| `scripts/platformkit/foundry/asof_supply.py` | 298 | + comma-listed sources, 3 tennis entries, the all-NaN guard |
| `scripts/platformkit/foundry/asof_supply_columns.py` | 36 | new - the closed column lists, moved out to stay under the cap |
| `scripts/platformkit/foundry/screen_predictor.py` | 300 | the served window put on the context `attrs` (1 line, no growth) |
| `scripts/platformkit/eval_gate/s111_screen.py` | 148 | new - the (d) run as a re-runnable script |
| `tests/platformkit/foundry/test_asof_supply.py` | 142 | + the all-NaN guard test, + comma-aware source glob assertion |
| `tests/platformkit/foundry/test_catalogue.py` | - | the absent list drops from five to two |

Artifacts written under `data/` (gitignored, never staged): `asof_features_wta.parquet`,
`asof_return_wta.parquet`, `asof_meta_wta.parquet`, and the rebuilt `asof_quarter_shape.parquet`.
