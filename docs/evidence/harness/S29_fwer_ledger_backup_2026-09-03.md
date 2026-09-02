# S29 -- FWER-ledger backup (implementer memo, MAIN repo)

Verdict: LANDED -- 5/5 CONSTRUCT + one real run; the live ledger is byte-identical.
Run in the MAIN repo, not a worktree: the eval_gate cache under `data/` is deliberately never
junctioned into worktrees, so an earlier codex attempt had no source and correctly FALSIFIED.
Nothing here calls `_charge_ledger`, takes the `.lock`, or opens the source except `"rb"`.

## PREMISE (step 0) -- HOLDS: zero backups exist

`data/cache/eval_gate/` = exactly `backtest_fwer.jsonl` (2,746 B), `backtest_fwer.jsonl.lock` (0 B),
`e4_promotion_trial_2026-09-01.json` (13,227), `gate_manifest.json` (7,186),
`hedge_trial_2026-09-01.json` (12,542). No backup: `data/backups/eval_gate/` absent,
`data/cache/eval_gate/_backup` absent (`data/backups/` held only unrelated `pnl_ledger.csv.*.gz`).
Ledger = 13 rows, `k_cumulative` 1..13 strictly increasing in file order, last two rows
`hedge_over_gap_arms` and `e4_promotion` (mlb). Per-night cost: 2,746 B ledger, 35,701 B all four.

## Source sha256 -- unchanged by everything below

before/after `52785ad273e24782dc7e94eeffbd47ed23c1a198d8a9d717e767d9947bb24cb7`;
mtime `2026-09-01 18:39:17.271881000 -0500` before and after.

## Module

`scripts/platformkit/eval_gate/ledger_backup.py` (182 LOC, stdlib only, 0 non-ASCII bytes).
`backup(src_dir, dest_root, *, now_iso, strict=False) -> dict` copies `backtest_fwer.jsonl` plus,
when present, `hypotheses.sqlite`, `gate_manifest.json` and `*_trial_*.json` into
`dest_root/<UTC date>/` with `manifest.json` (per-file sha256 + bytes, rows, `k_cumulative_max`,
monotonicity, `now_iso`, `prior_night`, `warn`). The copy lands OUTSIDE the directory it protects
(the roadmap wrote `data/cache/eval_gate/_backup/`, which a volume loss takes with it). It asserts
source sha256 before == after and copy == source; a mismatch raises and removes the partial dir.
Same-day rerun writes `<date>.tmp` then rmtree + rename. `verify(backup_dir)` recomputes every
manifest sha256, reporting OK/MISMATCH/MISSING per file; `latest(dest_root)` returns the newest
dated dir. Row shrink and `k_cumulative` regression are FLAGGED (return + manifest `warn`), never
blocking -- `strict=True` raises instead, naming both nights. All assertions run on the COPY, so a
bad night cannot be hidden by editing the source.

## Test -- 5/5 CONSTRUCT

`python -m pytest scripts/platformkit/eval_gate/test_ledger_backup.py -q -p no:cacheprovider`
-> `5 passed in 2.28s`. Every case uses a synthetic 13-row ledger under `tmp_path`; the real cache
is never opened by the test file.
1. backup -> all manifest sha256s verify OK; `hypotheses.sqlite` absent recorded in `absent`, not
   an error (S15 has not landed).
2. one byte tampered in the copy -> `verify` reports `MISMATCH` on that file, `OK` on the others.
3. second night over a source shrunk 13 -> 9 rows -> `ROWS_SHRANK: 13 -> 9` and
   `K_REGRESSED: 13 -> 9`, both naming `2026-09-01 -> 2026-09-02`; the copy stays usable.
4. same-day rerun overwrites its own dated dir cleanly (stale file gone, no `.tmp`, one dir in the
   root, `prior_night` null -- today is not its own prior).
5. source sha256 AND mtime identical across three backups plus a verify; no `.lock` created.

Non-tautology: cases 2 and 3 are the ones a lenient rule would drop -- a backup that cannot notice
a tampered byte or a shrinking ledger proves nothing.

## Real run (one nightly pass against the live cache)

`python -m scripts.platformkit.eval_gate.ledger_backup` -> `data/backups/eval_gate/2026-09-02/`
(UTC date; the local clock read 2026-09-01 evening CDT). Manifest: rows 13, `k_cumulative_max` 13,
`k_monotone` true, `prior_night` null, `warn` []. Files: `backtest_fwer.jsonl` 2,746 B
`52785ad2...4cb7`; `gate_manifest.json` 7,186 B `f6dcf91d...25c9`;
`e4_promotion_trial_2026-09-01.json` 13,227 B `611a9722...ecb2`;
`hedge_trial_2026-09-01.json` 12,542 B `85eb2f07...95e8`; `absent: ["hypotheses.sqlite"]`.
`--verify data/backups/eval_gate/2026-09-02` -> `ok: true`, all four `OK`.
Gitignored (`git check-ignore -v` -> `.gitignore:503:data/*`) and `git status --porcelain data/`
is EMPTY -- nothing under `data/` staged or committed.

## Scheduling -- NOT armed by this lane

For the human/orchestrator, verbatim (interpreter = the one that ran the pass above):

```
schtasks /Create /SC DAILY /ST 03:00 /TN CourtVision-FwerLedgerBackup /TR "C:\Users\neelj\AppData\Local\Programs\Python\Python310\python.exe -m scripts.platformkit.eval_gate.ledger_backup"
```

Run it with the repo root as the working directory (the default paths are relative to it).

## NOT VERIFIED

- No OS task created; no real nightly CADENCE has run. Exactly one real pass exists, so the
  prior-night comparison has never fired on real data (`prior_night` null); three-night behaviour
  is CONSTRUCT-only.
- `restore(...)` from the spec on disk was not built -- this work order defines `verify` + `latest`
  instead. Restoring today means copying the file back by hand after `--verify` says OK.
- `hypotheses.sqlite` does not exist yet (S15): that copy path is exercised only in the absent
  branch, never with a real sqlite file.
- The ledger is LOCAL-authoritative on this box (verified 2026-09-03) -- the pod does NOT hold it,
  contrary to the register's "pod-authoritative" wording. No ssh, no scp.
- The `<date>.tmp` -> `<date>` swap is not atomic on Windows; a crash between rmtree and rename
  leaves no dated dir for that night. Single nightly writer assumed, no lock against a concurrent
  `_charge_ledger` append (a mid-copy append trips the before/after assert and removes the partial
  dir -- safe, but that night is lost).
- No prereg seal: audit-trail infrastructure, not a scored or charged trial. Nothing here computes
  a metric, and no threshold under `scripts/platformkit/eval_gate/` was read or moved.
