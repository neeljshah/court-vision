- **S667 - HOLD.** The registered per-family cap is missing: `scripts/platformkit/execution/risk_limits.py:43-45` declares only six scopes, `:94-96` rejects an added family scope, and `:221-234` cannot report one. The required archived-night replay is still unverified (`docs/evidence/harness/S667_cloud_result_2026-09-30.md:82-85`); `tests/platformkit/execution/test_risk_limits.py:294-300` exercises synthetic sequences.

| S667 | HOLD | S666 | Per-family cap absent | M |

**Landing order:** Land S666. After fixes and verification, S660 is independent; S664 precedes S695 and measured-offset use in S663. S667 follows S666. S668 follows S666 and S695; S669 follows the risk inputs it is meant to report.
