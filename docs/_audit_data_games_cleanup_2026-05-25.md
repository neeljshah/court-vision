# Audit — Can `data/games/` Be Safely Deleted?

Repository: `nba-ai-system`
Audit date: 2026-05-25
Mode: READ-ONLY investigation. No files moved or deleted.
Triggered by: `docs/_audit_dead_files_2026-05-25.md` (Section 3, Priority 10) — flagged 759 MB at `data/games/` as likely-superseded by `data/tracking/<gid>/` layout.

---

## TL;DR

**Verdict: YELLOW — delete after a safety copy and one targeted rescue.**

`data/games/` is the pre-April-2026 layout. The current production pipeline (`run_phase_g`, `unified_pipeline`, `nba_enricher`) writes exclusively to `data/tracking/<gid>/`. No source file under `src/`, `api/`, or `tests/` references `data/games/`. Only a small handful of `scripts/` use it, and every one of them treats it as a legacy fallback (`tracking/ first, games/ second`) — those scripts will silently no-op the fallback branch when the dir is gone.

There are, however, **two narrow risks** worth handling before deletion:
1. Two games (`0022401123`, `0022501091`) live **only** in `data/games/` and have `predictions.json` / `team_colors.json` / `events_log.csv` artifacts that are not in `data/tracking/`.
2. The 4 `data/games/_templates/` entries (`0022400015`, `0022400686`, `0022400921`, etc.) include game `0022400921`, whose `data/tracking/0022400921/` dir is **empty** — `_templates` is the only place this game's outputs survive.

Recommended approach: **copy a thin rescue bundle (~120 MB) to `_archive/data_games_rescue_2026-05-25/`, then drop the 759 MB tree.** Section 7 below has the exact commands.

---

## Section 1 — `data/games/` Inventory

- **Total size:** 759 MB
- **Entry count:** 25 top-level items (8 numeric NBA game IDs, 16 named-clip dirs, 1 `_templates/` subtree)
- **Mtime range:** 2026-03-15 16:01 → 2026-04-03 17:17 (frozen for ~7 weeks)
- **File types found:** `tracking_data.csv`, `ball_tracking.csv`, `features.csv` (+`.pre_fix_bak`), `possessions.csv`, `possessions_enriched.csv`, `shot_log.csv`, `shot_log_enriched.csv`, `player_clip_stats.csv`, `events_log.csv`, `team_colors.json`, `predictions.json`, `manifest.json`

### 1a. Numeric NBA game IDs (8 dirs, 591 MB)

| game_id | size | last mtime | also in data/tracking/? | notes |
|---|---|---|---|---|
| `0022400625` | 408 MB | 2026-03-23 | YES (older schema, more rows) | 396 MB `features.csv` is the single biggest file in the entire tree |
| `0022400909` | 12 MB | 2026-03-31 | YES (tracking has only 2 files) | tracking dir is partial — only `tracking_data.csv` + `jersey_name_map.json` |
| `0022401123` | 37 MB | 2026-04-03 | NO | unique; has `predictions.json` + `team_colors.json` |
| `0022401175` | 7.7 MB | 2026-03-30 | NO | unique; has enriched files |
| `0022401183` | 13 MB | 2026-03-23 | YES (newer schema) | |
| `0022401185` | 25 MB | 2026-03-24 | YES (newer schema) | |
| `0022500757` | 51 MB | 2026-04-01 | NO | unique; has enriched files |
| `0022501091` | 33 MB | 2026-04-01 | NO | unique; has `events_log.csv`, `team_colors.json`, `player_clip_stats.csv` |

### 1b. Named-clip dirs (16 dirs, ~14 MB total)

`atl_ind_2025`, `bos_mia_2025`, `bos_mia_playoffs`, `cavs_broadcast_2025`, `cavs_celtics_2025`, `cavs_gsw_2016_finals_g7`, `den_gsw_playoffs`, `den_phx_2025`, `gsw_lakers_2025`, `lal_sas_2025`, `mem_nop_2025`, `mia_bkn_2025`, `mil_chi_2025`, `okc_dal_2025`, `phi_tor_2025`, `sac_por_2025` — all 78 KB to 1.7 MB each. These are pre-NBA-game-ID clip experiments from 2026-03-15. Standard schema: 5 files (`tracking_data.csv`, `ball_tracking.csv`, `features.csv`, `possessions.csv`, `player_clip_stats.csv`). None have an `0022...` analog.

### 1c. `data/games/_templates/` (27 dirs, 161 MB)

Per `vault/Sessions/_archive/PLAN_SESSION_30.md` (line 84-85), `_templates` was created as the recoverable home for "template" dirs during a March 2026 cleanup. Entries:

- 26 numeric game IDs (e.g. `0022400015`, `0022400021`, ... `0022401198`) — each 4-5 MB
- 1 named clip: `noid_cavaliers_gsw_2016_finals_g7_fullgame` (4.2 MB)

Of these 26 numeric IDs, **only 4 overlap** with a corresponding dir in `data/tracking/`: `0022400852`, `0022400921`, `0022400923`, `0022401198`. For 3 of those 4, the tracking dir has **more** rows than the templates copy (tracking wins). The exception is `0022400921` — see Section 3 for the rescue case.

---

## Section 2 — `data/tracking/` Inventory

- **Total size:** 3.4 GB (4.5x the size of `data/games/`)
- **Entry count:** 85 top-level entries — 69 are game-ID dirs (`0022...`), plus stray files and subdirs at root from earlier runs
- **Mtime range:** 2026-03-19 22:12 → 2026-05-22 21:15 (actively written through this week)
- **Empty game dirs:** 2 (`0022400689`, `0022400921`)

### 2a. Game-ID dirs (69, the canonical ones)

Per-game schema (see `0022400625` for the maximal example):
- `tracking_data.csv`, `tracking_data.csv.bak`
- `features.csv`, `features.csv.bak`
- `possessions.csv`, `possessions.csv.bak`, `possessions_enriched.csv`
- `shot_log.csv`, `shot_log.csv.bak`, `shot_log.csv.bak3`, `shot_log_enriched.csv`
- `ball_tracking.csv`
- `events_log.csv`
- `game_context.csv`
- `jersey_name_map.json`
- `manifest.json`

For `0022400625` only, there is a nested `data/tracking/0022400625/0022400625/` with `events_log.csv`, `jersey_name_map.json`, `shot_log.csv` (looks like a double-nesting bug from an earlier run, but is harmless).

### 2b. Stray root-level files in `data/tracking/` (NOT game data)

Cruft from older runs that were written into the root instead of into a `<gid>/` subdir:
- `ball_tracking.csv` (44 KB, 2026-03-19)
- `features.csv` (2.5 MB) + `features.csv.bak` (2.6 MB)
- `manifest.json`, `possessions.csv` (+`.bak`), `shot_log.csv` (+`.bak`), `tracking_data.csv` (1.6 MB, +`.bak`)
- `phase_g_batch2.log` (227 KB, 2026-03-27)
- `g1/`, `g2/`, `g3/` (empty subdirs from 2026-04-21)
- `test_knicks/run.log` (2 KB)
- `data/tracking_archive/` (empty)

These are **out of scope** for this audit (they're not in `data/games/`), but worth flagging in the broader cleanup.

---

## Section 3 — Overlap Analysis

### 3a. Game ID overlap

| Set | Game IDs |
|---|---|
| In both `data/games/` and `data/tracking/` | `0022400625`, `0022400909`, `0022401183`, `0022401185` (4 games) |
| Only in `data/games/` | `0022401123`, `0022401175`, `0022500757`, `0022501091` (4 games) |
| Only in `data/games/_templates/` (numeric) | 22 IDs; only `0022400921` has no usable tracking copy (tracking dir empty) |
| Only in `data/tracking/` | 65 game IDs (most of the dataset) |
| Named clips only in `data/games/` | All 16 (`atl_ind_2025`, `gsw_lakers_2025`, etc.) |

### 3b. Schema comparison — `0022400625` (the headline example)

Both `manifest.json` files are byte-identical (same `started_at: 2026-03-23T19:58:16`, same `tracking_rows: 819604`, same `total_frames: 367977`). So it was the same pipeline run — but the `features.csv` outputs are very different:

| File | `data/games/0022400625/features.csv` | `data/tracking/0022400625/features.csv` |
|---|---|---|
| Size | 396 MB | 144 MB |
| Rows | 819,605 | 197,139 |
| Columns | 96 | 157 |
| First data-row `frame` | 630 | 8019 |

The `data/tracking/` version has the **newer 157-column schema** (62 added feature columns including `bbref_bpm`, `cap_hit_pct`, `defender_dist_*`, `dribble_count`, `elo_*`, `hustle_*`, `injury_status_multiplier`, `jersey_number`, `lineup_id`, `player_name`, `paint_pressure_*`, `synergy_*`, `velocity_std_*`, `x_norm`/`y_norm`, etc.) and **also fewer rows** (197K vs 819K). Best inference: `data/tracking/` was re-built from the same `tracking_data.csv` source after a downstream filter (likely `_MIN_PLAYED ≥ 5` from the bot-loop cycle 22 era, before later relaxation to 1; or a `confidence ≥ 0.5` cut). The `data/games/` copy has the older schema but the raw row population.

Sample data row in `data/games/` features.csv: `630,10.511,4,green,195,1369,0.0,0.0,0.0,3pt_arc,...`
Sample data row in `data/tracking/` features.csv: `8019,133.784,5,green,1318,170,0.2797,0.2408,0.0,0.0,0.0,3pt_arc,...`

→ Different physical rows, different schema, same upstream run. **Not a clean duplicate.** But also: the production pipeline rebuilds `features.csv` from `tracking_data.csv` whenever feature engineering changes, so the older `data/games/` copy is a *frozen historical features.csv* that no current model consumes.

### 3c. Schema comparison — `0022401183` & `0022401185` (other overlaps)

| game | games/ cols | games/ rows | tracking/ cols | tracking/ rows |
|---|---|---|---|---|
| 0022401183 | 96 | 3,699 | 158 | 77,556 |
| 0022401185 | 96 | 23,602 | 139 | 202,513 |

Same pattern: `data/tracking/` has the newer schema and **more** rows. For these two, the `data/games/` copy is strictly a subset.

(The 4th overlap, `0022400909`, has only 2 files in `data/tracking/`: `tracking_data.csv` and `jersey_name_map.json`. The `data/games/0022400909/` copy has the full 10-file set including `features.csv`, `possessions.csv`, `possessions_enriched.csv`, `shot_log_enriched.csv`. **`0022400909` is a partial-tracking rescue case** — see Section 7.)

### 3d. `_templates` overlap with tracking — `0022400921` rescue case

| game | tracking_data rows in tracking/ | rows in `_templates/` |
|---|---|---|
| 0022400852 | 43,971 | 27,652 | tracking wins |
| 0022400921 | (dir empty) | 27,652 | **only `_templates/` has data** |
| 0022400923 | 98,042 | 27,652 | tracking wins |
| 0022401198 | 62,577 | 5,161 | tracking wins |

`0022400921` (DAL vs PHX, 2025-03-09) — `data/tracking/0022400921/` is an empty directory; `data/games/_templates/0022400921/` is the only place its tracking outputs survive (~4.2 MB: ball, features, possessions, shot, tracking, manifest, predictions). If you care about preserving that game's outputs, rescue this dir before deletion.

---

## Section 4 — Source Code References

### 4a. Production code: ZERO references to `data/games/`

```
$ grep -rn "data/games" src/ api/ tests/
(no results)
```

### 4b. Scripts: 8 files mention `data/games/`, all as legacy fallback

| Script | Role of `data/games/` |
|---|---|
| `scripts/batch_season.py` | Legacy fallback for `_already_done()` and `_read_metrics()` — comment line 91: *"run_phase_g writes to data/tracking/; legacy pipeline uses data/games/"* |
| `scripts/clean_existing_games.py` | `_find_game_dirs()` walks `tracking/` then `games/`, dedup by name — comment line 41: *"data/tracking/ is the canonical location written by run_phase_g / nba_enricher"* |
| `scripts/consolidate_game_data.py` | **The one-shot migration script itself** — module docstring: *"Merge data/games/ into data/tracking/ as single canonical location. data/tracking/{game} is canonical output dir (current pipeline standard)... Never delete anything — data/games/ stays intact as backup."* |
| `scripts/backfill_cv_features.py` | Iterates both dirs to backfill features into older outputs |
| `scripts/fix_prediction_ready.py` | Writes `predictions.json` to `data/games/{gid}` (deprecated path — `predict_player.py` is the live successor) |
| `scripts/process_game.py` | Docstring references `data/games/<game_id>/q<N>/` — superseded by `run_phase_g.py` per memory |
| `scripts/full_game_pipeline.py` | Same — superseded by `run_phase_g.py` |
| `scripts/validate_game.py` | Validation script — walks `data/games/` to write `validation.json` |

### 4c. `data/tracking/` references: 50+ files across src/, scripts/, tests/, api/

Includes the canonical writers: `scripts/run_phase_g.py`, `src/pipeline/unified_pipeline.py`, `src/data/nba_enricher.py`, `src/features/feature_engineering.py`, `scripts/batch_season.py`, `scripts/run_clip.py`, `scripts/reprocess_failed_games.py`. **Every active code path writes to and reads from `data/tracking/`.**

### 4d. Verdict on canonical layout

`data/tracking/<gid>/` is unambiguously the current canonical layout. The two scripts that fall back to `data/games/` (`batch_season.py`, `clean_existing_games.py`) do so safely — they `for parent in (tracking, games)` and skip non-existent dirs. Deleting `data/games/` will silently turn those into single-arm scans.

---

## Section 5 — Migration History (Git)

`git log -S "data/games"` returns ~16 commits going back to early 2026; `git log -S "data/tracking"` returns ~20 commits, the earliest of which is `654f4b8e feat: GPU pipeline v2 — decord decode, parallel-4 workers, RunPod 4090 cloud processing` (the RunPod / phase-G pipeline introduction).

No single explicit "move from data/games to data/tracking" commit exists. The migration appears to have happened by **convention shift**: `run_phase_g.py` (the RunPod batch runner) started writing to `data/tracking/` and was adopted as the only path forward. The older `process_game.py` / `full_game_pipeline.py` / `run_clip.py` scripts that wrote to `data/games/` were effectively retired without a hard cutover.

Evidence the migration is intentional and complete:
- `scripts/consolidate_game_data.py` exists explicitly to merge `games/ → tracking/`
- Comments throughout `batch_season.py` / `clean_existing_games.py` mark `data/games/` as legacy
- `data/games/` mtimes stop at 2026-04-03; `data/tracking/` has been actively written through 2026-05-22
- The dead-file audit (`docs/_audit_dead_files_2026-05-25.md` Section 3) independently flagged `data/games/` as "Old canonical layout — superseded by `data/tracking/`"

Also useful: `vault/Sessions/_archive/PLAN_SESSION_30.md` (the original cleanup plan that created `_templates/`) confirms the intent to converge under `data/games/` was set in March 2026, and `vault/Sessions/_archive/Session-2026-03-15.md` shows the named-clip era when `run_clip.py` wrote into `data/games/<clip_name>/`.

---

## Section 6 — Confidence-Graded Recommendation

### YELLOW — delete with backup (downgraded from GREEN by 2 narrow risks)

**Why not GREEN:**
1. **4 game IDs are unique to `data/games/`** (`0022401123`, `0022401175`, `0022500757`, `0022501091`) — totalling ~128 MB of `predictions.json`, enriched possessions/shots, `events_log.csv`, `team_colors.json`. None of this is in `data/tracking/`. Most of it is reproducible (re-run the pipeline) but two of those games (`0022401123`, `0022501091`) include `predictions.json` files that capture point-in-time projections worth preserving for retro CLV analysis.
2. **`data/games/_templates/0022400921/`** is the only surviving copy of game `0022400921`'s outputs — `data/tracking/0022400921/` is an empty directory.

**Why not RED:**
- No active code reads from `data/games/`.
- All overlapping games either have a newer / larger / better-schema copy in `data/tracking/` (`0022400625`, `0022401183`, `0022401185`) or only one missing-half file (`0022400909` — full features in `games/`, tracking-only in `tracking/`; fixable by a 12 MB rescue copy).
- The dead-file audit independently reached the same conclusion.
- A `consolidate_game_data.py` script already exists for one-shot reconciliation — and per its docstring, **it was designed never to delete the source** because the user wanted to keep `data/games/` as a backup. Once a rescue copy is taken, that requirement is satisfied.

**Confidence: HIGH that deletion is safe; MEDIUM that nothing in the unique 128 MB of artifacts will be missed.** If RunPod-side retraining ever needs raw `predictions.json` for those 4 games, they're reproducible from the parquet caches.

---

## Section 7 — Cleanup Plan (if user approves)

### Step 0 — Safety net: consolidate first

Run the existing one-shot consolidator (it never deletes from `data/games/`, only copies missing files into `data/tracking/`):

```powershell
python scripts/consolidate_game_data.py --dry-run
# review what it would do, then:
python scripts/consolidate_game_data.py
```

After this, `data/tracking/` will gain any of the missing-from-tracking files (e.g. `data/games/0022400909/features.csv` → `data/tracking/0022400909/features.csv`).

### Step 1 — Rescue bundle for non-reproducible artifacts (~5 MB)

Copy the irreplaceable bits to an archive folder (kept under the existing `_archive/` convention):

```powershell
$rescue = "_archive/data_games_rescue_2026-05-25"
New-Item -ItemType Directory -Force $rescue | Out-Null

# Rescue case 1: 0022400921 lives ONLY in _templates/, tracking dir is empty
Copy-Item -Recurse "data/games/_templates/0022400921" "$rescue/0022400921_from_templates"

# Rescue case 2: 4 unique-to-data/games games (keep predictions.json + enriched + events_log + team_colors)
# (Skip the huge features.csv/tracking_data.csv since they're regenerable.)
foreach ($g in @("0022401123","0022401175","0022500757","0022501091")) {
  $src = "data/games/$g"
  $dst = "$rescue/$g"
  New-Item -ItemType Directory -Force $dst | Out-Null
  foreach ($f in @("manifest.json","predictions.json","team_colors.json",
                   "shot_log.csv","shot_log_enriched.csv",
                   "possessions.csv","possessions_enriched.csv",
                   "events_log.csv")) {
    if (Test-Path "$src/$f") { Copy-Item "$src/$f" "$dst/$f" }
  }
}
```

Expected rescue size: ~5 MB (the heavy CSVs are excluded; everything else fits easily).

### Step 2 — Delete `data/games/` (759 MB freed)

```powershell
Remove-Item -Recurse -Force "data/games"
```

### Step 3 — Optional: clean stray root-level files in `data/tracking/` (separate task)

Not in scope here but worth flagging for the next pass — see Section 2b.

### Step 4 — Update the legacy-fallback scripts (low priority, post-deletion)

After deletion, the `for parent in (tracking, games)` loops in `scripts/batch_season.py` and `scripts/clean_existing_games.py` become dead branches. Simplify when convenient:

```python
# Before (batch_season.py line 69):
for parent in (TRACKING_DIR, GAMES_DIR):
# After:
for parent in (TRACKING_DIR,):
```

Not required for correctness — the existing code handles missing dirs gracefully.

### Verification after deletion

```powershell
python -m pytest tests/ -q                       # full test suite
python scripts/batch_season.py --status          # exercise the fallback paths
python scripts/clean_existing_games.py --dry-run # exercise _find_game_dirs()
```

If all green, the migration is complete.

---

## Appendix — Files Referenced

- `C:\Users\neelj\nba-ai-system\docs\_audit_dead_files_2026-05-25.md` (Section 3, line 230)
- `C:\Users\neelj\nba-ai-system\scripts\consolidate_game_data.py` (the existing one-shot migrator)
- `C:\Users\neelj\nba-ai-system\scripts\batch_season.py` (lines 66-110 — legacy fallback)
- `C:\Users\neelj\nba-ai-system\scripts\clean_existing_games.py` (lines 36-50 — legacy fallback)
- `C:\Users\neelj\nba-ai-system\vault\Sessions\_archive\PLAN_SESSION_30.md` (lines 54-89 — origin of `_templates/`)
- `C:\Users\neelj\nba-ai-system\.planning\optimization\03_BACKUP.md` (stale references to `data/games/*` for backup paths — update post-deletion)
- `C:\Users\neelj\nba-ai-system\docs\data_schema.md` (Section 8 — stale documentation pointing at `data/games/`, update post-deletion)
