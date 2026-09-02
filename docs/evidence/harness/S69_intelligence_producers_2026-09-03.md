# S69 -- the five broken intelligence producers

Row: `build_quarter_momentum` and `build_tipoff_predictability` die on
`KeyError: 'player_id'`; `build_cv_fatigue_trajectories`, `build_ingame_momentum`
and `build_lineup_chemistry` exceed 300 s -- 4 artifacts frozen at 2026-06-02.

Verdict: **ACCEPT WITH CORRECTIONS**, with a **PARTLY FALSIFIED PREMISE**.
All five producers now run to completion and `refresh_once` over exactly those
five returns **5 advanced / 5**, 0 failed, 0 timeout. The row's split of the
five into "2 schema, 3 wall time" is wrong: it is **3 schema, 2 wall time**, and
the schema fault is not a rename.

Calibration/audit work only. No dollar, ROI, profit or edge claim; no bar moved.

---

## 0. Premise re-measured first (Q8)

| the row says | measured 2026-09-02/03 | verdict |
|---|---|---|
| `build_quarter_momentum` dies on `KeyError: 'player_id'` | reproduced at `build_quarter_momentum.py:246`, after 310 of 404 directories | CONFIRMED |
| `build_tipoff_predictability` dies on `KeyError: 'player_id'` | reproduced at `build_tipoff_predictability.py:177`, after 308 of 404 | CONFIRMED |
| `build_cv_fatigue_trajectories` is a 300 s timeout | **FALSIFIED.** It CRASHES with `KeyError: 'velocity'` at **301 s** -- one second past S57's subprocess cap, so S57 saw a timeout and recorded one. Same root cause as the other two | FALSIFIED |
| `build_ingame_momentum` exceeds 300 s | CONFIRMED (a quadratic, section 3) | CONFIRMED |
| `build_lineup_chemistry` exceeds 300 s | CONFIRMED -- measured **627 s** end to end on the HEAD module | CONFIRMED |
| "schema drift ... `player_id` renamed" | **FALSIFIED.** No NBA input lost the column: **355 of 357** `tracking_data.csv` files still carry `player_id` in the same 67-column schema | FALSIFIED |
| 4 artifacts frozen | **5** artifacts sit behind the three crashing producers (`quarter_profiles`, `quarter_signatures`, `tipoff_predictability`, `tipoff_predictability_signals`, `cv_fatigue_trajectories`); 8 in total across all five producers | CORRECTED |

## 1. The actual cause -- a foreign sport's schema in the NBA tracking directory

`data/tracking/` is no longer NBA-only. The sport-blind tracking harness writes
its runs to the same tree in the `tracking_schema` shape, and every one of these
NBA intelligence builders enumerates **every subdirectory unconditionally**.

Census of `data/tracking/`, n = 357 (CONSTRUCT -- every directory holding a
`tracking_data.csv` is enumerated; 404 directories exist, 47 hold no CSV):

| header shape | n | example | effect |
|---|---|---|---|
| 67 cols, `frame,timestamp,player_id,team,...` (NBA) | **355** | `0022400625` | processed normally |
| 5 cols, `frame,track_id,cls,x,y` | 1 | `failclosed_smoke` | header only (1 line) -- already dropped by `MIN_TOTAL_ROWS` |
| 8 cols, `frame,track_id,cls,x,y,coordinate_space,observation,calibration` | 1 | `mlb_2iosUkpL0Bc` | **19,576 rows -- the crash** |

`mlb_` sorts after the numeric game ids, so all three builders did ~87 % of
their work and then died on the last-but-one directory. Nothing was renamed;
a second sport's tracking output simply landed in the NBA builders' input set.

## 2. CHANGE (a) -- a schema guard at each loader, not an alias

One guard at the point each builder reads the CSV, additive, returning the
builder's own "not usable" value so the directory is SKIPPED and the pass
continues (B3: missing is not bad):

- `build_quarter_momentum._process_one_game` -- `return []`
- `build_tipoff_predictability._process_one_game` -- `return []`
- `build_cv_fatigue_trajectories._load_features` -- `continue` to the next
  candidate source; it also checks `velocity`, the column it actually indexes

**Deliberately NOT an alias.** Mapping `track_id` onto `player_id` would fold a
baseball run's track ids into a per-NBA-player artifact whose CV feature columns
(`velocity`, `court_zone`, `team_spacing`, ...) that file does not have -- a
degenerate unit in the denominator (B9) and a contaminated metric (B1). The
honest handling of a foreign schema is to name it and skip it.

`build_lineup_chemistry` already had this guard (`"player_id" not in
df.columns`) and additionally requires `jersey_name_map.json`, which the MLB
directory has no reason to hold; `build_ingame_momentum` draws its game list
from the quality metrics CSV filtered to `quality == "high"`, which the MLB
directory cannot enter. Both were genuine wall-time failures.

## 3. CHANGE (b) -- two quadratics removed, both the same one

Both slow builders spent their time in a per-frame-row `DataFrame.iterrows()`,
which constructs one pandas `Series` per row of a whole game's tracking table.

**`build_ingame_momentum._build_slot_info`.** cProfile of one game
(`_process_game`, 35,392 rows): total 2.350 s, of which `_build_slot_info`
2.095 s = **89.1 %**. Over the 195 high-quality games in scope that is roughly
460 s against a 300 s cap. Replaced by columns prepared once plus a `Counter`
loop over plain numpy values -- the `Counter` is kept, so insertion-order
tie-breaking is unchanged.

**`build_lineup_chemistry.resolve_slots`.** Same pattern over
`df[["player_id", "jersey_number", "player_name"]]`.

Both verified PAIRED against the row loop they replace, not by inspection:

| function | corpus sample | equality | time |
|---|---|---|---|
| `_build_slot_info` | 5 games at the 0/25/50/75/100th percentile of the in-scope list (32,500-59,218 rows) | jersey map and team map identical on **5/5** | 6.68 s -> 0.21 s (**32.0x**) |
| `resolve_slots` | 6 games spanning the in-scope list, compared against the HEAD module's own `resolve_slots` loaded side by side | resolved slot map identical on **6/6** | counter loop 4.67 s -> whole function 0.18 s (**26x**) |

Three semantics that a naive vectorisation would have broken are pinned by
tests rather than trusted: slot 0 / NaN contributes nothing; a jersey of
`"12.0"` counts as `"12"` while a non-numeric one is dropped; and a NaN
`team_abbrev` does NOT fall back to `team` (NaN is truthy in Python, so
`row["team_abbrev"] or row["team"]` kept the NaN and the row was then dropped as
the string `"nan"`), while an empty-string abbrev does fall back.

## 4. Wall time, before -> after

Each figure is one full pass over the 357-game / 4.56 GB `data/tracking` corpus
on this box, shared with the other lanes running at the time.

| producer | before | after | what changed |
|---|---|---|---|
| `build_quarter_momentum` | crash, `KeyError: 'player_id'` | **132 s** | schema guard |
| `build_tipoff_predictability` | crash, `KeyError: 'player_id'` | **108 s** | schema guard |
| `build_cv_fatigue_trajectories` | crash at **301 s**, `KeyError: 'velocity'` | **275 s** | schema guard |
| `build_ingame_momentum` | > 300 s (S57 timeout) | **77 s** | `iterrows` removed |
| `build_lineup_chemistry` | **627 s** | **179 s** (3.5x) | `iterrows` removed |

## 5. CHANGE (c) -- the producer timeout, raised to a measured value

`intelligence_producers.PRODUCER_TIMEOUT_S` 300.0 -> **900.0**, with the five
measured walls in the comment. This is the knob S57's own memo labels "a knob,
not a bar" -- it is a subprocess kill cap on batch builders, not a harness
threshold or gate value, and no bar or threshold moved anywhere (B10/Q3).

The raise is not needed to pass: all five now finish inside 300 s. It is
headroom. This box's read throughput over the same corpus varied by more than an
order of magnitude between runs (antivirus scanning, `MsMpEng.exe` at 66,208 s
of CPU), and `build_cv_fatigue_trajectories` finished 25 s under the old cap --
300 s was killing runs that were merely slow. The ceiling is recorded in the
comment: a genuinely hung builder now wastes 15 min instead of 5.

## 6. CHANGE (d) -- `generated_at` on the two artifacts that can carry it

`quarter_signatures.json` and `tipoff_predictability_signals.json` already
stamped their own write time under the key `generated`, which
`gate_manifest._ASOF_KEYS` does not contain, so both registered `mtime`-sourced.
`generated_at` is added as an ADDITIVE sibling (`generated` untouched for every
existing reader) and is UTC-aware, because the naive local value read
**0.21 days stale** to a UTC freshness check on an artifact one minute old.

Confirmed through `gate_manifest._row_for` after the re-run:

| artifact | measured_at_source before | after | staleness_days |
|---|---|---|---|
| `quarter_signatures.json` | `mtime` | **`field:generated_at`** | 0.0 |
| `tipoff_predictability_signals.json` | `mtime` | **`field:generated_at`** | 0.0 |

The layer's self-stamped count goes 5 -> 7 of 151. `lineup_signatures.json` is
NOT stamped: it is a flat dict keyed by `<game_id>_L<lineup_id>` with no
metadata envelope, so a `generated_at` key would appear to every reader that
iterates it as a lineup (B2). The three parquet artifacts carry no field stamp
at all; S57's `mtime:` probe remains their stamp. Both are named here rather
than worked around.

## 7. The refresh pass -- 5 advanced / 5

```
refresh_once(root, None, <the five targets>, timeout_sec=900.0)
wall 708 s
n_targets 5  n_advanced 5  n_failed 0  n_timeout 0  n_no_producer 0  n_no_run 0
  intel:build_cv_fatigue_trajectories  ok  mtime:...T17:34:50Z -> mtime:...T17:42:23Z
  intel:build_ingame_momentum          ok  mtime:...T17:30:23Z -> mtime:...T17:43:11Z
  intel:build_lineup_chemistry         ok  ...T17:34:05Z -> ...T17:45:30Z
  intel:build_quarter_momentum         ok  ...T17:35:21Z -> ...T17:47:21Z
  intel:build_tipoff_predictability    ok  ...T17:36:36Z -> ...T17:48:56Z
```

All 8 artifacts behind the five producers regenerated, with row counts printed:

| artifact | rows |
|---|---|
| `quarter_profiles.parquet` | 559 x 15 |
| `quarter_signatures.json` | 3 top-level keys, `generated_at` stamped |
| `tipoff_predictability.parquet` | 45 x 6 |
| `tipoff_predictability_signals.json` | 4 top-level keys, `generated_at` stamped |
| `cv_fatigue_trajectories.parquet` | 164 x 8 |
| `ingame_momentum.parquet` | 878 x 16 |
| `lineup_chemistry.parquet` | 6,123 x 51 |
| `lineup_signatures.json` | 1,595 lineups |

`docs/INTELLIGENCE.md` carried three counts this pass made stale
(`lineup_chemistry` 4,760 + 1,175 -> 6,123 + 1,595, `quarter_profiles`
528 -> 559, `ingame_momentum` 775 -> 878); those three rows are corrected.
`tipoff_predictability` was already 45 and is unchanged.

**Why the pass was driven through `refresh_once` and not the CLI.** The first
attempt, `python -m ... artifact_refresh --once --intelligence --targets <five>`,
returned **5 TIMEOUT, 0 advanced** in 601 s. `artifact_refresh.py` now carries
`PRODUCER_TIMEOUT_SEC = 120.0` (S66, landed at HEAD while this lane ran), a
per-producer wall cap applied at the refresh layer on a daemon thread, with no
CLI flag to change it. 120 s is shorter than
four of the five measured walls. S69 owns none of that file and did not touch
it; the pass calls `refresh_once(..., timeout_sec=900.0)` instead. This is a
`NEW GAP`, section 9.

## 8. Tests

New, per file:

| file | n | what it pins |
|---|---|---|
| `tests/scripts/test_intelligence_producer_schema_guard.py` | 6 | a foreign-schema directory returns empty from both `_process_one_game`s instead of raising; a real NBA directory still produces rows (the guard cannot silently empty the corpus); both JSON builders carry `generated` AND a tz-aware `generated_at`, populated and empty branches |
| `tests/scripts/test_ingame_momentum_slot_info.py` | 5 | slot 0 / NaN dropped; `"12.0"` -> `"12"` and non-numeric dropped; NaN `team_abbrev` does not fall back while `""` does; `team` alone used when `team_abbrev` is absent; empty frame is not an error |
| `tests/scripts/test_lineup_chemistry_resolve_slots.py` | 5 | slot 0 / NaN contributes nothing; the jersey channel wins over the name channel; a non-numeric jersey falls through to the name channel; `"?"`/`"nan"`/`"None"`/`""` placeholder names dropped; an unresolvable slot is omitted, never invented |

Regression, run per file in master:

| file | result |
|---|---|
| `tests/platformkit/mcp_server/test_intelligence_producers.py` | 7 passed |
| `tests/platformkit/mcp_server/test_artifact_refresh.py` | 9 passed |

**32 passed, 0 failed**, every run scoped to a single file.

## 9. NEW GAPs

- **S66's 120 s wall cap re-breaks all five through the CLI.**
  `artifact_refresh.PRODUCER_TIMEOUT_SEC = 120.0` is committed at HEAD, is
  shorter than four of the five measured walls, and is not exposed on the CLI,
  so `--once --intelligence` returns TIMEOUT for every one of these producers
  even though all five now complete. Worse, the cap abandons a DAEMON thread while its subprocess keeps
  running and writing: the 601 s CLI attempt reported all five unchanged, yet
  three of the abandoned builders finished afterwards and moved their artifacts
  (visible as the `stamp_before` values in section 7 being newer than the
  section 4 run). Needs one owner to reconcile the two caps and expose the knob.
- **Seven sibling producers enumerate `data/tracking` with no `player_id`
  guard**: `build_clutch_cv`, `build_possession_type_intel`,
  `build_sequential_possession`, `build_shot_clock_buckets`, `build_trade_intel`,
  `eval_live_shot_quality` (and `train_shot_quality`, which already guards). All
  advanced in S57's pass, so their exposure is unproven -- but the same
  foreign-schema directory is in their input set and nothing stops a second one
  landing.
- **The write side is untouched.** This row guards the readers. Whatever writes
  `mlb_*` and `failclosed_smoke` into `data/tracking/` still does; a per-sport
  prefix or a `sport` field in `tracking_schema` would fix it once instead of
  once per reader, but that is the tracking harness's tree, not this row's.

## 10. NOT VERIFIED

- **The two vectorisations are verified on 5 and 6 games, not on all 195/331.**
  Equality is exact on those samples, drawn evenly across the sorted in-scope
  list (not a head slice, A3/B7), but a game with a tie in jersey or team mode
  that resolves differently would not be caught by an 11-game sample.
- **The regenerated artifact CONTENT was never opened.** Row counts and stamps
  were checked; nothing was scored, joined to a corpus, or checked against a
  close. This row makes five producers run and eight artifacts current. It makes
  no claim that any of them carries signal.
- **The three parquet artifacts still have no self-declared stamp**, so 149 of
  151 intelligence rows remain `mtime`-sourced and `assert_fresh` stays unarmed
  on the category (S57's finding, unchanged).
- **`build_ingame_momentum`'s "before" is S57's timeout, not a re-measured
  end-to-end run.** The `iterrows` removal landed before the baseline batch
  reached it, so the 77 s is an after-only wall; the removed cost is measured
  PAIRED at the function level (6.68 s -> 0.21 s on 5 games) rather than as a
  full old-code pass.
- **Wall times are single runs on a contended box.** The same corpus read varied
  by more than 10x between runs; the before/after pairs for
  `build_lineup_chemistry` (627 -> 179 s) and the four crash-to-completion
  numbers should be read as order-of-magnitude, not as benchmarks.
- **`failclosed_smoke` was never the crash** -- it is header-only and was
  already dropped by `MIN_TOTAL_ROWS`. Only `mlb_2iosUkpL0Bc` was proven to
  crash the builders; a third foreign schema with different columns is not
  covered by anything measured here, only by the guard's shape.
- **The 355/357 count is a header read**, not a full parse: a file whose header
  names `player_id` but whose column is entirely null would pass the guard.
- **No `data/registry/` write, no pod contact, no flag flipped on, no OS
  scheduler task armed, no ledger charge, K never read.** The three producers
  edited are 850-1,174-line legacy builders that were already far past the
  300 LOC rule before this row; the diff adds 9, 9 and 8 lines to them plus the
  two stamps, and does not reduce them.

## 11. Contract self-check

B1 no metric excludes its own failures -- the census denominator is all 357
tracking directories and the pass denominator is all 5 targets.
B2 additive: `generated` kept beside the new `generated_at`; every guard is a
new early return, no column, status value or field renamed or removed.
B3 a foreign-schema directory is SKIPPED and named, never quarantined into a
failure that stops the pass; the other 355 games still process.
B4 no claimable queue introduced. B5 nothing copied to the pod.
B6 no module moved or retired; no import, test or `-m` reference orphaned.
B7 the equality samples are spread evenly over the sorted corpus, not head
slices. B8 no fit, no residual. B9 the foreign track ids are refused precisely
so they cannot become a degenerate unit. B10 no bar or threshold changed --
`PRODUCER_TIMEOUT_S` is a subprocess kill cap, named as a knob in S57.
Q1-Q2 no scored comparison, no prereg needed, no ledger charge (K untouched).
Q3 no bar moved. Q4 nothing scored OOS. Q5 no AHEAD claimed.
Q6 calibration language only; no dollar, ROI, profit or edge word, and none of
the retracted figures appears.
Q7 `n = 357 (CONSTRUCT)` for the tracking census and `n = 5 (CONSTRUCT)` for the
producers -- both enumerations are the whole set.
Q8 premise re-measured in section 0 and partly FALSIFIED, reported as the
result.
