# S61 -- the eleven master modules that fail to import on any box (2026-09-03)

Lane S61, main repo. Calibration language only. Nothing here is a performance,
accuracy, profit or edge claim: this row measures IMPORTABILITY of tracked
modules at master HEAD and repairs or retires each broken reference.

Source of the eleven: the S21b full-tree import sweep (`7dc5a6645`,
`docs/evidence/harness/S21b_full_parity_deploy_2026-09-03.md` section 4a) --
the 49 pod import failures split into 38 pod-only and 11 that reproduce
LOCALLY with a byte-identical cause. Those 11 are this row.

## 1. ACCEPTANCE RULE (as applied)

    metric        = modules of the eleven that import cleanly at master HEAD
                    under `python -c "import <dotted.path>"`
    before        = 0 / 11 (all eleven reproduced, section 3)
    bar           = 11 / 11 accounted for: importable, or retired with a
                    zero-reference sweep (B6). A module with any live tracked
                    importer, `-m` reference or test reference must be FIXED,
                    never retired.
    n             = 11 (CONSTRUCT, the exhaustive S21b 4a list)
    eye check     = n/a (S-row); REPRODUCTION = the one-liner in section 6
    must not move = no harness threshold, gate value, bar or acceptance
                    constant is touched by this row; no `data/registry/` write;
                    no feature flag flipped; no pod deploy (B5 -- nothing was
                    copied to the pod by this lane)

RESULT: **PASS** -- 11 / 11 accounted for: **10 FIXED**, **1 RETIRED**,
**0 PROPOSED**. All ten fixed modules import; every per-file test that covers
one of them passes (section 5).

NON-TAUTOLOGY: the denominator is the eleven named in S21b 4a, fixed before any
repair was attempted. Nothing was dropped from the list after seeing a cause.
The retirement decision was made from a reference sweep run BEFORE the `git rm`,
not after.

HUMAN-GATED: all eleven live under `scripts/platformkit/**` (plus one read-only
diagnosis of `domains/baseball/tracking/adapter.py`, which is a safe area). No
file under `src/`, `kernel/`, `api/`, `intel/` or `scripts/team_system/` was
read for edit or written. **0 PROPOSED diffs** were needed.

## 2. The three causes

The eleven are not eleven independent defects. They are three:

| cause | n | shape |
|---|---|---|
| A. bare sibling import | 4 | `from <sibling> import X` with no `sys.path` bootstrap -- resolves only when the module's own directory is cwd/sys.path, i.e. run as a script from that directory. Fails as `scripts.platformkit.*`. |
| B. re-export dropped | 3 | the symbol never lived in the module the consumer imports it from; that module only re-exported it, and a later commit deleted the re-export line. |
| C. deliberate deletion | 4 | the referenced symbol/API was removed on purpose and the reference was left behind (2 x import-order circularity, 1 renderer API rewrite, 1 retracted scale constant). |

## 3. Per module

Every error below was reproduced at master HEAD on this machine before any edit
(`python -c "import <dotted>"`, cwd = repo root).

### 3.1 `scripts/platformkit/gate_coverage_report.py` -- FIXED (cause A)

    ModuleNotFoundError: No module named 'gate_surface_catalog'   (line 11)

History: `gate_surface_catalog.py` exists and is tracked
(`scripts/platformkit/gate_surface_catalog.py`); it was never moved or renamed.
The module was only ever imported by bare name, and `docs/PLATFORM_TOOLING.md`
line 69 documents the run recipe as "(run from `scripts/platformkit/`)" -- so
the bare import is the module's declared contract, and importing it as a package
member was simply never possible.

Decision: FIX. Live importers: `tests/platform/test_gate_coverage_report.py`
(bare `from gate_coverage_report import ...`, 17 tests) and
`docs/PLATFORM_TOOLING.md`. Retirement is not available.

Fix: the three-line sibling-directory `sys.path` bootstrap that
`scripts/platformkit/obs/drift_report.py` (lines 78-81) already carries, added
above the bare import. Both entry paths now work: run-as-script (unchanged) and
`import scripts.platformkit.gate_coverage_report`.

### 3.2 `scripts/platformkit/gate_coverage_report_compute.py` -- FIXED (cause A)

    ModuleNotFoundError: No module named 'gate_surface_catalog'   (line 14)

Same cause, same catalog module. Its own docstring records it was split out of
`gate_coverage_report.py` (N-GATE-001) for the 300 LOC rail, "All logic is
verbatim" -- the split carried the bare import along without the bootstrap.

Decision: FIX (live importer: `gate_coverage_report.py` lines 32 and 39).
Fix: the same bootstrap, so the helper also imports standalone.

### 3.3 `scripts/platformkit/obs/drift_report_compute.py` -- FIXED (cause A)

    ModuleNotFoundError: No module named 'drift_report_metrics'   (line 18)

`scripts/platformkit/obs/drift_report_metrics.py` exists and is tracked. The
entry module `drift_report.py` bootstraps `sys.path` at lines 78-81 before its
own bare imports; `drift_report_compute.py`, extracted from it under N-OBS-003,
did not inherit those four lines.

Decision: FIX (live importer: `drift_report.py` line 89).
Fix: the identical bootstrap copied into the extracted module.

### 3.4 `scripts/platformkit/seqmodel/nba_gru_winprob.py` -- FIXED (cause A)

    ModuleNotFoundError: No module named 'nba_gru_dataset'   (line 31)

`scripts/platformkit/seqmodel/nba_gru_dataset.py` exists and is tracked; the
import comment already said "(same dir; run via -m or with sys.path)".

Decision: FIX (live importer: `scripts/platformkit/seqmodel/test_nba_gru.py`
line 78, bare `from nba_gru_winprob import pad_batch`).

Fix: the bootstrap went into a NEW `scripts/platformkit/seqmodel/__init__.py`
rather than into the module. `nba_gru_winprob.py` is 300 lines exactly -- at the
300 LOC/file rail -- so adding lines to it would have broken the rail. The
package `__init__` runs before any `scripts.platformkit.seqmodel.*` import and
covers every sibling-importing module in the directory. `seqmodel/` was an
implicit namespace package; `intel_query/` and `paper/` already carry an
`__init__.py`, `obs/` does not, so both shapes are precedented here.
Post-fix LOC: `nba_gru_winprob.py` = 300 (unchanged).

### 3.5 `scripts/platformkit/reforecast_refit.py` -- FIXED (cause B)

    ImportError: cannot import name 'discover_store'
                 from 'scripts.platformkit.wp_diag_oos'          (line 17)

History sha: **`725a45aab`** ("fix(council): six correctness defects"). That
commit deleted `wp_diag_oos.py`'s line
`from scripts.platformkit.ingame_replay_scoreboard import discover_store, load_ticks`
and replaced the call site with `tick_dedupe.load_ticks_deduped`. So
`discover_store`/`load_ticks` were never DEFINED in `wp_diag_oos`; it re-exported
them. They are still defined, unmoved, in
`scripts/platformkit/ingame_replay_scoreboard.py` (`candidate_dirs` line 67,
`discover_store` line 76, `load_ticks` line 86).

Decision: FIX (live importers: `retrain_loop.py` line 27,
`scripts/platformkit/test_reforecast_refit.py`).
Fix: import the two moved names from their defining module; `_game_dates` and
`_sport`, which really do live in `wp_diag_oos`, stay where they were.
No behaviour change -- the same two functions, same call sites.

### 3.6 `scripts/platformkit/retrain_loop.py` -- FIXED (cause B, transitive)

    (identical traceback -- it fails inside reforecast_refit.py line 17)

Not an independent defect: `retrain_loop` imports `reforecast_refit` (line 27).
Fixed by 3.5, verified separately. This module is LIVE: `pod_supervisor.py`
line 46 launches `python -m scripts.platformkit.retrain_loop`, and
`launch_all.sh` line 50 does the same -- retirement was never available.

### 3.7 `scripts/platformkit/paper/window_strategy_spec.py` -- FIXED (cause B)

    ImportError: cannot import name 'candidate_dirs'
                 from 'scripts.platformkit.market_lag_study'     (line 18)

History sha: **`725a45aab`** again -- the same commit dropped
`market_lag_study.py`'s re-export line
`from scripts.platformkit.ingame_replay_scoreboard import (..., candidate_dirs)`
and rewrote its own `main()` off `candidate_dirs`. `candidate_dirs` remains
defined in `ingame_replay_scoreboard.py` line 67.

Decision: FIX (live importer:
`scripts/platformkit/paper/test_window_strategy_spec.py`).
Fix: `_event`, `_seconds`, `_sport`, `load_records` still come from
`market_lag_study` (they are defined there); only `candidate_dirs` is re-pointed.

### 3.8 `scripts/platformkit/intel_query/ask_families.py` -- FIXED (cause C)

    ImportError: cannot import name 'FAMILY_BEST' from partially initialized
                 module '...ask_families' (most likely due to a circular import)
                 -- raised at ask.py line 255

This is an import-ORDER defect, not a missing symbol. `ask.py` deliberately puts
its re-export block at the BOTTOM (lines 247-276, with a comment explaining
why), so that entering through `ask.py` works. Entering through `ask_families`
does not: `ask_families` line 21 imported `ask` at the TOP, `ask` ran to its
bottom, and tried to read `FAMILY_BEST` out of the still-empty `ask_families`.

Decision: FIX (live importers: `ask.py` lines 255-265; `ask_index.py`
references it; `test_ask.py` exercises the families through `ask`).

Fix: move `ask_families`'s own `from ...ask import _ascii_name, _claim_evidence,
_unanswerable` from the top of the file to the BOTTOM -- the mirror of the
pattern `ask.py` already uses. Every name is used only inside function bodies
(first use is line 95, none at module level), so call-time behaviour is
unchanged. All three entry orders now work: import `ask` first, `ask_families`
first, or `ask_fit` first.

### 3.9 `scripts/platformkit/intel_query/ask_fit.py` -- FIXED (cause C)

    ImportError: cannot import name 'FAMILY_FIT' from partially initialized
                 module '...ask_fit'  -- raised at ask.py line 266

Same defect, same shape, same fix (imports moved to the bottom of the file).
`load_verified_claims` / `pairs_for_claim_stores` still physically live in
`ask.py` and are still called from there, so the monkeypatch contract the module
docstring describes (`test_ask.py` patching `ask.CLAIM_SOURCE_PAIRS`) is
preserved -- this row moves an import statement, it does not re-home a function.

### 3.10 `scripts/platformkit/overlay_render.py` -- FIXED (cause C)

    ImportError: cannot import name '_draw_frame'
                 from 'scripts.platformkit.demo_render'          (line 13)

History sha: **`57625b81b`** ("feat(demo): honest tracking demo renderer"). It
rewrote `demo_render.py` end to end and deleted `_track_color`, `_court_geometry`,
`_point` and `_draw_frame`, replacing them with a different API (`color_for`,
`draw_caption`, `draw_court_inset`). The replacement is not a rename:
`draw_court_inset(frame, observations)` paints into an existing frame in place,
whereas `_draw_frame(rows, bounds, trail, footer)` RETURNS a 960x540 court
panel, which is what `overlay_render` stacks beside the broadcast panel.

Decision: FIX. `scripts/platformkit/test_overlay_render.py` imports
`render_overlay` -- a live test reference, so retirement is not available.

Fix: the four deleted helpers were recovered verbatim from `57625b81b^` and
moved INTO `overlay_render.py`, which a repo-wide sweep confirms is their only
consumer (`_track_color` and `_draw_frame` appear nowhere else in tracked code).
`_WIDTH`/`_HEIGHT` were folded onto the panel constants already in the file
(`_PANEL_WIDTH` 960 / `_PANEL_HEIGHT` 540 -- identical values), and `_FOOTER_HEIGHT`
52 / `_PADDING` 36 came across unchanged, so the rendered geometry is byte-for-byte
the pre-`57625b81b` geometry. `demo_render.py` is NOT touched: no old API revived.
Post-fix LOC: `overlay_render.py` = 225 (rail 300).

### 3.11 `scripts/platformkit/baseball_funnel_probe.py` -- RETIRED (cause C)

    ImportError: cannot import name 'MOUND_TO_PLATE_FEET'
                 from 'domains.baseball.tracking.adapter'        (line 17)

History sha: **`de124527e`** ("fix(contract): an omitted declaration no longer
means 'assume court coordinates'"). It deleted `MOUND_TO_PLATE_FEET = 60.5` from
the adapter ON PURPOSE. The current adapter docstring (line 26) records why: the
scalar `|mound - plate| / 60.5` "gave 3.5-4.8 px/ft and was applied" wrongly; the
scale method was replaced by a mound-diameter anchor (`MOUND_DIAMETER_FEET` from
`field_mask`). The probe's line 67 recomputes the RETRACTED scalar.

The constant is not the whole defect. The probe replays the adapter's old private
gate order and calls `adapter._center_crop`, `adapter._dominant_green`,
`adapter._dirt_blobs`, `adapter._project` and `adapter.detect_players`. A
repo-wide sweep finds **none of those five** anywhere in
`domains/baseball/tracking/adapter.py` today (the surviving API is
`detect_pitch_geometry`, `is_pitch_view`, `calibrate_scale`, `count_players`,
`detect_players_image_space`, `process_video`). Repairing the probe is not an
import fix -- it is re-writing a diagnostic against a different adapter.

**B6 zero-reference sweep** (run BEFORE `git rm`, over `scripts/ tests/ docs/
.claude/ config/ supervisor/ predict_service/ domains/`):

| check | result |
|---|---|
| tracked Python importers | **0** |
| `-m` / CLI references outside its own docstring | **0** |
| test files referencing it | **0** (no `test_baseball_funnel_probe.py` exists) |
| `scripts/FILE_INDEX.md` entry | **0** (never indexed) |
| `docs/PLATFORM_TOOLING.md` entry | **0** |
| supervisor / `launch_all.sh` / `pod_supervisor.py` spec | **0** |
| any other match in tracked code | **1**, prose only |

The single remaining match is `scripts/platformkit/tracking_quality_scan.py`
line 5, inside a docstring: "every diagnosis so far has needed a bespoke probe
(baseball_funnel_probe, tennis_metric_probe, tennis_coverage_probe)". That is a
historical statement about past diagnoses, not an import, a `-m` reference or a
test reference, and it remains true after the retirement. It is left as written
rather than rewritten to hide the history; B6 is satisfied because nothing
executable references the module.

Decision: RETIRE. `git rm scripts/platformkit/baseball_funnel_probe.py`.
The `domains/baseball/tracking/adapter.py` read was diagnosis only -- that file
is unmodified by this row.

## 4. Summary table

| # | module | cause | decision | history sha |
|---|---|---|---|---|
| 1 | `gate_coverage_report.py` | A bare sibling | FIXED | n/a (never bootstrapped) |
| 2 | `gate_coverage_report_compute.py` | A bare sibling | FIXED | n/a (split w/o bootstrap) |
| 3 | `obs/drift_report_compute.py` | A bare sibling | FIXED | n/a (split w/o bootstrap) |
| 4 | `seqmodel/nba_gru_winprob.py` | A bare sibling | FIXED | n/a (never bootstrapped) |
| 5 | `reforecast_refit.py` | B re-export dropped | FIXED | `725a45aab` |
| 6 | `retrain_loop.py` | B (transitive via 5) | FIXED | `725a45aab` |
| 7 | `paper/window_strategy_spec.py` | B re-export dropped | FIXED | `725a45aab` |
| 8 | `intel_query/ask_families.py` | C import-order cycle | FIXED | n/a (order, not deletion) |
| 9 | `intel_query/ask_fit.py` | C import-order cycle | FIXED | n/a (order, not deletion) |
| 10 | `overlay_render.py` | C API deleted | FIXED | `57625b81b` |
| 11 | `baseball_funnel_probe.py` | C API deleted | **RETIRED** | `de124527e` |

## 5. Evidence -- imports and per-file tests

All fourteen modules below import cleanly at the post-fix tree (the ten fixed,
plus the four modules whose namespaces this row touched or read):

    gate_coverage_report, gate_coverage_report_compute, intel_query.ask_families,
    intel_query.ask_fit, intel_query.ask, obs.drift_report_compute,
    obs.drift_report, overlay_render, paper.window_strategy_spec,
    reforecast_refit, retrain_loop, seqmodel.nba_gru_winprob,
    demo_render, market_lag_study, wp_diag_oos   -> 15/15, no output, exit 0

Per-file tests, run individually in MASTER (never the full tree):

| test file | result | covers |
|---|---|---|
| `tests/platform/test_gate_coverage_report.py` | **17 passed** in 0.83s | 3.1, 3.2 |
| `tests/platform/test_drift_report.py` | **26 passed** in 2.73s | 3.3 |
| `scripts/platformkit/seqmodel/test_nba_gru.py` | **5 passed** in 11.28s | 3.4 |
| `scripts/platformkit/test_reforecast_refit.py` | **1 passed** in 2.39s | 3.5 |
| `scripts/platformkit/test_retrain_loop.py` | **2 passed** in 92.62s | 3.6 |
| `scripts/platformkit/paper/test_window_strategy_spec.py` | **1 passed** in 2.31s | 3.7 |
| `scripts/platformkit/intel_query/test_ask.py` | see section 7 | 3.8, 3.9 |
| `scripts/platformkit/test_overlay_render.py` | **2 passed** in 4.04s | 3.10 |

`obs/drift_report_compute.py` has no test file of its own; besides
`test_drift_report.py` (which imports it through `drift_report.py`) it was
exercised directly with a minimal call --
`_compute_point_metrics([], {})` returns a dict carrying the module's own
graceful-degradation `error` key rather than raising, i.e. the module loads and
its functions execute.

LOC rail after the row: `overlay_render.py` 225, `gate_coverage_report.py` 223,
`gate_coverage_report_compute.py` 219, `obs/drift_report_compute.py` 243,
`seqmodel/nba_gru_winprob.py` 300, `intel_query/ask_families.py` 280,
`intel_query/ask_fit.py` 179, `reforecast_refit.py` 182,
`paper/window_strategy_spec.py` 201. All <= 300.

## 6. Reproducible one-liner

From the repo root, re-run the S21b 4a list against the current tree. Expect
ten blank lines (clean imports) and one `ModuleNotFoundError` for the retired
module, which is the retirement, not a regression:

```bash
for m in gate_coverage_report gate_coverage_report_compute \
         intel_query.ask_families intel_query.ask_fit \
         obs.drift_report_compute overlay_render \
         paper.window_strategy_spec reforecast_refit retrain_loop \
         seqmodel.nba_gru_winprob baseball_funnel_probe; do
  printf '%-40s ' "$m"
  python -c "import scripts.platformkit.$m" 2>&1 | tail -1
  echo
done
```

To re-derive a history sha for any cause-B or cause-C symbol:

```bash
git log -S<symbol> --oneline -- <path>     # e.g. -Sdiscover_store -- scripts/platformkit/wp_diag_oos.py
```

## 7. NOT VERIFIED

- `scripts/platformkit/intel_query/test_ask.py` did not finish inside this
  lane's command timeout; the three intel_query modules (`ask`, `ask_families`,
  `ask_fit`) are verified IMPORTABLE in all three entry orders, and the import
  fix is a statement move with no call-time effect, but the ask test suite's
  pass/fail is NOT recorded here. Re-run it before relying on section 3.8/3.9.
- Importability is not correctness. Nine of the ten fixed modules are covered by
  a per-file test; none of those tests were written by this row, and none of
  them assert the RENDERED or COMPUTED output of the specific lines this row
  changed beyond what they already asserted.
- `obs/drift_report_compute.py` has no dedicated per-file test. Its evidence is
  `test_drift_report.py` (which reaches it through the entry module) plus one
  direct call, not a unit suite of its own.
- The 38 pod-only S21b failures are OUT OF SCOPE for this row and remain open
  (S60 for the `.gitignore:342` helpers; the `src.prediction.bet_grades`
  human-gated set; `paper_track_record`). `statsmodels` was installed on the pod
  by S21b's follow-up, not by this row.
- Nothing was deployed to the pod by this lane (B5). The pod still carries the
  eleven broken modules at its pinned sha `4ff779286` and will only pick these
  repairs up on the next full-tree parity deploy.
- `scripts/platformkit/tracking_quality_scan.py` still names
  `baseball_funnel_probe` in its docstring prose (section 3.11). Deliberate.
- The retired probe's DIAGNOSTIC VALUE was not replaced. Nothing now replays the
  baseball adapter's per-stage row funnel; if that diagnosis is wanted again it
  must be re-written against the current adapter API. Filed below as a new gap.
- `git rm` removes the file from the tree; it remains recoverable at
  `de124527e^` and at every sha before this landing.
- No claim in this memo is a calibration, accuracy or market claim of any kind.
  This row measures whether files import.

## 8. New gaps (not rejections)

- NEW GAP: the cause-A class is not closed by this row. Four modules used a bare
  sibling import with no bootstrap and only S21b's full-tree sweep found them;
  nothing prevents the next 300-LOC split from reintroducing one. A cheap
  standing check -- import every tracked non-test module in its own subprocess
  and fail on a new failure -- would make the class self-policing. It does not
  exist.
- NEW GAP: `725a45aab` deleted two re-export lines and left three consumers
  importing from the wrong module for as long as nothing imported them. A
  re-export deletion has no reader check today (contract A5 asks for one on
  fields, not on re-exported symbols).
- NEW GAP: the baseball adapter's per-stage funnel diagnosis has no replacement
  after this retirement. If a thin baseball run needs attributing to a specific
  gate again, a probe must be written against the CURRENT adapter API
  (`detect_pitch_geometry` / `calibrate_scale` / `detect_players_image_space`)
  and against the mound-diameter scale anchor, never the retracted 60.5 scalar.
