# G154 local table census

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including A7 and
section B. Verdict: **ACCEPT WITH CORRECTIONS -- premise FALSIFIED.** This is
a local-only, read-only measurement. It moved no table, changed no eligibility
rule, 10-table bar, coordinate contract, threshold, or verdict, and made no
pod or network connection.

## Frozen population and eligibility definition

The unit is one immediate local
`data/tracking/<table>/tracking_data.csv` file. The enumeration is exhaustive
by construction: the census script globs that exact path once and writes one
row per result. Its **ELIGIBLE census denominator is all 361 enumerated local
tables**, not rows, frames, tracks, retries, or only tables that reach the
jump gate. Every share below uses that denominator (or the explicitly named
per-sport equivalent); no bare sample size is reported.

G109/G142's first-blocker order and vocabulary are preserved:

1. unknown sport routing;
2. empty or header-only;
3. all-`metric_local` scope;
4. declared coordinate-space rejection (including `image_px`);
5. missing coordinate declaration or another required schema prerequisite;
6. `INSUFFICIENT_DATA` for fewer than 30 distinct frames only after all prior
   prerequisites; and
7. reaches the unchanged jump calculation.

The `other` display bucket is intentionally additive only at the presentation
layer: it contains the 358 missing-coordinate/schema tables and the one
unknown-routed header-only smoke table. The per-table CSV retains each actual
first blocker. The script stops reading a file after a decisive header/first
row blocker, so it records `data_state=nonempty` rather than inventing an
irrelevant row or frame total; it fully reads the declared-court candidate to
apply the unchanged 30-frame and unique-modal-stride prerequisites.

## Result

The table-count premise holds exactly: **361 local tables**. The asserted
zero-eligible premise does not: `G83_tennis_09` reaches the gate. This is a
valid Q8 premise falsification, not a changed bar.

| First blocker | Tables | Share of 361-table ELIGIBLE census denominator |
|---|---:|---:|
| reaches gate | 1 | 1/361 = 0.2770% |
| coordinate-contract rejection | 1 | 1/361 = 0.2770% |
| INSUFFICIENT_DATA | 0 | 0/361 = 0.0000% |
| empty or header-only | 0 | 0/361 = 0.0000% |
| other | 359 | 359/361 = 99.4460% |
| **Total** | **361** | **361/361 = 100.0000%** |

The complete reusable artifacts are
[`g154_census/table_census.csv`](g154_census/table_census.csv),
[`bucket_summary.csv`](g154_census/bucket_summary.csv), and
[`sport_bucket_summary.csv`](g154_census/sport_bucket_summary.csv). Reproduce
them locally with:

```powershell
python scripts/platformkit/g154_local_table_census.py data/tracking docs/evidence/tracking/g154_census
```

## Per-sport breakdown

Every share is over the named sport's complete local-table denominator.

| Sport | Denominator | Gate | Coordinate rejection | INSUFFICIENT_DATA | Empty/header-only | Other |
|---|---:|---:|---:|---:|---:|---:|
| basketball | 358 | 0 (0.0000%) | 0 (0.0000%) | 0 (0.0000%) | 0 (0.0000%) | 358 (100.0000%) |
| baseball | 1 | 0 (0.0000%) | 1 (100.0000%) | 0 (0.0000%) | 0 (0.0000%) | 0 (0.0000%) |
| tennis | 1 | 1 (100.0000%) | 0 (0.0000%) | 0 (0.0000%) | 0 (0.0000%) | 0 (0.0000%) |
| UNKNOWN | 1 | 0 (0.0000%) | 0 (0.0000%) | 0 (0.0000%) | 0 (0.0000%) | 1 (100.0000%) |
| **Pooled** | **361** | **1 (0.2770%)** | **1 (0.2770%)** | **0 (0.0000%)** | **0 (0.0000%)** | **359 (99.4460%)** |

### Tennis control

The local tennis sub-table is not empty: its denominator is one table and it
has **1/1 = 100.0000%** reaching the gate. `G83_tennis_09` declares
`court_feet`, supplies canonical fields and usable player rows, has 38 distinct
frames (above the unchanged 30-frame floor), and has a unique positive modal
same-track stride of 2. This sole reachable table falsifies the asserted
zero-gate local premise; it does not imply that any downstream quality verdict
passes.

## Required three raw-CSV hand checks

The raw arithmetic is retained in
[`g154_census/hand_checks.csv`](g154_census/hand_checks.csv).

| Table | Why chosen | Direct raw observation and arithmetic | Classification |
|---|---|---|---|
| `0022400625` | One from the largest bucket | Its first data row is nonempty; its header has no `coordinate_space`; canonical columns present are `frame` only, so 1/5. | missing coordinate/schema |
| `mlb_2iosUkpL0Bc` | Awkward declared-coordinate case | Its first data row is nonempty; header has all 5/5 canonical columns and `coordinate_space`; row field 6 is `image_px`. | coordinate-contract rejection |
| `G83_tennis_09` | Awkward only gate-reaching table | 87 data rows, 38 distinct frames, 2 player tracks, and 74 positive same-track gaps. Gap 2 occurs 74 times with no tied mode; all rows declare `court_feet`. | reaches gate |

## VERIFIER_CONTRACT self-check

### A

- **A1:** The only new test is the required focused file,
  `python -m pytest tests/scripts/platformkit/test_g154_local_table_census.py -q`;
  it passed (1 passed). This worktree commit is ready for the verifier's
  master re-run.
- **A2:** An independent artifact read counted 361 unique `table` values and
  recomputed 1, 1, 0, 0, and 359 pooled rollup rows, summing to 361.
- **A3:** No render decision set applies: this is an exhaustive construct
  census, not a sampled visual metric. The required raw checks cover the
  largest bucket plus both awkward non-largest outcomes.
- **A4:** The census unit is one distinct source-table directory; the artifact
  has 361 unique `table` values.
- **A5:** No existing field or reader changed. The new script has no callers.
- **A6:** This lane lands as an explicit-path worktree commit only, as the
  task requires; no archive-to-master, deployment, or pod action occurred.
- **A7:** Before commit, every named repository artifact exists: this memo,
  the four `g154_census/` CSVs, the script, focused test, G109, G142, and the
  verifier contract.

### B

- **B1 CIRCULAR METRIC:** Clear. The complete glob is classified once; no
  failing table is omitted.
- **B2 NON-ADDITIVE SCHEMA:** Clear. No production schema, status, field, or
  reader changed.
- **B3 FALL-THROUGH LOSS:** Clear. Missing coordinate/schema, unknown routing,
  and empty data remain named blockers; missing is not treated as bad data.
- **B4 RE-CLAIM LOOP:** Clear. No claim, queue, retry, or ownership path changed.
- **B5 PRE-VERIFICATION DEPLOY:** Clear. No pod file was copied or changed.
- **B6 ORPHANS:** Clear. Nothing was moved or retired.
- **B7 HEAD-SLICE EVIDENCE:** Clear. The census is exhaustive and hand checks
  deliberately include the largest bucket and two awkward cases.
- **B8 SELF-FIT AS INDEPENDENT:** Clear. No fitted model or residual is claimed.
- **B9 DEGENERATE DENOMINATOR:** Clear. One distinct table directory is one
  unit; rows, frames, and track IDs are never recycled as the denominator.
- **B10 MOVED BAR:** Clear. The coordinate contract, 30-frame floor,
  unique-stride prerequisite, 10-table bar, and every verdict are unchanged.

## NOT VERIFIED

- Whether the one gate-reaching tennis table passes any downstream quality
  criterion; gate reachability is not a pass claim.
- Any subsequent local corpus state after this fixed local run.
- Why the 358 basketball tables lack the canonical coordinate declaration;
  this measurement classifies and does not repair them.
