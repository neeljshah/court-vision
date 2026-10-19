# S816 -- the issue scanner's ledger, lock-file and CLI-snapshot reads refuse a record nested past the decoder limit (PAPER ONLY)

## Premise (measured 2026-10-12 14:5xZ on master e6598098e, read-only, Python 3.10.0)
- Three scanner reads parse with `strict_json` outside the S815 catch (found by the S815 adversarial tier, S815_RESULT NEW GAP):
  paper_desk_issue_ledger.py:33 `recover` (each ledger line; catches ValueError, KeyError, TypeError, UnicodeError),
  paper_desk_issues.py:87 `lock` (the lock file; catches ValueError, OSError, KeyError, TypeError, InvalidOperation) and
  paper_desk_issues.py:164 (the --snapshot file; no catch of its own).
- `strict_json("[" * 10000 + "0" + "]" * 10000)` raises RecursionError. In `recover` that RecursionError escapes the per-line
  catch, so ONE deep ledger line (the ledger is append-only and never repaired) makes every later --write / --link scan
  exit 4 with path issues.jsonl. In `lock` it escapes before `held` is set, so the lock file is never unlinked and every
  later write scan exits 4 with path issues.lock. The --snapshot read sits inside main's `except Exception` handler, which
  already refuses it (exit 4, error RecursionError, path --snapshot), the same refusal a wrong-type snapshot takes.
- The ledger and lock file are the scanner's own files, so the input is not realistic today: this is a fail-closed guard.

## Change (owned files only)
- `recover`: RecursionError joins the per-line except tuple -> `bad` +1 and the scan folds the lines after it (the same
  branch an unparseable line already takes). One token on one line.
- `lock`: RecursionError joins the except tuple -> `unreadable` +1, pid None, the lock is reclaimed and rewritten (the same
  branch a byte-invalid lock already takes). One token on one line.
- --snapshot: NO code change (already refused by the outer handler); the new test pins that refusal.
- NEW tests/platformkit/ops/test_paper_desk_issue_s816.py: one 10,000-deep case per site plus the decoder premise.

## Clauses
- V1 The fixture overflows strict_json itself (pytest.raises RecursionError) -- the tests have power.
- V2 `recover` over [deep line, one empty scan batch] returns state {}, seq 1, last == that batch's scan_ts, bad 1, future 0:
  the deep line is counted and the batch after it still folds.
- V3 `lock` on a 10,000-deep lock file returns 1 (unreadable) and leaves a fresh record carrying the caller's pid.
- V4 `main --snapshot <10,000-deep file>` returns 4 and prints {"error": "RecursionError", "path": "--snapshot"}.
- V5 V2 and V3 fail on master's modules (the RecursionError escapes there); V4 passes on master (no code change at that
  site). Every other except-branch behaviour is unchanged; both modules stay under 300 lines.
- V6 No money or return language; PAPER ONLY.

ACCEPTANCE RULE: V1-V6 all hold on the branch diff + per-file test output.
