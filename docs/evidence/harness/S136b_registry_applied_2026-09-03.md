# S136b -- the S136 registry entries APPLIED, and the screen re-run from the landed tree

**Row:** S136 (data) in `docs/evidence/HARNESS_GAPS_2026-09-03.md`, follow-up landing.
**Parent memo:** `docs/evidence/harness/S136_tennis_roundgrain_builders_2026-09-03.md`, section 5.
**Verdict:** **ACCEPT -- the entries are on disk, the leak test passes with them declared, and
every number in S136 section 4 reproduces byte-for-byte from the landed tree.**

S136 built the four round-grain tables and screened them with the two families declared
IN-PROCESS ONLY, because `scripts/platformkit/foundry/asof_supply.py` was owned by the
S128/S129 lane at the time. That lane has landed (689a2ecf8). This memo applies section 5.

A SCREEN IS A NON-FINDING and this one is a NULL. Calibration language only -- no dollar, ROI,
profit or edge claim, and none of the retracted figures appears.

---

## 0. Premise (Q8), re-measured before any edit

| the fact section 5 rests on | measured on the landed tree | verdict |
|---|---|---|
| the four `_rg` parquets exist | `schedule_density_rg` 997,949 B, `schedule_density_rg_wta` 293,889 B, `travel_scouting_rg` 1,072,502 B, `travel_scouting_rg_wta` 240,646 B | **HOLDS** |
| `Supply` carries the S129 `pregame` field and `_side_rule` fails closed without it | `pregame: str = ""` declared; `_side_rule` raises `no declared pregame as-of basis` | **HOLDS** |
| the S122 leak test is already source-aware | `test_neither_family_is_declared_on_the_leaky_tourney_date_source` asserts `"_rg" in` every source part and `rest_days` absent | **HOLDS** |
| `catalogue.NAMED` is 33 and `test_catalogue.py:20` asserts 33 | both confirmed | **HOLDS** |
| the density table has no side flag; the travel table has `is_p1` | density columns carry `player_id` only; `travel_scouting_rg.is_p1` is `bool` | **HOLDS** |

Not falsified.

## 1. Registry applied

`scripts/platformkit/foundry/asof_supply.py`:

* `_load_tennis_sides` added and registered as `_LOADERS["tennis_sides"]` -- the density table's
  side is read off the event_id counted from the END (S122: a dashed tourney_id shifts the head).
* `tennis_schedule_density` declared over `schedule_density_rg.parquet,schedule_density_rg_wta.parquet`,
  rule `side`, members `("matches_last_7d", "matches_last_14d")`, `side="_is_p1"`,
  `entity_from="player"`, `loader="tennis_sides"`, with the S129 `pregame` basis.
* `tennis_travel_scouting` declared over `travel_scouting_rg.parquet,travel_scouting_rg_wta.parquet`,
  rule `side`, members `("miles_flown_in", "venue_altitude_m")`, `side="is_p1"`,
  `entity_from="player"`, `loader="glob"`, `overrides=(("venue_altitude_m", "a"),)`, with its own
  `pregame` basis.
* `rest_days` is NOT a member of either entry -- **CLOSED AT LIMIT**, per S136 section 3.
* The S122 "DELIBERATELY NOT declared" comment block is replaced; the leak it recorded, the fix and
  the dropped member are documented on the constants in `asof_supply_columns.py`.

**Byte-identity with what was screened.** The landed `Supply` fields were compared in-process with
`s136_screen`'s in-process declaration: `source`, `columns` and `pregame` are `True == True` for
both families, and `loader`/`side` are `tennis_sides`/`_is_p1` and `glob`/`is_p1`. The landed
entries are the screened entries.

`scripts/platformkit/foundry/catalogue.py`: `NAMED` gains the four `_rg` paths, **33 -> 37**; the
frozen four stay NAMED beside them. `tests/platformkit/foundry/test_catalogue.py:20` `== 33` -> `== 37`.

**300-line rail held (a CORRECTION to section 5).** Applying section 5 verbatim took
`asof_supply.py` to 332 lines, over the project's 300-LOC cap that S128 landed the file at exactly.
The pure-data split S128 established was extended: five member tuples (`_VALUE`, `_ADV`, `_RELIEF`,
`_REFEREE`, `_SERVE`) and four source paths (`_STYLE_SRC`, `_MATCHES_SRC`, `_VALUE_SRC`,
`_REFEREE_SRC`) moved verbatim into `asof_supply_columns.py` beside `_PIT` / `_STYLE` /
`_NBA_QUARTER`, and the S136 constants live there too. **`asof_supply.py` is exactly 300 lines
again.** No member list, source, rule or field VALUE changed -- the move is data relocation only,
and `tests/platformkit/foundry/test_asof_supply.py` (whose registry construct test asserts every
side entry declares a pregame basis and every season-grain entry declares exactly one season
field) passes 8/8 unchanged.

## 2. The leak test PASSES with the entries declared

`python -m pytest domains/tennis/test_wta_schedule_travel.py -q` -> **5 passed**. With both
families now present in `REGISTRY`, the source-aware assertions actually execute: every source
part carries `_rg` and neither member list carries `rest_days`. Re-registering the frozen
tourney-date parquets, or serving `rest_days` off either, still fails this test first.

## 3. The screen reproduces from the landed tree

`python -m scripts.platformkit.eval_gate.s136_screen --out-dir <scratch>` (`--predictor real`,
scratch sqlite, charges off), run twice -- once on the applied entries and again after the
300-line compaction -- gave **identical output both times**:

```
seeded sport=tennis n=108
screen_partition_sha256 sport=tennis c8dde4f3a44c8e58
foundry_pass=0 screens=108 promotions=32 charges=0 idle=False
charged_ledger_created=False
result rows: 104 = 72 T0 (32 COVERED, 40 UNCOVERED) + 32 T1 SCREEN
```

| family | T0 | COVERED | best filled/800 | pct | S136 |
|---|---|---|---|---|---|
| `tennis_schedule_density` | 16 | 16 | **800/800** | 1.0000 | matches |
| `tennis_travel_scouting` | 16 | 16 | **785/800** | 0.9812 | matches |
| `tennis_serve_return_profiles` (regression) | 40 | 0 | 593/800 | 0.7412 | matches |

| family | best member / transform | Brier incumbent | Brier model | improvement | DM CI 95 (recomputed) | p | clusters | S136 |
|---|---|---|---|---|---|---|---|---|
| `tennis_schedule_density` | `matches_last_7d__z_vs_league` | 0.197611 | 0.199231 | **-0.001620** | [-0.005050, +0.001810] | 0.3555 | 233 | matches |
| `tennis_travel_scouting` | `venue_altitude_m__z_vs_league` | 0.197611 | 0.199560 | **-0.001949** | [-0.005138, +0.001240] | 0.2321 | 233 | matches |

**Screens improving on the close at all: 0 of 32 (0.0 pct). CIs clearing zero: 0 of 32.**
**NO DIFFERENCE from S136 section 4 on any reported figure.** The screen partition sha256
`c8dde4f3a44c8e58` is byte-equal to S58c / S79 / S85 / S108 / S111 / S122 / S136.

The leak probe also reproduces exactly: the 2025 Wimbledon champion serves
`[0, 1, 2, 3, 4, 5, 6]`, 0.5363 of 83,772 rows read `matches_last_7d == 0`, `rest_days` is absent,
and the served correlations are `matches_last_7d +0.0481` (800/800), `matches_last_14d +0.0685`
(800/800), `miles_flown_in +0.0565` (773/800) -- all three inside the +/-0.0693 two-sigma band.

## 4. Tests (per-file only)

| file | result |
|---|---|
| `tests/platformkit/foundry/test_asof_supply.py` | **8 passed** (S128/S129's 8 kept green) |
| `tests/platformkit/foundry/test_catalogue.py` | **13 passed** (`NAMED == 37`) |
| `tests/platformkit/foundry/test_screen_predictor.py` | **5 passed** |
| `domains/tennis/test_wta_schedule_travel.py` | **5 passed** (leak test now exercised) |
| `domains/tennis/test_schedule_density_roundgrain.py` | **8 passed** |

A5 readers of the touched modules, re-run unchanged: `tests/platformkit/foundry/test_grammar.py`
5 passed and `scripts/platformkit/eval_gate/test_catalog_rescreen.py` 8 passed -- both walk
`catalogue.entries()`, which grows by the four present `_rg` tables (the `>= 69` floor is now 73).
`asof_supply_columns.py` has exactly ONE importer, `asof_supply.py`. The only external `Supply`
constructors are `s122_screen.register_leaky` and `s136_screen.register_roundgrain`, both of which
OVERWRITE the registry entry in-process, so neither is affected by the declaration landing.

## 5. Self-check (VERIFIER_CONTRACT B + Q)

- **B1** no metric computed after excluding failing rows; coverage is over the whole 800-row window
  and the UNCOVERED regression family is named at 593/800.
- **B2** additive schema. Two registry keys added, one loader added, four catalogue names appended;
  nothing renamed or removed for a reader. The five tuples and four paths moved to
  `asof_supply_columns.py` are verbatim and have exactly one importer, checked.
- **B3** nothing quarantines on absent evidence: an unresolved city and a debut stay NaN.
- **B5** no pod contact of any kind.
- **B6** no orphans: nothing moved out of a module with an outside importer, nothing retired.
- **B7** no head slices; all 800 served rows are scored and the champion probe prints R128..F.
- **B9** 233 CI clusters over 800 rows, the same cluster count S122/S136 reported.
- **B10 / Q3** NO BAR MOVED. `_COVERAGE_FLOOR = 0.8`, seed 20260903, 800 rows, purge/embargo and
  `IMPROVEMENT_BAR` byte-identical to master; partition sha `c8dde4f3a44c8e58` unchanged.
  `rest_days` stays CLOSED AT LIMIT, never re-admitted on a lowered bar.
- **Q1** nothing clears a bar, so no prereg and no seal is required; none is asserted.
- **Q2** NO CHARGE. `allow_charge=False`, `tiers.charge_tier` never reached, `_charge_ledger` never
  called, `charged_ledger_created=False` on both runs, and
  `data/cache/eval_gate/backtest_fwer.jsonl` is **18 rows, md5 a4ae7c13995672e478d59770591b83ba**
  before and after -- never opened.
- **Q4** every screen runs inside `eval_gate.walk_forward` with purging and the symmetric embargo;
  no meta-learner.
- **Q5** no AHEAD is claimed -- both families are BEHIND the close -- so the two-corpora rule is not
  engaged; both spines (ATP and WTA) were screened together regardless.
- **Q6** calibration language only. No dollar / ROI / profit / edge word; no retracted figure.
  S122's leak-artifact improvement is not quoted here at all. An honest NULL is a success.
- **Q7** coverage is SAMPLED at n = 800 and the screen table is n = 32, both above the rail. The
  registry field comparison is n = 6 (CONSTRUCT -- every declared field of both entries).
- **Q8** the premise was re-measured first (section 0); every part HOLDS.
- **Q9** each T1 trial's JSON carries its per-event differential and every CI above was recomputed
  from those rows by `s111_screen.dm_ci` in the documented direction, never from the stored
  `dm_stat`.

**Human-gated trees untouched:** nothing under `src/`, `kernel/`, `api/`, `intel/`,
`scripts/team_system/` was read for writing or edited. `data/registry/` untouched. No feature flag
flipped ON. No forced-overwrite flag used anywhere. No push. No file owned by the S126 re-run lane
(`eval_gate/s114_*`, `foundry/ingame_guards.py`, `foundry/ingame_screen*.py`) was touched.

## 6. NOT VERIFIED

- The re-screen is the LOCAL factory only, on the frozen 800-row tennis window; no pod run.
- The 0-mile within-tourney hop (S136 section 3) is unchanged: `miles_flown_in` still carries
  round depth as well as travel, pinned by a test rather than removed.
- Round-robin siblings still cannot be ordered among themselves (an UNDER-count on ~5.4 pct of
  appearance rows), unchanged from S136.
- The four hypotheses that needed `rest_days` stay UNCOVERED; lifting that needs a per-match date
  from another feed, not another builder.
- The 300-line compaction is a data relocation verified by test and by an in-process field
  comparison, not by a byte-diff of every served value across the whole registry.

## 7. Files

| file | LOC | what |
|---|---|---|
| `scripts/platformkit/foundry/asof_supply.py` | 300 | the two declarations + `_load_tennis_sides`; back at the rail |
| `scripts/platformkit/foundry/asof_supply_columns.py` | 85 | the S136 constants, plus five tuples and four paths lifted verbatim |
| `scripts/platformkit/foundry/catalogue.py` | 115 | `NAMED` 33 -> 37 |
| `tests/platformkit/foundry/test_catalogue.py` | -- | `== 33` -> `== 37` |
