"""v24: add _backfill_player_names_team_aware (force-overwrites tracking_data.csv
player_name using _by_team[team][jersey]), and have v20.1's hook call it instead
of the soft _backfill_player_names.

Bug: _backfill_player_names only updates rows where player_name is empty or has
"#?". After v20.1 prunes the cross-team roster, existing (wrong) names from the
during-run dynamic resolve aren't overwritten — they're stuck at wrong-team
players (e.g., DEN slot showing 'Zion Williamson').
"""
from pathlib import Path
SRC = Path("/workspace/nba-ai-system/src/pipeline/unified_pipeline.py")
src = SRC.read_text()

# 1) Add a new method right after _backfill_player_names.
old_anchor = """                print(f\"Player name backfill: {_updated} rows updated in {_fname}\")
            except Exception as _e:
                print(f\"  [backfill_names] {_fname} failed: {_e}\")


    def _backfill_team_abbrev(self, color_map: dict) -> None:"""
new_anchor = '''                print(f"Player name backfill: {_updated} rows updated in {_fname}")
            except Exception as _e:
                print(f"  [backfill_names] {_fname} failed: {_e}")


    def _backfill_player_names_team_aware(self) -> None:
        """v24 (2026-05-25): FORCE overwrite player_name using
        jersey_name_map[_by_team][team][jersey_number] lookup.

        Called by v20.1 hook AFTER apply_team_color_map prunes the roster.
        Unlike _backfill_player_names (which only fills empty), this REWRITES
        every row whose jersey_number + team match a cleaned roster entry.
        This is necessary because during the tracking loop, v16's
        _resolved_name_dynamic ran with the contaminated roster — every row
        was written with a potentially-wrong name. The post-run prune fixes
        the on-disk map but doesn't touch the already-written CSV rows.
        """
        if self._player_resolver is None:
            return
        _jersey_map_path = os.path.join(self._data_dir, "jersey_name_map.json")
        if not os.path.exists(_jersey_map_path):
            return
        try:
            with open(_jersey_map_path, encoding="utf-8") as _jf:
                _jmap = json.load(_jf)
        except Exception as _e:
            print(f"  [v24 backfill] map load failed: {_e}")
            return
        _by_team = _jmap.get("_by_team", {})
        if not _by_team:
            return

        for _fname in ("tracking_data.csv", "shot_log.csv"):
            _path = os.path.join(self._data_dir, _fname)
            if not os.path.exists(_path):
                continue
            try:
                with open(_path, newline="", encoding="utf-8") as _f:
                    reader = csv.DictReader(_f)
                    _fields = list(reader.fieldnames or [])
                    _rows = list(reader)
                if "player_name" not in _fields or "jersey_number" not in _fields:
                    continue
                _flipped = _preserved = 0
                for _row in _rows:
                    _jn = _row.get("jersey_number", "")
                    _team = _row.get("team", "")
                    if not _jn or not _team:
                        continue
                    try:
                        _jn_int = int(float(_jn))
                    except (ValueError, TypeError):
                        continue
                    _new_name = _by_team.get(_team, {}).get(str(_jn_int))
                    if not _new_name:
                        continue
                    _old = _row.get("player_name", "")
                    if _new_name != _old:
                        _row["player_name"] = _new_name
                        _flipped += 1
                    else:
                        _preserved += 1
                with open(_path, "w", newline="", encoding="utf-8") as _f:
                    w = csv.DictWriter(_f, fieldnames=_fields, extrasaction="ignore")
                    w.writeheader()
                    w.writerows(_rows)
                print(f"  [v24 backfill] {_fname}: flipped={_flipped} preserved={_preserved}")
            except Exception as _e:
                print(f"  [v24 backfill] {_fname} failed: {_e}")


    def _backfill_team_abbrev(self, color_map: dict) -> None:'''
assert old_anchor in src, "v24 anchor not found"
src = src.replace(old_anchor, new_anchor)

# 2) Have v20.1's hook call the new team-aware backfill INSTEAD of the soft one.
old_hook = """            if self._player_resolver is not None:
                try:
                    n_dropped = self._player_resolver.apply_team_color_map(_abbrev_map)
                    self._player_resolver.finalize()
                    self._player_resolver.save_jersey_name_map()
                    # Backfill again with corrected slot_to_player_name
                    self._backfill_player_names()
                    print(f\"  [v20 team_color] roster pruned ({n_dropped} entries), jersey_name_map.json rewritten, player_name backfilled\")
                except Exception as _v20err:
                    print(f\"  [v20 team_color] prune/save failed: {_v20err}\")"""
new_hook = """            if self._player_resolver is not None:
                try:
                    n_dropped = self._player_resolver.apply_team_color_map(_abbrev_map)
                    self._player_resolver.finalize()
                    self._player_resolver.save_jersey_name_map()
                    # v24: FORCE-rewrite player_name from cleaned jersey_name_map
                    # (the soft _backfill_player_names only fills empties; during-run
                    # dynamic names were written with the contaminated pre-prune map).
                    self._backfill_player_names_team_aware()
                    # Also run the soft backfill for any remaining empties.
                    self._backfill_player_names()
                    print(f\"  [v20 team_color] roster pruned ({n_dropped} entries), jersey_name_map.json rewritten, player_name force-backfilled\")
                except Exception as _v20err:
                    print(f\"  [v20 team_color] prune/save failed: {_v20err}\")"""
assert old_hook in src, "v20 hook not found"
src = src.replace(old_hook, new_hook)

SRC.write_text(src)
print("v24 team-aware backfill applied")
