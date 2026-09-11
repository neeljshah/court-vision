# G393 Leading-Hyphen Game-ID Parser Proposal

VERDICT: CLOSED AT LIMIT -- bar 2 clause "all 6 option-shaped values preserved" measured 5/6. Bars 1 and 3 met in full. No candidate caller form is eligible on the SEALED control bar; `--` is unrecoverable as an optional's value through this argparse in every form tested, a parser-level boundary the preregistration's caller-only change cannot reach.

Machine (S1): PC only, worktree `C:/Users/neelj/nba-track-a14`, branch `track-a14`. No pod, no GPU, no video decode, no production main imported, no deploy, no register write.

## PREMISE (step 0, Q8) -- TRUE

Code: `scripts/platformkit/track_daemon.py:95-97` passes the split pair `"--game-id", game_id`; `scripts/run_clip.py:424` declares `--game-id` with `default=None` and no `nargs`. Both re-read this session.

Affected share, over whole sets (S2), never head rows: ledger-snapshot counts withdrawn (the snapshot is not landable and unavailable to the verifier); G375 `g375_corpus_sport_purity_2026-09-10/census.csv` 3 / 1031 rows = 0.0029.

 Those 12 rows come from only 3 video stems (`-5l407QKuVk`, `-Oa_BpdVT64`, `-n4iviRLtsU`), so the effective unit count is 3, not 12; stated as CONSISTENT WITH the parser defect, never as its proof (B11).

**Re-run of the sealed replay vs the pre-seal run.** The codex PREPARE lane produced its receipts BEFORE the seal commit `e36198383`. The sealed replay was re-run this session from the committed modules: **byte-identical, 73 / 73 files** (`argv.jsonl`, `cases.csv`, `parsed_before_after.jsonl`, `failure_stderr.txt`, `caller_census.csv`, `source_hashes.json`, `summary.json`, all 66 `eye_cards/`). The pre-seal run is preserved under `pre_seal_run/`, superseded and not deleted. Seal verified: recomputed SHA-256 of every LF byte above the seal line equals `4787b4c8477a66fe8427ca0d46e1ed5b9fafa4ec776972e05f74bfe976f20d6c`.

## Measured bars

| bar | sealed value | measured | verdict |
|---|---|---|---|
| 1. Leading-id parse recovery | 30/30 recover exact value; reproduce all original failures | equals form 30/30; split baseline 0/30, all 30 reproduce `error: argument --game-id: expected one argument` (exit 2) | MET |
| 2a. Ordinary invariance | 30/30 equal namespaces | 30/30 identical namespaces, equals vs split | MET |
| 2b. Option-shaped controls | all 6 preserved | equals form 5/6 | **NOT MET** |
| 3. Patch isolation and identity | one caller hunk; source hashes verified; no production writes | one hunk at `track_daemon.py:95-97`; hashes recorded; nothing applied in the repo | MET |
| must not move | identifier bytes, `--frames 3000`, `--no-show`, space-bearing paths | 68/68 cases: zero unrelated drift in every form that parsed | MET |

## Candidate forms (30 real leading ids + 6 sealed controls + 2 extra controls)

| form | leading | ordinary | sealed controls | extra controls | eligible |
|---|---|---|---|---|---|
| `split_baseline` (landed) | 0/30 | 30/30 | 2/6 | 0/2 | no -- this is the defect |
| `dashdash_separator` | 0/30 | 0/30 | 0/6 | 0/2 | no |
| `equals_single_token` | 30/30 | 30/30 | 5/6 | 2/2 | no -- bar 2b |

Proposal-rejection findings, independently reproduced:

1. The `--` separator form is rejected outright. `--` ends option parsing for POSITIONALS; it cannot carry an optional's value, so `["--game-id", "--", gid]` fails all 68 cases including ordinary ids. It is strictly worse than the landed caller.
2. The `--` VALUE is rejected as sealed, and its failure is SILENT, which is worse than the split form's loud one. `--game-id=--` exits 0 and binds `game_id` to `[]`: argparse strips the first `--` out of an explicit value in `_get_values`. The split form at least exits 2. No caller-side argv arrangement recovers this value; only a parser-side change in `scripts/run_clip.py` could, and that file is human-gated and outside this row's sealed scope.
3. The two extra controls added by the finisher (`-x`, and an id equal to the valid option name `--video`) are both preserved by the equals form and both fail the split form. They are supplementary and did not relax the sealed bar (Q3).

The named PROPOSED diff `docs/research/organization-sprint/PROPOSED_g393_game_id.diff` therefore ships CONDITIONAL, not accepted: it is correct for all 30 real leading ids and for 7 of the 8 option-shaped controls, and carries the `--` limitation above. It is APPLIED NOWHERE. The scratch copies under `C:/Users/neelj/AppData/Local/Temp/g393_scratch/` are the only places any form was written; the equals copy hashes `faee2095f9e6ee78390fcb2d1777e8ee27b1c5fa36caf306e558b5fc4337ee08`, matching the in-memory proposal recorded in `source_hashes.json`.

## Caller census (file:line) and eye check

14 affected lines in 12 files build a run_clip game-id argument from a variable and would fail identically. Scope: files naming `run_clip`, excluding `add_argument` declaration lines. Full table: `caller_census_lines.csv`. Per METHOD step 7 the 13 lines other than `track_daemon.py:96` are filed as **NEW GAP**, not fixed here.

`scripts/platformkit/track_daemon.py:96` (this row's hunk); `scripts/platformkit/footage_cycle.py:154`; `scripts/platformkit/footage_bridge.py:500` (a SHELL STRING, `--game-id %s`, so a leading-hyphen id is both a flag and a quoting hazard); `scripts/ingest_one_game.py:116,155`; `scripts/master_pipeline.py:266`; `scripts/reprocess_20_games.py:79`; `scripts/reprocess_tracking_only.py:75`; `scripts/run_backfill.py:172`; `scripts/run_data_collection.py:199`; `scripts/run_phase_g.py:441`; `scripts/validate_tracker_e2e.py:81`; `scripts/platformkit/tracking/g310_native_input_arm.py:128,214`.

Eye check: 66 sealed `eye_cards/` (all 30 leading, all 30 ordinary, all 6 controls) plus 13 per-form `form_cards/`, sampled EVENLY over the leading set (ordinals 1, 13, 25, 37, 49) plus every control (A3, no head slice). Q6: 166 text artifacts scanned with patterns built from character codes, 0 non-opaque hits (`forms_summary.json`).

Incidental finding: the spec's line "current master run_clip differs from G380's deployed digest" is a line-ending artifact, not a code difference. The working copy is CRLF (`1e490eab...`, 37050 bytes); the git blob and the deployed digest are LF (`ccd08d32...`, 36229 bytes); the 821-byte gap is exactly the CRLF count. Python text-mode reads normalize to LF, so the replay hashed the same bytes the pod runs. Same for `track_daemon.py` (`ee425ee5` CRLF / `9747d9a0` LF, 438-byte gap).

## NOT VERIFIED

- Any live routing, tracking, decoding, rating or production behavior. This row makes no tracking-quality claim and no live-fix claim.
- That applying the diff would change the 12 thin ledger rows. The thin status is CONSISTENT WITH the defect over 3 stems; it is not attributed.
- The pod-deployed caller digest, and any composition with G380 at authorized deployment (METHOD step 8, a19's finisher).
- The 13 sibling caller lines, which are surveyed but untested.

Sign convention: this parser-only construct review produces no loss delta and no scored comparison. Wall time: 34 minutes. Artifact digests: full 64-hex SHA-256 with the path on the same line for every artifact above, including the preregistration seal line, in `g393_leading_hyphen_game_id_2026-09-11/digests.txt`. Orchestrator note (2026-09-11): the PROPOSED-CONDITIONAL diff is ALSO archived inside this evidence dir as PROPOSED_g393_game_id.diff (SHA-256 a3d5b960576b5ab7485e62513a2181052681eb4aeacaea45c0bc3630c201c691 docs/evidence/tracking/g393_leading_hyphen_game_id_2026-09-11/PROPOSED_g393_game_id.diff), because docs/research/ is local-only and does not land; the diff is applied nowhere. Fix 1d (2026-09-11, orchestrator, landing pre-check): the caller census walk now skips .claude/, .codex/, .agents/ and restored_sources/ (stale agent worktrees under .claude/worktrees in the main repo inflated the census; the 14 real caller lines are unchanged). No measurement changed.
