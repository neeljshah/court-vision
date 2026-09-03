# G197: harness attempted-frame coverage denominator

## Result

The harness now retains `coverage_pct` and `ball_valid_pct` as legacy,
emitted-frame-denominated fields and adds the gate metrics
`coverage_attempted_frames_pct` and `ball_valid_attempted_frames_pct`. The
new fields are `None` when no honest attempted-frame count is supplied. In
that case the harness fails closed with `attempted_frames unavailable`; it
does not substitute `frame.nunique()`.

This corrects a circular metric and makes coverage harder. It is not a moved
bar: every configured threshold is byte-identical.

## Denominators and gate

| Field | Numerator | Denominator recorded in report | Gates? |
|---|---|---|---|
| `coverage_pct` | emitted frames with at least `min_players` distinct players | `emitted_frames` | No |
| `ball_valid_pct` | emitted frames with a ball row | `emitted_frames` | No |
| `coverage_attempted_frames_pct` | emitted frames with at least `min_players` distinct players | `attempted_frames`, or `unavailable` | Yes |
| `ball_valid_attempted_frames_pct` | emitted frames with a ball row | `attempted_frames`, `not_applicable`, or `unavailable` | Yes when ball telemetry applies |

`attempted_frames` is accepted only as the explicit `evaluate(...,
attempted_frames=...)` argument or as one stable, non-null
`attempted_frames` value on every row of the input table. It must be a positive
integer at least as large as the emitted-frame count. `decoded_frames` is not
assumed to be attempted frames: G179 establishes that strided adapters can
decode more source frames than they attempt. No count is inferred from rows.

## Relationship to G179

G179 is not superseded. It corrected the daemon path: before the frozen
harness is called, `track_daemon_done._with_frame_denominator` pads a daemon
table over G179's derived evaluated-frame set. G197 corrects direct harness
scoring, where `evaluate()` previously used the emitted table's frame set as
its own denominator. This change does not edit or launch the pod daemon or
keeper. A direct table without an honest count is now explicitly unavailable
and fails closed rather than pretending its emitted frames are attempts.

## Local reconstruction from committed tables (Q7)

Construct: a committed CSV is counted when it is a complete canonical tracking
table with `frame`, `track_id`, `cls`, `x`, and `y`. Four files satisfy that
construct. The G82 `oversized_steps_above_p95.csv` and similar frame/track CSVs
are derived selected fragments, not complete emitted tables, and are excluded.
Other tracking evidence CSVs are labels, manifests, or measurements and lack
the canonical row contract.

For the **before** quantity, the old formula was reproduced exactly by passing
the emitted-frame count as the attempted count: that makes the new numerator
and denominator equal to the pre-change `n_frames = df["frame"].nunique()`.
For **after**, no table supplied `attempted_frames`, so the corrected metric is
`None`, as required. No source count was guessed.

| table | sport | rows | emitted-frame denominator | legacy coverage / ball | attempted-frame denominator | corrected coverage / ball | before -> after verdict |
|---|---|---:|---:|---|---|---|---|
| `g96_jump_flips/nyyk_720p_tracking_data.csv` | tennis | 5,333 | 2,245 | 1.0000 / 0.3755 | unavailable | None / None | FAIL -> FAIL (jump_max) |
| `g96_jump_flips/tennis_10_tracking_data.csv` | tennis | 2,103 | 880 | 1.0000 / 0.3898 | unavailable | None / None | FAIL -> FAIL (jump_max) |
| `g69_metric_local/metric_local_clean_rows.csv` | baseball | 90 | 30 | 1.0000 / 1.0000 | unavailable | None / None | PASS_METRIC_LOCAL -> FAIL_METRIC_LOCAL |
| `football_imagepx_snap/schema_sample_head30.csv` | football | 34 | not reached | 0.0000 / 0.0000 | not reached | None / None | FAIL -> FAIL (coordinate contract) |

The count is one PASS-to-FAIL and zero FAIL-to-PASS. The PASS-to-FAIL is the
expected direction: it is a previously circular direct score for which no
attempted-frame count was committed. A FAIL-to-PASS would have been alarming;
none occurred.

## A5 reader survey

The legacy names were neither removed, renamed, nor repurposed. Their values
remain emitted-frame values, and the new denominator-label fields make that
visible in every `QualityReport` JSON.

| Reader / producer | What it sees after G197 |
|---|---|
| `tracking_harness.py` | Produces unchanged legacy fields, new attempted fields and denominator labels; only the new fields gate. |
| `baseball_calib_probe.py` | Its fixed `keep` tuple still extracts the two legacy values unchanged; its `passed` output now reflects the attempted gate. |
| `evidence_page.py` | Its fixed metric list still displays legacy coverage and ball values; displayed PASS/FAIL reflects the new gate. |
| `ledger_report.py` | Its medians remain medians of legacy fields; its pass rate reflects the new gate. |
| `metric_local_profile.py` | Continues to produce its legacy emitted-frame fields; the harness wraps its early return with the attempted-frame gate and labels. |
| `track_daemon_done.py` | Still reads legacy `report.coverage_pct` into its existing daemon sidecar field; it was not edited. G179's padded path remains distinct. |
| `tracking_corpus_ab.py` | Its report JSON projection retains legacy coverage and ball fields; it receives no rename or removal. |
| `tracking/bridge_infill.py` | Its `coverage_observed` continues to read legacy `report.coverage_pct`; no changed field contract. |
| `tracking/depth_replay.py` | Its fixed `HARNESS_FIELDS` continues to contain legacy `coverage_pct`; new fields are additive. |
| `tracking/tennis_sequential_plan.py` | Its result projection continues to include legacy coverage and ball fields; it receives no rename or removal. |
| `answers/corpus_builder_v2.py` | Its report projection retains the legacy names and ignores the additive fields. |
| `teacher_student_ab.py` | Does not read a harness report: its `coverage_pct` is a join-pair percentage, semantically unrelated to G197. |
| `teacher_student_distill.py` | Does not read either harness field: it takes `pair_coverage_pct` from the teacher-student diagnosis. |
| Harness and downstream tests | Existing field fixtures/assertions retain their names; `test_tracking_harness.py` now supplies an honest fixture `attempted_frames` value for passing cases. |

The broad source survey also found many homonymous coverage variables in CLV,
ingame, progress, model, and test code. They are not harness report fields and
were not changed. This survey distinguishes them instead of treating every
`coverage_pct` spelling as a dependency.

## Threshold invariance

Local check, against `HEAD`:

```text
config_byte_identical=True
```

The compared slice is the complete `_BASKETBALL`, `_BASEBALL`,
`CONFIG_VERSIONS`, and `SPORTS` region (lines 21-59 before and after). A
`git diff --unified=0 HEAD -- scripts/platformkit/tracking_harness.py` contains
only references to existing `min_players`, `coverage_min`, and
`ball_valid_min` in the newly added scoring expression; it contains no edited
configuration-table line. Thus every bar, including every `coverage_min`, and
every `min_players` value is byte-identical.

## Tests

```text
python -m pytest scripts/platformkit/test_tracking_harness_g197.py -q
2 passed in 0.44s

python -m pytest scripts/platformkit/test_tracking_harness.py -q
24 passed in 0.90s
```

The new regression has 50 fully populated emitted frames out of 100 explicit
attempted frames. Without this change, both legacy quantities are 1.0 and the
old gate passes coverage. With the change, legacy quantities remain 1.0, the
new quantities are 0.5, and the unchanged basketball coverage gate fails.

## NOT VERIFIED

- No committed complete canonical table carried an honest attempted-frame
  count, so no real-table corrected percentage could be computed. The `None`
  result is intentional and is not a fallback.
- No pod route, pod process, daemon, keeper, video decode, model inference, or
  `run_clip.py` was launched.
- No natural post-change daemon completion was observed; daemon code and its
  existing G179 sidecar contract were deliberately left untouched.
- The committed-table construct covers complete canonical tracking CSVs only;
  it does not claim to score labels, manifests, selected fragments, or
  non-tabular evidence artifacts.
