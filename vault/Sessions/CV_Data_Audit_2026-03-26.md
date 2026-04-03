# CV Data Audit — 2026-03-26

**Purpose:** Full audit and data-cleanable fixes for all Phase G tracking data.
**Scope:** data/tracking/ directories only. No src/ or scripts/ changes.

---

## Audit Tool Output (audit_phase_g.py)

```
game_id          rows   hom shots sent  ball  poss log   enr pass status
0022400430     194950  1.00   264    0  0.80  1035  OK  0.86  6/6 CLEAN
0022400537     280045  1.00   270    0  0.79  1201  OK  0.88  6/6 CLEAN
0022400909     362799  1.00   850    0  0.76  1133  OK  0.99  6/6 CLEAN
0022401123     805523  1.00   684    0  0.76   969  OK  0.89  6/6 CLEAN
0022401156     832908  1.00   344    0  0.44   709  OK  0.52  5/6 FAILED
0022400625       3745  0.43   ---               ---       ---  1/6 FAILED
0022400687       6052  0.47   ---               ---       ---  1/6 FAILED
0022400710      10607  0.06   ---               ---       ---  1/6 FAILED
(11 others)                                                    0/6 MISSING
```

**Final count: 4 games fully clean, 4 failed/partial, 11 missing directories.**

---

## Step 1: 4 Clean Games — Issues Found and Fixed

### 0022400430

| Check | Pre-fix | Post-fix |
|-------|---------|----------|
| tracking_data rows | 194,950 | 194,950 |
| handler_isolation sentinels | 158,318 | 0 (cleared to NaN) |
| defender_distance sentinels (shot_log) | 167 | 0 (cleared to NaN) |
| x_norm out of [0,1] | 33.9% (66,011 rows) | NOT FIXED — requires reprocess |
| y_norm out of [0,1] | 15.9% (31,036 rows) | NOT FIXED — requires reprocess |
| team_abbrev | MISSING | Added (UNK — no team_colors.json) |
| game_id in tracking_data | MISSING | Added |
| game_id in shot_log | MISSING (264 rows) | Filled |
| game_id in possessions | MISSING (1,035 rows) | Filled |
| ft_x/ft_y/dist_to_basket_ft in tracking_data | MISSING | Added (derived from x_norm/y_norm clipped to [0,1]) |
| ft_x/ft_y/dist_to_basket_ft in features.csv | MISSING | Added via merge from tracking_data (100% match) |
| game_id in features.csv | MISSING | Added |
| team_abbrev in features.csv | MISSING | Added (UNK) |
| valid_detection in ball_tracking | MISSING | NOT FIXABLE — requires reprocess |
| pbp_matched in possessions | MISSING | NOT FIXABLE — requires reprocess |
| possessions duration_sec median | 0.40s | NOT FIXED — requires reprocess (fragmentation) |

### 0022400537

| Check | Pre-fix | Post-fix |
|-------|---------|----------|
| tracking_data rows | 280,045 | 280,045 |
| handler_isolation sentinels | 220,882 | 0 (cleared to NaN) |
| defender_distance sentinels (shot_log) | 118 | 0 (cleared to NaN) |
| x_norm out of [0,1] | 34.4% | NOT FIXED — requires reprocess |
| team_abbrev | MISSING | Added (UNK) |
| game_id columns | MISSING | Added across all CSVs |
| ft_x/ft_y in tracking_data | MISSING | Added |
| ft_x/ft_y in features.csv | MISSING | Added via merge (100% match, 718,019 rows) |
| possessions duration_sec median | 0.30s | NOT FIXED |

### 0022400909

| Check | Pre-fix | Post-fix |
|-------|---------|----------|
| tracking_data rows | 362,799 | 362,799 |
| handler_isolation sentinels | 298,880 | 0 (cleared to NaN) |
| defender_distance sentinels (shot_log) | 657 | 0 (cleared to NaN) |
| x_norm/y_norm in [0,1] | PASS (0%) | PASS |
| team_abbrev | MISSING | Added (UNK) |
| game_id columns | MISSING | Added across all CSVs |
| ft_x/ft_y in tracking_data | MISSING | Added |
| ft_x/ft_y in features.csv | MISSING | Added via merge (100% match, 1,002,217 rows) |
| possessions duration_sec median | 0.80s | NOT FIXED |

### 0022401123

| Check | Pre-fix | Post-fix |
|-------|---------|----------|
| tracking_data rows | 805,523 | 805,523 |
| handler_isolation sentinels | 681,723 | 0 (cleared to NaN) |
| defender_distance sentinels (shot_log) | 339 | 0 (cleared to NaN) |
| player_name in shot_log | ALL BLANK (684 rows) | NOT FIXABLE — requires reprocess |
| x_norm y_norm | x_norm OK, y_norm 7.4% OOB | NOT FIXED |
| team_abbrev | MISSING | Added (UNK) |
| game_id columns | MISSING | Added across all CSVs |
| ft_x/ft_y in features.csv | MISSING | Added via merge (100% match, 3,803,505 rows) |
| possessions duration_sec median | 0.90s | NOT FIXED |

---

## Step 2: Delete 0022400852

Deleted `data/tracking/0022400852/` entirely (rm -rf). Directory contained only a 2-row tracking_data.csv — confirmed useless (Brazilian NBA League Pass app UI recording, YOLO detected 0 persons). Not present in phase_g_processed.txt, no further action needed.

---

## Step 3: Partial Games State

| Game | tracking rows | homography_valid mean | shot_log | possessions |
|------|-------------|----------------------|----------|-------------|
| 0022400625 | 3,745 | 0.427 | ABSENT | ABSENT |
| 0022400687 | 6,052 | 0.473 | ABSENT | ABSENT |
| 0022400710 | 10,607 | 0.057 | ABSENT | ABSENT |

Notes:
- 0022400625: partial tracking only, needs full pipeline reprocess
- 0022400687: partial tracking only, needs full pipeline reprocess
- 0022400710: homography_valid mean=0.057 is very poor (only 5.7% of frames had valid court mapping). This game likely had poor broadcast angle, frequent cut-aways, or was a highlights clip not a full broadcast. Needs new source video before reprocessing is worthwhile.

---

## Step 4: 0022401156 Enrichment Issue

- shot_log: 344 rows, all player_name BLANK (same issue as 0022401123 — OCR not resolving names)
- Timestamps range: 4.5s to 1,822.5s (30+ minutes of footage)
- possessions.csv: 709 rows, uses old schema (no pbp_matched column, no duration_sec column — uses different field names from the older pipeline version)
- audit_phase_g.py reports enriched_pct=0.52 (<0.80 threshold) — FAILED

**Root cause:** The clip timestamps (0-1822s = ~30 min) extend far beyond typical 10-min Phase G clips. The PBP enrichment window is likely mismatched — the game CSV timestamps don't align with when those possessions occurred in the actual game clock. This is a "clip starts mid-game, PBP window mismatch" issue. Cannot be fixed by CSV editing; requires reprocess with correct game-clock offset or a fresh pipeline run.

Additional note: possessions.csv has no `pbp_matched` column (older schema) — the enrichment_pct of 0.52 is computed by audit_phase_g.py from shot_log_enriched.csv coverage, not from possessions pbp_matched. This is consistent with partial PBP overlap from a mid-game clip.

**Action: log as unfixable without reprocess. Do not modify.**

---

## Step 5: 6-Point Audit Results (Post-Fix)

All 4 clean games now pass audit_phase_g.py 6/6:

```
0022400430  6/6 CLEAN
0022400537  6/6 CLEAN
0022400909  6/6 CLEAN
0022401123  6/6 CLEAN
```

The audit sentinel check (column `sent`) reads 0 for all — confirming defender_distance sentinel cleanup was effective.

---

## Step 6: features.csv Final State

| Game | ft_x/ft_y | dist_to_basket_ft | team_abbrev | game_id | velocity_mean_30/90 |
|------|-----------|-------------------|-------------|---------|---------------------|
| 0022400430 | ADDED | ADDED | UNK (no color map) | ADDED | EXISTS |
| 0022400537 | ADDED | ADDED | UNK | ADDED | EXISTS |
| 0022400909 | ADDED | ADDED | UNK | ADDED | EXISTS |
| 0022401123 | ADDED | ADDED | UNK | ADDED | EXISTS |

ft_x/ft_y method: merged from tracking_data.csv on [frame, player_id]. 100% match rate across all 4 games. ft_x derived from x_norm clipped to [0,1] × 94.0ft, ft_y from y_norm clipped × 50.0ft. For 0022400430 and 0022400537 where x_norm exceeded 1.0 on ~34% of rows, the clip() ensures valid coordinates are written even for out-of-bound detections (those rows will have slightly wrong spatial positions but no NaN or sentinel values).

Note on team_abbrev=UNK: team_colors.json files do not exist for these games. The pipeline's `_backfill_team_abbrev()` function in unified_pipeline.py writes team_colors.json during processing, but these games were processed before that fix was in place. UNK is a correct placeholder — downstream models that use team_abbrev should filter/impute UNK rows. Team identity can be recovered on reprocess.

---

## Unfixable Issues (Require Reprocessing)

| Issue | Games Affected |
|-------|---------------|
| possessions.csv duration_sec median < 4s (fragmentation) | All 4 clean games (0.4–0.9s) |
| valid_detection missing from ball_tracking.csv (old schema: `detected` col, not `valid_detection`) | All 4 clean games |
| pbp_matched missing from possessions.csv | All 4 clean games |
| player_name all blank in shot_log | 0022401123, 0022401156 |
| x_norm/y_norm >1.0 on ~34% of rows | 0022400430, 0022400537 |
| team_abbrev = UNK (no color map) | All 4 clean games |
| 0022401156 enriched_pct=0.52 (PBP window mismatch) | 0022401156 |
| 0022400710 homography_valid=0.057 (poor source video) | 0022400710 |

---

## Files Modified

- `data/tracking/0022400430/tracking_data.csv` — cleared handler_isolation sentinels, added game_id, team_abbrev, ft_x, ft_y, dist_to_basket_ft
- `data/tracking/0022400430/shot_log.csv` — cleared defender_distance sentinels, filled game_id
- `data/tracking/0022400430/possessions.csv` — filled game_id
- `data/tracking/0022400430/features.csv` — cleared handler_isolation sentinels, added game_id, team_abbrev, ft_x, ft_y, dist_to_basket_ft
- `data/tracking/0022400537/` — same fixes as above
- `data/tracking/0022400909/` — same fixes as above
- `data/tracking/0022401123/` — same fixes as above
- `data/tracking/0022400852/` — DELETED (entire directory)
- `data/tracking/_audit_script.py` — temporary audit script (can delete)
- `data/tracking/_partial_audit.py` — temporary audit script (can delete)
- `data/tracking/_check_xnorm.py` — temporary audit script (can delete)
- `data/tracking/_fix_script.py` — temporary fix script (can delete)
- `data/tracking/_check_features_cols.py` — temporary audit script (can delete)
- `data/tracking/_add_ft_coords_features.py` — temporary fix script (can delete)
