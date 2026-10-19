# S678 cloud result -- closed-shard corpus manifest (2026-09-30)

Row S678 (QUANT_GRADE_BUILD_SLATE_2026-09-30.md section 2; one-off override section 3a). PAPER ONLY;
evidence-integrity tooling, no scored claim, no calibration number produced. Branch
`cloud/S678-2026-09-30` from trunk e1b3bcdc0. Build commit 4f1fc2e2, corrections commit follows it.
Machine: cloud clone, Python 3.11.15, no data/ directory; all shards are synthetic, built in tmp_path.

## Verdicts

| Tier | Who | Verdict |
|---|---|---|
| Pre-build critique | independent Opus sub-agent (astra role) | REVISE, 13 items -> all folded as spec AMENDMENT 1 |
| CONTRACT (A/B/Q + spec + AMENDMENT 1) | independent Opus sub-agent, did not build | ACCEPT WITH CORRECTIONS |
| ADVERSARIAL (M1-M8 + own probes) | independent Opus sub-agent, did not build, own git worktree | ACCEPT WITH CORRECTIONS |

Codex is not available in the cloud box; every critic and verifier role was an independent Opus
sub-agent (three separate agents), as the run's rule (c) allows.

Corrections applied after both tiers (commit after 4f1fc2e2; builder-applied, NOT re-verified by a
fresh tier because neither tier returned REJECT):
1. Both tiers: this memo (A7 evidence path) now exists.
2. ADVERSARIAL F5: `committed_before(..., cited_sha)` / `order --sha` trusted a caller sha over the
   night record. Now the night record's own citation is always read; a differing caller sha returns
   `cited_sha_differs_from_night`, a night citing nothing returns `night_cites_no_manifest` even with
   `--sha`. Mutant M9 (trust caller sha) turns test_g red.
3. CONTRACT F7/F8: tests added for `night_not_committed` and the `order` CLI exit codes (0 / 3); a
   missing manifest file now exits 2 (bad input), not an uncaught exit 1.

## What was built (new files only)

- `scripts/platformkit/eval_gate/corpus_manifest.py` (298 lines): full-file sha256 per closed shard
  `<root>/<sport>/<day>.jsonl`; refuses an open day (as_of < D+1T00:00Z + 300 s), a torn tail, a
  shard moving while hashed, and any link/reparse point from root to shard; canonical deterministic
  bytes with label tokens and POSIX relpaths only; immutable atomic write; verify; cite
  (`covered_days: [D]`); `embed_into_prereg` for a NEW unsealed dict only (refuses `seal`/`sha256`).
- `scripts/platformkit/eval_gate/corpus_manifest_git.py` (78 lines): manifest-before-night check by
  git ancestry and blob content; commit dates never used.
- `tests/platformkit/eval_gate/test_corpus_manifest.py` (297 lines).

## Tests (exact per-file commands, one process each)

    python3 -m pytest tests/platformkit/eval_gate/test_corpus_manifest.py -q   -> 16 passed
    python3 -m pytest tests/platformkit/test_loc_rail_scope.py -q              -> 1 passed

Mutants (restored after each), builder run after corrections, same test file:
M1 head/tail MiB only -> 2 red; M2 skip sha compare -> 2 red; M3 no closed-day check -> 2 red;
M4 non-strict ancestor -> 1 red; M5 refuse only `seal` -> 1 red; M6 ignore unlisted -> 1 red;
M7 write overwrites -> 1 red; M8 absolute-path label -> 1 red; M9 trust caller sha -> 1 red.
Both verifier tiers independently reproduced M1-M8 red at 4f1fc2e2.

Key construct claim, reproduced by the builder test and independently by both tiers: a same-size
single-byte edit at size//2 of a 3 MiB shard leaves S550's `_identity` (exec_quality_audit_io.py:79)
unchanged, and `verify` refuses `shard_rehash_mismatch` (also at a newline byte, and on
truncate-then-repad to equal size). n = 16 test functions (CONSTRUCT; test_g has 6 git topologies).

Must-not-move: `git diff origin/trunk --stat` lists only the four new files plus this memo;
exec_quality_audit_io.py, every PREREG*.json, seal-pinned files and gate values are untouched.
No register row or DESK_STATE edit on this branch.

## NOT VERIFIED

- Manifest committed before the night record on 3 consecutive REAL days (needs the recorder box).
- The tick wiring: the night step writing the `cite()` fields into nights/<D>.json (tick owner, WINDOWS).
- Real-archive hash time and RSS (full ~1 GB/day hash; no data/ here).
- The D+1 OPEN shard the night also reads is not covered (`covered_days` says so).
- Windows reparse-point (junction) refusal branch: cannot run on Linux. Note: the laptop night reads
  the junction view `data/cache/ingame_capture_view_v2`; the tick owner must pass the real roots.
- Python 3.10 behaviour (laptop interpreter); tested on 3.11.15 only.

## NEW GAP candidates (from the verifiers; not fixed here, no id allocated)

- verify does not check `n_shards` / `covered_days` / `day` against the shard list (cited sha covers them).
- `order` does not compare the night's `corpus_manifest_path` with `--manifest`.
- A night record added inside a merge commit, or only on a non-HEAD branch, reads `night_not_committed`
  (fails closed, wrong reason).
- Hard links out of a root are not refused (content change still caught by re-hash).
- Sport directory names have no pattern rule (case-only duplicates on Windows; hidden dirs hashed).
- Quarantine sidecars are compared by name+bytes only (equal-size content change not seen; by A1 design).
- Untested refusal paths: verify-side `torn_tail`, `manifest_unparsed`, `link_in_path` on the write
  target, `citations_required`.

PORTABLE: yes (code and construct tests); adoption is WINDOWS (tick owner).
