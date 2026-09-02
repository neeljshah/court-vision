# Harness gate audit -- can these metrics fail? (2026-09-02)

Scope: `scripts/platformkit/tracking_harness.py`, `scripts/platformkit/coordinate_provenance.py`,
`scripts/platformkit/tracking_schema.py`, `scripts/platformkit/metric_local_profile.py`,
read against `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B1, B2, B9.
Pulled in as needed: `scripts/platformkit/liveness_metrics.py` (the four liveness metrics the
harness gates on), `scripts/platformkit/tracking_timebase.py` and
`scripts/platformkit/tracking_media_inventory.py` (the G48 sampling-interval chain),
`scripts/platformkit/adapter_run.py` (the only caller that passes `source_metadata`).

Defect class hunted: a gate that cannot fail, or a metric computed from the very thing it is
meant to judge. Same family as G40 (tautological coverage), G50 (a 2-frame table scoring 1.0),
G48 (a bar on raw per-step distance) and G43 (`ball_valid_pct` blind to a 106,853 ft ball).

READ-ONLY audit. No code, threshold, register row or ledger line was changed. This memo is the
only file written. It is not committed.

## Method

Every claim below is either (a) a line I read, quoted, or (b) a fixture I constructed and ran.
Fixtures live in the session scratchpad, not in the repo, and each is labelled with its output.
The existing per-file test was run first to confirm the code is in a green state:

    python -m pytest scripts/platformkit/test_tracking_harness.py -q
    24 passed in 0.73s

No full-suite pytest was run.

---

## 1. The table

"Gates?" = whether the value can put a string into `failures` and therefore flip `passed`.

### Court profile (`tracking_harness.evaluate`, lines 211-294)

| Metric / gate | Denominator (exact) | Gates? | Can it fail? | Name matches behaviour? | Verdict |
|---|---|---|---|---|---|
| `coverage_pct` (L228) | `n_frames` = `df["frame"].nunique()` -- frames PRESENT in the table | yes, `< coverage_min` | yes, but see P1/P9 | **no** | Denominator is the emitted frames, never the clip's frames. 40 emitted frames of a 300-frame clip scores 1.0. G40's core is unresolved; nothing in the signature carries a clip length. |
| `median_track_len` (L230) | tracks that exist (`players.groupby("track_id")`) | yes, `< 3.0` | yes | yes | Fine. Fails closed: no players gives 0.0 which fails. The most load-bearing honest gate in the harness. |
| `oob_pct` (L232-233) | **player rows only** | yes, `> oob_max` | yes | **no** | Real gate, but the name does not say players-only. Ball rows are excluded entirely, which is how P4 survives. Returns 1.0 when there are no players, so it fails closed. |
| `jump_p95` (L239-241) | consecutive **row** pairs within a track (`groupby.diff()`) | yes, `> jump_p95_max` | yes, but only above ~5% prevalence | yes (it is honestly a p95) | The name is honest; the GATE is not. See P2 and P3. Structurally excludes the top 5% of steps, which is exactly where teleports live, and `diff()` is blind to frame gaps. |
| `jump_p95 unmeasurable` (L257-258) | n/a, structural guard | yes | yes | yes | Good guard. Closes the "players present, zero measurable steps" hole that would otherwise report `jump_p95 = 0.0` and pass a max gate. |
| `ball_valid_pct` (L234-235) | `n_frames` (all frames present) | yes, `< ball_valid_min` | yes, except football | **no** (documented at L102-105) | Measures ball-row PRESENCE only. Unchanged since G43. For `football` the bar is 0.0 (L53), so the check is never true -- decorative for that sport. See P11. |
| `ball_in_bounds_pct` (L237-238, L106) | ball rows | **no** | **NO -- decorative** | yes | The G43 remediation. It correctly reports 0.0 for a 106,853 ft ball and the run still returns `verdict PASS`. It sees the defect and cannot act on it. See P4. |
| `n_duplicate_frame_track_rows` (L217, L245) | n/a, a count | yes, any non-zero | yes (verified, fixture L) | yes | Fine. Keys on `game_id` when present. One of the few gates with no caveat. |
| `zero_step_share` (liveness_metrics L98) | steps (non-NaN diffs) | yes, basketball only | basketball yes; 7 sports no | yes | Threshold is `None` for wnba/tennis/soccer/baseball/npb/kbo/football (`_UNCALIBRATED`, L24-46) so it cannot fail there. Honestly documented; see P10. |
| `median_step_distance` (L99) | steps | yes, basketball only | basketball yes; 7 sports no | yes | Same `None`-threshold caveat. |
| `distinct_position_ratio` (L100-101) | `len(players)` -- player ROWS, positions pooled across all tracks | yes, basketball only | basketball yes; 7 sports no | partly | Two players on the same rounded coordinate collide and depress the ratio. Minor; noted, not ranked. |
| `stationary_track_share` (L102-107) | tracks | yes, basketball only | basketball yes; 7 sports no | yes | Floor is 0.50 ft for basketball, `None` (exact zero) elsewhere. |
| `liveness_verdict == FROZEN` (L263) | n/a | yes | yes, all sports | yes | The one liveness gate that binds for every sport. Requires `zero_step_share == 1.0` AND `stationary_track_share == 1.0`, so a stream drifting by 1e-9 escapes it. |
| `n_frames` (L211) | n/a, a count | no | n/a | yes | Reported only. |
| `n_unique_games` (L212-213) | `game_id` nunique, else `int(n_frames > 0)` | no | n/a | **no** | With no `game_id` column it reports 1 unique game from frame presence alone. B9 flavour, but nothing reads it. |
| `ball_rows` (L218) | n/a, a count | no | n/a | yes | Reported only. |
| `det_per_frame` (L229) | `n_frames` | **no** | **NO -- decorative** | yes | Nothing reads it. A table with 400 detections per frame and one with 1 both pass. |
| `insufficient_data` (L110, L289) | n/a, `n_frames < 30` | **no, by explicit design (L109)** | **NO -- decorative** | yes, and that is the problem | See P1: it suppresses the metrics without suppressing the verdict. |
| `sampling_interval_s` / `_reason` (L114-115, L131-150) | n/a | no | n/a | yes | Always `None` in production; see P3. |
| `jump_p95_ft_per_s` (L116, L272-273) | `sampling_interval_s` | **no, by explicit design (L111-113)** | **NO -- decorative** | yes | The G48 remediation. Dead in every production path; see P3. |
| `self_consistency_only` (L98) | n/a | no | n/a | yes | Hardcoded `True` at L287. A constant, not a measurement. |
| `source_resolution` / `source_frame_rate` (L122-128) | n/a | no | n/a | yes | Metadata passthrough. |
| `ball_valid` / `ball_valid_applicable` / `ball_telemetry_available` / `ball_telemetry_rule` | n/a | no | n/a | yes | Status labels, not measurements. `ball_valid_applicable` is `available is not False`, so a missing sidecar (`None`) counts as applicable and the ball gate binds -- fails closed, the right direction. |

### Metric-local profile (`metric_local_profile.report_fields`)

| Metric / gate | Denominator | Gates? | Can it fail? | Name matches? | Verdict |
|---|---|---|---|---|---|
| `coverage_pct` (L38) | `n_frames` | yes | yes | no (same as court) | **Not nulled under `insufficient_data`.** A 2-frame table publishes `coverage_pct 1.0` verbatim -- G50's literal headline, alive in this path. See P5. |
| `median_track_len` (L40) | tracks | yes | yes | yes | Fine. |
| `ball_valid_pct` (L41-42) | `n_frames` | yes | yes | no | Same presence-not-validity issue. |
| duplicates (L34, L46-47) | n/a | yes | yes | yes | Fine. |
| `zero_step_share` (L16-23, L63) | steps | **no** | **NO -- decorative** | yes | Computed exactly (no distance), reported, and never compared to any threshold in this path. |
| `insufficient_data` (L66) | `n_frames < 30` | no | n/a | yes | Hardcoded `30`, not `MIN_FRAMES_FOR_METRICS`. Two copies of one bar. |
| `passed` (L64) | n/a | n/a | n/a | **NO** | **Hardcoded `False`** while `verdict` can be `PASS_METRIC_LOCAL`. See P5. |
| 8 spatial fields (L9-13, L68) | n/a | no | n/a | yes | All set to the string `"not_applicable"`. Baseball metric-local rows get NO spatial gate at all: no `oob_pct`, no `jump_p95`, no liveness. Declared G69 design, recorded here for completeness. |

### Coordinate contract (`tracking_schema.py`, `coordinate_provenance.py`)

| Gate | Denominator | Gates? | Can it fail? | Name matches? | Verdict |
|---|---|---|---|---|---|
| `_validate_coordinate_space` (L135-160) | set of distinct declared values | yes | yes | yes | The real gate. Magnitude-independent by design, which is correct. |
| `_validate_image_px_containment` (L99-132) | rows declaring `image_px` | yes (raises) | **NO OUTCOME IT CAN CHANGE** | yes | `image_px` is in no sport's accepted set, so every table this could reject is rejected 3 lines later regardless. It changes the error MESSAGE only. See P8. |
| metric_local calibration check (L161-169) | distinct `calibration` values | yes | yes | yes | Fine. |
| `output_columns` partial-provenance check (`coordinate_provenance.py` L71-78) | provenance columns present | yes (raises) | yes | yes | Fine, and it is a write-side gate so it never reaches a report. |
| `identify_tracking_schema` (L209-226) | column set | raises `ValueError` | yes | yes | But it raises OUT of `evaluate` rather than producing a FAIL report; `except CoordinateTransformUnavailable` (L195) does not catch a plain `ValueError`. See P13. |
| `_producer_ball_telemetry` (L195-206) | sidecar file | raises on non-bool | yes | yes | Same out-of-band raise. |
| legacy-undeclared bypass (L144-147) | n/a | inverts the gate | n/a | yes | `allow_legacy_undeclared=True` skips the coordinate check entirely. `tracklet_merge.py:234-235` passes it. Audited-corpus switch, working as documented. |

**Count: 24 court-profile fields/gates, 8 metric-local, 6 contract gates = 38 examined.
9 can never fail** (`det_per_frame`, `ball_in_bounds_pct`, `insufficient_data`,
`jump_p95_ft_per_s`, `sampling_interval_s`, metric-local `zero_step_share`,
`_validate_image_px_containment` in outcome terms, `ball_valid_pct` for football, and
`self_consistency_only` which is a constant). The four liveness metrics can never fail for 7 of
the 8 configured sports.

---

## 2. Ranked problems

### P1 -- A 3-frame table returns `verdict PASS` with every metric `None`. (most serious)

This is G50 made worse, not fixed. Lines 291-293:

    if report.insufficient_data:
        for field in _N_DEPENDENT_METRIC_FIELDS:
            setattr(report, field, None)

`_N_DEPENDENT_METRIC_FIELDS` (L65-70) blanks 13 metrics. `passed`, `verdict` and `failures` are
deliberately not in that list (L109: "`passed` deliberately does not read it"). So the
degenerate run keeps its PASS and loses the numbers a reader would have used to doubt it.
Before G50 a reader at least saw `coverage 1.0 on 2 frames` and could smell it. Now they see
PASS and a column of nulls.

RAN IT (scratchpad `audit_fixture.py`), 3 frames x 10 players + 1 ball, basketball, court_feet:

    ---- T1 3-frame basketball
       n_frames               3
       coverage_pct           None
       det_per_frame          None
       median_track_len       None
       ball_valid_pct         None
       jump_p95               None
       oob_pct                None
       liveness_verdict       None
       insufficient_data      True
       passed                 True
       verdict                PASS
       failures               []

The 40-frame control (T2) returns the same `passed True / verdict PASS` with real numbers. The
degenerate run and the healthy run are indistinguishable on the headline field. That is the G50
finding restated, on the current code.

### P2 -- `jump_p95` structurally excludes the tail it exists to catch.

A 95th-percentile statistic ignores the top 5% of steps by construction. Teleports are, by
definition, in the top 5%. So the teleport gate is blind to teleports until they stop being rare.

RAN IT (scratchpad `audit_fixture5.py`), basketball, bar `jump_p95_max = 6.0` ft, 40 ft teleports
injected at varying prevalence:

    teleport every 50 steps (~ 2.0% of steps) -> jump_p95=  0.60 verdict=PASS
    teleport every 30 steps (~ 3.0% of steps) -> jump_p95=  0.60 verdict=PASS
    teleport every 20 steps (~ 5.0% of steps) -> jump_p95=  0.60 verdict=PASS
    teleport every 15 steps (~ 6.0% of steps) -> jump_p95= 40.00 verdict=FAIL
    teleport every 12 steps (~ 8.0% of steps) -> jump_p95= 40.00 verdict=FAIL
    teleport every 10 steps (~10.0% of steps) -> jump_p95= 40.00 verdict=FAIL
    teleport every  8 steps (~12.0% of steps) -> jump_p95= 54.00 verdict=FAIL

Up to 5% of all steps can be 40-foot jumps and the reported number does not move off 0.60.
This is the G43 signature exactly: one number for a clean input and a broken one. From
`audit_fixture4.py`, a clean path and a path with 10 forty-foot teleports both report:

    J. 10 tracks each with a 200-frame hole -> n_frames=40 jump_p95=0.6 verdict=PASS failures=[]
    K. same, but a 40 ft teleport across the hole -> jump_p95=0.6 verdict=PASS failures=[]

I am not recommending a fix here, only recording that the gate cannot see its own target defect
at the prevalence that matters.

### P3 -- G48 is unfixed at the gate, and its remediation field is dead in every production run.

Two separate problems on the same line.

(a) The bar is still on raw per-step distance. `tracking_timebase.py` says so in its own
output: `"note": "per_second values are reporting-only; frozen harness gates use raw per-step values"`.
`jump_p95_ft_per_s` is documented non-gating at L111-113. So the 6.0/8.0 ft bar still compares
clips sampled at different intervals. `sampling_plan` (L29-35) picks
`stride = max(1, int(round(frame_rate * 0.1)))`, which yields interval 0.1 s at 30 fps but
0.08 s at 25 fps -- the 25% spread G48 named, still applied against one fixed bar.

(b) `sampling_interval_s` is `None` in every real run, so `jump_p95_ft_per_s` is `None` too.
`_sampling_fields` (L131-150) requires `metadata["frame_stride"]` or `metadata["stride"]`:

    stride = metadata.get("frame_stride", metadata.get("stride"))
    ...
    if stride is None:
        return None, "frame stride unavailable"

`adapter_run.py:124` is the ONLY caller that passes `source_metadata`, and it passes the dict
from `probe_media`, which returns exactly:

    return {"width": stream.get("width"), "height": stream.get("height"),
            "frame_rate": fps, "bit_rate": _integer(stream.get("bit_rate")),
            "path": str(path)}

No stride. `adapter_run` computes `plan.stride` at L99 and puts it in `options`, never in
`metadata`. Every other caller (`tracking_regression.py:79`, `track_daemon_done.py`,
`bridge_infill.py:99`, `depth_replay.py:49`, `tracklet_merge.py:234-235`, `footage_cycle.py:174`,
`tracking_corpus_ab.py:82`, `basketball_relabel_image_px.py:97`, `corpus_rescore.py`) passes no
metadata at all. So the field added to answer G48 reports `None` everywhere and
`sampling_interval_reason` reads `"frame stride unavailable"` forever.

(c) Separately, `groupby.diff()` (L240) differences consecutive ROWS, not consecutive FRAMES.
A track observed at frame 20 and again at frame 220 contributes one "step" treated identically
to a 1-frame step. Fixture J/K above is that case.

### P4 -- `ball_in_bounds_pct` sees the G43 defect and cannot act on it.

RAN IT (`audit_fixture.py`), 40 frames, ball parked at (106853, 106853):

    ---- T3 40-frame, ball at 106853 ft
       ball_valid_pct         1.0
       ball_in_bounds_pct     0.0
       oob_pct                0.0
       passed                 True
       verdict                PASS

`oob_pct` is 0.0 because L232 computes it over `players` only. `ball_in_bounds_pct` is 0.0 and
nothing reads it (L104-105: "it does NOT gate, and no threshold reads it"). The report now
prints the evidence of the defect next to a PASS verdict. That is an improvement on G43 for a
reader who scans every column, and no improvement at all for anything automated.

### P5 -- The metric-local profile contradicts itself, and G50 is still live there.

`metric_local_profile.py` L64-65:

    "self_consistency_only": True, "passed": False,
    "verdict": "PASS_METRIC_LOCAL" if not failures else "FAIL_METRIC_LOCAL",

`passed` is a literal `False` regardless of outcome. RAN IT (`audit_fixture3.py`), a 40-frame
metric-local baseball table that clears every gate:

    G. clean metric_local -> verdict=PASS_METRIC_LOCAL  passed=False  failures=[]
    G. CLI would exit with: 1

A reader of `verdict` sees PASS; a reader of `passed` sees False; the CLI
(`tracking_harness.py:303`, `sys.exit(0 if report.passed else 1)`) exits 1 on a clean pass. I
cannot tell from the code whether the hardcoded `False` is intentional conservatism or an
oversight -- there is no comment on that line either way, so I am reporting it as an
inconsistency, not as a bug with a known intent.

Second half: this path has no equivalent of the court path's L291-293 nulling. RAN IT, 2-frame
metric-local table:

    B. metric_local n_frames=2 -> coverage_pct=1.0 median_track_len=2.0 insufficient_data=True

`coverage_pct 1.0` on a 2-frame table -- the exact string G50 was filed about -- is still
published, in the sibling code path the G50 fix did not touch.

### P6 -- Every empty table is routed to the metric-local (baseball mound) profile.

`tracking_harness.py:204`:

    if "coordinate_space" in df and df["coordinate_space"].eq(METRIC_LOCAL).all():

`.all()` on an empty Series is vacuously `True`. RAN IT (`audit_fixture2.py`) with an empty
basketball table declaring `court_feet`:

    A. empty df, coordinate_space.eq(METRIC_LOCAL).all() -> True
    A. verdict for empty basketball table -> FAIL_METRIC_LOCAL

Consequences: an empty basketball clip is reported under a baseball profile with eight spatial
fields reading `"not_applicable"`; and the harness's own empty-table branch (L219-223), which
exists to attach `n_duplicate_frame_track_rows` and `ball_rows` to a `_failed_report`, is dead
for any table that carries a `coordinate_space` column -- i.e. for every table not on the legacy
switch. The verdict is still FAIL, so no run is wrongly passed by this. It is a reporting and
routing defect, not a gate hole, which is why it sits below P5.

### P7 -- Two callers crash on any table under 30 frames (contract B2, unchecked reader).

The G50 nulling made `coverage_pct` nullable. Two readers do not check:

`scripts/platformkit/tracking/bridge_infill.py:99`

    def _coverage(table: pd.DataFrame, sport: str) -> float:
        return float(evaluate(table, sport).coverage_pct)

`scripts/platformkit/tracking/tracklet_merge.py:234-235`

    coverage_before=float(evaluate(tracks, key, allow_legacy_undeclared=True).coverage_pct),
    coverage_after=float(evaluate(after, key, allow_legacy_undeclared=True).coverage_pct),

RAN IT (`audit_fixture2.py`), a 5-frame table:

    F. bridge_infill._coverage(5-frame table) RAISED TypeError: float() argument must be a string or a real number, not 'NoneType'

`depth_replay.py:41-42` is safe by accident -- `_values` filters `raw[field] is not None`, so a
thin table silently drops `coverage_pct`, `jump_p95` and `oob_pct` from the before/after
comparison and the replay reports on depth fields alone with no flag.

### P8 -- The `image_px` containment gate cannot change any verdict.

Its docstring claims "this gate adds a rejection, never a pass" (`tracking_schema.py` L110-111).
That is true and also understates the problem: it adds no rejection either. `image_px` is in no
sport's accepted set (`coordinate_provenance.py` L20-25), so `_validate_coordinate_space`
rejects every `image_px` table at L153-160 regardless of where the points land.

RAN IT (`audit_fixture2.py`), the same 4 rows in three configurations:

    C. image_px WITH frame dims   -> ['coordinate_contract: image_px_containment: 0.0000 of 4 declared image_px points lie inside the decoded frame, below 0.95; x/y are not source-image pixels']
    C. image_px WITHOUT frame dims-> ['coordinate_contract: rows declare coordinate_space image_px not accepted for sport basketball; a preserved detection corpus is never a scorable game']
    C. image_px fully INSIDE frame-> ['coordinate_contract: rows declare coordinate_space image_px not accepted for sport basketball; a preserved detection corpus is never a scorable game']

All three FAIL. Points fully inside the decoded frame fail too. The gate selects the error string
and nothing else. As a diagnostic message that is genuinely useful; as a gate it is decorative,
and the 103,009-row map_2d incident it was written for would have been caught by the declaration
check alone.

### P9 -- `coverage_pct`'s denominator is the emitted frames, never the clip's frames.

    n_frames = int(df["frame"].nunique())                                  # L211
    coverage = float((per_frame >= cfg["min_players"]).sum() / n_frames)   # L228

The numerator counts frames meeting the player floor; the denominator counts frames the producer
chose to emit. A producer that drops 87% of a clip is measured only on what survived. RAN IT
(`audit_fixture3.py`), frames 0-39 of a nominally 300-frame clip:

    H. 40 emitted frames of a 300-frame clip -> n_frames=40 coverage_pct=1.0 verdict=PASS

Nothing in `evaluate`'s signature carries a clip length, and `probe_media` does not return a
frame count, so there is no denominator available to fix this with today. G40's stated finding
("computed over frames that HAVE rows") is accurate against the current code. The name
`coverage_pct` still promises clip coverage.

Partial credit where due: a frame present only via a ball row IS counted in the denominator and
not the numerator, so `coverage_pct` does correctly punish player-less frames that were emitted.

### P10 -- The liveness suite cannot fail for 7 of 8 sports.

`liveness_metrics.py` L24-46: `_UNCALIBRATED` sets all five thresholds to `None`, and
`liveness_failures` skips any check with `limit is None` (L78-79). wnba, tennis, soccer,
baseball, npb, kbo and football all get `_UNCALIBRATED`. Only the `FROZEN` check binds, and it
requires `zero_step_share == 1.0` AND `stationary_track_share == 1.0` exactly, so a stream
drifting by 1e-9 escapes it. This is honestly documented in the module docstring ("Their
acceptance thresholds are therefore `None` rather than guesses") and I read it as the right call
-- a guessed threshold would be worse. Ranked here because the report still prints a
`liveness_verdict` for those sports and a reader could mistake `UNCALIBRATED` for a measurement.

### P11 -- The football ball gate cannot fail, and the report does not say so.

`tracking_harness.py:53`: `"ball_valid_min": 0.0`. The check is `ball_valid < cfg["ball_valid_min"]`
(L259), and a share is never below 0.0. RAN IT (`audit_fixture2.py`), 40 frames of football with
zero ball rows:

    E. football, ZERO ball rows -> ball_valid_pct=0.0 ball_valid=evaluated failures=[] verdict=PASS

`ball_valid` reads `"evaluated"` and the verdict is `PASS`, not `PASS_NO_BALL` -- because
`PASS_NO_BALL` (L268) requires `ball_telemetry_available is False`, which needs a sidecar, and
without one it is `None`. The 0.0 threshold is a defensible encoding of "FootballAdapter
deliberately has no ball detector" (comment at L50-51); the misleading part is that the report
labels the metric `evaluated`.

### P12 -- `_failed_report` sentinels are the best possible scores.

L160-172 sets `coverage_pct=0.0, jump_p95=0.0, oob_pct=0.0, ball_valid_pct=0.0,
median_step_distance=0.0, stationary_track_share=0.0`. For `jump_p95`, `oob_pct` and
`stationary_track_share` -- all `max` gates -- 0.0 is a perfect score, indistinguishable in any
downstream aggregate from a genuinely clean measurement. Only `passed=False` separates them.
Also: `_failed_report` never sets `insufficient_data`, so it takes the L110 default `False` even
though the report it builds has `n_frames=0`. A report with zero frames states that its data is
sufficient.

### P13 -- Unrecognized schemas and malformed sidecars raise out of `evaluate`.

L192-196 catches only `CoordinateTransformUnavailable`. `identify_tracking_schema` raises a plain
`ValueError` (L221-226) for an unknown column set, and `_producer_ball_telemetry` raises a plain
`ValueError` (L205) for a non-boolean sidecar. `CoordinateTransformUnavailable` subclasses
`ValueError`, but not the reverse, so both propagate to the caller as exceptions rather than
becoming a FAIL report. Every other failure mode in this harness produces a report.

---

## 3. What is fine

Said plainly, so the list above is not read as "everything is broken":

- `median_track_len` is a clean gate with an honest denominator and it fails closed on empty
  input. It is what actually caught the degenerate cases in my fixtures.
- The duplicate `(game_id, frame, track_id)` gate is exact, keys correctly, and fires on a single
  duplicated row (fixture L).
- `oob_pct` returns 1.0 when there are no players -- fails closed, the right direction.
- The `jump_p95 unmeasurable` guard (L257-258) closes a real hole: without it, a table of
  single-observation tracks would report `jump_p95 = 0.0` and sail through a max gate.
- `_validate_coordinate_space` is magnitude-independent on purpose and that is the correct
  design -- it is the one place in this system that cannot be fooled by rescaling pixels into
  court bounds.
- The liveness thresholds being `None` rather than guessed for uncalibrated sports is the right
  call, honestly documented.
- `ball_valid_applicable` treats a missing sidecar (`None`) as applicable, so the ball gate binds
  rather than being skipped. Fails closed.
- `_stamp` handling the empty-frame case (`coordinate_provenance.py` L32-49) is a real,
  correctly-reasoned edge case.

## 4. NOT VERIFIED

Things I could not check, and why. None of these are implied passes.

1. **Whether P5's hardcoded `"passed": False` is intentional.** There is no comment on
   `metric_local_profile.py:64` and no test I read asserts either intent. I did not open the
   G69/G72 spec that produced the file. Reported as an inconsistency, not as a bug.
2. **Whether P7's crash is reachable in production.** I proved the `TypeError` on a constructed
   5-frame table. I did not establish that `bridge_infill` or `tracklet_merge` are ever handed a
   sub-30-frame table by a real caller, which would require tracing their own callers and the
   corpus. The defect is real; its production frequency is unmeasured.
3. **No real corpus was scored.** Every number above comes from synthetic fixtures I wrote. I did
   not read any file under `data/tracking/` or `data/tracking_reports/`, so I cannot say how many
   landed reports currently carry a null-metric PASS (P1) or a `None` `jump_p95_ft_per_s` (P3).
   The code path is proven; the blast radius is not.
4. **The G48 sampling claim is read, not measured.** I read `sampling_plan` and computed the
   0.08 s vs 0.10 s spread by hand from `int(round(fps * 0.1))`. I did not probe real clips at
   24/25/30/60 fps to confirm the strides those files actually get.
5. **Register rows and the results ledger were not consulted.** The task scoped me to the four
   source files plus the contract. I do not know whether any of P1-P13 is already an open row in
   `docs/evidence/HARNESS_GAPS_2026-09-03.md` or the tracking gap ledger, so some of these may be
   known and queued rather than new.
6. **Only `test_tracking_harness.py` was run** (24 passed). I did not run
   `test_tracking_harness_g50b.py`, `test_tracking_harness_g72_metric_local.py`,
   `test_harness_additive_metrics.py`, `test_tracking_schema_coordinate_space.py` or
   `test_tracking_schema_image_px_containment.py`, so I cannot say whether any existing test
   already asserts the behaviours I flag -- in particular whether a test pins P5's `passed=False`
   as intended.
7. **`compute_liveness_metrics` reads `players.loc[steps.index, "track_id"]`** (L102) after a
   `sort_values`. I read this as correct but did not construct a duplicate-index case to prove
   the alignment holds under a non-unique index.
8. **No claim here is a quality claim about the tracker.** This audit is about whether the
   harness can detect defects, not about whether the tracker has any. A gate that cannot fail
   says nothing either way about the data it was pointed at.
