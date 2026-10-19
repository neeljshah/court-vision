# S815 -- the issue scanner counts a JSON record nested past the decoder limit as a malformed read (PAPER ONLY)

## Premise (measured 2026-10-12 13:4xZ on master 81a741889, read-only, Python 3.10.0)
- paper_desk_issue_common.py:117 `Context.read` catches (OSError, ValueError, TypeError). `strict_json` (json.loads with
  parse_float=Decimal and parse_constant) raises RecursionError on `"[" * 10000 + "]" * 10000` ("maximum recursion depth
  exceeded while decoding a JSON array"); a probe through Context.read on a tmp root let that RecursionError escape the
  read (found by the S813 tiers 2026-10-09, S813_RESULT NEW GAP).
- A crafted or corrupt detail / journal file under its 2 MiB cap therefore stops the whole scan instead of being counted.

## Change (owned files only)
- `except (OSError, ValueError, TypeError, RecursionError)` -- the same branch as every other malformed read:
  input_refused +1 and the scan_input_unreadable FAIL observation with evidence "<relative>: unreadable". No new counter
  (the row asks for the same malformed read). One token on one line.
- NEW tests/platformkit/ops/test_paper_desk_issue_common_s815.py: 10,000-deep list and object fixtures.

## Clauses
- V1 The fixture overflows strict_json itself (pytest.raises RecursionError) -- the test has power.
- V2 Context.read on the 10,000-deep list / object returns None, diagnostics == {input_refused: 1}, observations == [the one
  FAIL observation with evidence "<relative>: unreadable"] -- exactly what the existing malformed-read branch emits.
- V3 A 50-deep list / object still reads: value == strict_json(text), no counter, one PASS observation.
- V4 The new test fails on master's module (V2 raises there); every other except-branch behaviour is unchanged.
- V5 No money or return language; PAPER ONLY; the module stays well under 300 lines.

ACCEPTANCE RULE: V1-V5 all hold on the branch diff + per-file test output.
