"""governance -- Milestone-10 enforced honesty gates.

Every honesty invariant in this repo (no retracted ROI numbers, no $-edge field,
conservative real-money eligibility, train==inference parity, leak-free
walk-forward, provenance honesty) is turned into an ENFORCED, TESTED gate here.
The gates aggregate into a single ``run_governance`` preflight that exits 0/1; a
non-zero exit means the stack is NOT real-money-eligible (a fabrication slipped
in) and must not boot for live use.

DECISION-ONLY where it touches money: nothing here authorizes a bet or moves
money. A human flip plus a valid signed token is ALWAYS required downstream.

``governance.policy`` is the single source of governance constants every gate
reads, so every gate measures against the same banned numbers, banned tokens,
thresholds, and provenance vocabulary.
"""
