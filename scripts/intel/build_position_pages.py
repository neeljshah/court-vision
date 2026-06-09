"""
Build per-position rolling pages (PG / SG / SF / PF / C plus combos like F-G).

For each position label found in the 582 player notes, write
vault/Intelligence/Positions/<position_slug>.md with ranked tables for:
  - Top scorers / volume leaders (usage)
  - Top playmakers (AST pts created + A/TO)
  - Top defenders (FG% suppression + form blocks/steals)
  - Top shooters (3PT share + catch-and-shoot eFG)
  - Top rebounders (DREB%)

Plus Positions_Index.md MOC.

Idempotent. UTF-8 output.
"""
from __future__ import annotations
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PLAYERS_DIR = ROOT / "vault" / "Intelligence" / "Players"
POSITIONS_DIR = ROOT / "vault" / "Intelligence" / "Positions"
INDEX = ROOT / "vault" / "Intelligence" / "Positions_Index.md"


def _grab(text, label_pat, num=True):
    """Extract a value from bullets like '**[Section — ]Label:** value[%]'."""
    pat = rf"[-*]\s+\*\*(?:[^*\n]*?\s)?{label_pat}\s*:?\s*\*\*\s*([-+]?\d*\.?\d+%?|\w[\w \-\/]*)"
    m = re.search(pat, text, re.I)
    if not m:
        return None
    v = m.group(1).strip()
    if not num:
        return v
    cleaned = v.rstrip("%").replace(",", "")
    try:
        f = float(cleaned)
        return f / 100.0 if v.endswith("%") else f
    except ValueError:
        return None


def _parse_player(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if "<!-- PLAYSTYLE-EXPORT v1 -->" not in text:
        return None
    d = {"path": path, "slug_full": path.stem,
         "pid": path.stem.split("_", 1)[0]}
    m = re.search(r"^#\s+(.+?)\s*$", text, re.M)
    d["name"] = m.group(1).strip() if m else d["pid"]
    m = re.search(r"\*\*Team:\*\*\s*\[\[([A-Z]{3})\]\]", text)
    d["tri"] = m.group(1) if m else None
    m = re.search(r"\*\*Archetype:\*\*\s*([^·\n]+)", text)
    d["archetype"] = m.group(1).strip() if m else "Role Player"
    d["position"] = _grab(text, r"Position", num=False) or "Unknown"
    d["usage"] = _grab(text, r"Usage rate")
    d["mpg"] = _grab(text, r"Minutes per game")
    d["ast_pct"] = _grab(text, r"AST %")
    d["pie"] = _grab(text, r"Pie mean")
    d["impact_rank"] = _grab(text, r"Impact % rank")
    d["ast_pts"] = _grab(text, r"AST pts created")
    d["ato"] = _grab(text, r"AST to TOV")
    d["passes"] = _grab(text, r"Passes made")
    d["three_share"] = _grab(text, r"Pts 3pt share")
    d["paint_share"] = _grab(text, r"Pts paint share")
    d["ft_share"] = _grab(text, r"Pts FT share")
    d["drives"] = _grab(text, r"Drives per game")
    d["catch_efg"] = _grab(text, r"Catch shoot eFG")
    d["unassist_3"] = _grab(text, r"Unassisted share 3PM")
    d["dreb"] = _grab(text, r"DREB rate(?! rank)")
    d["oreb"] = _grab(text, r"OREB rate(?! rank)")
    d["treb"] = _grab(text, r"Total reb rate(?! rank)")
    d["fg_allow"] = _grab(text, r"FG % allowed")
    d["three_allow"] = _grab(text, r"3PT % allowed")
    d["form_blk"] = _grab(text, r"Monthly form — BLK per game")
    d["form_stl"] = _grab(text, r"Monthly form — STL per game")
    d["form_pts"] = _grab(text, r"Monthly form — Pts per game")
    d["form_ast"] = _grab(text, r"Monthly form — AST per game")
    d["form_reb"] = _grab(text, r"Monthly form — Reb per game")
    d["onoff"] = _grab(text, r"On off net diff")
    d["gravity_rank"] = _grab(text, r"Gravity % rank")
    return d


POSITION_DESC = {
    "Guard": "Backcourt — primary ball-handlers and perimeter shot creators.",
    "Forward-Guard": "Wing — combo F/G with both perimeter and slashing skill.",
    "Forward": "Frontcourt wings — mix paint pressure and stretch shooting.",
    "Forward-Center": "Stretch / hybrid bigs — anchor or floor-space depending on lineup.",
    "Center": "Frontcourt anchors — rim protection and interior scoring.",
    "Unknown": "Position not classified in source data.",
}


def _pos_slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def _fmt_pct(v, nd=1):
    if v is None:
        return "—"
    return f"{v*100:.{nd}f}%" if v <= 1 else f"{v:.{nd}f}%"


def _fmt_num(v, nd=2):
    if v is None:
        return "—"
    return f"{v:.{nd}f}"


def _link(p):
    return f"[[{p['slug_full']}\\|{p['name']}]]"


def _team(p):
    return f"[[{p['tri']}]]" if p.get('tri') else "—"


def _rank_table(players, key, header_cols, row_fn, *, reverse=True, top_n=15,
                min_filter=None):
    """Generic ranking table. row_fn(p) -> list of cell strs."""
    pool = [p for p in players if p.get(key) is not None]
    if min_filter:
        pool = [p for p in pool if min_filter(p)]
    pool = sorted(pool, key=lambda p: (p[key] is None, -(p[key] if reverse else -p[key])))
    L = ["| " + " | ".join(header_cols) + " |",
         "|" + "|".join(["---"] * len(header_cols)) + "|"]
    for i, p in enumerate(pool[:top_n], 1):
        L.append(f"| {i} | " + " | ".join(str(c) for c in row_fn(p)) + " |")
    return "\n".join(L)


def _build_page(pos, players):
    L = [f"<!-- POSITION-HUB v1 -->",
         f"---",
         f"position: {pos}",
         f"position_slug: {_pos_slug(pos)}",
         f"n_players: {len(players)}",
         f"n_teams: {len({p['tri'] for p in players if p.get('tri')})}",
         f"as_of: 2026-06-01",
         f"---",
         "",
         f"# Position — {pos}",
         "",
         POSITION_DESC.get(pos, "Position label discovered from current-season data."),
         "",
         f"**{len(players)} current-season players** across "
         f"{len({p['tri'] for p in players if p.get('tri')})} teams.",
         "",
         "[[_Atlas|← Intelligence Atlas]] · [[Positions_Index|All positions]] · [[Players_Index|All players]]",
         "",
         "---",
         ""]

    # Min minutes for "meaningful" rankings
    def min_mpg(min_m): return lambda p: (p.get("mpg") or 0) >= min_m

    L += ["## Top scorers / volume", "",
          "*Ranked by usage rate. Min 15 mpg.*", "",
          _rank_table(players, "usage",
                      ["#", "Player", "Team", "Usage%", "MPG", "PTS/g", "3PT share", "Impact rank"],
                      lambda p: [_link(p), _team(p), _fmt_pct(p["usage"]), _fmt_num(p["mpg"], 1),
                                 _fmt_num(p.get("form_pts"), 1), _fmt_pct(p.get("three_share")),
                                 _fmt_num(p.get("impact_rank"), 0)],
                      min_filter=min_mpg(15), top_n=15), ""]

    L += ["## Top playmakers", "",
          "*Ranked by points created via assists. Min 10 mpg.*", "",
          _rank_table(players, "ast_pts",
                      ["#", "Player", "Team", "AST pts/g", "A/TO", "Passes/g", "AST%"],
                      lambda p: [_link(p), _team(p), _fmt_num(p["ast_pts"], 1),
                                 _fmt_num(p.get("ato"), 2), _fmt_num(p.get("passes"), 1),
                                 _fmt_pct(p.get("ast_pct"))],
                      min_filter=min_mpg(10), top_n=12), ""]

    L += ["## Top defenders", "",
          "*Ranked by FG% suppression on matchups (lower = better). Min 12 mpg.*", "",
          _rank_table(players, "fg_allow",
                      ["#", "Player", "Team", "FG% allowed", "3PT% allowed", "BLK/g", "STL/g"],
                      lambda p: [_link(p), _team(p), _fmt_pct(p["fg_allow"]),
                                 _fmt_pct(p.get("three_allow")), _fmt_num(p.get("form_blk"), 1),
                                 _fmt_num(p.get("form_stl"), 1)],
                      reverse=False, min_filter=min_mpg(12), top_n=12), ""]

    L += ["## Top shooters", "",
          "*Ranked by catch-and-shoot eFG. Min 5% 3PT share to filter out non-shooters.*", "",
          _rank_table(players, "catch_efg",
                      ["#", "Player", "Team", "Catch eFG", "3PT share", "Unassisted 3PM%", "MPG"],
                      lambda p: [_link(p), _team(p), _fmt_pct(p["catch_efg"]),
                                 _fmt_pct(p.get("three_share")), _fmt_pct(p.get("unassist_3")),
                                 _fmt_num(p.get("mpg"), 1)],
                      min_filter=lambda p: (p.get("three_share") or 0) >= 0.05 and (p.get("mpg") or 0) >= 10,
                      top_n=12), ""]

    L += ["## Top rebounders", "",
          "*Ranked by DREB%. Min 12 mpg.*", "",
          _rank_table(players, "dreb",
                      ["#", "Player", "Team", "DREB%", "OREB%", "TREB%", "REB/g"],
                      lambda p: [_link(p), _team(p), _fmt_pct(p["dreb"]),
                                 _fmt_pct(p.get("oreb")), _fmt_pct(p.get("treb")),
                                 _fmt_num(p.get("form_reb"), 1)],
                      min_filter=min_mpg(12), top_n=12), ""]

    # archetype distribution
    arch_count = defaultdict(int)
    for p in players:
        arch_count[p["archetype"]] += 1
    L += ["## Archetype distribution within position", "",
          "| Archetype | Players |", "|---|---|"]
    for arch, n in sorted(arch_count.items(), key=lambda x: -x[1]):
        slug = re.sub(r"[^a-z0-9]+", "_", arch.lower()).strip("_")
        L.append(f"| [[Archetypes/{slug}\\|{arch}]] | {n} |")
    L.append("")

    # On/off net rating leaders
    L += ["## On/off net rating leaders (positive impact)", "",
          _rank_table(players, "onoff",
                      ["#", "Player", "Team", "On/off net", "MPG", "Usage%"],
                      lambda p: [_link(p), _team(p), f"{p['onoff']:+.1f}" if p.get('onoff') is not None else "—",
                                 _fmt_num(p.get("mpg"), 1), _fmt_pct(p.get("usage"))],
                      min_filter=min_mpg(15), top_n=10), ""]

    return "\n".join(L) + "\n"


def main():
    POSITIONS_DIR.mkdir(parents=True, exist_ok=True)
    by_pos = defaultdict(list)
    for f in sorted(PLAYERS_DIR.glob("*.md")):
        d = _parse_player(f)
        if d:
            by_pos[d["position"]].append(d)

    written = 0
    for pos, players in by_pos.items():
        out = POSITIONS_DIR / f"{_pos_slug(pos)}.md"
        out.write_text(_build_page(pos, players), encoding="utf-8")
        written += 1

    # Index MOC
    L = ["<!-- POSITIONS-INDEX v1 -->",
         "# Positions Index",
         "",
         f"Per-position rankings across all current-season players. Generated 2026-06-01.",
         "",
         "[[_Atlas|← Intelligence Atlas]]",
         "",
         "| Position | Players | Teams | Page |",
         "|---|---|---|---|"]
    for pos in sorted(by_pos, key=lambda p: -len(by_pos[p])):
        ps = by_pos[pos]
        n_teams = len({p['tri'] for p in ps if p.get('tri')})
        L.append(f"| {pos} | {len(ps)} | {n_teams} | [[Positions/{_pos_slug(pos)}\\|Open]] |")
    INDEX.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"positions_written: {written}")
    print(f"positions: {sorted(by_pos)}")
    print(f"index: {INDEX}")


if __name__ == "__main__":
    main()
