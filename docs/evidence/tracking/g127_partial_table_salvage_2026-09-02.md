# G127 Partial-table salvage

**Verdict: CLOSED AT LIMIT.** The 68 historical adapter `thin` outcomes that
G124 recorded with 5--499 rows were scored read-only with the current pod
harness. This memo follows [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md),
including A7 and section B. No tracking was rerun and no stored verdict,
ledger row, threshold, coordinate contract, daemon, source, or pod process was
changed.

## Premise, population, and preservation limit

G124's premise holds in the fresh read: the live ledger has 413 lines and has
**68** historical `thin` adapter outcomes with recorded rows in the inclusive
5--499 range. The complete outcome-level capture is
[outcome_scores.csv](g127_salvage/outcome_scores.csv). It is deliberately
one row per historical ledger outcome, not one per current game path.

That distinction changes the answer. The 68 outcomes now resolve to only
**20 distinct current CSV paths**. Only **3/68 outcomes** still have a current
CSV whose row count equals its historical ledger count; the other 65 current
CSV contents cannot establish what the old partial output contained because
they have been replaced or otherwise changed. G124 warned that these current
paths are mutable; treating their new, often much larger, outputs as the old
5--499-row tables would turn a preservation failure into a false salvage
claim.

The headline below therefore has two explicit scopes:

| Scope | What it answers | Count |
|---|---|---:|
| All 68 historical outcomes, scored against their current path read-only | What the current artifact at each historical path yields today | 68 outcomes / 20 distinct paths |
| Identity-preserved partial outputs | What can still be attributed to a historical 5--499-row outcome by matching its recorded row count | 3 distinct tables |

## Current-artifact frame and verdict results

The frame count is the raw distinct `frame` count in the CSV before calling the
harness. This matters because the harness returns zero frames after a
coordinate-contract short circuit. The full raw-frame distribution is in
[frame_distribution.csv](g127_salvage/frame_distribution.csv), reconstructed
from the 68 outcome rows rather than from row counts.

| Frame band | Historical outcomes | Distinct current paths |
|---|---:|---:|
| 0 | 1 | 1 |
| 1--29 | 0 | 0 |
| 30--59 | 0 | 0 |
| 60--89 | 0 | 0 |
| 90--119 | 2 | 2 |
| 120--159 | 3 | 1 |
| 160 or more | 62 | 16 |
| **Total** | **68** | **20** |

The current harness distribution is:

| Current-harness result | Historical outcomes | Distinct current paths |
|---|---:|---:|
| `INSUFFICIENT_DATA` | 1 | 1 |
| Coordinate-contract rejection | 60 | 14 |
| Reaches a real verdict | 7 | 5 |
| `PASS` or `PASS_NO_BALL` | 0 | 0 |

All seven real verdicts are `FAIL`; none is a harness pass. The additive
source for these counts is [verdict_distribution.csv](g127_salvage/verdict_distribution.csv).

Under G107's unchanged definition, **7/68 outcome entries** reach the
modal-stride jump calculation. They are only **5 distinct current table
paths**, because `tennis_06` occupies three old ledger outcomes. This is not
seven new independent tables and must not be added to G109's eligible-table
denominator. Of the identity-preserved historical partial outputs, **3/3**
are jump-gate eligible, but all three return `FAIL`; this row does not alter
G109's system census or any stored adjudication.

## What is actually salvageable

The three row-count-matching partial CSVs are `tennis_3x3eEWCZmWQ` (266 rows,
101 frames), `tennis_nyYk2nPZAwY` (415 rows, 160 frames), and `tennis_08`
(228 rows, 93 frames). Each reaches a real current harness verdict and each
fails it: the two larger tables fail the unchanged jump statistic, while
`tennis_08` fails out-of-bounds and jump checks. Thus **3 tables are still
scoreable and source-retained, but 0 are usable as passing tracking outputs**.

No identity-preserved table is near the 30-frame floor: the closest is 93
frames. This does not make these short tables trustworthy; it only means this
row does not have a floor-adjacent result to mistake for a reliable pass.
The ceiling remains strict: a 5--499-row table can produce a plausible metric
for the wrong reason, and no G127 result changes G80's 30-frame guard or
upgrades a `FAIL` into a stored verdict.

## Source retention and content check

Using G116's filename convention, source presence was checked read-only in
`data/footage_corpus/`, `data/videos/`, and `data/footage_bridge/`; a ledger
claim was not used as proof. The outcomes and exact source-presence
denominators are in [source_retention.csv](g127_salvage/source_retention.csv).
All **3/3** identity-preserved and jump-eligible partial tables retain a
matching corpus source. That is a focused retention rate, not a revision of
G116's overall 73/199 result.

Per the required eye check, the header plus first and last rows of all three
identity-preserved tables were opened. Their physical CSV line counts equal
the recorded data-row counts, and their rows declare `court_feet`; the
checked source sizes and content check are retained in
[eye_check.csv](g127_salvage/eye_check.csv). This is table-content inspection,
not a claim about the historical footage timeline.

## NOT VERIFIED

- Historical frame counts and current-harness verdicts for the other 65
  outcomes: their current path has a different row count, so its current
  content is not evidence of the old partial artifact.
- Byte-identical historic source identity for the three retained sources;
  presence is re-checkability, not a historical checksum.
- Any positive quality conclusion from the three scoreable partials: all
  currently fail, and no stored verdict was changed.
- Any increase to G109's unique eligible-table denominator: duplicate ledger
  outcomes and re-tracked current paths are not independent tables.

## VERIFIER_CONTRACT self-check

### A

- **A1:** No code was added, so no new per-file test exists.
- **A2:** The 68 outcome rows sum to the frame and verdict distributions; the
  three matching rows recompute directly from the retained outcome table.
- **A3:** No render metric is claimed. This is an exhaustive 68-outcome read,
  and all three identity-preserved outputs were opened.
- **A4:** Counts distinguish 68 historical outcomes from 20 distinct current
  paths and from 3 identity-preserved tables; duplicated `tennis_06` outcomes
  are never treated as independent jump tables.
- **A5:** Evidence only; no field, schema, or reader changed.
- **A6:** This lane makes an explicit-path evidence commit in `track-a5`; no
  archive landing, ledger/register append, deployment, or pod copy was done.
- **A7:** Before commit/report, every repository evidence path named by this
  memo was checked to exist: this memo, all five G127 derived CSVs, G124,
  G116, G107, G109, `tracking_harness.py`, and `VERIFIER_CONTRACT.md`.

### B

- **B1:** Clear. All 68 ledger outcomes are retained, including coordinate
  rejections, the insufficient table, replacements, and duplicates.
- **B2--B6:** Clear. No schema, gate, claim/retry behavior, deployment,
  module, import, or test changed.
- **B7:** Clear. The calculation enumerates every G124 5--499 outcome; the
  content check opens all three attributable outputs rather than a head slice.
- **B8--B9:** Clear. This is direct artifact inspection by named historical
  outcome and separately named current path, not a fitted metric or recycled
  track-ID denominator.
- **B10:** Clear. No harness threshold, gate, coordinate contract, or stored
  verdict moved.
