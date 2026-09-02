# S65 -- soccer event-grain as-of ingredients (CLOSED AT LIMIT)

Gap (register, reserved by this lane): the eleven soccer mechanisms S53 left
NOT_TESTABLE need an event/shot/possession grain (score state, shot type, PPDA,
goal-kick height, tactical shift, substitution minute, possession id,
play_pattern). Build per-team AS-OF aggregates from the StatsBomb event grain,
join them into the gate spine by the S53 pattern, re-run S22's soccer engine.

**Verdict: CLOSED AT LIMIT. The ingredients exist on disk; the OVERLAP does not.
StatsBomb open data covers 160 of the 16,322 SCORED soccer rows = 0.009803,
against `mechanism_close_effect.MIN_COVERAGE = 0.25` -- short by a factor of
25.5. The bar was not moved and no feature column was built or joined.**

Calibration language only. DESCRIPTIVE_ONLY. Nothing scored, promoted or
charged: `data/cache/eval_gate/backtest_fwer.jsonl` was never opened, K is
unchanged, and no `_charge_ledger` path exists in anything this lane touched.
`data/registry/` untouched. No flag flipped. Nothing copied to the pod.

## LICENCE FIRST -- OPEN for research, CLOSED for commercial use

Full record: `docs/evidence/harness/LICENCE_statsbomb_open_data.md` (S62 format,
source + URL + clause quoted + date + permitted use). Read from the licensor's
own document, `LICENSE.pdf` at the root of github.com/statsbomb/open-data,
"StatsBomb Data: User Agreement Standard Terms - last updated 8 September 2023",
retrieved and read 2026-09-03. Summary of the two clauses that decide this lane:

- **1.1 permits it.** "access to the Service to be used for analysis, research
  and to facilitate the shared ideas & understanding of the data". A calibration
  census is analysis and research, so this lane's measurement is inside the
  grant.
- **1.2.2 forbids the product.** "commercially exploit the data or any analysis
  derived from the use of the Service". The clause reaches the *analysis*, not
  only the data, so a StatsBomb-derived spine column would be a licence liability
  the moment the platform is sold. **1.2.1 / 7** additionally forbid
  redistribution, so `data/cache/statsbomb/` stays gitignored and no derived
  parquet is committed. **1.4** requires StatsBomb attribution on publication.
  **2.2** requests registration at statsbomb.com/resource-centre -- OUTSTANDING,
  one form, flagged for Neel.

The licence is therefore not what closes this row -- the overlap is. But it is
the reason a StatsBomb-derived column would have been the wrong thing to ship
even if the overlap had been sufficient.

## STEP 0 -- the inventory and the overlap

### What event-grain soccer data exists locally

| store | what | rows / files |
|---|---|---|
| `data/cache/statsbomb/events/*.json` | full StatsBomb event grain | **4,235 files, 13 GB** |
| `data/cache/statsbomb/match_meta_full.parquet` | match_id, date, teams, score, competition | 3,961 |
| `data/cache/statsbomb/matches/` | per-competition match lists | 7.5 MB |
| `data/cache/statsbomb/possession_chains_full.parquet` | possession chains | 3.1 MB |
| `data/cache/statsbomb/formation_lineups_full.parquet` | formations / lineups | 636 KB |
| `data/domains/soccer/*.parquet` | ESPN + football-data match-grain backfills | match grain only |
| `data/domains/soccer/_raw/footballdata` | football-data.co.uk raw | match grain only |

**No ESPN or FotMob event-grain store exists** under `data/domains/soccer/`; every
parquet there is match grain (S53 enumerated them). StatsBomb is the only
event-grain soccer source on this box.

All eleven ingredients ARE present in the event files -- verified by reading one
Premier League 2015/16 file (match 3754217, 3,732 events): `shot.type.name`,
`shot.statsbomb_xg`, `possession`, `play_pattern`, `pass.height.name` on
`pass.type.name == "Goal Kick"`, `Substitution.minute`, `Tactical Shift`,
`Pressure` / `Duel` / `Interception` for PPDA, `location` for block depth. The
enumeration of all eleven and the field each needs is frozen in
`soccer_event_asof.EVENT_GRAIN_INGREDIENTS` -- n = 11 (CONSTRUCT), exhaustive
against the S53 list.

### The overlap, measured

Instrument: `scripts/platformkit/soccer_event_asof.py`
(`python -m scripts.platformkit.soccer_event_asof`). Artifact:
`docs/evidence/harness/S65_soccer_event_asof_census.json`.

Join key: **(match date, corpus_unit, home slug, away slug)** -- date-EXACT and
orientation-preserving. A +/- 2-day tolerance was probed and recovers **0**
additional matches, so no tolerance is used.

| step | count | denominator |
|---|---|---|
| StatsBomb matches in the six corpus leagues (D1 E0 E1 F1 I1 SP1) | 2,169 | 3,961 SB matches |
| ... inside the spine's date range (>= 2015-08-07) | **1,815** | |
| ... joining the gate spine on (date, unit, home, away) | **1,740** | / 25,834 = **0.067353** |
| ... inside the SCORED frame (close-joined states) | **160** | / 16,322 = **0.009803** |

Unmapped club names after the crosswalk: **0** (the crosswalk is fuzzy with an
8-entry manual table for the names fuzzy matching gets wrong or reverses --
`Hertha Berlin` scores higher against `union_berlin` than against `hertha`, so
that one is manual by necessity, not convenience).

**Join correctness, independent of the name crosswalk:** StatsBomb's own
scoreline reproduces the spine's over-2.5 label on **1,740 / 1,740 = 1.000000**.
A mispaired club would break this. Uniqueness (A4): the 1,740 rows are 1,740
distinct `event_id`s and 1,740 distinct StatsBomb `match_id`s.

### Why the scored overlap collapses from 1,740 to 160

It is a calendar fact, not a matching artifact. StatsBomb's four FULL league
seasons are all **2015/16** (Premier League 380, La Liga 380, Serie A 342,
Ligue 1 305 joined), while the soccer close only begins **2019-08-02** (S02).
Those four seasons therefore contribute **0** scored rows. What survives is five
partial single-team seasons:

| competition | scored rows | corpus_unit |
|---|---|---|
| La Liga 2019/20 + 2020/21 (Barcelona's matches) | 68 | SP1 |
| Ligue 1 2021/22 + 2022/23 (Paris Saint-Germain's matches) | 58 | F1 |
| 1. Bundesliga 2023/24 (Bayer Leverkusen's matches) | 34 | D1 |
| **total** | **160** | |

## Why nothing was built

`mechanism_close_effect.MIN_COVERAGE = 0.25`, measured as
`values.notna().sum() / len(frame)` against the scored frame. The ceiling for ANY
event-grain as-of column is 160 / 16,322 = 0.009803 -- **25.5x short**. Even on
the most generous framing (the full 25,834-row spine rather than the scored
frame) the ceiling is 0.067353, still 3.7x short.

There are exactly three ways past that, and all three are forbidden:

1. **Lower MIN_COVERAGE.** Refused -- B10 / Q3. A bar found unmeetable is
   reported CLOSED AT LIMIT, never lowered.
2. **Restrict the scored frame to the covered rows.** Refused -- that is B1
   verbatim: a metric computed after excluding the rows that would fail it.
3. **Score per corpus_unit only.** Refused -- coverage is a corpus-wide gate in
   the module, and the per-unit counts would not survive it either: SP1 68,
   F1 58, D1 34 against `MIN_UNIT_ROWS = 30` a side (60 scored rows minimum), so
   D1 fails outright and the other two clear by 8 and would be a
   `single_corpus_unit` result on 2 units at 0.4 pct and 0.36 pct of their own
   units.

So the honest deliverable is the LIMIT, not a feature parquet: parsing 13 GB of
event JSON to produce columns that provably cannot clear the gate would add ~30
dead columns to the corpus, move the corpus sha (and every downstream watermark)
for nothing, and change no verdict. **`data/domains/soccer/asof_event_features.parquet`
was NOT written. `corpus_cache._build_soccer` was NOT touched. The spine is
byte-identical: 25,834 rows, 33 columns, unchanged.**

The two DERIVABLE-but-not-derived ingredients from S53's NEW GAP (a date-lagged
referee card/foul profile; a prior-season style fingerprint) were also not built:
they need no StatsBomb data and would reach high coverage, but S53 already
established that **no mechanism in the soccer ledger names either one**, so
neither can move S22's tally either. They belong to the foundry's candidate
surface, not to this row -- re-filed as a NEW GAP below rather than smuggled in.

## S22 soccer re-run -- tally UNCHANGED, 14 NOT_TESTABLE + 1 NULL_LOCAL

`python -m scripts.platformkit.analytics_showcase.mechanism_close_effect --sport soccer`

| sport | wired/defined | with trigger | CONFIRMED_LOCAL | NULL_LOCAL | NOT_TESTABLE |
|---|---|---|---|---|---|
| soccer BEFORE (S53) | 15/15 | 1 | 0 | 1 | 14 |
| soccer AFTER (S65) | 15/15 | 1 | 0 | 1 | **14** |

The re-run reproduced `out/mechanism_wiring_soccer.json` **byte-identically apart
from `generated_at`** (the only line in the git diff), so the artifact was
restored rather than committed. The one NULL_LOCAL row
(`trailing_xg_supremacy_is_a_stable_team_trait`, n = 16,284, six units, mixed
signs) is S53's, unchanged. Bars byte-identical to S22: `|effect| >= 0.02 AND
p < 0.01`, coverage >= 0.25, >= 30 rows a side.

The eleven rows keep their declared absence. What changes is only what the
evidence now says about it: the reason "the ingredient is StatsBomb event grain,
not a corpus column" is now backed by a measured ceiling on how much of the
scored corpus that grain could ever reach.

## Test

`scripts/platformkit/test_soccer_event_asof.py` -- **5 passed in 2.10 s**
(`python -m pytest scripts/platformkit/test_soccer_event_asof.py -q`, per-file):

1. crosswalk: the manual entry beats the fuzzy near-collision
   (`Hertha Berlin` -> `hertha`, not `union_berlin`), the fuzzy path still works,
   and an unmappable club is RETURNED in `unmapped`, never silently dropped;
2. the overlap join is date-EXACT and orientation-preserving -- a one-day slip
   and a swapped home/away pair each yield 0 rows, only the exact match yields 1;
3. `MIN_COVERAGE == 0.25` -- the verdict is only honest while the bar it misses
   is the declared one (B10 / Q3 guard: lowering the bar fails this test);
4. the census reproduces all six real-data denominators (25,834 / 16,322 / 1,815
   / 0 unmapped / 1,740 / 160), the 1.000000 label agreement, both uniqueness
   counts, and `bar_moved is False`;
5. the eleven-mechanism enumeration is n = 11 with a named ingredient each.

## ACCEPTANCE

metric = soccer mechanisms whose declared event-grain ingredient can reach the
declared `MIN_COVERAGE = 0.25` bar on the scored corpus; denominator = 11.
before = **0/11**. after = **0/11**, at a measured ceiling of 0.009803 (25.5x
short) rather than at an unmeasured absence.
n = 16,322 scored rows; 25,834 spine rows; 1,740 joined matches; 11 (CONSTRUCT)
mechanisms enumerated exhaustively.
must not move: `MIN_COVERAGE` 0.25, `MIN_UNIT_ROWS` 30, `ALPHA` 0.01,
`MIN_EFFECT` 0.02 (all byte-identical), the gate spine (25,834 rows x 33
columns, untouched), `out/mechanism_wiring_soccer.json` (restored),
`data/registry/**` (untouched), `backtest_fwer.jsonl` (never opened, K unchanged).
No bar lowered, no rows excluded, no column added, no flag flipped.

## NEW GAP

`NEW GAP: the soccer event-grain lane is corpus-limited, not code-limited -- the
only event-grain soccer source on disk (StatsBomb open data, 4,235 files) covers
160 of 16,322 scored rows because its four full league seasons are all 2015/16
while the close starts 2019-08-02. Making the eleven mechanisms testable needs an
event-grain feed with 2019-2026 coverage of D1/E0/E1/F1/I1/SP1 under permitted
terms; StatsBomb's own commercial feed would clear the coverage but its open-data
agreement clause 1.2.2 (no commercial exploitation of the data OR of any analysis
derived from it) means the open tier can never serve a sold product regardless of
coverage. Same shape as S52: a licensed-feed purchase decision for Neel, not a
join. Until then the eleven rows are CLOSED AT LIMIT, not merely NOT_TESTABLE.`

`NEW GAP: S53's two derivable soccer as-of ingredients are still underived and
are now the only remaining high-coverage candidates -- a DATE-LAGGED referee
card/foul profile (prior-matches-only expanding mean per referee over
referee_card_foul_profiles.parquet, 10,251/25,834 = 0.3968 coverage, blank-referee
placeholder on 15,583 rows) and a PRIOR-SEASON style fingerprint (the team's
previous season only, from style_fingerprints.parquet, 1,336 team-seasons). Both
would clear MIN_COVERAGE where StatsBomb cannot, but NO mechanism in the soccer
ledger names either, so they widen the foundry's candidate surface (S11/S16)
rather than moving S22's tally. Needs its own row with a foundry consumer named,
or it stays permanently unbuilt.`

## NOT VERIFIED

- **The event grain itself was never parsed.** One event file (match 3754217) was
  read to confirm the eleven fields exist; the other 4,234 were not opened. The
  claim "every ingredient is present" rests on that single file plus the
  StatsBomb schema, not on a census of all 4,235.
- The 1,740-row overlap is validated by label agreement and uniqueness, not by a
  fixture-by-fixture eyeball. A club pair that is consistently wrong in BOTH
  corpora would survive both checks (no such pair is known).
- The 75 in-window StatsBomb matches that did NOT join (1,815 - 1,740) were not
  individually diagnosed. All eight previously unmapped club names are now
  mapped and a +/- 2-day probe recovers 0 of them, so the residue is not a name
  or a small-slip problem. It is entirely Serie A 2015/16 (38) and Ligue 1
  2015/16 (37) -- both outside the close window, so it could not enter the
  scored frame regardless of the cause.
- `MIN_COVERAGE` is read from the module at census time. The test pins it at
  0.25, but the census result is only meaningful against the bar as of this run.
- The scored frame is the close-joined states, whose close carries a **SYNTHETIC
  vintage (S34)**. Nothing here is scored against it, so that does not affect
  this verdict -- but it does mean the 16,322 denominator is a
  synthetic-vintage frame, same caveat S53 carries.
- The licence reading is this lane's reading of the licensor's own document, not
  legal advice. Clause 1.2.2's reach over "any analysis derived from the use of
  the Service" is the operative restriction and is quoted verbatim in the licence
  record; the commercial-use call is Neel's (S62).
- Registration under clause 2.2 has NOT been completed.
- No edits to `src/`, `kernel/`, `api/`, `intel/`, `data/registry/`,
  `corpus_cache.py`, the S22 wiring modules, or the register.
