# G107: jump-statistic policy measurement

Date: 2026-09-02. Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`,
including section A (especially A7) and every section B condition. Verdict:
**NOT VALIDATED**. This is a read-only policy measurement. It does not change
`tracking_harness.py`, any bar, any verdict, the coordinate contract, any pod
file, or any pod process.

## Pre-registered rule, before the first metric

The protocol was committed before the pod measurement as
`g107_policy/G107_PREREGISTRATION.md` at `c01e35eeef3ece76edded94c626e3f18cb3b37a7`.
It fixes the population, modal-stride pairing, sport bars, all six candidate
rules, the eligible-report definition, the two known-defect disqualification
rule, and the recommendation rule. No candidate or bar was added, removed, or
altered after the snapshot.

An eligible report has at least 30 distinct frames, all rows in `court_feet`,
usable player `track_id`, `frame`, `x`, and `y`, and a unique positive modal
same-track stride with at least one pair at that stride. Coordinate-contract
rejections, `INSUFFICIENT_DATA`, metric-local/non-court-feet tables, missing
required fields, and no/tied modal strides are named exclusions, not filtered
on a displacement or a verdict.

## Read-only pod snapshot and denominator

The canonical pod corpus was the one CSV per source directory at
`/workspace/nba-ai-system/data/tracking/*/tracking_data.csv`, read once. It
contained **193 total reports**. Only **6 reports reach the jump statistic**;
the required eligible denominator is therefore **6**, not 193 and not the two
current PASS reports. This is below the required minimum of 10, so no policy
can be validated or landed from this snapshot.

| Status | Reason | Reports |
|---|---|---:|
| Eligible | reached modal-stride jump calculation | 6 |
| Excluded | non-court-feet / coordinate-contract short circuit | 129 |
| Excluded | missing required columns / short circuit | 47 |
| Excluded | fewer than 30 frames / INSUFFICIENT_DATA | 10 |
| Excluded | unknown sport prefix | 1 |
| Total | canonical pod raw-table corpus | 193 |

The complete, per-source snapshot (including SHA-256, harness reconstruction,
eligibility reason, all candidate inputs, and candidate flags) is
`g107_policy/pod_table_snapshot.csv` (SHA-256
`1AE70D0EE9AF07FD047A68C762FD338664F9459158FCD709B6A9789B7B91C171`).
`g107_policy/eligibility_census.csv` is the tabulated denominator above.

`scripts/platformkit/a3_artifacts/.../tracking_data.csv` files were not added:
they are noncanonical experiment artifacts outside the raw corpus and include
copies of current tables. Counting them would recycle report units and violate
the denominator rule.

## Candidate results on the eligible denominator

All candidates use each table's unique modal positive same-track stride and
the unchanged sport bar (tennis 8 ft here). Current reconstructed verdicts are
two PASS and four FAIL. Candidate impact means replacement of the legacy jump
gate while retaining the table's other current failures. The full deterministic
aggregation is in `g107_policy/candidate_summary.csv`.

| Candidate | Fixed rule | PASS-to-FAIL / eligible | FAIL-to-PASS / eligible | Candidate failures | Warnings | G96 nyYk 56.389551 ft | G82 basketball 16 real oversized steps | Status |
|---|---|---:|---:|---:|---:|---|---|---|
| C0 | modal-stride p95 > existing bar | 0 / 6 | 0 / 6 | 0 | 0 | No: p95 1.734368 < 8 | No: G82 raw p95 2.160134 < 6 | Disqualified |
| C1 | modal-stride p99.9 > existing bar | 2 / 6 | 0 / 6 | 5 | 5 | Yes: 17.037303 > 8 | Not verified: G82's durable table records p95/max and the 16 events, not p99.9; it cannot be credited with detection | Disqualified (does not establish both checks) |
| C2 | fifth-largest pair > existing bar | 1 / 6 | 0 / 6 | 2 | 2 | Yes: 12 pairs > 8 | Yes: 16 / 35,188 pairs in G82 exceed the 6-ft basketball bar | Eligible candidate, but n=6 |
| C3 | count of pairs > existing bar >= 5 | 1 / 6 | 0 / 6 | 2 | 2 | Yes: count 12 | Yes: count 16 | Eligible candidate, but n=6 |
| C4 | rate of pairs > existing bar >= 0.50 percent | 0 / 6 | 0 / 6 | 3 | 3 | No: 12 / 4,396 = 0.272975 percent | No: 16 / 35,188 = 0.0455 percent | Disqualified |
| C5 | max > bar WARNING; FAIL only at C4 rate | 0 / 6 | 0 / 6 | 3 | 5 | Yes: WARNING, max 56.389551 > 8 | Yes: WARNING because max exceeds the 6-ft bar | Eligible candidate, but n=6 |

C2 and C3 are intentionally equivalent count formulations. C1 is not
credited from an inference about a percentile that G82 did not retain; that is
an explicit evidence gap rather than a silently favorable result.

The six per-table candidate inputs are: `g89_tennis_09` (current FAIL, 19 / 2,430
above 8 ft), `g89_tennis_10` (current PASS, 3 / 1,726),
`g89_tennis_nyYk2nPZAwY_720p` (current PASS, 12 / 4,396), `tennis_08`
(current FAIL, 0 / 120), `tennis_3x3eEWCZmWQ` (current FAIL, 1 / 116), and
`tennis_nyYk2nPZAwY` (current FAIL, 1 / 190). These exact values and each
source hash are in the snapshot; none was selected by its candidate result.

## Known-defect checks

G96 establishes that nyYk's 56.389551-ft modal-stride maximum is a real bad
coordinate, not a player teleport or pairing artefact. G82 establishes that
all 16 / 16 basketball 10--29-ft oversized steps are above a 2.160134-ft p95,
at 16 / 35,188 = 0.0455 percent. C0 misses both; C4 misses both; C1 cannot
establish the G82 p99.9 result from retained evidence. C2, C3, and C5 flag both
by their fixed rules. C5's flag is deliberately a warning rather than a table
FAIL when the rate bar is not reached.

## Recommendation

**Do not change or deploy a jump gate now.** The live pod supplies only 6
eligible reports, below the pre-registered minimum of 10. If a fresh
read-only pod snapshot reaches that denominator, C5 is the pre-registered
leading policy to remeasure: retain a modal-stride max WARNING above the
existing sport bar and use the 0.50-percent rate only for a verdict. That keeps
the confirmed sparse coordinate defects visible without letting one maximum
alone decide the verdict. This is a recommendation for a later adjudication,
not an implementation instruction.

## VERIFIER_CONTRACT self-check

### A

- **A1:** No source code or test was added, so there is no new per-file test
  for a verifier to rerun in MASTER.
- **A2:** The candidate summary was independently recomputed from the committed
  per-table snapshot after capture; its six eligible rows reproduce the table
  above.
- **A3:** No render or visual evidence is used. G96's decisive eye check is
  cited, not repeated.
- **A4:** The metric unit is a distinct canonical source-table directory. The
  6 eligible directories have 6 distinct source SHA-256 values; no artifact
  copy outside `data/tracking` is counted.
- **A5:** Evidence only: no field, schema, or reader changed.
- **A6:** The lane made an explicit-path evidence commit in its worktree; no
  archive-to-master action or deployment was attempted.
- **A7:** At final check, every repository evidence path named in this memo
  exists: this memo; `g107_policy/G107_PREREGISTRATION.md`;
  `g107_policy/pod_table_snapshot.csv`; `g107_policy/eligibility_census.csv`;
  `g107_policy/candidate_summary.csv`; `g82_jump_statistic_limit_2026-09-02.md`;
  `g96_jump_flip_adjudication_2026-09-02.md`; and `VERIFIER_CONTRACT.md`.

### B

- **B1 CIRCULAR METRIC:** Clear. Eligibility and every candidate rule were
  committed before the snapshot and never use displacement, candidate result,
  or harness verdict to select rows.
- **B2 NON-ADDITIVE SCHEMA:** Clear. No code, schema, field, status, or reader
  changed.
- **B3 FALL-THROUGH LOSS:** Clear. No gate or quarantine changed; absent or
  short-circuited evidence is explicitly counted as excluded, not treated bad.
- **B4 RE-CLAIM LOOP:** Clear. No claim, queue, retry, or ownership code changed.
- **B5 PRE-VERIFICATION DEPLOY:** Clear. Pod commands only read files and
  streamed standard output; no copy, deployment, restart, kill, or re-track.
- **B6 ORPHANS:** Clear. No module was moved, retired, imported, or added.
- **B7 HEAD-SLICE EVIDENCE:** Clear. This uses the complete canonical pod raw
  corpus and no render sample.
- **B8 SELF-FIT AS INDEPENDENT:** Clear. No fitted model or residual is claimed.
- **B9 DEGENERATE DENOMINATOR:** Clear. Each unit is one distinct canonical
  source-table directory; eligible modal-stride pairs are distinct ordered
  same-track pairs, not recycled track IDs.
- **B10 MOVED BAR:** Clear. No harness file, bar, verdict, or coordinate
  contract changed; analysis used the existing 6/8/10-ft sport bars exactly.

## NOT VERIFIED

- The required >=10 eligible pod reports: current complete snapshot has 6.
- C1's G82 p99.9 value: G82 retained p95, max, and the 16 oversized events,
  but not the full p99.9 value; no local retained table was substituted for the
  pod corpus.
- A policy verdict or deployment: barred by the eligible-denominator failure.
- The tennis_10 eye check: G96 already records that its exact source is pruned;
  it was not retried or rendered here.
- No focused test was run because no source code was added; no full test suite
  was run.
