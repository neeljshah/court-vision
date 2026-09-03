# S128 + S129 -- the as-of supply registry's two round-2 leaks, reproduced and closed

**Rows:** S128 (the `prior` rule leaks the event's own season on soccer) and S129 (the `side`
rule has no as-of guard), both filed by `docs/evidence/harness/REDTEAM_ROUND2_2026-09-03.md`
as F7 and F17 (numbered S135 / S136 there; the register assigned S128 / S129).

**Owned files:** `scripts/platformkit/foundry/asof_supply.py`,
`scripts/platformkit/foundry/asof_supply_columns.py`,
`tests/platformkit/foundry/test_asof_supply.py`. One further file was edited because it is a
READER of the field the diff adds (section 6).

**Contract self-check:** VERIFIER_CONTRACT sections B and Q applied below (section 7).
A SCREEN IS A NON-FINDING. Calibration language only -- no dollar, ROI or edge claim.

---

## 0. PREMISE (Q8) -- both rows reproduced from disk BEFORE any edit

Both probes ran against the committed tree through `asof_supply.supply` itself, not a
re-implementation.

### S128 -- the own-season leak

```
seasons spanning TWO calendar years: 11 of 11
share of matches whose calendar year != its season label: 0.5178

event_id                          date        season  home       away
20260101-E0-brentford-tottenham   2026-01-01  2025    Brentford  Tottenham

SERVED ppg (home-away): -0.221968
  Brentford  2024 ppg 1.473684 | 2025 ppg 1.394737   (its OWN season)
  Tottenham  2024 ppg 1.000000 | 2025 ppg 1.078947   (its OWN season)
  honest (seasons <= 2024)      -0.275744
  own-season included (<= 2025) -0.221968   <-- the served value
```

**NOT FALSIFIED.** `_prior_rule` mapped the event to `pd.to_datetime(date).dt.year` = 2026 and
`merge_asof(allow_exact_matches=False)` then admitted season 2025 -- the match's own season.

### S129 -- the side rule serves the event's own row

A synthetic family whose column IS the event outcome, registered in-process and served:

```
side rule served: [9.0, 9.0, -9.0]   -- straight off the event's own row
```

**NOT FALSIFIED.**

---

## 1. The change

`Supply` gains three declared fields; the two rules consult them and nothing else moves.

**(a) S128 -- the event's season comes from the SOURCE's own convention, never `dt.year`.**
`_season_of` resolves a `grain="season"` entry one of two declared ways and refuses when
neither is declared:

- `season_table` -- a repo-relative table mapping the entry's `key` to the source's own
  `season` column. `soccer_style_fingerprints` declares
  `data/domains/soccer/matches.parquet`, which carries `event_id` + `season` and covers
  **16,322 of 16,322** corpus events and **800 of 800** of the screen window.
- `season_start_month` -- the month a season starts, for a source whose season IS a calendar
  span. `tennis_serve_return_profiles` declares `1`, which is `dt.year` exactly, so that
  family is byte-identical (section 3).

A month rule was measured for soccer and REJECTED as the soccer mechanism: no month is both
exact and leak-free. `season_start_month=8` misassigns 10 matches FORWARD (a leak) and 11
backward; `=9` is leak-free but costs 1,970 matches a season of history. The table lookup is
exact, so it is what soccer declares.

The tennis declaration is measured, not assumed: across the 41,886 ATP+WTA `event_id`s the
calendar year of the id's date prefix is **never ahead** of the season the id itself carries
(41,719 equal, 167 behind -- Dec-31 matches belonging to the next season, which read one
season LESS history, never more).

**(b) S129 -- the side rule fails closed.** `_side_rule` serves the event's own row, so an
entry must now DECLARE its pregame as-of basis (`pregame`: the table plus the date rule) or
every column of it is refused by name:

```
no declared pregame as-of basis for unit_family/leak_outcome
```

`nba_player_value_features` -- the registry's only side family, S122 having removed the two
tennis ones -- declares `"player_boxscores.parquet, state BEFORE game_id"`. That declaration
is MEASURED, not taken on the producer's word (section 2).

**Named limit.** `pregame` is a declaration, so a column planted INSIDE an entry that already
declares one is still served. The guard closes the default (an undeclared side entry supplies
nothing); the audit in section 2 is what backs the one declaration that exists. The same
ceiling is written at the call site in `s122_screen.register_leaky`, which deliberately
declares a basis it does not have in order to keep reproducing the S122 leak.

---

## 2. S129's bar -- the per-column self-inclusion audit

The register row asks for a per-column audit of every side-served column. The registry
declares **4** (`roster_value_asof`, `star_absence_delta`, `continuity`, `top_heavy`); the
row's "9" counted the two tennis families S122 removed, which are no longer declared.

**Recompute against the producer's own walk-forward pass** (`player_value_asof.py`,
7,222 team-game rows):

```
roster_value_asof   share of rows differing from the strictly-prior recompute: 0.0000 (0 of 7222)
star_absence_delta  0.0000 (0 of 7222)
continuity          0.0000 (0 of 7222)
top_heavy           0.0000 (0 of 7222)
first-game star_absence_delta all zero: True | first-game continuity all zero: True
```

That check alone is partly self-confirming (it proves the parquet IS the producer's output).
The INDEPENDENT check is a perturbation, because truncation cannot see a same-row leak (that
is round 2's own F2 finding): the target game's OWN boxscore rows are rewritten
(`min * 3 + 7`, `plus_minus * -5 - 11`) and the table rebuilt. 5 games sampled EVENLY over the
3,611 ordered games (A3, not a head slice):

```
game 0022300332  own-row values unchanged: True   perturbation visible in the next game: True
game 0022301055  own-row values unchanged: True   perturbation visible in the next game: True
game 0022400553  own-row values unchanged: True   perturbation visible in the next game: True
game 0022500020  own-row values unchanged: True   perturbation visible in the next game: True
game 0022500767  own-row values unchanged: True   perturbation visible in the next game: True
columns whose own-row value moved: 0 of 4 x 5 samples
```

The "visible in the next game" column is the probe's own liveness check: the perturbation DOES
reach later games, so the unchanged own-row value is an as-of property, not a dead probe. No
column is demoted or dropped.

---

## 3. S128's bar -- every other family byte-identical

Every declared (family, column) pair was served over its own gate corpus by the PRE-FIX module
(`git show HEAD:...asof_supply.py`, loaded side by side) and by the fixed one, and compared
element-wise with NaN treated as equal:

| family | pairs | rows differing |
|---|---|---|
| `soccer_style_fingerprints` | 14 / 14 | 8,560-8,567 of 16,322 (0.5244-0.5249); `n_matches` 3,692 (0.2262) |
| every other declared family | 51 | **0** |

The moved share matches the 0.5178 of matches whose calendar year differs from their season
label, plus the rows whose served value changes between a number and NaN. The three families
the fix could plausibly have disturbed are all unmoved: `nba_player_value_features` (the side
rule), `tennis_serve_return_profiles` (the other season-grain family) and
`soccer_referee_card_foul_profiles` (the other soccer entry).

**Coverage moves, honestly and downward:** `soccer_style_fingerprints` serves 15,646 -> 14,878
non-null of 16,322. The 768 lost rows are matches that used to be served their own season and
now have no strictly-prior season at all. Coverage on the 800-row screen window is 800/800
before and after, so nothing is refused and no T0 verdict changes.

---

## 4. The re-run screens (before / after)

`s111_screen.run` machinery with `TARGETS` narrowed to the two affected families: scratch
sqlite in the session scratchpad, `allow_charge=False`, a ledger path that was never created,
the real predictor, 800 screen rows. Screen-partition sha256 recomputed here and **byte-equal**
to S58c / S79 / S85 / S108 / S111: soccer `5c8d63970b08ce97`, nba `1a32541d44aa7fcb`.
288 result rows = 144 T0 (144 COVERED, 0 UNCOVERED) + 144 T1 SCREEN, both sides.

| family | T1 rows | best member / transform | incumbent | Brier incumb | Brier model | improvement | DM CI 95 (recomputed) | DM p |
|---|---|---|---|---|---|---|---|---|
| `soccer_style_fingerprints` BEFORE | 112 | `z_corners_pm` / `ew` h=20 | devigged close | 0.241896 | 0.243054 | -0.001158 | [-0.004504, +0.002188] g=3 | 0.5674 |
| `soccer_style_fingerprints` AFTER | 112 | `cards_pm` / `rank_in_league` | devigged close | 0.241896 | 0.242901 | **-0.001006** | [-0.005228, +0.003216] g=3 | 0.6865 |
| `nba_player_value_features` BEFORE | 32 | `continuity` / `z_vs_league` | p_base (Elo) | 0.205118 | 0.199897 | +0.005221 | [+0.000451, +0.009992] g=30 | 0.0404 |
| `nba_player_value_features` AFTER | 32 | `continuity` / `z_vs_league` | p_base (Elo) | 0.205118 | 0.199897 | +0.005221 | [+0.000451, +0.009992] g=30 | 0.0404 |

Per-row, keyed on the trial hash (the same 144 keys both sides):

- `soccer_style_fingerprints`: **112 of 112 T1 rows moved**, improvement shifting between
  -0.000482 and +0.000452. The S85 row's own member/transform goes -0.001158 -> -0.001128.
  Screens with improvement > 0: **0 of 112 before, 0 of 112 after**.
- `nba_player_value_features`: **0 of 32 moved**; 29 of 32 positive before and after.
- Across all 144: 29 improved (20.1 pct) before and after; 2 recomputed CI lower bounds above
  0 before and after, both `nba_player_value_features.continuity`, both unmoved.

**NOTHING CLEARS.** The S85 negative moves and stays negative: the family is still BEHIND the
devigged close, and it is now behind it honestly. The one family with a positive screen is
NBA, is scored against Elo rather than a close, and did not move at all.

### Landed numbers that change

- **S85 section 2.1**, the `soccer_style_fingerprints` row: best member/transform
  `z_corners_pm`/`ew` -> `cards_pm`/`rank_in_league`, Brier model 0.243054 -> 0.242901,
  improvement -0.001158 -> -0.001006, DM p 0.5674 -> 0.6865, CI [-0.008504, +0.006187] ->
  [-0.005228, +0.003216]. (S85's stored CI for that row differs from the recomputation on both
  sides; the recomputed pair is the comparable one.)
- **S85 section 3**, the cross-family list: `soccer_style_fingerprints` -0.001158377 ->
  -0.001006.
- **S85 section 1**, the coverage table: `soccer_style_fingerprints` 15,646 -> 14,878 of
  16,322.
- **S111**: unchanged. Its TARGETS are tennis + NBA and none of those families moved.
- **S113**: unchanged. It re-prices the NBA/MLB incumbent; no soccer family and no moved
  family is involved.
- No promotion, no charge and no FWER row is affected: nothing was promoted on either side and
  the ledger was never opened.

---

## 5. Tests (per-file only)

- `tests/platformkit/foundry/test_asof_supply.py` -- **8 passed**. Three new:
  `test_prior_rule_uses_the_source_season_not_the_calendar_year` (synthetic season spanning
  into the next calendar year, plus the refusal when neither season field is declared),
  `test_soccer_prior_serves_the_honest_pre_season_value_on_the_real_corpus` (the
  Brentford-Tottenham case serves **-0.275744**), and
  `test_side_rule_refuses_a_column_with_no_declared_pregame_basis` (the planted
  outcome-equal column, refused by name). The registry construct test now also asserts that
  every side entry declares a `pregame` basis and every season-grain entry declares exactly
  one of the two season fields. S122's `_sides` leak test is untouched and green.
- Readers re-run unchanged: `test_screen_predictor.py` **5 passed**, `test_catalogue.py`
  **13 passed**.

---

## 6. A5 -- every reader of the touched fields

`Supply` is constructed outside `asof_supply.py` in exactly two places, both in-process
registrations for evidence scripts:

- `scripts/platformkit/eval_gate/s136_screen.py` already feature-detects the field
  (`has_pregame = "pregame" in Supply.__dataclass_fields__`) and declares a basis for both
  entries -- no change needed.
- `scripts/platformkit/eval_gate/s122_screen.py` (`register_leaky`) declared no basis and its
  reproduction would have refused instead of reproducing. It now passes a `pregame` string
  that says in words that the basis is NOT as-of, which is the point of that script: the flag
  is a promise, and S122 exists to show the leak such a promise would have covered. Both
  modules were imported and their registrations run after the change.

`MLB_ALIAS` and `IDENTIFIERS` moved to `asof_supply_columns.py` (pure data, to stay inside the
300-line cap) and are re-exported by name into `asof_supply`; no other module reads either.
`asof_supply.py` is **300 lines**.

---

## 7. Contract self-check

**B1** the moved-row count is over the whole corpus with nothing excluded. **B2** additive:
three new dataclass fields with defaults that reproduce the old behaviour where declared, and
the one external constructor that needed a value got one. **B3** a season-grain entry with no
declaration is REFUSED, not silently served -- absent evidence stops the supply rather than
faking it. **B6** no module moved or retired; the two constants moved inside the same package
and are imported by name. **B7** the perturbation games are sampled evenly over the ordered
set, not from the head. **B8** the producer recompute is acknowledged as partly
self-confirming and the independent perturbation probe carries its own liveness check.
**B9** 800 states, 800 unique event_ids, both sides. **B10** no bar moved: coverage floor 0.8,
seed 20260903, 800 rows, purge/embargo, IMPROVEMENT_BAR and both partition shas
byte-identical to master.

**Q1** nothing scored here is a prereg'd claim; these are screens. **Q2/Q6** no ledger row was
charged: `allow_charge=False`, `tiers.charge_tier` never reached, `_charge_ledger` never
called, `data/cache/eval_gate/backtest_fwer.jsonl` **18 rows before and after** and never
opened; `charged_ledger_created=False` on both runs. **Q3** no threshold moved. **Q5** no
AHEAD is claimed anywhere -- the only screen that moved is negative before and after.
**Q6** calibration language only; none of the retracted figures appears. **Q7** the audits are
CONSTRUCT enumerations (4 of 4 side columns, 65 of 65 declared pairs, 11 of 11 soccer
seasons), not samples, except the 5 perturbation games which are a liveness probe on top of an
exhaustive recompute. **Q8** both premises were reproduced before any edit (section 0).
**Q9** the before and after trial archives (per-event differential, cluster, timestamps) are
written under the session scratchpad `before/trials` and `after/trials` and every CI in
section 4 is recomputed from them, never quoted from `dm_stat`.

`data/registry` untouched, no flag flipped ON, no forced-overwrite flag used anywhere, no pod
contact, no push, nothing written under `src/`, `kernel/`, `api/`, `intel/`,
`scripts/team_system/`, and no file owned by the close-fix, in-game guards or tennis builders
lanes edited.
