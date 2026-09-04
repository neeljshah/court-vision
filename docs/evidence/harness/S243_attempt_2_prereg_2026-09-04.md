# S243 attempt 2 preregistration

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q.

## Fixed purpose

This correction pass addresses only the two S243 rejection findings: use a real
named on-disk source instead of authored targets, and replace repeated inputs
with a distinct exhaustive 30-case matrix. The existing S243 bar remains
top-five player q50 minutes no greater than `240 + 5 * overtime_periods`; PTS,
REB, and AST use absolute and percent deviation only when their named,
nonzero team target exists.

## Fixed source procedure

The first and only store to inspect is
`data/intelligence/matchup_grid.parquet`, the S243 context-cited archived NBA
matchup store. It is opened read-only, one store at a time, only if its file
size is at most 300 MB. The inspection records its path, bytes, row count,
date range, and column names. Required usable row fields are player q50
`minutes`, `pts`, `reb`, and `ast`, plus named team q50 targets for `pts`,
`reb`, and `ast` keyed to the same game/team. If any required field is absent,
the result is CLOSED AT LIMIT with every absent field named; no player rows,
team totals, or deviations will be authored or fabricated.

## Fixed implementation and test condition

Only if every required source field exists, the checker test will read rows
from that named source and report its real-data table and summary. The one
pytest case will iterate a distinct exhaustive 30-case matrix covering every
target/source-validation branch, including zero target and missing target. If
the source condition fails, no synthetic substitute will be introduced merely
to populate either the table or matrix.

## Scoring and scope

This is a coherence construction and source-availability check, not an OOS
comparison. No charged trial, ledger, register, deployment, data write, or
feature-flag change is authorized. The final memo will state the source
inspection result, before/after status, and an explicit NOT VERIFIED list.

Seal SHA-256: 324f66f755fecffee740f2c7890ec2675c7bdda45c8b6ba594e40731a8b56ba0
