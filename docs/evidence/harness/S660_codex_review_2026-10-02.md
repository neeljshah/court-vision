### Branch reviews

- **S660 - HOLD.** `scripts/platformkit/ingame/kalshi_ws_signer.py:205-220` checks the credential destination only once. A file appearing after that check can be overwritten by `:153` and deleted by `:218`; `:217-220` also swallows cleanup failure. The same replace call lacks the Windows retry helper. `tests/platformkit/ingame/test_kalshi_ws_signer.py:281-283` hashes checkout bytes of a file without an LF rule, so CRLF checkout can fail the test. Master has changed the branch's `docs/operations/cloud/setup.sh` path since the merge base.

| branch | verdict | must-land-after | top defect | fix size (S/M/L) |
|---|---|---|---|---|
| S660 | HOLD | none | Credential path race and destructive cleanup | M |

**Landing order:** Land S666. After fixes and verification, S660 is independent; S664 precedes S695 and measured-offset use in S663. S667 follows S666. S668 follows S666 and S695; S669 follows the risk inputs it is meant to report.
