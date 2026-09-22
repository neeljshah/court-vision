GAP S368 | sport all (event market sets) | worktree harness-h26 (master-based) | log cx_s368_coherence_scanner
# Structural coherence scanner over synchronized event market sets (design: docs/evidence/harness/ASTRA_ROUND12_2026-09-21.md section 4; section 6 row 9)

SINGLE PROBLEM: the rebuilt capture records complete event market sets (winner + spread / total ladders, snapshot_bulk rows with
receipts), but nothing checks them for structural contradictions, and bulk retrieval is not atomic.

BINDING BEFORE-CONDITION: `ls scripts/platformkit/execution/coherence_scanner.py` fails; read the landed
scripts/platformkit/execution/coherence_audit.py (row S339) and REUSE its helpers by import where they fit.

CHANGE:
1. scripts/platformkit/execution/coherence_scanner.py (<= 300 LOC, Decimal arithmetic): per event and capture instant build, for
   each contract, L = bid - fee - one tick and U = ask + fee + one tick (fees from venue_fees, per contract, stated unit), then
   the three falsifiers exactly as the design states: (a) COMPLETE SETS -- only for mutually exclusive AND exhaustive outcome
   sets (winner markets incl. a draw where it exists; spread / total ladders are NOT complete sets): flag unless sum(L) <= 1 <=
   sum(U); (b) NESTED TOTALS -- high-threshold success implies low-threshold success: flag L_high > U_low; (c) SPREAD / WINNER --
   a positive-margin cover implies winning under matching settlement rules: flag L_cover > U_winner. REFUSE (status
   sync_failure) any comparison whose rows' response_end times differ by more than 5 s; REFUSE incomplete sets; unknown settlement
   rule -> not_comparable. Report residual size, persistence (consecutive instants) and game incidence as MARKET-STRUCTURE
   MEASUREMENTS; the module's docstring and output state that a residual is not an opportunity and that related contracts of one
   game are not independent families.
2. tests/platformkit/execution/test_coherence_scanner.py: three synthetic violations detected; asynchronous and incomplete sets
   refused; fee-aware tolerance removes a sub-fee residual; fractional / fixed-point string inputs.
3. Memo docs/evidence/harness/S368_coherence_scanner_2026-09-21.md with the finisher command over data/cache/ingame_books_local.

CONTROLS: PREPARE only, NEW files only (edit no pre-existing module; import landed code), construct / fixture tests, no real
archive run, no network, no measured calibration, fill or markout number. ACCEPTANCE: the per-file tests pass; every CLI has
--help; diff = NEW files only. Vocabulary follows contract Q6; automated scan required; assemble retracted-figure literals
from single digits. The memo ends with a NOT VERIFIED list. The pod is OFF.
