"""v20: fix the catastrophic jersey_name_map team-segmentation bug.

Bug: _fetch_roster_api stores each player under BOTH (jersey, "green") AND
(jersey, "white") because it doesn't know which color each team wears in this
specific game. _save_jersey_name_map then writes _by_team with identical
roster lists for both colors. Result: jersey #4 = "Hunter Dickinson" under
both teams, so a NOP player wearing #4 resolves to Dickinson (DEN player).

Fix:
(a) _fetch_roster_api now stores TEAM_ABBREVIATION in each roster entry (was empty).
(b) PlayerResolver gains a new method `apply_team_color_map(color_map)` that
    accepts {"green": "DEN", "white": "NOP"} and prunes the roster to only
    contain (jersey, color) entries whose team_abbrev matches color_map[color].
(c) unified_pipeline.py calls apply_team_color_map AFTER computing
    _court_side_team_map, BEFORE _save_jersey_name_map runs the final save.
(d) Add a public method PlayerResolver.save_jersey_name_map() so the pipeline
    can trigger a re-save after pruning.
"""
from pathlib import Path

PR = Path("/workspace/nba-ai-system/src/tracking/player_resolver.py")
src = PR.read_text()

old_entry = """                for label in labels:
                    key = (jersey_num, label)
                    self._roster[key] = {
                        "player_id":   pid,"""
new_entry = """                for label in labels:
                    key = (jersey_num, label)
                    self._roster[key] = {
                        "player_id":   pid,
                        "team_abbrev": abbr,  # v20: NBA tricode (e.g., "DEN", "NOP")"""
assert old_entry in src, "fetch_roster_api anchor not found"
src = src.replace(old_entry, new_entry)

old_anchor = """    def reset_slot(self, slot: int) -> None:"""
new_methods = '''    def apply_team_color_map(self, color_map: dict) -> int:
        """v20 (2026-05-25): prune _roster to only correct (jersey, color) entries.

        Before this fix, _fetch_roster_api wrote each player under BOTH "green"
        and "white" labels (because it didn't know which color each team wears
        in THIS game). That made (jersey, color) lookups return wrong players
        when both teams had the same jersey number.

        color_map: {"green": "DEN", "white": "NOP"} or similar.

        Returns the number of entries dropped.
        """
        if not color_map:
            return 0
        bad_keys = []
        for (jersey_num, label), info in self._roster.items():
            expected = color_map.get(label, "")
            if not expected or expected.startswith("team_"):
                continue  # no usable mapping — keep entry as-is (best-effort)
            actual = info.get("team_abbrev", "")
            if actual and actual != expected:
                bad_keys.append((jersey_num, label))
        for k in bad_keys:
            self._roster.pop(k, None)
        self._jerseys_by_team.clear()
        for (jersey_num, team_label), _info in self._roster.items():
            self._jerseys_by_team.setdefault(team_label, set()).add(jersey_num)
        self.slot_to_player_name.clear()
        self.slot_to_player_id.clear()
        self._warmup_done = False
        log.info("PlayerResolver: pruned %d wrong-team entries via color_map %s; jerseys_by_team=%s",
                 len(bad_keys), dict(color_map),
                 {k: len(v) for k, v in self._jerseys_by_team.items()})
        return len(bad_keys)

    def save_jersey_name_map(self) -> None:
        """v20: public API to trigger a re-save of jersey_name_map.json."""
        self._save_jersey_name_map()

    def reset_slot(self, slot: int) -> None:'''
assert old_anchor in src, "reset_slot anchor not found"
src = src.replace(old_anchor, new_methods)
PR.write_text(src)
print("PlayerResolver patched")

UP = Path("/workspace/nba-ai-system/src/pipeline/unified_pipeline.py")
up = UP.read_text()

old_pipe = """                # FIX 7: persist the color→abbrev map to data/tracking/{game_id}/team_colors.json
                _tc_path = os.path.join(self._data_dir, "team_colors.json")
                try:
                    with open(_tc_path, "w", encoding="utf-8") as _tcf:
                        json.dump(_ct_map, _tcf, indent=2)
                    print(f"  [team_colors] written → {_tc_path}")
                except Exception as _tc_err:
                    print(f"  [team_colors] write failed: {_tc_err}")"""
new_pipe = """                # FIX 7: persist the color→abbrev map to data/tracking/{game_id}/team_colors.json
                _tc_path = os.path.join(self._data_dir, "team_colors.json")
                try:
                    with open(_tc_path, "w", encoding="utf-8") as _tcf:
                        json.dump(_ct_map, _tcf, indent=2)
                    print(f"  [team_colors] written → {_tc_path}")
                except Exception as _tc_err:
                    print(f"  [team_colors] write failed: {_tc_err}")
                # v20 (2026-05-25): NOW prune PlayerResolver._roster of wrong-team
                # entries using the color→abbrev map, then re-save jersey_name_map.json
                # with correct team segmentation.
                if self._player_resolver is not None and _ct_map:
                    try:
                        n_dropped = self._player_resolver.apply_team_color_map(_ct_map)
                        self._player_resolver.finalize()
                        self._player_resolver.save_jersey_name_map()
                        print(f"  [v20 team_color] roster pruned ({n_dropped} entries), jersey_name_map.json rewritten")
                    except Exception as _v20err:
                        print(f"  [v20 team_color] prune/save failed: {_v20err}")"""
assert old_pipe in up, "pipeline anchor not found"
up = up.replace(old_pipe, new_pipe)
UP.write_text(up)
print("unified_pipeline.py patched")
