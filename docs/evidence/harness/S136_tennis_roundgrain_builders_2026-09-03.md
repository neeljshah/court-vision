# S136 -- the tennis schedule-density and travel builders, rebuilt at (date, ROUND) grain

**Row:** S136 (data) in `docs/evidence/HARNESS_GAPS_2026-09-03.md`.
**Parent:** S122 (`docs/evidence/harness/S122_tennis_wta_schedule_travel_2026-09-03.md`), section 4.
**Verdict:** **ACCEPT WITH CORRECTIONS -- the leak is removed and the re-screen is NULL.**
Four new `*_rg` tables are built beside the frozen four; nothing existing moved. The
permutation S122 pinned is gone (the 2025 Wimbledon champion serves `0,1,2,3,4,5,6`), the
served value's correlation with the outcome falls from `+0.2616` to `+0.0481` -- inside the
`+/- 0.0693` two-sigma band at n = 800 -- and the local re-screen of both families against the
devigged close is a **clean NULL: 0 of 32 screens improve on the close at all.** One member,
`rest_days`, is **CLOSED AT LIMIT** and dropped. The registration itself is NOT applied here:
`foundry/asof_supply.py` is owned by another lane, so the exact entries are handed to the
orchestrator in section 5.

A SCREEN IS A NON-FINDING, and a NULL screen is the expected one. Calibration language only --
no dollar, ROI, profit or edge claim appears here, and none of the retracted figures is quoted.
S122's `+0.020155` is a MEASUREMENT ARTIFACT of the leaky tables and is never a result.

---

## 0. Premise (Q8), re-measured before any change

`python -m scripts.platformkit.eval_gate.s122_screen --leak-probe` on the working tree, verbatim:

```
ATP spine: 1451 tourneys, 1451 with exactly ONE distinct date
WTA spine:  974 tourneys,  974 with exactly ONE distinct date
rows reading rest_days == 0: 0.4618 of 83772
2025 Wimbledon champion, matches_last_7d by round R128..F: [0.0, 3.0, 4.0, 5.0, 1.0, 6.0, 2.0]
matches_last_7d          filled 800/800  corr(p1-minus-p2, outcome) = +0.2616
miles_flown_in           filled 773/800  corr(p1-minus-p2, outcome) = -0.0944
```

| the row's premise | measured | verdict |
|---|---|---|
| Sackmann's `date` is the tourney START date | 1451/1451 ATP and 974/974 tourneys carry exactly ONE distinct date | **HOLDS** |
| the champion's seven matches serve a permutation | `0,3,4,5,1,6,2` reproduced byte-for-byte | **HOLDS** |
| the served value correlates +0.2616 with the outcome | `+0.2616` reproduced | **HOLDS** |
| frozen table sizes 61,232 / 55,446 | `schedule_density.parquet` 61,232 rows, `travel_scouting.parquet` 55,446 | **HOLDS** |
| *the row's premise for the FIX:* the spines carry a Sackmann round column | `round` present on BOTH spines with **zero nulls**: ATP 30,616 rows as R32 9,316 - R16 5,400 - R64 4,413 - R128 3,744 - RR 2,911 - QF 2,715 - SF 1,408 - F 704 - BR 5; WTA 11,270 rows as R128 3,520 - R64 2,702 - RR 2,266 - R32 1,392 - R16 716 - QF 356 - SF 210 - F 105 - BR 3. `ER` does not occur. | **HOLDS** |
| no builder already orders by round | `round` appears in neither `domains/tennis/ingest_schedule_density.py` nor `scripts/platformkit/geo/travel_scouting_tennis.py` nor `travel_scouting_common.py` nor `domains/tennis/wta_schedule_travel.py` -- the only matches for the token are the Python builtin `round(...)` in two coverage-percentage lines | **HOLDS -- not falsified** |

The row is **NOT FALSIFIED**. Every fact it rests on reproduces, and the fix it names is available.

---

## 1. What changed -- the ORDER, and only the order

`domains/tennis/schedule_density_roundgrain.py` (169 LOC). Every player's appearances are
sorted by `(tourney start date, ROUND)` and a match at `(D, r)` counts **only** rows with

* `date < D`, or
* `date == D` **and** `round < r`,

inside the same trailing window the frozen builder used (`(D - n days, D]`, pandas'
right-closed `rolling("<n>D")`). Two bounds do the work, both read off the sorted arrays: `lo`
is the first row inside the window, and `first` is the first row carrying **this row's own**
`(date, round)` key -- so the count stops before the whole tie, not merely before this row. A
row can therefore never see itself, a sibling of equal round, or a later round of its own event.

The travel table reuses the frozen city resolution and descriptor walk unchanged: it is handed
a frame **already ordered** by `(player, date, round)`, and `travel_scouting_common.prior_city_travel`
breaks ties by original row order, so its "previous resolved host city" is read under exactly
the same order. No second copy of the geo walk exists.

The Sackmann round order used is
`ER 0 - R128 1 - R64 2 - R32 3 - R16 4 - RR 5 - QF 6 - SF 7 - BR 8 - F 9`.
`RR` sits above the draw rounds and below `QF` on a measured fact: the only round sets that
contain `RR` in either spine are `{RR}`, `{RR,SF,F}` and `{RR,QF,SF,F}` -- `RR` never co-occurs
with a draw code, so its rank cannot re-order anything. An unknown round code raises rather than
mapping to NaN, which would sort silently to one end.

---

## 2. What was built

| table | rows | players | sha256[:16] | bytes |
|---|---|---|---|---|
| `data/domains/tennis/schedule_density_rg.parquet` | 61,232 | 1,273 | `90df53674cb8f47a` | 997,949 |
| `data/domains/tennis/schedule_density_rg_wta.parquet` | 22,540 | 968 | `39445654217fe585` | 293,889 |
| `data/domains/tennis/travel_scouting_rg.parquet` | 55,446 | 783 | `af44e0411915b7f4` | 1,072,502 |
| `data/domains/tennis/travel_scouting_rg_wta.parquet` | 18,106 | 486 | `df3f4066f167e861` | 240,646 |

Row counts are **identical** to the four frozen tables (61,232 / 22,540 / 55,446 / 18,106): the
appearance spine is unchanged, only the values on it move. Written through
`scripts/platformkit/ops/safe_parquet_write.write_parquet_atomic` (atomic replace,
refuse-to-shrink), the S95/S111 shape. **NEW TABLES BESIDE THE OLD ONES** -- the frozen parquets
are the pinned `sources` of families the FWER spec hashes and none of them is touched.

The permutation is gone:

```
2025 Wimbledon champion, matches_last_7d by round R128..F: [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
round-grain rows reading matches_last_7d == 0: 0.5363 of 83772
rest_days present in the round-grain table: False
```

The `matches_last_7d == 0` share RISES (0.4618 of rows read `rest_days == 0` before; 0.5363 of
rows now read a zero count) because the leak was an OVER-count: rows that were being handed a
later round's number now honestly read zero.

---

## 3. Three limits, recorded rather than papered over

**`rest_days` is CLOSED AT LIMIT and DROPPED.** Real rest DAYS inside a tournament are not
recoverable from a tourney-grain date: every round of an event shares one date, so the honest
answer for every round after the first is 0, and the column would be a round-depth proxy
wearing a rest name. It is not a column of the round-grain table and is not in the declared
member list, so its four hypotheses stay UNCOVERED exactly as they are today. Lifting this needs
a per-match date from another feed, not another builder -- unchanged from S122's finding.

**Round-robin ties are an UNDER-count, never a leak.** All group matches carry the single code
`RR`, so a player's group matches cannot be ordered among themselves. Measured: **5.41 pct** of
ATP and **5.65 pct** of WTA appearance rows sit in a `(tourney, player, round)` tie -- 3,311 of
61,232 ATP rows, all `RR`; 1,274 of 22,540 WTA rows, 1,250 `RR` and 24 `R16`. Under the
strictly-before rule tied rows do not see each other, so a round-robin sibling counts zero of
its own group. That is a systematic under-count of at most a few matches on 5 pct of rows, and
it can only ever remove information, never add the future.

**A within-tourney later round still reports a 0-mile hop.** Every round of an event shares one
resolved host city, so a player's second and later appearances there read `miles_flown_in == 0`.
That is arithmetically correct under the order (no flight happened) but it means the column
still carries round-depth information as well as travel. It is pinned by a test rather than
hidden, and the re-screen below is NULL on this family with or without the ambiguity.

---

## 4. The re-screen -- NULL

`python -m scripts.platformkit.eval_gate.s136_screen --out-dir <scratch>`. The two families are
declared over the round-grain sources **for the life of the process only** -- nothing on disk
changes -- and screened with `--predictor real` against the devigged close on the frozen
800-row screen window.

```
seeded sport=tennis n=108
screen_partition_sha256 sport=tennis c8dde4f3a44c8e58
foundry_pass=0 screens=108 promotions=32 charges=0 idle=False
wall_seconds=29.1 charged_ledger_created=False
result rows: 104 = 72 T0 (32 COVERED, 40 UNCOVERED) + 32 T1 SCREEN
```

| family | T0 | COVERED | best filled/800 | pct |
|---|---|---|---|---|
| `tennis_schedule_density` | 16 | **16** | **800/800** | 1.0000 |
| `tennis_travel_scouting` | 16 | **16** | **785/800** | 0.9812 |
| `tennis_serve_return_profiles` (regression) | 40 | 0 | 593/800 | 0.7412 |

Both families clear the frozen `_COVERAGE_FLOOR = 0.8` at the same coverage S122 measured on the
leaky tables (800/800 and 785/800), and the regression family is unmoved at 593/800, 0 COVERED.

| family | screens | best member / transform | incumbent | Brier incumbent | Brier model | improvement | DM CI 95 (recomputed) | screen p | clusters |
|---|---|---|---|---|---|---|---|---|---|
| `tennis_schedule_density` | 16 | `matches_last_7d__z_vs_league` | devigged close | 0.197611 | 0.199231 | **-0.001620** | [-0.005050, +0.001810] | 0.3555 | 233 |
| `tennis_travel_scouting` | 16 | `venue_altitude_m__z_vs_league` | devigged close | 0.197611 | 0.199560 | **-0.001949** | [-0.005138, +0.001240] | 0.2321 | 233 |

**T1 with a recomputed CI lower bound above zero: 0 of 32** (about 0.8 expected by chance at
2.5 pct). **Screens improving on the close at all: 0 of 32 (0.0 pct).** The BEST member of each
family is BEHIND the close, and every interval straddles zero. Compare S122's leaky run on the
same window: 5 of 40 CIs cleared zero, four of them the same `matches_last_7d` column, and the
best improvement was the `+0.020155` artifact. The signature of a leak is gone with the leak.

The served value against the outcome, before and after, measured like-for-like on the identical
800-row window (the "before" row re-declares the frozen sources FOR MEASUREMENT ONLY):

| served column | frozen (tourney-date) | round-grain | 2-sigma noise band at n = 800 |
|---|---|---|---|
| `matches_last_7d` | **+0.2616** | **+0.0481** | +/- 0.0693 |
| `matches_last_14d` | +0.2112 | +0.0685 | +/- 0.0693 |
| `miles_flown_in` | -0.0944 | +0.0565 | +/- 0.0693 |

All three round-grain correlations sit inside the band; none of the three frozen ones did on the
density side. **NO PREREG DRAFTED** and none is required: nothing here clears a bar, so there is
no scored claim to seal (Q1).

**No bar moved (Q3/B10).** `_COVERAGE_FLOOR = 0.8` in `foundry/tiers.py` is byte-identical to
master, as are the seed 20260903, the 800-row window, the purge/embargo and `IMPROVEMENT_BAR`.
The tennis screen-partition sha256 is `c8dde4f3a44c8e58`, **byte-equal** to
S58c / S79 / S85 / S108 / S111 / S122.

---

## 5. The exact registry entries for the orchestrator

`scripts/platformkit/foundry/asof_supply.py` is owned by the asof_supply lane and was **not
edited here**. Apply these three pieces there. Note the `pregame` field: the S129 fix in that
lane's working tree makes `_side_rule` fail closed unless an entry DECLARES its pregame as-of
basis, and both entries below carry one. The screen in section 4 was run with that guard live.

```python
def _load_tennis_sides(path: str) -> pd.DataFrame:
    """The round-grain density table carries `player_id` but no side flag, so the side is read
    off the event_id, counted from the END (S122: a dashed tourney_id shifts the head)."""
    frame = _load_glob(path).copy()
    frame["_is_p1"] = (frame["player_id"].astype(str)
                       == frame["event_id"].astype(str).str.split("-").str[-3])
    return frame


_LOADERS = {"glob": _load_glob, "referee": _load_referee, "player_adv": _load_player_adv,
            "tennis_sides": _load_tennis_sides}
```

```python
    # S136: the ROUND-GRAIN rebuild of the two tables S122 withheld. The frozen parquets keyed
    # every match of a tourney on the START date, so a trailing count spanned rounds played
    # AFTER the match and the rolling result landed on a duplicated index (the 2025 Wimbledon
    # champion served 0,3,4,5,1,6,2 and the served value correlated +0.2616 with the outcome).
    # domains/tennis/schedule_density_roundgrain.py orders each player's history by
    # (tourney start date, Sackmann round) and counts only rows strictly before at that grain:
    # the champion now serves 0,1,2,3,4,5,6, the correlation is +0.0481 inside a +/-0.0693
    # two-sigma band, and the local re-screen is NULL (0 of 32 screens improve on the close).
    # `rest_days` is DELIBERATELY ABSENT: real rest days inside a tourney are unrecoverable at
    # this date grain, so the member is CLOSED AT LIMIT rather than served as a round-depth
    # proxy. See docs/evidence/harness/S136_tennis_roundgrain_builders_2026-09-03.md.
    "tennis_schedule_density": Supply(
        "data/domains/tennis/schedule_density_rg.parquet,"
        "data/domains/tennis/schedule_density_rg_wta.parquet",
        "side", ("matches_last_7d", "matches_last_14d"),
        side="_is_p1", entity_from="player", loader="tennis_sides",
        pregame="schedule_density_roundgrain: a match at (D, r) counts only rows with date < D, "
                "or date == D and round < r -- strictly before at (tourney start date, Sackmann "
                "round) grain, so the row can never see itself, a sibling of equal round, or a "
                "later round of its own event"),
    "tennis_travel_scouting": Supply(
        "data/domains/tennis/travel_scouting_rg.parquet,"
        "data/domains/tennis/travel_scouting_rg_wta.parquet",
        "side", ("miles_flown_in", "venue_altitude_m"),
        side="is_p1", entity_from="player", loader="glob",
        overrides=(("venue_altitude_m", "a"),),
        pregame="schedule_density_roundgrain: prior_city_travel reads the player's PREVIOUS "
                "resolved host city under that same (date, round) order -- a first appearance "
                "is NaN, never 0; venue_altitude_m is a property of the venue, published with "
                "the draw"),
```

Land the catalogue names in the SAME commit so the count moves once:
`scripts/platformkit/foundry/catalogue.py` `NAMED` gains
`data/domains/tennis/schedule_density_rg.parquet`,
`data/domains/tennis/schedule_density_rg_wta.parquet`,
`data/domains/tennis/travel_scouting_rg.parquet`,
`data/domains/tennis/travel_scouting_rg_wta.parquet`
(33 -> 37), and `tests/platformkit/foundry/test_catalogue.py:20` `== 33` becomes `== 37`.
These four files were left UNNAMED here because both files sit outside this lane's safe areas
and `len(NAMED) == 33` would have broken for whoever committed next.

`domains/tennis/test_wta_schedule_travel.py`'s leak test is already source-aware and **PASSES
with both entries declared** -- verified in-process. It now refuses a declaration whose source
is not the `_rg` pair, and refuses `rest_days` in either member list, so re-registering the
leaky tables still fails a test first. It was renamed
`test_neither_family_is_declared_because_the_date_is_the_tourney_date` ->
`test_neither_family_is_declared_on_the_leaky_tourney_date_source`; the S122 memo's section 4
prose names the old title.

---

## 6. Self-check against `docs/evidence/tracking/VERIFIER_CONTRACT.md` (B + Q)

- **B1** no metric is computed after excluding rows that would fail it. Coverage is measured
  over the whole frozen 800-row window; the UNCOVERED family and its count are named (593/800).
- **B2** additive schema. Four NEW parquets; no existing table gains or loses a column and no
  frozen source is rewritten. The one edit to an existing file is the S122 leak test's body,
  which is loosened from "never declared" to "never declared on the leaky source" -- strictly
  more specific, and it still fails on the frozen parquets (demonstrated in-process).
- **B3** no gate quarantines on absent evidence: an unresolved tourney city stays NaN and drops
  out of the alignment, and a player's debut stays NaN, exactly as before.
- **B5** nothing was copied to the pod. No pod contact of any kind.
- **B6** no orphans: the new module is imported by its own test and by `s136_screen`; nothing
  was moved or retired. `_load_tennis_sides` lives in `s136_screen` with its only caller.
- **B7** no head slices. Every one of the 800 served rows is scored; the champion probe prints
  the full R128..F sequence; the strictly-before test recomputes 300 RANDOMLY SAMPLED players
  (seed 20260903) row by row, not the first N.
- **B9** no degenerate denominator: 61,232 + 22,540 appearance rows over 1,273 + 968 distinct
  players, and the CI clusters at 233 -- the same cluster count S122 reported.
- **B10 / Q3** no bar moved. `_COVERAGE_FLOOR = 0.8`, seed 20260903, 800 rows, purge 48 h,
  embargo 3 d, `IMPROVEMENT_BAR` all byte-identical to master. `rest_days` is reported CLOSED AT
  LIMIT, never served on a lowered bar.
- **Q1** no scored comparison is claimed -- the screen is NULL -- so no seal is required and
  none is asserted. No prereg drafted.
- **Q2** no charge. `allow_charge=False`, `tiers.charge_tier` never reached, `_charge_ledger`
  never called, the scratch ledger path never created (`charged_ledger_created=False`), and
  `data/cache/eval_gate/backtest_fwer.jsonl` is **18 rows** before and after and was never opened.
- **Q4** every screen runs inside `eval_gate.walk_forward` with purging and the symmetric
  embargo; no meta-learner is involved. The defect this row repairs was upstream of the walk --
  in the SOURCE's ordering -- which is why the walk could not catch it and a builder had to.
- **Q5** no AHEAD is claimed (the result is BEHIND on both families), so the two-corpora rule is
  not engaged. Both spines, ATP and WTA, were nonetheless rebuilt and screened together.
- **Q6** calibration language only; no dollar / ROI / profit / edge word, and none of the
  retracted figures appears. S122's `+0.020155` is named only as the LEAK ARTIFACT it is. An
  honest NULL is a success.
- **Q7** coverage is a SAMPLED metric at n = 800 and the screen table is n = 32 screens, both
  above the rail. The round distributions, the tie counts and the one-date-per-tourney counts
  are CONSTRUCT -- every row of both spines is enumerated.
- **Q8** the premise was re-measured first (section 0) and every part of it HOLDS, including the
  fix's own premise: both spines carry a zero-null Sackmann `round` column and no builder
  already orders by it. NOT falsified.
- **Q9** each T1 trial's JSON carries its full per-event differential and every CI in section 4
  was recomputed from those rows alone by `s111_screen.dm_ci` in the documented direction
  (d = loss_incumbent - loss_model), never taken from the stored `dm_stat` (S79's unrepaired
  sign mirror). The whole of section 4 re-runs from the landed tree with one command.

**Human-gated trees untouched:** nothing under `src/`, `kernel/`, `api/`, `intel/`,
`scripts/team_system/` was read for writing or edited. `data/registry/` untouched. No feature
flag flipped. No `--force`. No push. **No file owned by another live lane was edited** --
`foundry/asof_supply.py` (asof_supply lane), `eval_gate/close_join_nba_mlb.py` (close lane) and
`foundry/ingame_screen.py` / `foundry/ingame_guards.py` (in-game guards lane) were read only.

---

## 7. Tests

Per-file only:

```
python -m pytest domains/tennis/test_schedule_density_roundgrain.py -q   8 passed in 1.22s
python -m pytest domains/tennis/test_wta_schedule_travel.py -q           5 passed in 0.40s
```

The eight cover: the seven rounds of one tourney serving `1..7` on a synthetic same-date spine;
`rest_days` absent and `round` present; an unknown round code raising instead of sorting to one
end; the landed ATP table recomputed ROW BY ROW against the rule as prose on 300 sampled players
(both windows); the 2025 Wimbledon champion serving `0..6` on the real corpus; travel reading the
previous city under the round order with an honest NaN debut; the landed travel table's 55,446
rows all carrying a round and every player's first appearance NaN; and every within-tourney
later round reporting a 0-mile hop.

Readers of the touched modules and artifacts, re-run unchanged (A5):
`domains/tennis/test_ingest_schedule_density.py` 5 passed -
`scripts/platformkit/geo/test_travel_scouting.py` 12 passed -
`scripts/platformkit/ops/test_safe_parquet_write.py` 6 passed -
`tests/platformkit/foundry/test_asof_supply.py` 5 passed -
`tests/platformkit/foundry/test_catalogue.py` 13 passed -
`scripts/platformkit/eval_gate/test_catalog_rescreen.py` 8 passed -
`scripts/platformkit/data_frontier/test_utilization_audit.py` 4 passed.

## 8. Files

| file | LOC | what |
|---|---|---|
| `domains/tennis/schedule_density_roundgrain.py` | 169 | new -- the (date, round)-grain rebuild of both tables, both spines |
| `domains/tennis/test_schedule_density_roundgrain.py` | 116 | new -- strictly-before recomputed row by row, the champion sequence, the travel order |
| `scripts/platformkit/eval_gate/s136_screen.py` | 161 | new -- the in-process declaration, the leak probe and the re-screen, both re-runnable |
| `domains/tennis/test_wta_schedule_travel.py` | 87 | the S122 leak test made source-aware: a declaration is legal only off the `_rg` pair and never carries `rest_days` |

Artifacts written under `data/` (gitignored, never staged): `schedule_density_rg.parquet`,
`schedule_density_rg_wta.parquet`, `travel_scouting_rg.parquet`, `travel_scouting_rg_wta.parquet`.
