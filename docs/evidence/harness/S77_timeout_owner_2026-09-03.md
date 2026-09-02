# S77 -- one owner for the producer wall cap, and six unguarded siblings

Row: two producer timeout knobs with no owner (`artifact_refresh` 120.0 vs
`intelligence_producers` 900.0); the CLI refresh over the five S69 producers
returned 5 TIMEOUT / 0 advanced while all five completed; also 6 sibling
producers enumerate `data/tracking` unguarded against sport-blind runs.

Verdict: **ACCEPT** -- premise CONFIRMED (there was no owner), one owner landed,
and the real CLI pass over exactly the five S69 producers returns **5 advanced /
5, 0 failed, 0 TIMEOUT** where the same command returned 5 TIMEOUT / 0 advanced.

Calibration/audit work only. No dollar, ROI, profit or edge claim; no bar or
threshold moved anywhere.

---

## 0. Premise re-measured first (Q8) -- CONFIRMED, not falsified

There is no single owner at HEAD. Both constants exist, both are live, and the
one that decides the CLI's TIMEOUT is the SHORTER of the two.

| fact | measured at HEAD (`277bfa90b`) | verdict |
|---|---|---|
| two constants | `scripts/platformkit/mcp_server/artifact_refresh.py:43` `PRODUCER_TIMEOUT_SEC = 120.0` and `scripts/platformkit/mcp_server/intelligence_producers.py:59` `PRODUCER_TIMEOUT_S = 900.0` | CONFIRMED |
| no CLI flag | `artifact_refresh.main` has no `--timeout-sec`; its only pass call is `artifact_refresh.py:284` `refresh_once(args.root, args.out_dir, targets)` -- the fourth parameter is never passed | CONFIRMED |
| the shorter one wins | that call falls to the default at `:208` (`timeout_sec: float = PRODUCER_TIMEOUT_SEC` = 120.0), which `_refresh_target` (`:166`) hands to `_run_producer` (`:186`) | CONFIRMED |
| the thread is abandoned | `_run_producer` joins at `:159` and, if `thread.is_alive()` at `:160`, returns `(1, "producer exceeded 120s wall cap", True)` -- the daemon thread is never cancelled and the row becomes `TIMEOUT` at `:190` | CONFIRMED |
| the writer keeps running | the abandoned thread is still inside `intelligence_producers._runner.run`, whose child had `subprocess.run(..., timeout=PRODUCER_TIMEOUT_S)` at `:252` -- i.e. up to **900 s** of further writing after the 120 s TIMEOUT row was already recorded | CONFIRMED |
| 5 TIMEOUT / 0 advanced | S69 section 7 records the CLI attempt returning 5 TIMEOUT, 0 advanced in 601 s (~120 s x 5) with all five producers completing afterwards | CONFIRMED (S69 measurement, not re-run at 120 s here) |

**No single owner exists, so the row is NOT falsified.** 601 s is exactly what a
120 s cap over five producers costs, and 4 of the 5 walls S69 measured
(132 / 108 / 275 / 77 / 179 s) sit above 120 s.

### The 6 unguarded siblings (CONSTRUCT, n = 7 named by S69)

Every one of these enumerates `data/tracking` and indexes an NBA-only column.
`train_shot_quality.py:166` already carries the guard, so the unguarded set is 6:

| producer | the unguarded read at HEAD | how it failed on a sport-blind run |
|---|---|---|
| `scripts/build_clutch_cv.py` | `:226` `pd.read_csv(td_path)` then `:252` `group_key = "player_name" if ... else "player_id"` | `KeyError` on the groupby |
| `scripts/build_possession_type_intel.py` | `:117` `pd.read_csv(path, usecols=...)` | `usecols` keeps only `frame`; downstream indexes `player_id` |
| `scripts/build_sequential_possession.py` | `:154` `usecols=lambda c: c in needed_cols` | same shape, `player_id` never present |
| `scripts/build_shot_clock_buckets.py` | `:181` `read_csv_safe(td_path, usecols=...)` | tracking columns silently absent, no row and no reason |
| `scripts/build_trade_intel.py` | `:214`, `:273`, `:290` `int(row.get("player_id", 0) or 0)` | never raises -- the directory silently contributed **0 slots**, unnamed |
| `scripts/eval_live_shot_quality.py` | `:83` `pd.read_csv(csv)` over `*/shot_log_enriched.csv` | `made` / `defender_distance` absent |
| `scripts/train_shot_quality.py` | `:166` `if "player_id" not in raw.columns` | ALREADY GUARDED -- not touched |

`build_trade_intel` is the interesting one: `dict.get` with a default cannot
raise, so its exposure is not a crash but a SILENT zero contribution. That is
the failure mode B3 exists for -- missing is not bad, but it must be named.

## 1. CHANGE (a) -- one owner for the wall cap

`intelligence_producers.PRODUCER_TIMEOUT_S` keeps the value (900.0, unchanged
from S69, sitting beside the five measured walls in its comment) and becomes THE
owner. `artifact_refresh` imports it:

```python
from scripts.platformkit.mcp_server.intelligence_producers import PRODUCER_TIMEOUT_S
...
PRODUCER_TIMEOUT_SEC = PRODUCER_TIMEOUT_S
```

The name `PRODUCER_TIMEOUT_SEC` is KEPT as an alias, so every S66 reader and the
existing `test_artifact_refresh.py` resolve unchanged (B2: additive, nothing
renamed or removed). The import is safe in both directions: `intelligence_
producers` imports `artifact_refresh.Target` lazily inside `targets()`, so there
is no cycle.

`--timeout-sec` is added to the CLI with `default=PRODUCER_TIMEOUT_SEC`, and
`main()` now passes it: `refresh_once(args.root, args.out_dir, targets,
args.timeout_sec)`. One number, one flag, one owner.

**This is a knob, not a bar.** It is a subprocess kill cap on batch builders,
exactly as S57 and S69 labelled it. No harness threshold, gate value or
acceptance bar was read or written by this row (B10 / Q3).

## 2. CHANGE (b) -- a TIMEOUT kills its writer

The abandonment is the real defect: S69 measured three builders that finished
and moved their artifacts AFTER the pass had already recorded them unchanged.

`intelligence_producers._runner` now uses `Popen` and publishes the live child
on the callable, and reads its cap from the callable at call time:

```python
proc = subprocess.Popen([sys.executable, script], cwd=str(root), env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
run.proc = proc
try:
    _, err = proc.communicate(timeout=run.timeout_sec)
except subprocess.TimeoutExpired:
    proc.kill()
    proc.communicate()
    raise
...
run.proc = None
run.timeout_sec = PRODUCER_TIMEOUT_S
```

and `artifact_refresh._run_producer` propagates the cap down and kills on the
way out:

```python
if hasattr(producer, "timeout_sec"):
    producer.timeout_sec = timeout_sec   # one owner, propagated to the child
...
if thread.is_alive():
    proc = getattr(producer, "proc", None)
    if proc is not None and proc.poll() is None:
        proc.kill()
        thread.join(30.0)
    return 1, "producer exceeded {0:.0f}s wall cap".format(timeout_sec), True
```

Whichever cap fires first now kills the child, so a `TIMEOUT` row can no longer
leave a writer running. `stdout`/`stderr` stay piped and `communicate()` still
drains them, so the S57 `PYTHONIOENCODING` fix and the rc-tail error message are
byte-identical for the non-timeout paths.

**Ceiling, named not hidden:** an IN-PROCESS producer (the four MCP front-door
adapters `_run_atlas`, `_run_mechanism`, `_run_harness_health`, `_run_execution`)
has no child to kill. Its daemon thread is still abandoned on timeout, exactly as
before. Only producers that shell out -- i.e. all 95 intelligence producers -- are
covered. Killing an in-process thread is not possible in CPython; making those
four subprocesses too is a larger change than this row.

## 3. CHANGE (c) -- the 6 siblings guarded with the S69 guard

The guard S69 landed (`build_quarter_momentum.py:220`,
`build_tipoff_predictability.py:157`, `build_cv_fatigue_trajectories.py:106`) is
an early return at the point the loader reads the CSV, returning the caller's own
"not usable" value and PRINTING the directory name. Reused verbatim in shape:

| producer | guard site | skip value |
|---|---|---|
| `build_clutch_cv._process_one_game` | after `MIN_TOTAL_ROWS`, before `_load_jersey_map` | `return []` + named print |
| `build_possession_type_intel.load_game_frames` | after `read_csv` | `return None` + named print |
| `build_sequential_possession.load_tracking` | after `read_csv` | `return pd.DataFrame()` + named print |
| `build_shot_clock_buckets.process_game` | after `read_csv_safe(td_path)` | `td = None` + a named `warns` entry (its own reporting channel) |
| `build_trade_intel` | new `_has_player_id(td_path)` header check, called from BOTH tracking read sites (`_get_team_for_game_slot`, `build_player_game_team_map`) | `return None` / shot_log fallback + named print |
| `eval_live_shot_quality.load_all_shots` | after `read_csv` of each `shot_log_enriched.csv` | `continue` + named print |

**Skip and name, never alias** -- the S69 reasoning is unchanged: mapping
`track_id` onto `player_id` would fold a baseball run's track ids into a
per-NBA-player artifact that carries none of the CV feature columns (B9
degenerate unit, B1 contaminated metric).

`build_trade_intel` gets a helper rather than two inline guards because both of
its read sites are `csv.DictReader` loops where the check has to be on the
HEADER, not on a DataFrame -- one function, two call sites, root cause fixed
where both callers route through.

## 4. Tests

New, run per file:

| file | n | result | what it pins |
|---|---|---|---|
| `tests/platformkit/mcp_server/test_artifact_refresh_timeout_owner.py` | 5 | **5 passed** | `ar.PRODUCER_TIMEOUT_SEC is ip.PRODUCER_TIMEOUT_S` and >= 900; the `--timeout-sec` argparse default read from `main()`'s own parser equals it; `--timeout-sec 7.5` on the real CLI reaches `_run_producer`; a 20 s subprocess producer under a 1 s cap is KILLED (`proc.poll()` is not None) and its post-timeout marker file never appears; the producer-side cap kills too; a failing producer still reports `rc=3` + stderr tail |
| `tests/scripts/test_sibling_tracking_schema_guard.py` | 12 | **12 passed** | each of the 6 siblings SKIPS the exact 8-column MLB fixture (`frame,track_id,cls,x,y,coordinate_space,observation,calibration`) without raising AND names it, and each still reads a real NBA fixture -- the guard cannot silently empty the corpus |

Regression, each run scoped to a single file:

| file | result |
|---|---|
| `tests/platformkit/mcp_server/test_artifact_refresh.py` | 9 passed |
| `tests/platformkit/mcp_server/test_intelligence_producers.py` | 7 passed |
| `tests/scripts/test_intelligence_producer_schema_guard.py` | 6 passed |

**39 passed, 0 failed.** Never a full-suite run.

## 5. The CLI refresh over the five S69 producers -- 5 advanced / 5

The command is S69's own CLI attempt, the one that returned 5 TIMEOUT:

```
python -m scripts.platformkit.mcp_server.artifact_refresh --once --intelligence
  --scope all --targets intel:build_cv_fatigue_trajectories,intel:build_ingame_momentum,
  intel:build_lineup_chemistry,intel:build_quarter_momentum,intel:build_tipoff_predictability
```

(one line; `--timeout-sec` NOT passed, so the pass ran on the new shared default.)

```
artifact refresh -- 5 target(s), 5 advanced, 0 failed, 0 timeout, 0 no_producer, 0 no_run
```

`data/cache/mcp_server/artifact_refresh_status.json`, this pass:

| counter | value |
|---|---|
| `n_targets` | 5 |
| `n_advanced` | **5** |
| `n_failed` | 0 |
| `n_timeout` | **0** |
| `n_no_producer` | 0 |
| `n_no_run` | 0 |
| `n_stale` | 0 |
| `started_at` -> `finished_at` | 2026-09-02T18:15:00Z -> 2026-09-02T18:34:25Z |
| **pass wall** | **1,165.1 s** |

Per target, with the per-producer wall taken as the gap between consecutive
artifact stamps (the pass is sequential, so this is the producer's own time plus
its probe):

| target | status | stamp before -> after | wall (s) | over the old 120 s cap? |
|---|---|---|---|---|
| `intel:build_cv_fatigue_trajectories` | ok | `mtime:...T17:42:23Z` -> `mtime:...T18:22:04Z` | ~424 | YES (3.5x) |
| `intel:build_ingame_momentum` | ok | `mtime:...T17:43:11Z` -> `mtime:...T18:23:20Z` | ~76 | no |
| `intel:build_lineup_chemistry` | ok | `...T17:45:30Z` -> `...T18:26:57Z` | ~217 | YES |
| `intel:build_quarter_momentum` | ok | `...T17:55:46Z` -> `...T18:30:59Z` | ~242 | YES |
| `intel:build_tipoff_predictability` | ok | `...T17:57:36Z` -> `...T18:34:24Z` | ~205 | YES |

Four of the five again exceeded 120 s, so the old cap would have produced four
TIMEOUT rows on this very pass. `build_cv_fatigue_trajectories` at ~424 s is now
also **above S69's measured 275 s** and would have been killed by the pre-S69
300 s cap as well -- direct evidence for the 900 s headroom S69 argued for on a
contended box, and the reason a single owner had to take the LARGER value.

All eight artifacts behind the five, re-read after the pass:

| artifact | shape |
|---|---|
| `cv_fatigue_trajectories.parquet` | 164 x 8 |
| `ingame_momentum.parquet` | 878 x 16 |
| `lineup_chemistry.parquet` | 6,123 x 51 |
| `lineup_signatures.json` | 1,595 lineups (no `generated_at`, as S69 named) |
| `quarter_profiles.parquet` | 559 x 15 |
| `quarter_signatures.json` | 4 top-level keys, `generated_at` present |
| `tipoff_predictability.parquet` | 45 x 6 |
| `tipoff_predictability_signals.json` | 5 top-level keys, `generated_at` present |

Every parquet shape reproduces S69's exactly, so the six new guards changed
nothing about what these producers emit.

## 6. NOT VERIFIED

- **The 120 s failure was not re-reproduced at HEAD.** The 5 TIMEOUT / 0 advanced
  and the 601 s figure are S69's measurement, quoted; this row read the code path
  that produces them (section 0) rather than spending another ~600 s of corpus
  reads to watch it fail again. What IS measured here is the after state.
- **The in-process producers are still abandoned on timeout.** `_run_atlas`,
  `_run_mechanism`, `_run_harness_health` and `_run_execution` are in-process
  callables with no child, so a hang there still leaks a daemon thread exactly as
  before. Only the 95 subprocess producers are covered. Named, not fixed.
- **`proc.kill()` kills the direct child only.** If a builder itself spawned
  grandchildren those survive; none of the five does, but nothing enforces it.
- **The kill path is tested on a synthetic 20 s sleeper, not on a real builder.**
  The test proves the child dies and its post-timeout write never lands; it does
  not prove a half-written parquet is impossible if a real builder is killed
  mid-`to_parquet`. A killed producer can still leave a partial artifact -- the
  TIMEOUT row now at least tells the truth about it.
- **The six sibling guards are proven on a FIXTURE, not on the live corpus.**
  The fixture is the exact 8-column shape S69 measured in
  `data/tracking/mlb_2iosUkpL0Bc`, but none of the six was run over the real
  357-directory tree in this row, so their end-to-end walls and outputs are
  unmeasured here. A third foreign schema with different columns is covered only
  by the guards' shape, not by measurement.
- **`build_trade_intel`'s guard is a HEADER read**, so a file naming `player_id`
  with an all-null column still passes -- the same limit S69 recorded for its own
  355/357 census.
- **The write side is still untouched** (S69's third new gap). Whatever writes
  `mlb_*` and `failclosed_smoke` into `data/tracking/` still does; this row guards
  readers, one per reader, instead of fixing it once at the writer.
- **LOC.** `intelligence_producers.py` and `artifact_refresh.py` are both exactly
  300 lines after this row (`intelligence_producers` was 301 at HEAD, and the
  reduction is comment/docstring compression, not deleted logic). The six edited
  builders are 436-926-line legacy files already far past the 300 LOC rule before
  this row; the diff adds 6-25 lines to each and does not reduce them.
- **No `data/registry/` write, no pod contact, no flag flipped on, no OS
  scheduler task armed, no ledger charge, K never read, nothing scored.** The
  refreshed artifacts' CONTENT was not opened beyond shape; this row makes the CLI
  report the truth, it claims nothing about signal.

## 7. Contract self-check

B1 no metric excludes its own failures -- the pass denominator is all 5 targets
and the sibling enumeration is all 7 producers S69 named (6 unguarded + 1 already
guarded), n = 7 (CONSTRUCT).
B2 ADDITIVE: `PRODUCER_TIMEOUT_SEC` is KEPT as an alias of the owning constant; no
status value, column or field renamed or removed; `--timeout-sec` is a new
defaulted flag and every existing caller of `refresh_once` and `_run_producer`
keeps its signature.
B3 a foreign-schema directory is SKIPPED and NAMED (a print, or a `warns` entry
where that is the function's own reporting channel), never quarantined into a
failure that stops the pass; every NBA directory still processes.
B4 no claimable queue introduced; a TIMEOUT now kills its writer, so a row can no
longer be contradicted by an artifact that moves after the pass ended.
B5 nothing copied to the pod. B6 no module moved or retired; no import, test or
`-m` reference orphaned -- the alias keeps S66's readers resolving.
B7 not applicable: no sampling, the CLI pass is the whole target set.
B8 no fit, no residual. B9 the foreign track ids are refused precisely so they
cannot become a degenerate unit.
B10 / Q3 NO BAR OR THRESHOLD MOVED. The only value changed is
`artifact_refresh.PRODUCER_TIMEOUT_SEC`, which becomes an alias of the EXISTING
900.0 -- a subprocess kill cap that S57, S66 and S69 all label a knob, not a bar.
No harness threshold or gate value was read or written by this row.
Q1-Q2 no scored comparison, no prereg needed, no ledger charge, K untouched.
Q4 nothing scored OOS. Q5 no AHEAD claimed.
Q6 calibration language only; no dollar, ROI, profit or edge word appears, and
none of the retracted figures appears.
Q7 `n = 5 (CONSTRUCT)` for the pass and `n = 7 (CONSTRUCT)` for the sibling
enumeration -- both are the whole set, so the sampling rail does not bind.
Q8 premise re-measured FIRST (section 0) and CONFIRMED, with the deciding code
path printed line by line.
Q9 no scored artifact, so no differential to archive.
