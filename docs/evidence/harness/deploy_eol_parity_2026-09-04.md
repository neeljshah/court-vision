# S190 deploy EOL parity - CLOSED AT LIMIT

## Verdict

CLOSED AT LIMIT. The S190 archive-versus-worktree comparison cannot isolate
line-ending conversion at `a3704ca00` in this worktree because twenty-two
archive members differ by content from the current checked-out files.

This memo records the required stop result. No emitter, test, JSON summary, or
per-member archive table was added, because the S190 limit expressly requires
the lane to stop rather than fold these content changes into an EOL count.

## Reproduction

- Worktree: `C:/Users/neelj/nba-track-a13`
- Branch: `track-a13`
- Current HEAD: `29f0173cbfe674f34d4af890572a07a8031bb475`
- Trial revision: `a3704ca00672603a073f9586d3ba14e9b7185050`
- Deploy paths: `scripts/platformkit`, `supervisor`, `predict_service`,
  `domains`, `config`, `ops`, `kernel`, `governance`, `data_registry`,
  `improve`, and `frontend`

Before the comparison, `git status --porcelain -- <all eleven deploy paths>`
returned no tracked modifications. The clean status establishes that the
worktree files match its current HEAD; it does not make that later HEAD equal
to the trial revision.

The current full census streamed every regular member from `git archive
a3704ca00 -- <all eleven deploy paths>` and compared its bytes with the same
worktree path. The results are `n=4,950`, `identical=4,926`, `eol_only=2`,
`content=22`, and `absent=0`. Thus `raw_differing=24` and
`CRLF-normalised_differing=22`. A member is EOL-only only when both streams
are equal after CRLF-to-LF normalization.

Every raw-differing archive member is named below:

1. content: `scripts/platformkit/calibration_scoreboard.py`
2. content: `scripts/platformkit/combo/corpus_cache.py`
3. content: `scripts/platformkit/combo/corpus_cache_sources.py`
4. content: `scripts/platformkit/eval_gate/close_join.py`
5. content: `scripts/platformkit/eval_gate/family_bars.py`
6. eol_only: `scripts/platformkit/foundry/ingame_grammar_nba_pairs.py`
7. content: `scripts/platformkit/foundry/ingame_screen.py`
8. eol_only: `scripts/platformkit/foundry/ingame_screen_nba.py`
9. content: `scripts/platformkit/ingame/gap_effective_n.py`
10. content: `scripts/platformkit/ingame/ingame_baseline_lock.py`
11. content: `scripts/platformkit/ingame/ingame_enrichment_runner.py`
12. content: `scripts/platformkit/ingame/mlb_book_capture.py`
13. content: `scripts/platformkit/ingame/s88_phase_recal.py`
14. content: `scripts/platformkit/ingame/s90_microstructure_screen.py`
15. content: `scripts/platformkit/ops/pod_bootstrap.sh`
16. content: `scripts/platformkit/ops/pod_bootstrap_check.py`
17. content: `scripts/platformkit/pod_pull_sync.sh`
18. content: `scripts/platformkit/test_track_daemon_done.py`
19. content: `scripts/platformkit/test_track_daemon_ledger_denominator.py`
20. content: `scripts/platformkit/track_daemon.py`
21. content: `scripts/platformkit/track_daemon_done.py`
22. content: `scripts/platformkit/track_daemon_ledger.py`
23. content: `scripts/platformkit/tracking/worktree_data_links.py`
24. content: `scripts/platformkit/venue_history/game_key.py`

## Limit application

S190 step 1 says to stop and report CLOSED AT LIMIT if any deploy member
differs by content rather than EOL at the trial revision. The current content
count is 22, so the specified 4,950-member bar is not emitted from this later
worktree. Doing so would combine revision changes with the intended archive
smudge comparison.

## ATTEMPT 2

The verifier's candidate census reported `raw_differing=20`, `eol_only=2`,
`content=18`, and `absent=0` over `n=4,950`. This current census is
`raw_differing=24`, `eol_only=2`, `content=22`, and `absent=0` over the same
denominator. The four additional current content members are
`scripts/platformkit/combo/corpus_cache.py`,
`scripts/platformkit/ops/pod_bootstrap.sh`,
`scripts/platformkit/pod_pull_sync.sh`, and
`scripts/platformkit/tracking/worktree_data_links.py`. The current HEAD is
newer than the verifier candidate; the clean deploy-path status confirms these
are revision differences, not uncommitted deploy-path modifications.

Before: raw 20, EOL-only 2, content 18, absent 0, identical 4,930.

After: raw 24, EOL-only 2, content 22, absent 0, identical 4,926.

## NOT VERIFIED

- The current bytes, line endings, checkout revision, and Git configuration of
  any pod were not verified: no host was contacted.
- No deployment, copy, transport, or checkout operation was performed, so its
  effect on archive bytes was not verified.
- Runtime execution or shebang handling on a pod was not verified.
- The historical 338-member pure-EOL premise was not reproduced in this later
  worktree; the 22 named content members prevent an isolated EOL result here.
- The S21b and S21c recorded values were not recomputed or changed here.
- No normal emitter, focused emitter test, JSON summary, or per-member table
  was created because the limit requires stopping before that change.

## Verifier self-check

- B1: No subset metric was published; every qualifying content member is
  named.
- B2-B6: No runtime schema, reader, gate, deployment, or module was changed.
- B7-B10: No sampling, fitted comparison, denominator, or threshold was used.
- Q1-Q5: No scored comparison or threshold result was emitted.
- Q6: This memo uses calibration language only and contains no prohibited
  performance terminology or retracted figures.
