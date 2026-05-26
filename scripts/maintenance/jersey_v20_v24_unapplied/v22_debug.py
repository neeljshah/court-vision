"""v22: Add diagnostic prints to apply_team_color_map so we can see what's happening."""
from pathlib import Path

PR = Path("/workspace/nba-ai-system/src/tracking/player_resolver.py")
src = PR.read_text()

old = '''    def apply_team_color_map(self, color_map: dict) -> int:
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
                bad_keys.append((jersey_num, label))'''
new = '''    def apply_team_color_map(self, color_map: dict) -> int:
        """v20 (2026-05-25): prune _roster to only correct (jersey, color) entries.

        Before this fix, _fetch_roster_api wrote each player under BOTH "green"
        and "white" labels (because it didn't know which color each team wears
        in THIS game). That made (jersey, color) lookups return wrong players
        when both teams had the same jersey number.

        color_map: {"green": "DEN", "white": "NOP"} or similar.
        v22: fall back to info["team"] when info["team_abbrev"] is missing
        (older roster entries from _fetch_roster_common_team had only "team").

        Returns the number of entries dropped.
        """
        if not color_map:
            return 0
        # v22 diagnostic
        print(f"  [v20-debug] apply_team_color_map: color_map={color_map}", flush=True)
        if self._roster:
            _sample = next(iter(self._roster.items()))
            print(f"  [v20-debug] sample roster entry: {_sample}", flush=True)
        bad_keys = []
        for (jersey_num, label), info in self._roster.items():
            expected = color_map.get(label, "")
            if not expected or expected.startswith("team_"):
                continue  # no usable mapping — keep entry as-is (best-effort)
            # v22: prefer team_abbrev, fall back to team field (older entries)
            actual = info.get("team_abbrev", "") or info.get("team", "")
            if actual and actual != expected:
                bad_keys.append((jersey_num, label))'''
assert old in src
src = src.replace(old, new)
PR.write_text(src)
print("v22 debug applied")
