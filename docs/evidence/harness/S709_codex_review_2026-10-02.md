- **S709 -- HOLD.** DESK_ROOT adoption is proposed, not applied (`docs/evidence/harness/S709_PROPOSED_desk_root_diffs_2026-09-30.md:14-42`), so the tick does not yet resolve a different root. Two tests are also Windows-incompatible: `test_s709_desk_root.py:96-99` expects the Linux path-error outcome, and line 107 rejects backslashes in a native Windows scratch path. Apply the adoption and make those assertions platform-aware before the Windows tick contract run.

| S709 | HOLD | None | Adoption absent; Windows tests fail | M |
