GAP S371 | sport all (maker channel) | worktree harness-h29 (master-based) | log cx_s371
# Position ledger: durability and locking fail CLOSED; order ids cannot be reused to hide exposure (audit findings 8 and 3)

OWNED FILES: scripts/platformkit/execution/position_ledger.py, position_reducers.py, replay_units.py and their test files
(test_position_ledger.py, test_position_reducers.py, test_fractional_chain.py; + new test files if a cap is hit).
DEFECTS (audit, reproduced): an import failure of the lock helper DISABLES locking; required=False permits an unlocked read or
append; an fsync failure is swallowed while append reports success. And a day-1 order id Q (submit + fill, terminal) followed by a
day-2 submit with the SAME id Q and qty 10 reduced to terminal = True, open = False, unfilled 0 -- the new resting order vanished
from worst-case exposure, so caps would permit more than allowed.
CHANGE: (1) locking is mandatory: if the lock helper cannot be imported or acquired, append and read RAISE; remove the unlocked
path (tests inject a fake lock). (2) append = ONE os.write of one encoded line on an O_APPEND descriptor, then flush + fsync; an
fsync failure RAISES and is never reported as success. (3) ORDER IDS ARE GLOBALLY UNIQUE: replay_units builds order / quote ids as
<utc-day>-<run-nonce>-<counter> (run nonce supplied by the caller, recorded in every event); the ledger REFUSES a submit or intent
whose order id already exists in a terminal state, or exists with a different idempotency key, with reason order_id_reuse. A
replayed identical event stays a no-op.

AUTHORITY: docs/evidence/harness/AUDIT_EXEC_CHAIN_2026-09-21.md (quote the finding text in the memo). RULES: EDIT ONLY the row-owned modules named above (all were created on
2026-09-21 by this program; the module edits are REQUIRED -- this is NOT a tests-only row) plus their test files; never edit
venue_fees.py, executor/lifecycle.py, paper_maker.py or any other pre-existing module. Keep every public signature and every
existing reason code byte-compatible; ADD fields, never rename (contract B2). Re-run each reproduction from the audit FIRST and
quote it failing, then show it fixed. Construct / fixture tests only; no real archive, no network, no measured number.
ACCEPTANCE: every per-file test of every touched module passes, run one file at a time; each file <= 300 lines. Vocabulary
follows contract Q6; automated scan required; assemble retracted-figure literals from single digits. The memo
docs/evidence/harness/S371_ledger_durability_ids_2026-09-21.md ends with a NOT VERIFIED list. The pod is OFF.
