# S122 -- the WTA half of the tennis schedule/travel tables, and the leak it exposed

**Row:** S122 (data) in `docs/evidence/HARNESS_GAPS_2026-09-03.md`.
**Parent:** S111 (`docs/evidence/harness/S111_coverage_acquisitions_2026-09-03.md`), section 2.
**Verdict:** **ACQUISITION LANDED / BOTH FAMILIES CLOSED AT LIMIT.** The WTA halves are built and
the registration they enable does carry both families over the frozen 0.8 floor -- 800/800 and
785/800. That registration is **NOT landed**, because the screen it unlocks is a **LEAK**: the
sources are keyed on Sackmann's tourney-START date, so a trailing-window count cannot order a
player's matches inside an event. The row's anticipated failure mode (a missing column on the WTA
spine) is **FALSIFIED**; the real limit is one the row did not name.

A SCREEN IS A NON-FINDING, AND A LEAKY SCREEN IS NOT EVEN THAT. Calibration language only -- no
dollar, ROI, profit or edge claim appears here, and none of the retracted figures is quoted.
**The `+0.020155` improvement reproduced in section 4 is a MEASUREMENT ARTIFACT. It must never be
quoted as a result.**

---

## 0. Premise (Q8), measured before any change

`python -m scripts.platformkit.eval_gate.s122_screen --out-dir <scratch>` on master:

| the row's premise | measured | verdict |
|---|---|---|
| `tennis_schedule_density` sits at 469/800 | **469/800 = 0.5863** (best filled member) | **HOLDS** |
| `tennis_travel_scouting` sits at 454/800 | **454/800 = 0.5675** | **HOLDS** |
| both are under the floor because their parquets are ATP-only | `schedule_density.parquet` 61,232 rows and `travel_scouting.parquet` 55,446 rows, both built from `matches.parquet` (30,616 rows, 100 pct `tour == "atp"`); the tennis gate corpus is 41,886 rows = 30,616 ATP + 11,270 WTA | **HOLDS** |
| *the row's implicit failure mode:* a required column may be absent from `wta_matches.parquet`, in which case report CLOSED AT LIMIT with the missing column | `wta_matches.parquet` (11,270 rows) carries **every** column both builders read -- `event_id, date, surface, tourney_name, p1_id, p2_id, p1_name, p2_name` -- with **zero nulls in all eight**, and the same 21-column schema as the ATP spine | **FALSIFIED** -- no column is missing |

Both builders are already parametrised by their spine, so no new walk was needed:
`domains/tennis/ingest_schedule_density.build(src, out)`, and
`scripts/platformkit/geo/travel_scouting_tennis.build_corpus(matches_path)` +
`add_descriptors` + `write(df, out)`.

**Join keys and the strictly-before rule as the builders define them.** Both MELT the wide spine
into one row per player-appearance (p1 and p2 of every match) and walk each player's own sorted
history: schedule density takes `groupby(player_id)["date"].diff()` (a player's first appearance
-> NaN) plus a trailing time-window rolling count minus the current row; travel takes
`prior_city_travel`, the great-circle miles from that player's PREVIOUS resolved host city (first
appearance -> NaN, never 0-filled). The bridge then reads a side off the `event_id` and serves
p1-minus-p2. Family members are the frozen ones:
`tennis_schedule_density` = `year, rest_days, matches_last_7d, matches_last_14d` (`year` is an
IDENTIFIER and always refused); `tennis_travel_scouting` = `is_p1, miles_flown_in,
venue_altitude_m` (`is_p1` likewise refused).

---

## 1. What was built

`domains/tennis/wta_schedule_travel.py` (107 LOC). The two frozen builders called with the WTA
spine -- there is no second copy of either walk to keep in step. Each builder writes its own
parquet, so it writes a scratch file next to the target which is then re-written through
`scripts/platformkit/ops/safe_parquet_write.write_parquet_atomic` (atomic replace,
refuse-to-shrink; the S111 shape).

| table | rows | sha256[:16] | bytes | leak / debut check |
|---|---|---|---|---|
| `data/domains/tennis/schedule_density_wta.parquet` | **22,540** (= 11,270 x 2, both sides of every WTA match), 968 distinct players | `7381fa6e044eddc6` | 298,991 | 968 players; a player's first appearance carries NaN `rest_days` |
| `data/domains/tennis/travel_scouting_wta.parquet` | **18,106** of 22,540 appearance rows (80.3 pct tourney-name-to-city resolution), 486 players | `e49cb765414a4318` | 186,472 | 486 first appearances, **0** with a non-NaN `miles_flown_in`; `venue_altitude_m` non-null on all 18,106 |

**A NEW TABLE, NOT A WIDER SPINE** -- the S111 rule. The ATP parquets are the frozen `sources` of
families the FWER spec pins by hash; appending WTA rows to them would move a family's source.

`scripts/platformkit/foundry/catalogue.py` NAMES `travel_scouting_wta.parquet` (`NAMED` 32 -> 33).
`catalogue.absent()` drops from two paths to **one** (`data/domains/soccer/asof_discipline_features.parquet`).

---

## 2. The side-parse repair (`asof_supply._sides`)

A tennis `event_id` ENDS `<p1_id>-<p2_id>-<match_num>`, but the bridge read the side from split
position **4**. A dashed `tourney_id` shifts the head, and both spines have plenty:

| spine | `str[4] == p1_id` | `str[-3] == p1_id` | `str[-2] == p2_id` | id part counts |
|---|---|---|---|---|
| ATP (30,616) | **93.17 pct** | 100 pct | 100 pct | 7: 28,526 - 14: 1,310 - 15: 636 - 16: 144 |
| WTA (11,270) | **74.91 pct** | 100 pct | 100 pct | 7: 8,442 - 16: 1,008 - 11: 820 - 14: 429 - 15: 200 - 10: 189 - 17: 182 |

Repaired to `str[-3]` / `str[-2]`. It is a correctness fix that moves **no landed number**: the
only surviving consumer is `tennis_serve_return_profiles`, whose filled count on the served window
is **423/800 under `str[4]` and 423/800 under `str[-3]`** (a `prior`-rule row fills only when BOTH
sides resolve, and the shifted ids resolve to players absent from that 383-player table anyway).
Its T0 `n_eff` is 593/800 in both the before and after runs, and it is UNCOVERED in both.
`_load_tennis_sides` had one caller, the withheld entry, and is retired with it (B6).

---

## 3. The registration -- BUILT, MEASURED, AND WITHHELD

Declaring the two families over the ATP+WTA source pair (the S111 comma-listed `source`, `_load_glob`)
**does** clear the floor. Reproducible from the landed tree with
`python -m scripts.platformkit.eval_gate.s122_screen --out-dir <scratch> --register-leaky`, which
declares them IN THIS PROCESS ONLY and writes nothing to disk:

| family | best filled/800 BEFORE | AFTER | T0 rows | COVERED before -> after | T1 screens before -> after |
|---|---|---|---|---|---|
| `tennis_schedule_density` | 469 (58.63 pct) | **800 (100 pct)** | 24 | 0 -> **24** | 0 -> **24** |
| `tennis_travel_scouting` | 454 (56.75 pct) | **785 (98.12 pct)** | 16 | 0 -> **16** | 0 -> **16** |
| `tennis_serve_return_profiles` (regression) | 593 (74.12 pct) | 593 (74.12 pct) | 40 | 0 -> 0 | 0 -> 0 |

**THE FLOOR WAS NOT MOVED (Q3).** `_COVERAGE_FLOOR = 0.8` in `foundry/tiers.py` is byte-identical
to master, as are the seed 20260903, the 800-row window, the purge/embargo and `IMPROVEMENT_BAR`.
The tennis screen-partition sha256 recomputed here is `c8dde4f3a44c8e58`, **byte-equal** to
S58c / S79 / S85 / S108 / S111.

**In the LANDED registry both families are refused**: 40 T0 rows, **0 COVERED, 0 T1 SCREEN**, and
the only family reported is `tennis_serve_return_profiles` at 593/800.

---

## 4. Why it is withheld -- the tourney-date leak

`python -m scripts.platformkit.eval_gate.s122_screen --leak-probe`:

```
ATP spine: 1451 tourneys, 1451 with exactly ONE distinct date
WTA spine:  974 tourneys,  974 with exactly ONE distinct date
rows reading rest_days == 0: 0.4618 of 83772
2025 Wimbledon champion, matches_last_7d by round R128..F: [0.0, 3.0, 4.0, 5.0, 1.0, 6.0, 2.0]
matches_last_7d          filled 800/800  corr(p1-minus-p2, outcome) = +0.2616
miles_flown_in           filled 773/800  corr(p1-minus-p2, outcome) = -0.0944
```

Two stacked defects, both in the FROZEN ATP builders and both **predating this row**:

1. **`date` is the tournament START date, not the match date.** Every match of a tournament carries
   one identical date -- 1451/1451 ATP and 974/974 WTA tourneys have exactly one distinct value. A
   "matches in the trailing 7 days" count therefore spans the player's whole run at that event,
   including the rounds played AFTER this match, and 46.18 pct of all 83,772 rows read
   `rest_days == 0` because their previous appearance is a sibling match of the same event.
2. **The values are scrambled across a player's rows within the tie.** The builder indexes on
   `date` and assigns the grouped rolling result back onto a duplicated index. The 2025 Wimbledon
   champion's seven matches serve `0,3,4,5,1,6,2` -- the correct chronological sequence
   `0..6`, permuted onto the wrong rows. An R64 row can be handed a semifinal's count.

Recomputed on the 800-row served window, the diff of a strictly-EXCLUSIVE count (`< D`) correlates
`+0.1338` with the outcome; the builder's inclusive count (`<= D`) correlates `+0.7451`; the value
the bridge actually serves correlates `+0.2616`, sitting between the two because of defect 2.

The screen this produces, **reported here only so it is never mistaken for a result**:

| family | screens | best member / transform | incumbent | Brier incumbent | Brier model | improvement | DM CI 95 | screen p | clusters |
|---|---|---|---|---|---|---|---|---|---|
| `tennis_schedule_density` | 24 | `matches_last_7d` / `rank_in_league` | devigged close | 0.197611 | 0.177456 | **+0.020155 (LEAK ARTIFACT)** | [+0.011018, +0.029293] | 0.0000 | 233 |
| `tennis_travel_scouting` | 16 | `miles_flown_in` / `rank_in_league` | devigged close | 0.197611 | 0.192989 | +0.004622 | [-0.000912, +0.010156] | 0.1030 | 233 |

5 of 40 screens have a recomputed CI lower bound above zero against ~1.0 expected by chance; all
five are `tennis_schedule_density`, four of them the same `matches_last_7d` column. That is the
signature of a leak, not of a signal. `tennis_travel_scouting` is **NULL on its own terms** (the
interval spans zero) and is contaminated by the same defect anyway: within a tournament every
appearance shares one city and one date, so `miles_flown_in` reads 0 for a player's second and
later matches -- a round-depth proxy wearing a travel name.

**NO PREREG DRAFTED.** The bar was a close-relative screen clearing +0.004 with a CI excluding
zero. One screen meets it arithmetically and is a leak; the other does not meet it. Registering
either would arm a charged promotion on a column that is not settled before the event -- the
`allow_charge=False` run already held 20 + 16 promotions for exactly these two families.

**CLOSED AT LIMIT.** No as-of column can be built off this date grain. The limit is the source
data: Sackmann publishes a tourney date, not a match date. Lifting it needs a per-match date from
another feed, not another builder. The WTA halves are built and named so that acquisition is done
when a match-level date arrives.

`asof_supply.REGISTRY` carries the measurement as a comment where the two entries would go, and
`test_neither_family_is_declared_because_the_date_is_the_tourney_date` pins it on the real corpus,
so re-registering these columns fails a test first.

---

## 5. Self-check against `docs/evidence/tracking/VERIFIER_CONTRACT.md` (B + Q)

- **B1** no metric is computed after excluding rows that would fail it. Coverage is measured over
  the whole frozen 800-row served window and the UNCOVERED families are named with their counts.
- **B2** additive schema. Two NEW parquets; no existing table gains or loses a column. The two
  withheld registry entries never produced a COVERED row or a screen in any run (0 T1 before, 0 T1
  landed), so removing them moves no landed number -- and the one behaviour change, `_sides`
  `str[4] -> str[-3]`, is measured at 423/800 -> 423/800 on its only consumer (section 2).
- **B3** no gate quarantines on absent evidence: an unresolved tourney city stays NaN and drops out
  of the alignment, exactly as before.
- **B5** nothing was copied to the pod.
- **B6** `_load_tennis_sides` is retired together with its only caller; no import or `-m` reference
  is left behind (grepped across `scripts`, `domains`, `tests`). The renamed catalogue test
  (`..._exactly_the_two_still_unbuilt` -> `..._exactly_the_one_still_unbuilt`) is referenced only
  in the S111 memo's prose.
- **B7** no head slices: every one of the 800 served rows is scored, and the leak probe reports the
  champion's full R128..F sequence, not a prefix.
- **B10 / Q3** no bar moved: `_COVERAGE_FLOOR = 0.8`, seed 20260903, 800-row window, purge 48 h,
  embargo 3 d, `IMPROVEMENT_BAR` all untouched. The families that could not be served honestly are
  reported CLOSED AT LIMIT, never served on a lowered bar.
- **Q1** no scored comparison is claimed, so no seal is required and none is asserted.
- **Q2** no charge. `allow_charge=False`, `tiers.charge_tier` never reached, `_charge_ledger` never
  called, the scratch ledger path never created, and `data/cache/eval_gate/backtest_fwer.jsonl` is
  **18 rows** before and after and was never opened.
- **Q4** every screen runs inside `eval_gate.walk_forward` with purging and the symmetric embargo;
  no meta-learner is involved. The leak in section 4 is a defect of the SOURCE, upstream of the
  walk -- which is precisely why the walk could not catch it and the family is withheld instead.
- **Q5** no AHEAD is claimed, so the two-corpora rule is not engaged.
- **Q6** calibration language only; no dollar / ROI / profit / edge word, and none of the retracted
  figures appears. The one figure that clears a bar is labelled a LEAK ARTIFACT everywhere it is
  printed. An honest REJECT is a success.
- **Q7** coverage is a SAMPLED metric at n = 800; the screen table is n = 40 screens; the spine
  date-uniqueness and the id-part counts are CONSTRUCT (every tourney and every id enumerated).
- **Q8** the premise was re-measured first (section 0). Its two coverage numbers reproduce exactly;
  its implicit failure mode (a missing column) is FALSIFIED.
- **Q9** each T1 trial's JSON carries its full per-event differential and every CI in section 4 was
  recomputed from those rows alone by `s111_screen.dm_ci` in the documented direction.

**Human-gated trees untouched:** nothing under `src/`, `kernel/`, `api/`, `intel/`,
`scripts/team_system/` was read for writing or edited. `data/registry/` untouched. No feature flag
flipped. No file owned by the S92 / S118 / S120 / S121 lanes was edited --
`foundry/ingame_screen.py` was neither read for writing nor touched.

---

## 6. Tests

Per-file only:

```
python -m pytest domains/tennis/test_wta_schedule_travel.py -q          5 passed in 0.31s
python -m pytest tests/platformkit/foundry/test_asof_supply.py -q       5 passed in 1.62s
python -m pytest tests/platformkit/foundry/test_catalogue.py -q        13 passed in 0.53s
```

Readers of the touched modules and artifacts, re-run unchanged (A5):
`tests/platformkit/foundry/test_screen_predictor.py` 5 passed -
`tests/platformkit/foundry/test_tiers.py` 12 passed -
`tests/platformkit/foundry/test_family_combo_screen.py` 3 passed -
`tests/platformkit/foundry/test_foundry_runner_s16.py` 7 passed -
`scripts/platformkit/test_foundry_runner.py` 1 passed -
`domains/tennis/test_ingest_schedule_density.py` 5 passed -
`scripts/platformkit/geo/test_travel_scouting.py` 12 passed -
`domains/tennis/test_asof_wta_siblings.py` 3 passed -
`scripts/platformkit/ops/test_safe_parquet_write.py` 6 passed -
`scripts/platformkit/eval_gate/test_catalog_rescreen.py` 8 passed -
`scripts/platformkit/data_frontier/test_utilization_audit.py` 4 passed.

## 7. Files

| file | LOC | what |
|---|---|---|
| `domains/tennis/wta_schedule_travel.py` | 107 | new - runs the two frozen ATP builders against the WTA spine, atomic refuse-to-shrink write |
| `domains/tennis/test_wta_schedule_travel.py` | 80 | new - strictly-before on a synthetic spine, the side-parse repair, and the tourney-date leak pinned on the real corpus |
| `scripts/platformkit/eval_gate/s122_screen.py` | 156 | new - the screen as a re-runnable script, plus `--register-leaky` and `--leak-probe` so both halves of this memo reproduce from the landed tree |
| `scripts/platformkit/foundry/asof_supply.py` | 293 | `_sides` reads the side from the END of the event_id; the two tennis entries and `_load_tennis_sides` withheld, with the measurement in their place |
| `scripts/platformkit/foundry/catalogue.py` | - | + `travel_scouting_wta.parquet` NAMED (32 -> 33) |
| `tests/platformkit/foundry/test_catalogue.py` | - | the absent list drops from two to one |

Artifacts written under `data/` (gitignored, never staged): `schedule_density_wta.parquet`,
`travel_scouting_wta.parquet`.
