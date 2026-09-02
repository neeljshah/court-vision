# G96: G88 jump-flip adjudication

Date: 2026-09-02. Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md,
including A7 and every B condition. This is a read-only measurement: no harness,
bar, verdict, coordinate contract, deployment, or pod process was changed.

## Recommendation

**Leave G88 retracted: both maxima are genuinely modal-stride-adjacent and nyYk's pixels disprove a player teleport, but the required tennis_10 original-frame render cannot be produced from the pruned source, so a reinstatement would not satisfy the mandatory two-table eye check.**

This is therefore **NOT VALIDATED**, rather than evidence of an implementation
bug. It does not reinstate, re-land, or deploy G88.

## Durable inputs and pairing definition

The two read-only pod tables were copied verbatim to the durable evidence
directory. Both declare only coordinate_space=court_feet.

| Table | Durable copy | SHA-256 |
|---|---|---|
| tennis_10 | g96_jump_flips/tennis_10_tracking_data.csv | 95306DBA89D198F27DB2BEC53A54A32923552A8D6D46A0CC37C4201BB8F8C445 |
| nyYk 720p | g96_jump_flips/nyyk_720p_tracking_data.csv | 9232E98DEB96D0BC6128A1E044313DB7D031F6BDDBB966FD07B4F6AB2CFB5F29 |

For each cls=player row, rows are sorted by track_id, frame; a pair is eligible
exactly when its positive same-track frame delta equals the unique most-common
positive frame delta. No pair is selected by its displacement or by the harness
verdict. This independently reproduces G88's stated adjacency definition.

## Full modal-stride distributions

| Table | Player rows | Positive pairs | Modal stride | Eligible pairs | >8 ft | >20 ft |
|---|---:|---:|---:|---:|---:|---:|
| tennis_10 | 1,760 | 1,738 | 2 frames (1,726 occurrences) | 1,726 | 3 | 3 |
| nyYk 720p | 4,490 | 4,436 | 5 frames (4,396 occurrences) | 4,396 | 12 | 3 |

The only non-modal positive gaps are 10 pairs at delta 4 and 2 at delta 6 for
tennis_10, and 36 pairs at delta 10 and 4 at delta 15 for nyYk. Neither mode
is tied.

| Table | min | p01 | p05 | p10 | p25 | p50 | p75 | p90 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| tennis_10 (ft) | 0.003128 | 0.013013 | 0.030274 | 0.048854 | 0.112154 | 0.315559 | 0.718076 | 1.224252 | 1.554966 | 2.792705 | 45.213780 |
| nyYk 720p (ft) | 0.000617 | 0.015110 | 0.040239 | 0.062667 | 0.147450 | 0.349886 | 0.723805 | 1.278136 | 1.734368 | 3.208030 | 56.389551 |

Both tails are sparse rather than broad: 3 of 1,726 and 12 of 4,396 eligible
pairs exceed 8 ft. The maxima are not percentile artefacts.

## Hand-verified largest-pair row dumps

Every row below declares court_feet. The listed delta equals that table's modal
stride, checked directly from both frame numbers.

### tennis_10: modal stride 2

| rank | track_id | frame from -> to | x,y from | x,y to | delta | step ft |
|---:|---:|---|---|---|---:|---:|
| 1 | 21 | 7156 -> 7158 | (24.139399, 46.666195) | (-15.970135, 25.797289) | 2 | 45.213780 |
| 2 | 14 | 4226 -> 4228 | (82.113876, 6.822009) | (40.708973, -7.137815) | 2 | 43.694882 |
| 3 | 4 | 1016 -> 1018 | (82.209686, 20.687403) | (105.737640, 34.410801) | 2 | 27.237773 |
| 4 | 10 | 2978 -> 2980 | (83.762482, 32.015415) | (78.779640, 32.200100) | 2 | 4.986263 |
| 5 | 8 | 2308 -> 2310 | (86.060699, 21.832207) | (81.925430, 22.357286) | 2 | 4.168472 |

### nyYk 720p: modal stride 5

| rank | track_id | frame from -> to | x,y from | x,y to | delta | step ft |
|---:|---:|---|---|---|---:|---:|
| 1 | 30 | 20295 -> 20300 | (71.380791, 46.967636) | (127.734909, 48.966347) | 5 | 56.389551 |
| 2 | 14 | 11725 -> 11730 | (105.957291, 38.800690) | (112.721420, 61.676193) | 5 | 23.854604 |
| 3 | 14 | 11895 -> 11900 | (127.698830, 49.385956) | (106.854530, 38.835934) | 5 | 23.362101 |
| 4 | 14 | 11755 -> 11760 | (113.288574, 62.096119) | (128.681305, 49.740665) | 5 | 19.738120 |
| 5 | 14 | 11720 -> 11725 | (88.451477, 32.736847) | (105.957291, 38.800690) | 5 | 18.526297 |

Thus G88 is not pairing across a non-modal gap on either flip: the largest pair
has delta 2 of 2 on tennis_10 and delta 5 of 5 on nyYk.

## Eye check

g96_jump_flips/nyyk_720p_largest_pair_track30_f20295_f20300.jpg is the
side-by-side source-frame render for nyYk's largest pair (SHA-256
F8A8465BB5CBA3A06A2BE62F72AD080ACFD6F02F7EBAEA34A09C5DAA442433A5).
I looked at it: source frames 20295 and 20300 are a static wide shot five
source frames apart; the two players remain in nearly the same image locations
and no player crosses the court. The 56.389551-ft change is therefore not a
visible player movement.

The retained CSV has no bbox, foot-pixel, or image-space point columns, so the
render labels the exact track_id=30 source rows and their stored court points
without inventing a pixel box. This retained-table limitation is explicit in
the image itself.

The original 1,920x1,080, 7,252-frame tennis_10 source named by G57 is absent
from both the pod and local corpus. Three distinct public-source retrieval paths
failed, and the surviving public stream is a 6,145-second 23.98-fps re-encode,
not the original short 25-fps clip; it cannot be substituted for frames 7156
and 7158. Therefore no tennis_10 frame-pair render exists and the required
two-table eye check is incomplete.

## Already-failing-table signature

A read-only inspection of the already failing G89 tennis_09 pod table found the
same coordinate-tail signature: unique modal stride 2, 2,430 eligible pairs,
19 above 8 ft, and a 50.791508-ft maximum (p50 0.350912, p95 1.501242,
p99 4.073622). Its extant harness verdict is FAIL on oob 0.29 > 0.08. This
supports the statement that sparse oversized modal-stride coordinate steps are
not unique to the two former PASS tables, but the G89 tennis_09 source table
was not pulled because the spec authorizes exactly the two flipped-table pulls.

## Contract self-check

- **A7:** At check time, every repository evidence path named in this memo
  exists: this memo; both durable table copies; the nyYk render; G96 spec;
  VERIFIER_CONTRACT.md; G88's memo; G82's memo; RESULTS_LEDGER.md; and
  TRACKING_GAPS_2026-09-01.md. The absent tennis_10 source frame pair is named
  only as a NOT VERIFIED absence, never silently treated as evidence.
- **B1:** The excluded set is named before reading displacement: all pairs
  whose positive frame delta is not the unique modal stride. No failing row or
  large step is excluded.
- **B2:** No schema, field, reader, or code changed.
- **B3:** No gate, quarantine, or missing-evidence path changed.
- **B4:** No claim, queue, retry, or ownership path changed.
- **B5:** The pod was read-only: two CSV pulls and read commands only; no copy
  to the pod, deploy, restart, kill, or re-track occurred.
- **B6:** No module was moved or retired, and no code was added.
- **B7:** The top-five dumps and maximum-pair render are the tail checks
  explicitly required by G96, not a start-of-set sample or broad visual-rate claim.
- **B8:** No fitted model or self-fit comparison is claimed.
- **B9:** The denominator is distinct same-track modal-stride row pairs
  (1,726 and 4,396), counted once per ordered adjacent row pair.
- **B10:** tracking_harness.py, every bar, every verdict, and the coordinate
  contract are untouched.

## NOT VERIFIED

- The tennis_10 largest-pair eye check and required side-by-side render: the
  exact original footage is gone and the available public re-encode is not
  frame-compatible.
- A pixel-location mark for track_id=30: the retained nyYk CSV has no bbox or
  source-foot-point field. The exact source rows and frames are marked instead.
- The G89 tennis_09 tail calculation is a read-only pod observation only; its
  raw table was not copied because this spec permits exactly two table pulls.
- No focused test was run because no source code was added; a full test suite
  was not run.
