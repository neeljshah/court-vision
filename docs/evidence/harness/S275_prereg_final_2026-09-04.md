# S275 final preregistration: explicit calibration-basis consumers

Status: SEALED BEFORE THE VALID S275 COMPARISON.

Machine: local worktree `C:/Users/neelj/nba-track-a16`. The existing local
corpus cache and evaluator are used; no pod operation is authorized or needed.

## Target identity correction

The two earlier S275 preregistrations are superseded for target identification
only. Their NBA calls are excluded from all S275 premise and acceptance tables.
They respectively selected current artifact files whose positional values have
drifted from the S50 declarations. This document changes no tolerance and binds
the canonical S50 values explicitly, before the valid eight-value comparison.

The canonical values are the S50 values restated in the sealed S267
preregistration, `docs/evidence/harness/S267_prereg_2026-09-04.md` (2471
bytes): nba positional `0.024842541854003943`, per-unit
`0.02658254607099417`; mlb positional `0.008076735465020577`, per-unit
`0.012666184733512256`; soccer positional `0.009302164221488884`, per-unit
`0.028722315180213532`; tennis positional `0.008402944939872484`, per-unit
`0.015403176684314482`. The current eight artifact paths and their byte sizes
are recorded as input identity only, never substituted for these targets.

## Binding scope

Before change, remeasure the named three implicit reader sites and the absent
`positional` / `per_unit` report keys. Then, once per sport, run
`build_report(load_gate_corpus(sport), sport)` and
`build_report(load_gate_corpus(sport), sport, order_by="event_date",
unit_col="corpus_unit")`. The current actual values must remain within `1e-6`
of the eight canonical targets. If a before-condition is false, S275 is
FALSIFIED and closes without an implementation change.

If it holds, add explicit basis summaries without moving default top-level
keys or values, migrate the three named reader sites with an old-artifact
fallback, and make the constructed consumer-read flip check. A fresh eight
value second run must match a newly committed S275 reference JSON within `1e-9`.
The existing report preserves its walk-forward expanding-fit route; no evaluator,
corpus, model, threshold, `cpcv_engine.py`, or `walkforward.py` changes.

All four sports and both bases are required. The acceptance table contains all
eight S50 comparisons, all eight second-run comparisons, and the three
consumer readings for every sport/basis pair. Every consumer-reading absolute
difference must be `0.0`. The deliverables are the scoped code/test changes,
reference and second-run JSON artifacts, flip table, and evidence memo. They
use calibration language only.

Seal SHA-256 of every LF byte above this line: C43FB0B12DA955B80658500D4D85F156A3AC43521C9395FCAF9DE1C3084E1BB4
