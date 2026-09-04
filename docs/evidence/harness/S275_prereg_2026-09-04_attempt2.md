# S275 attempt 2 preregistration: explicit calibration-basis consumers

Status: SEALED BEFORE ATTEMPT 2 SCORING.

Machine: local worktree `C:/Users/neelj/nba-track-a16`. Each corpus is opened
and evaluated one sport at a time. No deployment or pod copy is authorized.

## Correction scope

Attempt 1 met its eight S50 comparisons, second-run comparisons, explicit
consumer reads, and flip-invariance construct. It was rejected because its
resolver LOC allowance was changed from 1323 to 1325 and its committed
preregistration prefix did not match the embedded seal. Attempt 2 retains the
1323 rail and preserves the additive explicit per-unit read with an older
artifact fallback. No field, status, or reader behavior is renamed or removed.

## Binding scope and unchanged bars

The canonical S50 targets are the eight values named in
`docs/evidence/harness/S275_prereg_final_2026-09-04.md`: nba positional
`0.024842541854003943`, per-unit `0.02658254607099417`; mlb positional
`0.008076735465020577`, per-unit `0.012666184733512256`; soccer positional
`0.009302164221488884`, per-unit `0.028722315180213532`; tennis positional
`0.008402944939872484`, per-unit `0.015403176684314482`.

Before scoring, retain the verified explicit-basis implementation and run
`build_report(load_gate_corpus(sport), sport)` plus
`build_report(load_gate_corpus(sport), sport, order_by="event_date",
unit_col="corpus_unit")` for every sport. All eight values must differ from
the canonical S50 targets by at most `1e-6`. An immediately following fresh
run must differ from the new attempt-2 reference JSON by at most `1e-9` for
all eight values. The three explicit consumer sites and the two-call default
flip construct must have absolute difference `0.0`.

The existing expanding walk-forward evaluator remains unchanged. No corpus,
model, threshold, `cpcv_engine.py`, `walkforward.py`, register, or ledger is
modified. The required new artifacts are
`S275_basis_reference_2026-09-04_attempt2.json`,
`S275_basis_second_run_2026-09-04_attempt2.json`, and
`S275_key_explicit_consumers_v2_2026-09-04_attempt2.md`. All use calibration
language only and enumerate four sports by two bases.

Seal SHA-256 of every LF byte above this line: CFB5E1DC7221EA361A9D029A140D2574670FEB3AF62DCD9F0A9975B6549E982E
