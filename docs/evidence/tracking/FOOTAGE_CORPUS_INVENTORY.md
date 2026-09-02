# Footage corpus inventory -- where the video actually is

Generated 2026-09-02 from the pod. **THE CORPUS LIVES ON THE POD, NOT LOCALLY.**

- Pod `/workspace/nba-ai-system/data/footage_corpus/`: **63 clips, 6.6 GB**
- Local main repo `data/footage_corpus/`: **2 file(s)**
- A fresh git worktree: fewer still, and `data/` is gitignored so it is never cloned

**Consequence for lanes:** any measurement that decodes video frames MUST run on the
pod. Three lanes (G25b, G33b, G44b) returned NOT VALIDATED on 2026-09-02 because they
looked for source clips in a local worktree that never had them. That is an
infrastructure gap, not a lane failure. Check this table for the clip you need and
design the measurement to run where the clip is.

## What was fixed 2026-09-02

`scripts/platformkit/tracking/worktree_data_links.py` did not link `footage_corpus` or
`tracking` at all, so a codex worktree saw neither source clips nor tracking tables. Both are
now in `RELS`, and all 8 worktrees have been provisioned. After the fix each worktree sees the
local main corpus (4 clips) and, where no stale directory shadows the junction, all 418 tracking
tables.

Still outstanding: `a3`, `a5` and `a7` contain a REAL `data/tracking/` directory that shadows the
junction, so they see 1 file instead of 418. Clearing it needs a directory removal under `data/`
which is guarded; do it deliberately rather than in passing. It does NOT affect footage, which is
linked correctly in all 8.

Linking is necessary but not sufficient: the local corpus is 4 clips against the pod's 63. A lane
needing any other clip must run on the pod.

| sport | clip | MB | in local main repo |
|---|---|---:|:---:|
| football | `football__football_20pezoC5jRQ.mp4` | 67.6 | no |
| football | `football__football_34GmmlakBYU.mp4` | 61.3 | no |
| football | `football__football_5x9vPq9HsTI.mp4` | 82.7 | no |
| football | `football__football_B7znSVfBnM4.mp4` | 54.3 | no |
| football | `football__football_gek9fXGlwas.mp4` | 63.0 | no |
| football | `football__football_h-_3BmAh9po.mp4` | 57.9 | no |
| football | `football__football_wHZt1eY3A9s.mp4` | 233.0 | no |
| football | `football__football_wHZt1eY3A9s_1080p.mp4` | 141.5 | no |
| football | `football__giants_jets_format96_1080p.mp4` | 141.5 | no |
| kbo | `kbo__kbo_8yxSFxuR2Lk.mp4` | 33.6 | no |
| kbo | `kbo__kbo_9Hv-cd-BmSY.mp4` | 47.0 | no |
| kbo | `kbo__kbo_FDSWjM_OaTs.mp4` | 44.1 | no |
| kbo | `kbo__kbo_Lh8n_DUXyGE.mp4` | 37.4 | no |
| kbo | `kbo__kbo_W-tKSex-WPU.mp4` | 41.5 | no |
| kbo | `kbo__kbo_ahHGpSJWcIU.mp4` | 63.3 | no |
| kbo | `kbo__kbo_bGQwZl43E9Y.mp4` | 33.7 | no |
| kbo | `kbo__kbo_lIxmDQyQDtc.mp4` | 33.3 | no |
| kbo | `kbo__kbo_lrK_Hv6BEE0.mp4` | 89.5 | no |
| kbo | `kbo__kbo_qLQbGFQ0-EQ.mp4` | 31.7 | no |
| kbo | `kbo__kbo_tzC71aneg9c.mp4` | 31.5 | no |
| mlb | `mlb__mlb_2iosUkpL0Bc.mp4` | 141.4 | no |
| mlb | `mlb__mlb_3Oc4S_1np98.mp4` | 85.5 | no |
| mlb | `mlb__mlb_5IA4jaKNOYg.mp4` | 32.0 | no |
| mlb | `mlb__mlb_7T-rpI5l0ro.mp4` | 38.6 | no |
| mlb | `mlb__mlb_ARtRmUHC7dw.mp4` | 119.8 | no |
| mlb | `mlb__mlb_FGtFanovws4.mp4` | 22.2 | no |
| mlb | `mlb__mlb_NiSezRTvsew.mp4` | 47.5 | no |
| mlb | `mlb__mlb_PPj97yvNGOo.mp4` | 67.8 | no |
| mlb | `mlb__mlb_dVNOESziFWQ.mp4` | 99.5 | no |
| mlb | `mlb__mlb_gMm3EODDb6w.mp4` | 86.7 | no |
| mlb | `mlb__mlb_ptIBgr6U1Y8.mp4` | 185.0 | no |
| mlb | `mlb__mlb_x6YpMlNYbrU.mp4` | 52.2 | no |
| ncaa_basketball | `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` | 72.6 | no |
| ncaa_basketball | `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p.mp4` | 313.1 | no |
| ncaa_basketball | `ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss.mp4` | 66.1 | no |
| ncaa_basketball | `ncaa_basketball__ncaa_basketball_sRtHQbywiTE.mp4` | 232.4 | no |
| ncaa_basketball | `ncaa_basketball__ncaa_basketball_tiUvyvWOCxo.mp4` | 236.0 | no |
| ncaa_basketball | `ncaa_basketball__ncaa_basketball_zqBCKovJCQU.mp4` | 446.3 | no |
| npb | `npb__npb_01_720p.mp4` | 106.8 | no |
| npb | `npb__npb_3PwJwWdTMek.mp4` | 201.4 | no |
| npb | `npb__npb_HQfhD5Iwm7U.mp4` | 60.6 | no |
| npb | `npb__npb_V3FrwLVwCpA.mp4` | 71.0 | no |
| npb | `npb__npb_jm2Ocr-LAtc.mp4` | 60.6 | no |
| npb | `npb__npb_kqPv-_WwWLk.mp4` | 50.8 | no |
| soccer | `soccer__soccer_AgspyOj5BPk.mp4` | 133.6 | no |
| soccer | `soccer__soccer_DdnvC6-PGYY.mp4` | 146.7 | no |
| soccer | `soccer__soccer_EKhrdU9bVZA.mp4` | 133.7 | no |
| soccer | `soccer__soccer_cKXZysISV4w.mp4` | 126.9 | no |
| soccer | `soccer__soccer_kSgNjoaqCpI_1080p.mp4` | 252.5 | no |
| tennis | `tennis__tennis_06.mp4` | 110.7 | no |
| tennis | `tennis__tennis_07.mp4` | 29.5 | no |
| tennis | `tennis__tennis_08.mp4` | 29.3 | no |
| tennis | `tennis__tennis_09.mp4` | 84.9 | yes |
| tennis | `tennis__tennis_10.mp4` | 92.8 | no |
| tennis | `tennis__tennis_3x3eEWCZmWQ.mp4` | 69.7 | no |
| tennis | `tennis__tennis_459iho5_AFs.mp4` | 71.6 | no |
| tennis | `tennis__tennis_nyYk2nPZAwY.mp4` | 65.8 | no |
| tennis | `tennis__tennis_nyYk2nPZAwY_720p.mp4` | 261.7 | yes |
| wnba | `wnba__wnba_01.mp4` | 145.1 | no |
| wnba | `wnba__wnba_01_1080p.mp4` | 293.8 | no |
| wnba | `wnba__wnba_02.mp4` | 132.2 | no |
| wnba | `wnba__wnba_04.mp4` | 129.5 | no |
| wnba | `wnba__wnba_05.mp4` | 130.3 | no |

## Clips per sport (pod)

| sport | clips |
|---|---:|
| football | 9 |
| kbo | 11 |
| mlb | 12 |
| ncaa_basketball | 6 |
| npb | 6 |
| soccer | 5 |
| tennis | 9 |
| wnba | 5 |
