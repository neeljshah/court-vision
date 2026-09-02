# G61 unversioned pod tracking code

## Scope

This lane reproduced the drift check before changing master, searched the pod
for import callers using read-only `grep`, and made no pod write, deployment,
restart, kill, or signal. Master catches up to the pod in this row.

## Reproduced premise

Command run before any source edit:

```text
python scripts/platformkit/tracking/pod_drift.py --repo .
```

Output:

```text
== pod drift (tracking-number producer modules)
  DIFFERS (6)
    domains/baseball/tracking/geometry.py
    domains/basketball/tracking/line_calibration.py
    domains/football/tracking/clustering_diagnostic.py
    domains/football/tracking/geometry.py
    domains/tennis/tracking/court_lines.py
    scripts/platformkit/tracking/__init__.py
  POD-ONLY (4)
    domains/baseball/tracking/pitch_view_gate.py
    scripts/platformkit/tracking/basketball_floor_gate.py
    scripts/platformkit/tracking/tennis_keypoint_train.py
    scripts/platformkit/tracking/tennis_vertical_probe.py
  MASTER-ONLY (1)
    scripts/platformkit/tracking/pod_drift.py
```

The four POD-ONLY paths and baseball geometry are the five G61 dispositions.
The five additional DIFFERS paths are recorded above but are outside this row.

## Caller audit and disposition

The pod was searched once with this read-only command. A source file's own
match, a docstring, and a `_retired/` text mention do not count as a caller.

```text
grep -RIn --include=*.py -e pitch_view_gate -e basketball_floor_gate \
  -e tennis_keypoint_train -e tennis_vertical_probe \
  -e domains.baseball.tracking.geometry -e detect_pitch_geometry \
  /workspace/nba-ai-system
```

| Pod path | What it does | Pod caller evidence | Duplicate on master | Outcome |
|---|---|---|---|---|
| `domains/baseball/tracking/pitch_view_gate.py` | Classifies a baseball frame with default green evidence and opt-in hue/geometry evidence. | `scripts/platformkit/baseball_pitchview_g11b.py:19` and `baseball_pitchview_g11c.py:13` import `classify_pitch_view`. | No module duplicate; only the legacy green predicate existed in `geometry.py`. | LANDED at the same master path; `test_pitch_view_gate.py` passes. |
| `domains/baseball/tracking/geometry.py` | Finds a grass-bounded mound and its lateral pixel scale after a field precondition. | The baseball adapter imports it at `adapter.py:44-46`; `baseball_pitchview_g11b.py:18`, `baseball_pitchview_g11c.py:12`, `baseball_landmark_census.py:20`, and `tracking/baseball_scale_probe.py:18` also import it. | It is the divergent version of the existing master module, not a second module. | LANDED additively with `gate_mode`; the default preservation test passes. |
| `scripts/platformkit/tracking/basketball_floor_gate.py` | Learns a court-color mask and tags observations outside it as `nonfloor`. | No pod import match. | No current master module implements this per-frame mask and recoding. | DEAD CODE recorded; not landed. The only copy is on the read-only pod, so deletion requires a separately authorized pod operation. |
| `scripts/platformkit/tracking/tennis_keypoint_train.py` | Trains and evaluates a ResNet heatmap student from tennis pseudo-labels. | No pod import match; its only match was its own evidence-path literal. | No current master trainer or `TennisKeypointNet` implementation. | DEAD CODE recorded; not landed. The only copy is on the read-only pod, so deletion requires a separately authorized pod operation. |
| `scripts/platformkit/tracking/tennis_vertical_probe.py` | Counts production and raw vertical tennis-line segments to diagnose a rejection cause. | No pod import match; its own run docstring and `_retired/` text reference are not imports. | Stale duplicate of `scripts/platformkit/_retired/tennis_vertical_probe.py`; the pod version retains the old Hough indexing while the retired copy handles both shapes. | DEAD CODE recorded; not landed. The only copy is on the read-only pod, so deletion requires a separately authorized pod operation. |

## Landing and tests

The initially named saved geometry source was absent from
`docs/evidence/tracking/pod_only_modules_2026-09-02/`. That would fail A7 if it
were cited as existing evidence. The exact source was therefore read from the
pod without mutation and restored at
`docs/evidence/tracking/pod_only_modules_2026-09-02/baseball_geometry_POD_VERSION.py`.
The remote and landed geometry MD5 are both
`d48616d8a0063de5b3a18c4dcf489964`. The remote and landed pitch-gate MD5 are
both `694124ba065833abe11ffb22e1cce3db`.

Per-file tests only:

```text
python -m pytest domains/baseball/tracking/test_pitch_view_gate.py -q
2 passed in 1.04s

python -m pytest domains/baseball/tracking/test_geometry.py -q
1 passed in 0.86s
```

`test_default_mode_calls_dominant_green_and_matches_legacy_output` constructs a
pitch-view frame, spies on `dominant_green`, asserts that the default path does
not call the opt-in classifier, and compares every `PitchGeometry` output field
with the pre-change default calculation. No default gate value changed.

## Contract B self-check

| Check | Result |
|---|---|
| B1 circular metric | Not applicable: this is a provenance disposition, with no scored metric or excluded rows. |
| B2 non-additive schema | Pass: no data schema, field, or reader changed. |
| B3 fall-through loss | Pass: default geometry remains its prior green precondition; opt-in selection is explicit. |
| B4 re-claim loop | Not applicable: no claim workflow changed. |
| B5 pre-verification deploy | Pass: no pod mutation occurred. |
| B6 orphans | Pass: no master module was moved or retired; the three unused pod modules were not landed. |
| B7 head-slice evidence | Not applicable: no render or row sample is claimed. |
| B8 self-fit as independent | Not applicable: no fitted or scored result is claimed. |
| B9 degenerate denominator | Not applicable: no metric denominator is claimed. |
| B10 moved bar | Pass: no harness threshold or gate value changed. |

## NOT VERIFIED

- The original claim that all five source snapshots already existed before this
  lane is not independently verified: the geometry snapshot was absent at
  intake and was recovered with a read-only pod source read. The replacement
  path exists at report time, satisfying A7 for this memo.
- The three dead modules remain on the pod because this lane is prohibited from
  changing it. Their lack of callers is a point-in-time import search, not a
  statement that no human can invoke them manually.
- The five non-G61 DIFFERS paths from the reproduced drift output were not
  classified or changed.
- No deployment, daemon restart, or live tracking run was authorized or made.
