GAP S372 | sport all (maker channel) | worktree harness-h30 (master-based) | log cx_s372
# One atomic boundary from the cap engine to the quote engine: rooms are RESERVED, never caller-authored (audit finding 2)

OWNED FILES (NEW): scripts/platformkit/execution/quote_reservation.py, tests/platformkit/execution/test_quote_reservation.py.
No landed module is edited.
DEFECT (audit, reproduced): with an open resting YES 8 and a global cap of 10, check_caps refuses YES 3, yet make_quotes emits a
bid of qty 3 when the caller hands it generous room dictionaries -- the quote engine trusts rooms that nothing ties to the ledger.
CHANGE: quote_reservation.reserve(positions_snapshot, caps, ticker, game_id) returns the ONLY room object a caller may pass to
quote_engine.make_quotes: per side, room = the largest whole-contract qty for which position_caps.check_caps permits the order
(worst case, resting orders included), floored, never negative; it carries a reservation id, the snapshot digest it was computed
from and an expiry; submit(reservation, quote) REFUSES when the snapshot digest no longer matches the current ledger state (a fill
or another reservation landed in between) or the reservation expired or the quoted qty exceeds the reserved room; reservations are
atomic with respect to each other (two reservations computed from one snapshot cannot both be submitted if together they breach).
make_quotes_reserved(...) is the single entry point a harness uses; the memo states that calling make_quotes directly with
hand-written rooms is a contract violation and lists every current caller (grep).

AUTHORITY: docs/evidence/harness/AUDIT_EXEC_CHAIN_2026-09-21.md (quote the finding text in the memo). RULES: EDIT ONLY the row-owned modules named above (all were created on
2026-09-21 by this program; the module edits are REQUIRED -- this is NOT a tests-only row) plus their test files; never edit
venue_fees.py, executor/lifecycle.py, paper_maker.py or any other pre-existing module. Keep every public signature and every
existing reason code byte-compatible; ADD fields, never rename (contract B2). Re-run each reproduction from the audit FIRST and
quote it failing, then show it fixed. Construct / fixture tests only; no real archive, no network, no measured number.
ACCEPTANCE: every per-file test of every touched module passes, run one file at a time; each file <= 300 lines. Vocabulary
follows contract Q6; automated scan required; assemble retracted-figure literals from single digits. The memo
docs/evidence/harness/S372_quote_reservation_2026-09-21.md ends with a NOT VERIFIED list. The pod is OFF.
