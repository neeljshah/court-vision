"""v20.1: move the team-color prune hook to AFTER _abbrev_map is computed,
so it fires whenever ANY color→abbrev mapping is known (not just the
court-side fallback path)."""
from pathlib import Path

UP = Path("/workspace/nba-ai-system/src/pipeline/unified_pipeline.py")
up = UP.read_text()

# 1) Remove the misplaced v20 hook (inside the not-_team_map_applied block).
old_misplaced = """                except Exception as _tc_err:
                    print(f\"  [team_colors] write failed: {_tc_err}\")
                # v20 (2026-05-25): NOW prune PlayerResolver._roster of wrong-team
                # entries using the color→abbrev map, then re-save jersey_name_map.json
                # with correct team segmentation.
                if self._player_resolver is not None and _ct_map:
                    try:
                        n_dropped = self._player_resolver.apply_team_color_map(_ct_map)
                        self._player_resolver.finalize()
                        self._player_resolver.save_jersey_name_map()
                        print(f\"  [v20 team_color] roster pruned ({n_dropped} entries), jersey_name_map.json rewritten\")
                    except Exception as _v20err:
                        print(f\"  [v20 team_color] prune/save failed: {_v20err}\")"""
new_misplaced = """                except Exception as _tc_err:
                    print(f\"  [team_colors] write failed: {_tc_err}\")"""
assert old_misplaced in up, "misplaced hook not found"
up = up.replace(old_misplaced, new_misplaced)

# 2) Add the v20 hook AFTER _backfill_team_abbrev, where _abbrev_map is known to be valid.
old_anchor = """        if _abbrev_map:
            self._backfill_team_abbrev(_abbrev_map)

        # DB writes (SQLite by default, PostgreSQL when DATABASE_URL is set)"""
new_anchor = """        if _abbrev_map:
            self._backfill_team_abbrev(_abbrev_map)
            # v20.1 (2026-05-25): prune PlayerResolver._roster using the real
            # color→abbrev map, then re-save jersey_name_map.json + re-run
            # finalize so slot_to_player_name picks up the cleaned roster.
            # ALSO re-run _backfill_player_names so tracking_data.csv player_name
            # column gets the now-correct names (was wrong before due to the
            # cross-team roster contamination).
            if self._player_resolver is not None:
                try:
                    n_dropped = self._player_resolver.apply_team_color_map(_abbrev_map)
                    self._player_resolver.finalize()
                    self._player_resolver.save_jersey_name_map()
                    # Backfill again with corrected slot_to_player_name
                    self._backfill_player_names()
                    print(f\"  [v20 team_color] roster pruned ({n_dropped} entries), jersey_name_map.json rewritten, player_name backfilled\")
                except Exception as _v20err:
                    print(f\"  [v20 team_color] prune/save failed: {_v20err}\")

        # DB writes (SQLite by default, PostgreSQL when DATABASE_URL is set)"""
assert old_anchor in up, "post-backfill anchor not found"
up = up.replace(old_anchor, new_anchor)

UP.write_text(up)
print("v20.1 relocate applied")
