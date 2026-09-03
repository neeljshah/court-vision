GAP G181 | sport all | worktree a2 | log cx_g181_unadjudicated_games
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it (A2, A3, A7, B3, Q8); self-check B.
RAILS: heavy work ON THE POD under nohup, batched collection, never poll. Read one store at a time,
never a whole store over 300 MB. NEVER kill, restart or deploy over the pod daemon or its keeper.
Never launch powershell. Never write under `data/` in the repo. Never paste a credential-shaped string
into a memo, even a fake fixture -- describe it instead. ASCII only.

THE SITUATION. Two source videos on the pod are held indefinitely because their tracking never
produced a durable result, and they are the ONLY corpus sources the retention pass may not delete:

  - `data/footage_corpus/wnba__wnba_01.mp4` -- 2.73 GB
  - `data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` -- 1.70 GB

Neither has a `data/tracking/<game_id>/tracking_data.csv` nor a `harness_verdict.json`. Their ledger
rows carry `coverage_pct = None` and no failure head, which is the "thin" outcome. **A FAIL with a
durable verdict is a finished result; these are unfinished work**, which is why B3 forbids deleting
them and why they sit on a 50 GB volume costing 4.4 GB.

Both route through `run_clip.py` (they are in `track_daemon.CLIP_SPORTS`), NOT through the tennis
adapter path.

DO THIS:
  (a) Q8 FIRST: re-verify the premise. Confirm from the pod that each file exists, that no table and
      no verdict exist for it, and quote its ledger row verbatim. **If a verdict has appeared since
      this spec was written, say so and STOP** -- the row closes and the retention pass will handle
      the file.
  (b) Establish WHY the previous run produced nothing. Read the job log beside the staged file if one
      survives, and the daemon log around that game id. `thin rows=0` and a `None` coverage are the
      symptoms; find the cause and quote it. This is the deliverable even if nothing is re-tracked.
  (c) Only if (b) shows a re-run is worth attempting: re-track ONE of them on the pod under
      `nohup ... > log 2>&1 &`, using a scratch game id you name in the memo so nothing existing is
      overwritten, and collect the result in ONE batched ssh. Do NOT stage into
      `data/footage_bridge` -- the daemon owns that directory and would race you.
  (d) Report rows, distinct emitted frames, decoded frames and the harness verdict for whatever you
      produce. Report the coordinate declaration and the solved-geometry share SEPARATELY, per G152:
      the declaration is stamped and is not evidence of recovered geometry.
  (e) State plainly whether these two files can ever produce a durable verdict, or whether they should
      be recorded as permanently unfinished. **You may NOT delete them either way** -- that is the
      orchestrator's call under the user's authorization, and B3 governs.

DO NOT change any threshold, bar, the coordinate contract, the eligibility definition, or a verdict.
Do not modify `src/` (human-gated). Do not delete any footage.

ACCEPTANCE RULE:
  metric        = per file: existence, table/verdict absence, the verbatim ledger row, the cause of
                  the thin outcome quoted from a log, and any re-track's rows/frames/verdict
  before        = two sources held indefinitely with no durable result and no diagnosed cause
  bar           = NO pass bar. "The cause is X and a re-run cannot fix it" is a FULL SUCCESS and is
                  the most useful outcome, because it lets the orchestrator decide about 4.4 GB.
  n             = 2 files (CONSTRUCT, exhaustive)
  eye check     = REQUIRED only if you produce a table: 5 frames sampled EVENLY (never a head slice)
  must not move = every threshold and bar, the coordinate contract, the eligibility definition,
                  every verdict, `src/`, and every footage file
EVIDENCE: docs/evidence/tracking/g181_unadjudicated_games_2026-09-03.md with the per-file findings,
the quoted cause, any re-track result, and a NOT VERIFIED list. **COMMIT THE MEMO BEFORE YOU REPORT
(A7)** -- lanes today exited 0 having committed nothing, and an EXIT:0 is not evidence of a commit.
TEST: one per-file test only if you add code; run it alone. NEVER a full pytest.
COMMIT: explicit pathspec only, in a2, no push. Report the sha.
NEVER PARK.
