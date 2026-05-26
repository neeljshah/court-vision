# Jersey-Map Team-Segmentation Fix (v20-v24, UNAPPLIED)

**Origin:** Rescued from root-level `.tmp_v20_*.py`, `.tmp_v22_debug.py`, and `.tmp_v24.py`
on 2026-05-25 during dead-file cleanup (see `docs/_audit_dead_files_2026-05-25.md` Section 1).

**Status:** UNAPPLIED. None of the v20/v22/v24 changes are present in current source.
Verified 2026-05-25 — `apply_team_color_map`, `save_jersey_name_map` (public),
`_backfill_player_names_team_aware`, the `team_abbrev` field in `_fetch_roster_api`,
and the `[v20-debug]` / `[v20 team_color]` print markers are all absent from
`src/tracking/player_resolver.py` and `src/pipeline/unified_pipeline.py`.

These four patch scripts contain a coherent fix sequence for a known jersey-map
team-segmentation bug. Kept here for reference / future re-application.

## The bug

`_fetch_roster_api` (in `src/tracking/player_resolver.py`) stored each player
under BOTH `(jersey, "green")` AND `(jersey, "white")` because at fetch time
it didn't know which color each team wears in this specific game. The result:
`_save_jersey_name_map` wrote a `_by_team` dict with identical roster lists
for both colors. A NOP player wearing #4 would resolve to "Hunter Dickinson"
(DEN's #4) because of the cross-team contamination.

## Patch sequence

| File | Purpose |
|---|---|
| `v20_team_map.py` | Adds `team_abbrev` to roster entries; adds `apply_team_color_map` and public `save_jersey_name_map` to `PlayerResolver`; wires the prune+resave into `unified_pipeline.py` after `_court_side_team_map` is computed. |
| `v20_relocate.py` | v20.1 — moves the prune hook to AFTER `_backfill_team_abbrev` (so it fires whenever ANY color->abbrev mapping is known, not just the court-side fallback path). |
| `v22_debug.py` | Adds diagnostic prints; widens the team-abbrev lookup to fall back from `info["team_abbrev"]` to `info["team"]` for older roster entries from `_fetch_roster_common_team`. |
| `v24.py` | Adds `_backfill_player_names_team_aware` which FORCE-overwrites `tracking_data.csv` / `shot_log.csv` `player_name` columns using the cleaned `_by_team` map. Wires it into the v20.1 hook ahead of the soft backfill. |

## How to apply (if needed)

These scripts are SELF-MODIFYING — each one rewrites `src/...` files in place
via `Path.read_text()` / `replace(old, new)` / `write_text()`. The anchor
strings reflect the source at the time of authorship (2026-05-25). If source
has drifted since, the `assert old in src` checks will fail and you'll need to
re-derive the patch by hand.

Also note: paths are hard-coded to `/workspace/nba-ai-system/...` (RunPod).
Adjust before running locally.

Recommended sequence: `v20_team_map.py` -> `v20_relocate.py` -> `v22_debug.py` -> `v24.py`.
