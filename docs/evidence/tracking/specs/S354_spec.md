GAP S354 | sport all (execution + capture) | worktree harness-h11 | log cx_s354_venue_time
# One shared, version-independent venue-time parser; fix the LANDED S343 markout, which drops ~10 pct of live ticks as marks

SINGLE PROBLEM: the venue trims trailing zeros from fractional seconds. MEASURED on the S341 archive (2026-09-21): 962 of 9,737
created_time values (9.9 pct) carry 4 or 5 fractional digits. datetime.fromisoformat on Python 3.10 (this machine) rejects them;
Python 3.11+ accepts them, so results differ between machines. LANDED code affected, reproduced on master:
`scripts.platformkit.execution.markout_causal._epoch("2026-09-21T19:20:51.1492Z")` returns None while the 6-digit form parses.
It fails closed (never a wrong number) but a skipped tick means the mark comes from a LATER tick than the first valid one, which
lengthens the realized horizon for about one tick in ten.

BINDING BEFORE-CONDITION (re-run, quote the output):
`python -c "from scripts.platformkit.execution import markout_causal as m; print(m._epoch('2026-09-21T19:20:51.1492Z'))"` prints None.

CHANGE:
1. NEW scripts/platformkit/execution/venue_time.py (<= 120 LOC, stdlib, pure, ASCII): `parse_venue_time(value) -> float | None`
   (UTC epoch seconds). Accepts: ISO-8601 with a trailing Z or a +HH:MM / -HH:MM offset, 0 to 9 fractional digits (normalized to
   6 by padding or truncation, never rounding up), a naive string is REFUSED (None) rather than assumed UTC, int / float epoch
   seconds when finite, and None / bool / NaN / inf / anything else -> None. `venue_time_reason(value)` returns a short reason
   string for a refusal. Behaviour is identical on Python 3.10 and 3.12 (no reliance on fromisoformat's version-specific grammar
   for the fraction).
2. EDIT scripts/platformkit/execution/markout_causal.py (a module created by row S343 on 2026-09-21; this row owns the change):
   `_epoch` delegates to parse_venue_time. Public signatures, return shapes and every reason code stay byte-compatible
   (contract B2). Keep the file <= 300 LOC.
3. tests: NEW tests/platformkit/execution/test_venue_time.py (0, 1, 3, 4, 5, 6, 9 fractional digits; Z and offset forms give the
   same instant; truncation not rounding at 7+ digits; naive refused; NaN, inf, bool, None refused; int and float epochs) and ONE
   added regression test in tests/platformkit/execution/test_markout_causal.py: a tick stamped with a 4-digit fraction inside the
   window IS selected as the mark (today it is skipped).
4. Memo docs/evidence/harness/S354_venue_time_2026-09-21.md: list every OTHER call to datetime.fromisoformat on a venue or capture
   timestamp under scripts/platformkit/execution and scripts/platformkit/ingame (grep), one line each with a verdict (affected /
   input always 6 digits / not a venue time). Do NOT fix those here; they become follow-up rows.

CONTROLS: infrastructure row, construct tests only, no measured calibration or markout number. ACCEPTANCE: both per-file test
runs pass (python -m pytest <file> -q -p no:cacheprovider, one file at a time); the existing 30 markout_causal tests still pass
unchanged; the before-condition command now prints a float. Vocabulary follows contract Q6; automated scan required; assemble any
retracted-figure literal from single digits. Memo ends with a NOT VERIFIED list. The pod is OFF.
