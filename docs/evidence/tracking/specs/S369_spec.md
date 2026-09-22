GAP S369 | sport all (maker channel) | worktree harness-h27 (master-based) | log cx_s369
# Causal markout: mark identity, tie-breaking, clustering and price-unit guards (audit findings 6 and 7a)

OWNED FILES: scripts/platformkit/execution/markout_causal.py, markout_causal_windows.py, tests/platformkit/execution/
test_markout_causal.py, test_markout_mark_selection.py (+ a new test file if a cap is hit).
DEFECTS (audit, reproduced): a fill with game_id G1 accepted a same-ticker tick carrying game_id G2; reversing two equal-time ticks
changed the selected mid (0.6 -> 0.8); two tickers of ONE game were reported as two default clusters; markout accepted a price given
in CENTS (price = 55) and returned a large negative number instead of refusing.
CHANGE: (1) a mark must match the fill on ticker AND, when both carry one, on game_id; a game_id mismatch is cross_game_mark.
(2) two candidate ticks with the same time and DIFFERENT mids inside a window are a conflict: the horizon is unscored with reason
conflicting_equal_time_marks unless both rows carry a capture sequence field (response_end_ts or seq) that orders them; identical
mids are fine; the result never depends on input order (test by shuffling). (3) summary clustering DEFAULTS to game_id (fall back
to ticker only when game_id is absent, and say which was used in the output). (4) markout_strict refuses any fill price or mark
mid outside [0, 1] with reason price_not_probability / mid_not_probability -- a cents value can never be scored.

AUTHORITY: docs/evidence/harness/AUDIT_EXEC_CHAIN_2026-09-21.md (quote the finding text in the memo). RULES: EDIT ONLY the row-owned modules named above (all were created on
2026-09-21 by this program; the module edits are REQUIRED -- this is NOT a tests-only row) plus their test files; never edit
venue_fees.py, executor/lifecycle.py, paper_maker.py or any other pre-existing module. Keep every public signature and every
existing reason code byte-compatible; ADD fields, never rename (contract B2). Re-run each reproduction from the audit FIRST and
quote it failing, then show it fixed. Construct / fixture tests only; no real archive, no network, no measured number.
ACCEPTANCE: every per-file test of every touched module passes, run one file at a time; each file <= 300 lines. Vocabulary
follows contract Q6; automated scan required; assemble retracted-figure literals from single digits. The memo
docs/evidence/harness/S369_markout_identity_units_2026-09-21.md ends with a NOT VERIFIED list. The pod is OFF.
