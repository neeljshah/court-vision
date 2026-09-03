# S151 wall-clock provenance

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.

## Premise (Q8)

`git show 333af3149fde92cca7b0b8dd95dae94fde97bafa:scripts/platformkit/venue_history/nba_wallclock_join.py`
contains the five named provenance items. The historical docstring is one physical line, despite
the row's 36-line description. Exact phrase searches in current tracked `docs/` and `scripts/`
found no other complete copy of the historical text, so the premise is CONFIRMED.

## Change and reproduction

`nba_wallclock_join_PROVENANCE.md` quotes that historical docstring verbatim and names its source
SHA. It also records why S145 moved it for the 300-LOC rail and points to the S141 300-second
staleness rail. The module now has a three-line docstring linking to the provenance document.
Its executable code is unchanged; it remains below 300 lines.

| Metric | Before | After | n |
|---|---:|---:|---:|
| Restored, linked provenance items | 0/5 | 5/5 | 5 (CONSTRUCT) |

## Focused verification

- `python -m pytest tests/platformkit/venue_history/test_nba_wallclock_join_loc.py -q`
- `python -m pytest tests/platformkit/venue_history/test_nba_wallclock_join_provenance.py -q`

Both passed (1 each).

## Contract self-check

B1-B10: this is an exhaustive five-item document construct; no schema, gate, claim state,
deployment, reader, threshold, or executable behavior changed. Q1-Q2 and Q4-Q5/Q9 do not apply;
no scored comparison or ledger charge occurred. Q3 preserves the 300-second rail. Q6 remains
calibration-only. Q7 is exhaustive at n = 5. Q8 was measured before the edit.
