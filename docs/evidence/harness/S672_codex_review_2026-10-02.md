**S672 - LAND AFTER FIX**

- **The refusal test can delete existing laptop data.** `tests/platformkit/ingame/test_s672_reading_guards_io.py:158` targets `REPO/data/s672_refused_probe.json`; lines 162-166 delete it and sibling artifacts regardless of who created them. Fix: use `tmp_path/data`, run with `cwd=tmp_path`, and remove manual repository cleanup.
- **A nonexistent archive produces a successful empty report.** `scripts/platformkit/ingame/s672_reading_guards_cli.py:90` silently globs a missing directory; line 135 returns success. Fix: reject a supplied non-directory before producing artifacts and add a missing-directory CLI assertion.

The numerical tests independently check coefficients/bootstrap calculations. No concrete numerical defect or unlanded dependency found.

| S672 | LAND AFTER FIX | None | Test deletes pre-existing data | S |

After their listed fixes: S672, S674, S677.
