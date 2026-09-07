# S314 TEACH-0 teacher packet census -- 2026-09-07 (CENSUS HALF ONLY; no alignment, no qualification, no fit)

VERDICT: BLOCKED -- the S314 binding before-condition does NOT hold today. No packet was staged, no interval was aligned, nothing was fitted. This is the census-first
branch of S314 (spec `docs/evidence/tracking/specs/S314_spec.md`), never its alignment half. Calibration language only; no claim about prediction quality is made here.
Recipe: `docs/research/astra_teach_feasibility_2026-09-07.md` section "Eligible denominator census recipe". The local python block ran as written with one added existence
guard on the three ledgers; the pod block was extended to also count unique game ids, unique frames and the column list. Raw records:
`docs/evidence/harness/S314_census_local_2026-09-07.jsonl` (3,058 records, local checkout `C:/Users/neelj/nba-ai-system`) and `S314_census_pod_2026-09-07.jsonl`
(31 records, pod `/workspace/nba-ai-system`, read-only, snapshot `2026-09-07T22:29:50Z`). Nothing on the pod was written, moved or stopped.

## Nested counts (strict nesting: footage -> API -> outcome -> qualified)
| stage | local | pod | union by official id | first 3 ids |
|---|---|---|---|---|
| N_footage | 351 | 3 official ids (12 segment dirs; 31 CSVs, 96,792 rows) | 351 | 0022400625, 0022400687, 0022400690 |
| N_API (PBP file present) | 19 | 0 | 19 | 0022400625, 0022400687, 0022400690 |
| N_outcome (dated home_win) | 19 | 3, but they fail at the API stage | 19 | 0022400625, 0022400687, 0022400690 |
| N_qualified | UNKNOWN | UNKNOWN | UNKNOWN | -- (verified lower bound = 0; pending alignment) |

Pod official ids: 0022500575, 0022500594, 0022500630 (first 3 = all 3). Each already has a local canonical directory, so the union by official id is 351, NOT 354. Pod rows
inside official-id segments: 27,525 of 96,792. Local outcome dates span 2025-01-23 .. 2025-10-24; the three pod ids carry 2026-01-14 / 2026-01-17 / 2026-01-22. Local box
files for the 19: 6 traditional (0022500002, 0022500004, 0022500005, 0022500006, 0022500090, 0022500099 -- all `game_status` "Final") and 13 with `boxscore_adv_*` only.

## Exclusions and aliases (every drop counted by reason)

- 408 immediate directories under `data/tracking`: 47 have no `tracking_data.csv`; 361 have one; of those 1 has a header but no data record and 10 have NON-canonical names
  -> 351 canonical ten-digit directories with a first data record = N_footage(local).
- Non-canonical local names (aliases and non-game tables, NOT games): `0022500966.f136`, `0022500966.f298`, `G83_table_0022400625`, `G83_table_0022400687`,
  `G83_table_0022400690`, `G83_tennis_09` and 4 more. `0022500966` appears ONLY as a frame-slice alias and has no canonical directory; it needs a reviewed crosswalk first.
- Pod: 34 directories, 31 with a CSV, 3 without (`0022500594_s1500`, `0022500594_s9300`, `cavs_broadcast_2025`). 12 are official-id segments `<gid>_s<offset>`; 8 are
  NBA-named without an official id (`bos_mia_playoffs`, `den_phx_2025`, `g220c_jh3fnwMi7dM`, `gsw_lakers_2025`, `mem_nop_2025`, `mia_bkn_2025`, `mil_chi_2025`,
  `okc_dal_2025`) and are EXCLUDED until an official-ID crosswalk is proved; 11 are NCAA/WNBA and are EXCLUDED -- never pooled under NBA.
- `data/tracking/footage_bridge_ledger.jsonl` line 125 is malformed JSON (reported, never silently dropped). Staged and duplicate ledger records are not games. Both local
  `data/tracking_reports/basketball` reports carry `passed: false`.
- TWO SAME-NAME STORES DIFFER: the local `data/tracking/<gid>/tracking_data.csv` for the three pod official ids is the OLD producer schema (no `coordinate_space`, no
  `source_fps`), while the pod segment CSVs carry both. The local copy is NOT the pod producer's output; the two must never be merged on name alone.

## The two broadcasts that would be staged, and the item that is missing

Requirement (S314 PREMISE): >= 2 NBA broadcasts with prior API history AND outcomes AND native source images AND declared source PTS AND independent observation labels.
- Set A -- the 19 API-complete games: PBP yes, outcome yes, box yes. Native images: 1 of 19 present on disk (`data/videos/full_games/0022401183.mp4`); 3 more carry a
  manifest naming a file that does not exist (0022400625, 0022400852, 0022401185); 15 carry no manifest at all. Declared source PTS: 0 of 19 -- none of these CSVs has
  `source_fps` or `source_height`, and `scoreboard_game_clock` is empty in the first record of all 19. MISSING ITEM: native source images AND declared source PTS.
- Set B -- the 3 pod official ids: native images yes (`data/footage_bridge/nba__0022500575_s1500.mp4`, 13,632,393 bytes, plus four `nba__0022500594_s*.mp4`), declared
  source PTS yes (`source_fps` 29.97002997002997, `source_height` 360, `source_duration` 151.08 s), `coordinate_space` `image_px`, `observation` `observed`, outcomes yes.
  MISSING ITEM: PRIOR API HISTORY -- `pbp_0022500575*.json`, `pbp_0022500594*.json` and `pbp_0022500630*.json` are absent locally, and `ls data/nba/pbp_*.json` on the pod returns 0 files.
- Independent observation labels are ALSO unqualified in Set B: `tracking_capability.json` reports `ball_telemetry_available: false` (a PASS_NO_BALL corpus cannot qualify a
  ball signal), `player_id` is a local track id (first record `"1"`), `team` is a colour (`"green"`), and `harness_verdict.json` reports `passed: false`,
  `rung: IMAGE_PX_DECLARED`, `coverage_pct: 0.1208`, `harness_coverage_pct: 0.0`.
- IF and only if PBP for those games is fetched and independent labels are established, the two broadcasts to stage are 0022500575 and 0022500594 -- the two with the most
  segments, the most rows and native footage present on the pod. That is a conditional plan, not a satisfied before-condition.

## NOT VERIFIED

- N_qualified, teacher_qualification for any signal, clock alignment and interval resolution: none attempted here.
- Full-file row counts for the 351 local CSVs (headers and first records only; the pod CSVs were streamed once and counted).
- Official-ID crosswalks for the 8 NBA-named pod directories and for `0022500966.f136` / `0022500966.f298`.
- Producer and harness hashes, source resolution/hash provenance for any local game, and pod code identity.
- Whether alternate API stores outside `data/nba/pbp_*.json` hold PBP for 0022500575 / 0022500594 / 0022500630. A missing local copy is NOT proof of corpus absence, so this
  census does NOT claim those games have no API history anywhere -- it reports BLOCKED on the authoritative stores it read.
- Per-game lineup reconstruction, live API receipt cutoffs, label-correction timing and outcome reconciliation for the 19. The corpus is LIVE: the pod daemon added 2 CSVs
  between this session's first and second pod scan, so these counts are a snapshot, not a frozen denominator.
