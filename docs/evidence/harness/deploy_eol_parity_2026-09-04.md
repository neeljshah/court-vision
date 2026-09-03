# S190 deploy EOL parity - CLOSED AT LIMIT

## Verdict

CLOSED AT LIMIT. The S190 archive-versus-worktree comparison cannot isolate
line-ending conversion at `a3704ca00` in this worktree because seventeen
archive members differ by content from the current checked-out files.

This memo records the required stop result. No emitter, test, JSON summary, or
per-member archive table was added, because the S190 limit expressly requires
the lane to stop rather than fold these content changes into an EOL count.

## Reproduction

- Worktree: `C:/Users/neelj/nba-track-a13`
- Branch: `track-a13`
- Current HEAD: `b50c0ecebf38462db6fa56b542c558934ed04758`
- Trial revision: `a3704ca00672603a073f9586d3ba14e9b7185050`
- Deploy paths: `scripts/platformkit`, `supervisor`, `predict_service`,
  `domains`, `config`, `ops`, `kernel`, `governance`, `data_registry`,
  `improve`, and `frontend`

Before the comparison, `git status --porcelain -- <all eleven deploy paths>`
returned no tracked modifications. The clean status establishes that the
worktree files match its current HEAD; it does not make that later HEAD equal
to the trial revision.

For every modified deploy-path member from
`git diff --name-only --diff-filter=M a3704ca00 HEAD -- <all eleven deploy
paths>`, the check compared raw bytes from `git show a3704ca00:<path>` with
raw worktree bytes. A member is EOL-only only when both byte streams become
equal after deleting carriage-return bytes. All seventeen modified members
remain different after that normalization:

1. `scripts/platformkit/calibration_scoreboard.py`
2. `scripts/platformkit/combo/corpus_cache_sources.py`
3. `scripts/platformkit/eval_gate/close_join.py`
4. `scripts/platformkit/eval_gate/family_bars.py`
5. `scripts/platformkit/foundry/ingame_screen.py`
6. `scripts/platformkit/ingame/gap_effective_n.py`
7. `scripts/platformkit/ingame/ingame_baseline_lock.py`
8. `scripts/platformkit/ingame/ingame_enrichment_runner.py`
9. `scripts/platformkit/ingame/mlb_book_capture.py`
10. `scripts/platformkit/ingame/s88_phase_recal.py`
11. `scripts/platformkit/ingame/s90_microstructure_screen.py`
12. `scripts/platformkit/test_track_daemon_done.py`
13. `scripts/platformkit/test_track_daemon_ledger_denominator.py`
14. `scripts/platformkit/track_daemon.py`
15. `scripts/platformkit/track_daemon_done.py`
16. `scripts/platformkit/track_daemon_ledger.py`
17. `scripts/platformkit/venue_history/game_key.py`

## Limit application

S190 step 1 says to stop and report CLOSED AT LIMIT if any deploy member
differs by content rather than EOL at the trial revision. The count is 17, so
the specified 4,950-member bar is not emitted from this later worktree. Doing
so would combine revision changes with the intended archive smudge comparison.

## Scope retained

- No host was contacted; no file was deployed or copied.
- `.gitattributes`, S21b, S21c, the factory source manifest, pod bootstrap,
  data, the tracking register, and the results ledger were not changed.
- This is a stop memo, not a pod-parity finding.

## Verifier self-check

- B1: No subset metric was published; every qualifying content member is
  named.
- B2-B6: No runtime schema, reader, gate, deployment, or module was changed.
- B7-B10: No sampling, fitted comparison, denominator, or threshold was used.
- Q1-Q5: No scored comparison or threshold result was emitted.
- Q6: This memo uses calibration language only and contains no prohibited
  performance terminology or retracted figures.
