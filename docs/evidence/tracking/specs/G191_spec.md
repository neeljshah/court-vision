GAP G191 | sport all | worktree a7 | log g191_per_sport_baseline
**MEASUREMENT ONLY. Change NO code.** No bar, threshold, gate, coordinate contract or verdict.
`src/` is HUMAN-GATED: run it, never edit it.

**S1 MACHINE: RUN EVERYTHING ON THE POD.** 16 GB local box, other lanes live, two RAM guards already
fired today. Pod has an RTX 3090, 24 GB, and is measurably under-used.

**S3 DEPENDENCY:** G189 (ACCEPT, landed) established the `run_clip.py` route is NON-DETERMINISTIC --
1,104 to 1,549 rows across five identical runs. **That is why this row reports DISTRIBUTIONS and
never a single run.** A single-run number here would be an automatic reject.

CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read in full, self-check section B.

WHY: **0 of 40 pod ledger rows pass and there is no per-sport baseline to improve against.** Before
any component is replaced, we need to know what each sport currently produces, as a distribution,
with its footage properties recorded. This row is the baseline every later comparison uses.

PREMISES VERIFIED BY THE ORCHESTRATOR BEFORE DISPATCH (S2) -- the pod corpus, exact and complete:

| path (under `/workspace/nba-ai-system/`) | bytes | resolution | frames |
|---|---:|---|---:|
| `data/footage_corpus/wnba__wnba_01.mp4` | 2,931,985,407 | 1920x1080 | 174,430 |
| `data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` | 3,580,059,573 | 1920x1080 | 205,444 |
| `data/footage_corpus/soccer__soccer_dnR5C6WLJI4.mp4` | 3,373,680,742 | 1920x1080 | 250,200 |
| `data/footage_corpus/baseball__kbo_06.mp4` | 642,203,161 | 1920x1080 | 53,196 |
| `data/footage_corpus/baseball__kbo_07.mp4` | 648,964,602 | 1920x1080 | 54,180 |
| `data/footage_corpus/baseball__npb_02.mp4` | 895,692,406 | **640x360** | 411,191 |
| `data/footage_corpus/baseball__npb_03.mp4` | 3,093,450,494 | 1280x720 | 430,371 |
| `data/footage_corpus/football__football_Z8Ezd95NnjM.mp4` | 2,493,550,705 | 1280x720 | 288,230 |
| `data/footage_corpus/football__football_yahhMkUWd7c.mp4` | 2,567,704,906 | 1280x720 | 303,583 |
| `data/footage_corpus/mlb__mlb_nLoG6gvC-Nk.mp4` | 1,066,801,340 | 1280x720 | 220,624 |

Re-confirm this listing cheaply before starting; if it differs, report the difference and use what is
actually there.

THE TASK: for **one clip per sport** (wnba, ncaa_basketball, soccer, baseball, football, mlb -- six
runs' worth of sports), run the existing bounded route **3 times** and report a DISTRIBUTION:

    python3 scripts/run_clip.py --video <path> --frames 1200 --no-show --skip-features --data-dir <fresh per run>

Per sport report, over the 3 runs: player rows (min/median/max), distinct player-row frames,
distinct attempted gameplay frames (**this is the ELIGIBLE DENOMINATOR** -- name it, never the
`--frames` argument), declared `coordinate_space`, and wall time. Choose the 1920x1080 clip where a
sport has one; for baseball pick `kbo_06` and say why. **Record `npb_02` as 640x360 in your notes
even though you are not running it** -- resolution is a confound any later comparison must respect.

Then answer, per sport, in one line each: **what does this sport currently produce, and what is the
first thing that stops it being scorable?** Ground each answer in the landed rows -- G185 established
that baseball, football and soccer take an uncalibrated preservation path by configuration
(`adapter_run.py:47`), so for those the honest answer is about the route taken, not about quality.

MANDATORY:
  - **B11: no single-run number may be quoted as a property of any sport.** Every figure is a range
    or a median over 3 runs, and says so.
  - **B13: store per-run records** in the artifact, not just the summary table.
  - **A9: name each source's full path, byte size and resolution** in the memo.
  - Report pod GPU utilization and memory at each run start, and total pod wall time consumed.
  - If a sport's run FAILS, that is a result: report the traceback and move to the next sport. Do not
    stop the whole row for one failing sport.

ACCEPTANCE RULE:
  metric        = per-sport 3-run distribution of rows, frames and coordinate_space, plus a one-line
                  blocker statement per sport
  before        = 0 of 40 ledger rows pass and no per-sport baseline exists to improve against
  bar           = NO pass bar. A sport that produces nothing, or crashes, is a FULL result. Do not
                  tune, retry-until-good, or select the best of three -- report all three.
  n             = 3 runs per sport (DISTRIBUTION, mandated by G189); 6 sports
  eye check     = none required; this is a counts-and-routes baseline, and G189 established that
                  single-run renders are not evidence about the system
  must not move = every bar, gate, threshold, coordinate contract, verdict, `src/`, the pod daemon
                  and keeper, the corpus (delete NOTHING -- 10 reader-required sources were already
                  lost to premature deletion, G183)
EVIDENCE: docs/evidence/tracking/g191_per_sport_baseline_2026-09-03.md with the per-sport
distribution table, per-run records, the blocker lines, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
TEST: only if you add a harness; then a per-file test, pasted. NEVER a full pytest.
POD: run your jobs there, sequentially so they do not contend. Never kill, restart or deploy over the
daemon or keeper, and do not wait on the daemon -- it is slow by a known defect (G186).
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
