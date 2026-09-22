GAP S370 | sport all (maker channel) | worktree harness-h28 (master-based) | log cx_s370
# Tape fill simulator: version-independent venue time and fail-closed fee inputs (audit findings 5 and 7b)

OWNED FILES: scripts/platformkit/execution/tape_fill_sim.py, tests/platformkit/execution/test_tape_fill_sim.py (+ a new test file if
the 300-line cap is hit). tape_fill_adapters.py is NOT edited.
DEFECTS (audit, reproduced on this machine's Python 3.10): tape_fill_sim._ts("2026-09-21T19:20:51.1492Z") raises ValueError while
scripts.platformkit.execution.venue_time.parse_venue_time returns 1790018451.1492 -- quote submit / cancel times and book snapshot
times with 4- or 5-digit fractions (9.9 pct of real venue times) break the simulator. And venue_fees.fee_kalshi_maker returns 0.0
for an invalid size or price (fail-open), so a bad input becomes a free fill.
CHANGE: (1) _ts delegates to parse_venue_time; a None result refuses that quote / snapshot / print with a counted reason -- never an
exception that aborts the run, never a silent skip. (2) before calling the fee function validate: cumulative filled size is a
finite Decimal > 0 and price is an integer 1..99 cents; otherwise the fill is REFUSED and counted as fee_input_invalid (a fee of
zero from the venue module is never trusted for an input the simulator has not validated). venue_fees.py is NOT edited; record in
the memo that its fail-open return is a finding for the owner.

AUTHORITY: docs/evidence/harness/AUDIT_EXEC_CHAIN_2026-09-21.md (quote the finding text in the memo). RULES: EDIT ONLY the row-owned modules named above (all were created on
2026-09-21 by this program; the module edits are REQUIRED -- this is NOT a tests-only row) plus their test files; never edit
venue_fees.py, executor/lifecycle.py, paper_maker.py or any other pre-existing module. Keep every public signature and every
existing reason code byte-compatible; ADD fields, never rename (contract B2). Re-run each reproduction from the audit FIRST and
quote it failing, then show it fixed. Construct / fixture tests only; no real archive, no network, no measured number.
ACCEPTANCE: every per-file test of every touched module passes, run one file at a time; each file <= 300 lines. Vocabulary
follows contract Q6; automated scan required; assemble retracted-figure literals from single digits. The memo
docs/evidence/harness/S370_tape_fill_time_fees_2026-09-21.md ends with a NOT VERIFIED list. The pod is OFF.
