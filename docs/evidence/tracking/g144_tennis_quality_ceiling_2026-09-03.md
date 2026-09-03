# G144: Tennis quality ceiling

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), section A including
A7 and section B. Verdict: **CLOSED AT LIMIT**. This is a read-only census:
no threshold, gate, verdict rule, coordinate contract, source table, pod file,
process, or deployment was changed.

## Census and unchanged quality input

At `2026-09-03T03:06:07.246119+00:00`, one exhaustive read of
`/workspace/nba-ai-system/data/tracking/*/tracking_data.csv` found 215 unique
source-table directories. Eight reached the pre-existing jump-statistic
eligibility definition and all eight route to tennis. The other 207 are named
in [the census artifact](g144_ceiling/quality_census.json): 135 not all
`court_feet`, 53 missing required columns, 7 empty, 1 insufficient-frame, and
11 unknown sport. Quality failure never selected the eight.

The quality input is the daemon's unchanged decoded-frame procedure: validate
the independent video-frame denominator, add non-player/non-ball rows for each
decoded but un-emitted frame, then run the unchanged tennis bars (coverage
`>= 0.90`, median track length `>= 3`, oob `<= 0.08`, ball-valid `>= 0.20`,
and `jump_p95 <= 8.00`). The full raw rows, input hashes, exact thresholds and
denominator status are in
[quality_census.json](g144_ceiling/quality_census.json).

`ffprobe -count_frames` could not finish through the 30-second read-only
transport cap. A distinct, read-only `-count_packets` measurement matched the
container `nb_frames` for every video, and reproduces the already persisted
decoded counts for `tennis_07` (24,051) and `tennis_08` (24,055). This is a
documented bounded fallback, not a changed denominator.

## Every eligible tennis table (`n = 8`)

`coverage` and `ball` use decoded frames. `jump` is the unchanged pod
`jump_p95` gate statistic. `tennis_08` fails closed before denominator padding;
its displayed coverage is the production sidecar value, 0.0000.

| Table | Coverage | Det/frame | Median track | OOB | Ball valid | Zero step | Jump p95 | Verdict | Failed gates |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| g89_tennis_09 | 0.1633 | 1.22 | 98.5 | 0.2851 | 0.0530 | 0.0000 | 1.50 | FAIL | coverage, oob, ball-valid |
| g89_tennis_10 | 0.1213 | 1.17 | 68.0 | 0.0682 | 0.0473 | 0.0000 | 1.56 | FAIL | coverage, ball-valid |
| g89_tennis_nyYk2nPZAwY_720p | 0.0467 | 1.06 | 65.0 | 0.0610 | 0.0175 | 0.0000 | 1.75 | FAIL | coverage, ball-valid |
| tennis_06 | 0.0059 | 1.01 | 1.0 | 0.1773 | 0.0024 | 0.0000 | 3.46 | FAIL | coverage, median-track, oob, ball-valid |
| tennis_07 | 0.1216 | 1.17 | 66.5 | 0.1744 | 0.0532 | 0.0000 | 2.03 | FAIL | coverage, oob, ball-valid |
| tennis_08 | 0.0000 | 2.51 | 94.0 | 0.2022 | 0.5181 | 0.0000 | 1.70 | FAIL | decoded-frame-denominator, oob |
| tennis_3x3eEWCZmWQ | 0.0042 | 1.01 | 101.0 | 0.0000 | 0.0027 | 0.0000 | 24.37 | FAIL | coverage, jump-p95, ball-valid |
| tennis_nyYk2nPZAwY | 0.0067 | 1.01 | 160.0 | 0.0719 | 0.0040 | 0.0000 | 19.12 | FAIL | coverage, jump-p95, ball-valid |

**Pass/fail count: 0 PASS, 8 FAIL.** `zero_step_share` blocks none. There is
no hidden PASS from the direct-CSV metric: that shortcut would discard decoded
but un-emitted frames and is not the daemon verdict input.

## Gates ranked by tables blocked

| Rank | Gate | Tables blocked | Tables |
|---:|---|---:|---|
| 1= | coverage | 7 | all except tennis_08 |
| 1= | ball-valid | 7 | all except tennis_08 |
| 3 | oob | 4 | g89_tennis_09, tennis_06, tennis_07, tennis_08 |
| 4= | jump-p95 | 2 | tennis_3x3eEWCZmWQ, tennis_nyYk2nPZAwY |
| 4= | decoded-frame denominator | 1 | tennis_08 |
| 4= | median track length | 1 | tennis_06 |

The lead is a tie. Coverage is the first actionable diagnosis because it is a
production denominator property; ball-valid is co-leading but its labelling
branch is already closed, so it is not an honest target for more label work.

## Three evenly distributed coverage explanations

The coverage decision set is the seven tables above. Ranks 1, 4, and 7 were
selected before visual inspection, using each selected table's largest internal
un-emitted interval; the exact frames and observations are committed in
[render_checks.csv](g144_ceiling/render_checks.csv), rather than a head slice.

- `g89_tennis_09`: 1,226 emitted frames out of 7,507 (0.1633), including an
  826-frame gap from 5072 to 5898; midpoint frame 5485 is a crowd/scoreboard
  shot, so the frozen no-non-play-classifier denominator charges it as unsolved.
- `tennis_06`: 141 of 24,084 (0.0059), with a 3,272-frame gap from 20062 to
  23334; midpoint 21698 is a bench/replay-style split screen and is likewise
  charged as unsolved rather than a missed on-court player pair.
- `tennis_nyYk2nPZAwY`: 160 of 24,024 (0.0067), with a 2,726-frame gap from
  22 to 2748; midpoint 1385 is a full-screen shot-quality graphic overlay.
  It establishes the same denominator mechanism at the opposite end of the
  decision set.

## Honest ceiling

At the frozen gate the ceiling is **0 of 8 PASS**. Seven tables fail
ball-valid, and G92/G98 changed 0 of 109 reviewed labels while G102/G118's
temporal lower bound was 68.1%, below its fixed 75.0% bar; G118 therefore
closed that branch. Those seven cannot be counted as passable through more
labelling.

The remaining table, `tennis_08`, is not a loophole: it currently fails closed
because emitted frame 24290 exceeds the independently measured 24,055 decoded
frames. If that fixable index defect alone were repaired while retaining its
10,589 current emitted identities, its coverage would be
`10,589 / 24,055 = 0.4402`, still below 0.90. OOB repair also cannot create a
PASS. Thus no table can pass under the unchanged gate by fixing only failures
that are presently evidenced as fixable.

This is not an argument to lower a bar. An independently established non-play
denominator or a new source population would require its own adjudication; it
is not counted in this ceiling.

## VERIFIER_CONTRACT self-check

### A

- **A1:** No code was added, so no new per-file test exists.
- **A2:** The headline is reproducible from `g144_ceiling/quality_census.json`:
  eight unique table names, zero `PASS` verdicts, seven coverage failures,
  seven ball-valid failures, four oob failures, two jump failures, and one each
  of median-track and decoded-frame-denominator failures.
- **A3:** The coverage renders use evenly spaced ranks 1, 4, and 7 of the
  ordered seven-table decision set, not leading frames.
- **A4:** Unit is one source-table directory; the eight table names and their
  eight CSV SHA-256 values are unique.
- **A5:** Evidence only; no changed field has a reader.
- **A6:** This lane makes an explicit-path evidence commit in `track-a6`; no
  archive landing, pod deployment, or restart is attempted.
- **A7:** Before commit, every repository evidence path named here and every
  three remote source-video path named by `render_checks.csv` is checked to
  exist.

### B

- **B1:** Clear. Eligibility was enumerated before quality values; all 215
  source tables have a named classification.
- **B2:** Clear. No schema, field, reader, or code changed.
- **B3:** Clear. Empty, missing, non-court-feet, insufficient and unknown
  inputs remain named census classes; `tennis_08` fails closed on explicit
  malformed evidence, not absence.
- **B4:** Clear. No claim, queue, retry, or ownership path changed.
- **B5:** Clear. Pod commands only read CSVs, source videos, and code; nothing
  was copied to, written on, restarted, or killed on the pod.
- **B6:** Clear. No module, import, test, or command moved or retired.
- **B7:** Clear. Census is exhaustive and visual ranks span the decision set.
- **B8:** Clear. No fitted residual is claimed.
- **B9:** Clear. The denominator is distinct table directories, never rows,
  frames, track IDs, or historical outcomes.
- **B10:** Clear. The pod's frozen threshold map is recorded unchanged in the
  census artifact; no bar or coordinate contract changed.

## NOT VERIFIED

- A completed `ffprobe -count_frames` reproduction: it exceeded the fixed
  read-only transport cap. Packet count equals container `nb_frames` for all
  eight and agrees with two persisted decoded counts, but is explicitly the
  bounded fallback.
- Whether an independently labelled non-play classifier can make the coverage
  numerator/denominator meaningful without moving the gate. It was not made or
  implied here.
- Any repair of oob, jump, median-track, decoded-frame index, ball detection,
  or source acquisition; this row measures existing quality only.
- Whether the seven ball-valid failures can be solved by a mechanism other than
  the closed written-criterion and temporal-label branches.
