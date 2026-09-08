VERDICT: PREMISE FALSE -- current pod availability has 2, not >=6, G346 LIVE full tracking sections with >=300 evaluated frames; STOP per G356 step 0.

# G356 full-section gate execution premise check (2026-09-08)

Spec: `docs/evidence/tracking/specs/G356_spec.md` VERSION 2026-09-08. Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` A/B/Q. Machine: local worktree `C:\Users\neelj\nba-track-a3`; native OpenSSH performed a read-only pod census. No pod scratch, deployed-tree write, data write, scorer, adapter, test, threshold, flag, or source edit occurred. Eye check: NONE.

## Binding before-condition rerun

Exact local output: `MIN_FRAMES_FOR_METRICS=30 at scripts/platformkit/tracking_harness.py:65`; `G348 fixtures=30; under_floor=30; attempted_frames=13,17,18,20`. The unchanged image evaluator uses unique frames as `n_frames`; the sealed fixture input `docs/evidence/tracking/g348_gate_execution_2026-09-08/fixtures.csv` (5,642 bytes, sha256 `d285664f17239cfba01c7d11b0a4fd60504b85903994889724b8d3c38cd42904`, non-video) has 30/30 `attempted_frames < 30`. Its entity `rows_in_window` is not substituted for that denominator.

The remaining binding condition was recomputed over the WHOLE sealed G346 LIVE set, not a head slice. Input manifest: `docs/evidence/tracking/g346_frozen_video_gate_2026-09-08/sealed_sections.csv` (15,411 worktree bytes; LF-normalised / git-blob sha256 `c4f3b9fb8f4344a146f7e5d1de75a79de74da05e84fb5e58a416b3ea749c4305`; exact worktree sha256 `e47725778702781b5b3b6632b5f6baeb9b3808231bc0c67b45df3974c6a57e01`); it names 50 LIVE source sections. Each derived current tracking path was tested; every present table was opened alone, skipped if >300 MiB (none were), SHA-256ed, and counted by unique `frame` values. Result: `live=50 present=4 qualified=2`.

| G346 LIVE source (bytes, resolution, sha256) | Current tracking table (bytes, sha256) | unique frames | disposition |
| --- | --- | ---: | --- |
| `/workspace/nba-ai-system/data/footage_corpus/basketball__acb-DCA1PAsKVJs_s2840.mp4` (54,939,520; 1920x1080; `d6fd6cb813ff7b7710d56a2aaf956b5305c0d69e6cf8d2c1ef45c31a6b3a3092`) | `/workspace/nba-ai-system/data/tracking/acb-DCA1PAsKVJs_s2840/tracking_data.csv` (1,267; `2d38d0664ebc7bec3685db670655ff86520fec06ebf79a1db50fad3dc2ed8511`) | 1 | below 300 |
| `/workspace/nba-ai-system/data/footage_corpus/basketball__cba-FaMCJR6tFm0_s5062.mp4` (94,601,410; 1920x1080; `c15d55286677f04336d15bf91341cbf67f331a48d9a8b2bef1be357c537d76cb`) | `/workspace/nba-ai-system/data/tracking/cba-FaMCJR6tFm0_s5062/tracking_data.csv` (979,515; `6bc9302b26b3f3999d5c3126e4cdb7b0650dc7f6cb5c05f4b0f6a35c52575888`) | 600 | qualifies |
| `/workspace/nba-ai-system/data/footage_corpus/basketball__lnb-ouDVA0vM20g_s1379.mp4` (66,705,562; 1920x1080; `8914fc9cf7aba7e461af02cb5d12cc97fd91689ca70844504589d308f2efc17c`) | `/workspace/nba-ai-system/data/tracking/lnb-ouDVA0vM20g_s1379/tracking_data.csv` (1,656,594; `381b262b8c70fdbcfe658dbe75d7e7d8fae8e7c18d2814379e9f1a1876aa2ca5`) | 1000 | qualifies |
| `/workspace/nba-ai-system/data/footage_corpus/nba__0022500081_s357.mp4` (29,931,165; 1280x720; `079aa75b62764c3a1ecb7951b36a53f8c82e5e9b3c5e450ce488c4529a1d8852`) | `/workspace/nba-ai-system/data/tracking/0022500081_s357/tracking_data.csv` (1,512; `a66e7f7b76d48759cc66d646ccb43ce5398227a6ea554da01f70d90ba127dbdc`) | 1 | below 300 |

The other 46 sealed G346 LIVE source identities have no matching current tracking table. The two qualifiers span two games, also below the required four. The G348 source-video identities `0022400909`, `0022401198`, `wnba_02`, and `wnba_05` have no current matching file in `/workspace/nba-ai-system/data/footage_corpus`; their existing tracking-table counts cannot substitute for a G346 LIVE classification.

No scored comparison occurred, so Q1 preregistration/seal, Q2 ledger charge, Q4 evaluator state, Q5 corpus claim, Q9 differential archive, and delta sign convention are N/A. No `RESULTS_LEDGER.md` or allocation register row was written under the user instruction not to touch a ledger or register. A later lane must first rerun this full-set availability condition after corpus rotation, then make a standalone LF-normalized preregistration commit before any scoring. Exact future availability command: native OpenSSH with the existing pod config, serially open each `sealed_sections.csv` LIVE-derived `tracking_data.csv`, then require unique `frame >= 300` on >=6 sections from >=4 games.

Landing: sandbox denied this worktree's Git index lock, so the orchestrator must commit this single memo with an explicit pathspec using `lane_commit`; no commit SHA exists in this lane.

Wall time: 2026-09-08 local premise check, approximately 5 minutes. Local CSV seals are LF-normalized; remote table SHA-256s are from current bytes. Calibration language only; no delta is claimed.

2026-09-08 lander: ACCEPT WITH CORRECTIONS (codex-sol); the >= 300 evaluated-frame floor was the orchestrator's wrong scaling for the daemon stride (about 180 frames per 130 s section); successor G358 (fc98f3db1) uses >= 150; NEW GAPS in the ledger (two source videos rotated away while their tracking tables remained).

## NOT VERIFIED

- No six-section/full-duration gate execution, planted-arm detection, duration table, Wilson interval, diagnosis, adapter, or adapter test was run because the binding premise is false.
- The pod corpus is rotating; its later availability may differ.
- No video pixels or table resolution fields were opened; listed resolutions are the sealed G346 manifest values.
- No G348 game can presently be established as G346 LIVE from the current footage corpus.
