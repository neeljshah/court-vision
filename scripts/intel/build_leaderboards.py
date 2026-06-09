"""
build_leaderboards.py — Generate vault/Intelligence/Leaderboards.md

Single idempotent run produces one file with:
  Section 1 — Team leaderboards (top-5 / bottom-5 across every dimension)
  Section 2 — Player leaderboards (top-10 per stat)
  Section 3 — Cross-cuts (net rating, extreme identity, pace mismatches)

Python 3.9 | stdlib + pandas
"""
from __future__ import annotations
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
TEAMS_DIR  = ROOT / "vault" / "Intelligence" / "Teams"
PLAYERS_DIR = ROOT / "vault" / "Intelligence" / "Players"
OUT_PATH   = ROOT / "vault" / "Intelligence" / "Leaderboards.md"

TEAM_NAMES = {
    "ATL": "Atlanta Hawks",       "BKN": "Brooklyn Nets",
    "BOS": "Boston Celtics",      "CHA": "Charlotte Hornets",
    "CHI": "Chicago Bulls",       "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks",    "DEN": "Denver Nuggets",
    "DET": "Detroit Pistons",     "GSW": "Golden State Warriors",
    "HOU": "Houston Rockets",     "IND": "Indiana Pacers",
    "LAC": "LA Clippers",         "LAL": "Los Angeles Lakers",
    "MEM": "Memphis Grizzlies",   "MIA": "Miami Heat",
    "MIL": "Milwaukee Bucks",     "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans","NYK": "New York Knicks",
    "OKC": "Oklahoma City Thunder","ORL": "Orlando Magic",
    "PHI": "Philadelphia 76ers",  "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers","SAC": "Sacramento Kings",
    "SAS": "San Antonio Spurs",   "TOR": "Toronto Raptors",
    "UTA": "Utah Jazz",           "WAS": "Washington Wizards",
}

NUM_RE = r"[-+]?\d*\.?\d+"


# ──────────────────────────────────────────────────────────────────── helpers

def _grab(text: str, label_pattern: str, value_pattern: str = NUM_RE) -> float | None:
    patterns = [
        rf"[-*]\s+\*\*(?:[^*\n]*?\s)?{label_pattern}\s*:?\s*\*\*\s*({value_pattern})",
        rf"\*\*(?:[^*\n]*?\s)?{label_pattern}\s*:?\s*\*\*\s*({value_pattern})",
        rf"\|\s*{label_pattern}\s*\|\s*({value_pattern})\s*\|",
        rf"(?:^|\n){label_pattern}\s*:\s*({value_pattern})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            v = m.group(1).strip()
            cleaned = v.rstrip("%").replace(",", "")
            try:
                f = float(cleaned)
                if v.endswith("%") and f > 1.0:
                    return f / 100.0
                return f
            except (TypeError, ValueError):
                return None
    return None


def _grab_str(text: str, label_pattern: str) -> str | None:
    patterns = [
        rf"[-*]\s+\*\*(?:[^*\n]*?\s)?{label_pattern}\s*:?\s*\*\*\s*([^\n|]+?)\s*(?:\||\n|$)",
        rf"\*\*(?:[^*\n]*?\s)?{label_pattern}\s*:?\s*\*\*\s*([^\n|]+?)\s*(?:\||\n|$)",
        rf"\|\s*{label_pattern}\s*\|\s*([^\n|]+?)\s*\|",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _f(v: Any, nd: int = 2) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return "—"


def _pct(v: Any, nd: int = 1) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        if 0 <= f <= 1.0:
            f *= 100
        return f"{f:.{nd}f}%"
    except (TypeError, ValueError):
        return "—"


# ──────────────────────────────────────────────────────────────────── parsers

def parse_team(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    d: dict = {"abbr": path.stem}
    m = re.search(r"^#\s+([A-Z]{3})\b", text, re.M)
    if m:
        d["abbr"] = m.group(1)

    # Ratings / basic
    d["offrtg"]     = _grab(text, r"OffRtg(?! L10)")
    d["defrtg"]     = _grab(text, r"DefRtg(?! L10| trend)")
    d["pace"]       = _grab(text, r"Pace\b(?!\s*(?:label|identity|imposed|context))")
    d["efg"]        = _grab(text, r"eFG%")
    d["ts"]         = _grab(text, r"TS%")
    d["tov_ratio"]  = _grab(text, r"TOV ratio")
    d["ast_pct"]    = _grab(text, r"Ast%")
    d["oreb_pct"]   = _grab(text, r"OReb%(?! season| L10| rank)")
    d["dreb_pct"]   = _grab(text, r"DReb%(?! season| L10| rank)")

    # 3PT defence
    d["opp_3p_pct"] = _grab(text, r"Opp 3P%")
    d["opp_3pa_g"]  = _grab(text, r"3PA/g")
    d["opp_3pa_rate"]= _grab(text, r"3PA rate")

    # Rim defense
    d["rim_fg_allow"]= _grab(text, r"Rim FG% allowed")
    d["paint_fg"]    = _grab(text, r"Paint FG% allowed")

    # Perimeter pressure z-scores
    d["contest_z"]   = _grab(text, r"Contested shot rate z")
    d["def_dist_z"]  = _grab(text, r"Avg defender distance z")
    d["pace_impose_z"]= _grab(text, r"Pace imposed z")

    # Offensive tempo/spacing z-scores
    d["tempo_z"]     = _grab(text, r"Tempo z")
    d["trans_share_z"]= _grab(text, r"Transition share z")
    d["spacing_z"]   = _grab(text, r"Avg spacing z")

    # Ball movement / drives
    d["passes_g"]    = _grab(text, r"Passes made/g")
    d["drives_g"]    = _grab(text, r"Drives/g")
    d["drive_fg"]    = _grab(text, r"Drive FG%")

    # Turnover / deflections
    d["opp_tov"]     = _grab(text, r"Opp TOV% \(season\)")
    d["deflect_g"]   = _grab(text, r"Deflections/g")

    # FT environment
    d["pf_g"]        = _grab(text, r"PF/g")
    d["net_fta"]     = _grab(text, r"Net FTA differential")

    # Scheme axis z-scores
    d["drop_switch"] = _grab(text, r"Drop vs Switch")
    d["paint_prot"]  = _grab(text, r"Paint Protection")
    d["perim_denial"]= _grab(text, r"Perimeter Denial")
    d["pace_ctrl"]   = _grab(text, r"Pace Control")
    d["iso_force"]   = _grab(text, r"Iso Force")
    d["closeout"]    = _grab(text, r"Active Closeouts")

    # Opp shot mix z-scores
    d["opp_paint_z"] = _grab(text, r"Opp paint% z")
    d["opp_3_z"]     = _grab(text, r"Opp 3pt% z")

    return d


def parse_player(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    if "<!-- PLAYSTYLE-EXPORT v1 -->" not in text:
        return None

    d: dict = {}
    m = re.search(r"^#\s+(.+?)\s*$", text, re.M)
    d["name"] = m.group(1).strip() if m else path.stem

    m = re.search(r"\*\*Team:\*\*\s*\[\[([A-Z]+)\]\]", text)
    d["team"] = m.group(1) if m else "???"

    # Key stats
    d["usage_rate"]  = _grab(text, r"Usage rate")
    d["usage_rank"]  = _grab(text, r"Usage % rank")
    d["ast_pct"]     = _grab(text, r"AST %")
    d["ast_rank"]    = _grab(text, r"AST % rank")
    d["pie"]         = _grab(text, r"Pie mean")
    d["impact_rank"] = _grab(text, r"Impact % rank")
    d["on_off"]      = _grab(text, r"On off net diff")
    d["drives"]      = _grab(text, r"Drives per game")
    d["ast_pts"]     = _grab(text, r"AST pts created")
    d["ato"]         = _grab(text, r"AST to TOV")
    d["dreb"]        = _grab(text, r"DREB rate(?! rank)")
    d["oreb"]        = _grab(text, r"OREB rate(?! rank)")
    d["three_share"] = _grab(text, r"Pts 3pt share")
    d["catch_efg"]   = _grab(text, r"Catch shoot eFG")
    d["catch_rank"]  = _grab(text, r"Catch shoot % rank")
    d["fg_allow"]    = _grab(text, r"FG % allowed")
    d["three_allow"] = _grab(text, r"3PT % allowed")
    d["gravity"]     = _grab(text, r"Gravity score")
    d["gravity_rank"]= _grab(text, r"Gravity % rank")
    d["minutes"]     = _grab(text, r"Minutes per game")

    return d


# ──────────────────────────────────────────────────────────────────── team leaderboard builder

def _team_wiki(abbr: str) -> str:
    return f"[[Teams/{abbr}|{abbr}]]"


def _player_wiki(d: dict) -> str:
    return f"[[Players/{d['name'].replace(' ', '_')}|{d['name']}]]"


def _lb_table(rows: list[tuple], headers: list[str]) -> str:
    """rows = list of tuples matching headers"""
    sep = " | ".join("---" for _ in headers)
    hdr = " | ".join(headers)
    lines = [f"| {hdr} |", f"| {sep} |"]
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines)


def team_leaderboard(
    teams: list[dict],
    field: str,
    label: str,
    fmt_fn,
    high_is_good: bool = True,
    top_n: int = 5,
    read_fn=None,
    unit: str = "",
) -> str | None:
    """Return markdown block or None if no data."""
    valid = [(t, t[field]) for t in teams if t.get(field) is not None]
    if not valid:
        return None

    # Sort so best teams come first regardless of direction
    valid.sort(key=lambda x: x[1], reverse=high_is_good)
    top5 = valid[:top_n]    # best by this metric
    bot5 = valid[-top_n:]   # worst by this metric

    top_label = "Best 5" if high_is_good else "Best 5 (lowest)"
    bot_label = "Worst 5" if high_is_good else "Worst 5 (highest)"

    def rows(entries, rank_start=1):
        return [
            (f"#{rank_start + i}", _team_wiki(t["abbr"]), fmt_fn(v))
            for i, (t, v) in enumerate(entries)
        ]

    top_rows = rows(top5, rank_start=1)
    bot_rows = rows(bot5, rank_start=len(valid) - top_n + 1)

    top_tbl = _lb_table(top_rows, ["Rank", "Team", label + unit])
    bot_tbl = _lb_table(bot_rows, ["Rank", "Team", label + unit])

    read_line = ""
    if read_fn:
        read_line = f"\n**Read:** {read_fn(top5[0][0])}"

    return (
        f"#### {label} — {top_label}\n\n{top_tbl}\n\n"
        f"#### {label} — {bot_label}\n\n{bot_tbl}"
        f"{read_line}\n"
    )


def _auto_read_pace(t: dict) -> str:
    abbr = t["abbr"]
    pace = t.get("pace")
    return f"{abbr} pushes pace ({_f(pace, 1)} poss/g) — accelerates transition before sets are established."


def _auto_read_offrtg(t: dict) -> str:
    abbr = t["abbr"]
    return f"{abbr} leads offense (OffRtg {_f(t.get('offrtg'), 1)}) — opponent prep must neutralize their halfcourt efficiency."


def _auto_read_defrtg(t: dict) -> str:
    abbr = t["abbr"]
    return f"{abbr} best defense (DefRtg {_f(t.get('defrtg'), 1)}) — limits scoring outputs across all opponent archetypes."


def _auto_read_spacing(t: dict) -> str:
    abbr = t["abbr"]
    z = t.get("spacing_z")
    return f"{abbr} imposes wide spacing (z={_f(z)}) — fits a movement-shooting offense."


def _auto_read_drives(t: dict) -> str:
    abbr = t["abbr"]
    return f"{abbr} drives the paint hard ({_f(t.get('drives_g'), 1)}/g) — collapses help defense and creates kick-out 3s."


def _auto_read_passes(t: dict) -> str:
    abbr = t["abbr"]
    return f"{abbr} maximizes ball movement ({_f(t.get('passes_g'), 1)} passes/g) — extra possessions from assist chains."


def _auto_read_oreb(t: dict) -> str:
    abbr = t["abbr"]
    return f"{abbr} crashes hard ({_pct(t.get('oreb_pct'))} OReb%) — second-chance volume distorts game scripts."


def _auto_read_rim(t: dict) -> str:
    abbr = t["abbr"]
    return f"{abbr} rim protection ({_pct(t.get('rim_fg_allow'))} FG allowed at rim) — suppresses paint finishing."


def _auto_read_deflect(t: dict) -> str:
    abbr = t["abbr"]
    return f"{abbr} active hands ({_f(t.get('deflect_g'), 1)} deflections/g) — disrupts passing lanes and forces live-ball turnovers."


def _auto_read_contest(t: dict) -> str:
    abbr = t["abbr"]
    return f"{abbr} contests everything (z={_f(t.get('contest_z'))}) — shooter efficiency suppressed on mid-range and 3s."


def _auto_read_tempo_z(t: dict) -> str:
    abbr = t["abbr"]
    return f"{abbr} pushes league-high tempo (z={_f(t.get('tempo_z'))}) — exploits early-game defensive rotations."


# ──────────────────────────────────────────────────────────────────── player leaderboard builder

def player_leaderboard(
    players: list[dict],
    field: str,
    label: str,
    fmt_fn,
    min_minutes: float = 0.0,
    min_field: str | None = None,
    min_val: float | None = None,
    top_n: int = 10,
    note_fn=None,
) -> str | None:
    filtered = [
        p for p in players
        if p.get(field) is not None
        and (p.get("minutes") or 0) >= min_minutes
        and (min_field is None or (p.get(min_field) is not None and p[min_field] >= (min_val or 0)))
    ]
    if not filtered:
        return None
    filtered.sort(key=lambda p: p[field], reverse=True)
    top = filtered[:top_n]

    def _context(p: dict) -> str:
        if note_fn:
            return note_fn(p)
        return ""

    rows = [
        (f"#{i+1}", _player_wiki(p), p.get("team", "?"), fmt_fn(p[field]), _context(p))
        for i, p in enumerate(top)
    ]
    tbl = _lb_table(rows, ["Rank", "Player", "Team", label, "Context"])
    return f"{tbl}\n"


# ──────────────────────────────────────────────────────────────────── main build

def build(teams: list[dict], players: list[dict]) -> str:
    lines: list[str] = []
    n_team_lb = 0
    n_player_lb = 0
    n_cross = 0

    ts_now = "2026-06-01"
    lines.append(f"# League Leaderboards\n")
    lines.append(f"*Auto-generated by `scripts/intel/build_leaderboards.py` — do not edit manually.*  ")
    lines.append(f"*Last updated: {ts_now} | {len(teams)} teams · {len(players)} players*\n")
    lines.append("---\n")

    # ──────────── SECTION 1: TEAM LEADERBOARDS
    lines.append("## Section 1 — Team Leaderboards\n")
    lines.append("*Top-5 / Bottom-5 across all extracted dimensions. Wiki-links open the team card.*\n")

    def _add_team_lb(field, label, fmt_fn, high_good, read_fn=None, unit=""):
        nonlocal n_team_lb
        block = team_leaderboard(teams, field, label, fmt_fn, high_good, read_fn=read_fn, unit=unit)
        if block:
            lines.append(f"### {label}\n")
            lines.append(block)
            n_team_lb += 1

    # Pace
    _add_team_lb("pace", "Pace (poss/g)", lambda v: _f(v, 1), True, _auto_read_pace)
    # OffRtg
    _add_team_lb("offrtg", "OffRtg", lambda v: _f(v, 1), True, _auto_read_offrtg)
    # DefRtg (lower = better)
    _add_team_lb("defrtg", "DefRtg (lower = better)", lambda v: _f(v, 1), False, _auto_read_defrtg)
    # eFG%
    _add_team_lb("efg", "eFG%", lambda v: _pct(v), True)
    # TS%
    _add_team_lb("ts", "TS%", lambda v: _pct(v), True)
    # Assist rate
    _add_team_lb("ast_pct", "Assist Rate", lambda v: _pct(v), True)
    # TOV ratio (lower = better)
    _add_team_lb("tov_ratio", "TOV Ratio (lower = better)", lambda v: _f(v, 1), False)
    # 3PA/g
    _add_team_lb("opp_3pa_g", "3PA/g (opponent)", lambda v: _f(v, 1), False)
    # 3PA rate
    _add_team_lb("opp_3pa_rate", "3PA Rate (opponent)", lambda v: _pct(v), False)
    # Drives/g
    _add_team_lb("drives_g", "Drives/g", lambda v: _f(v, 1), True, _auto_read_drives)
    # Drive FG%
    _add_team_lb("drive_fg", "Drive FG%", lambda v: _pct(v), True)
    # Passes/g
    _add_team_lb("passes_g", "Passes/g", lambda v: _f(v, 1), True, _auto_read_passes)
    # OReb%
    _add_team_lb("oreb_pct", "OReb% (offensive glass)", lambda v: _pct(v), True, _auto_read_oreb)
    # DReb%
    _add_team_lb("dreb_pct", "DReb% (defensive glass)", lambda v: _pct(v), True)
    # Opp 3P%
    _add_team_lb("opp_3p_pct", "Opp 3P% (3PT defense — lower = better)", lambda v: _pct(v), False)
    # Rim FG% allowed (lower = better)
    _add_team_lb("rim_fg_allow", "Rim FG% Allowed (lower = better)", lambda v: _pct(v), False, _auto_read_rim)
    # Opp TOV% (higher = better defense)
    _add_team_lb("opp_tov", "Opp TOV% (turnover forcing)", lambda v: _pct(v), True)
    # Deflections/g
    _add_team_lb("deflect_g", "Deflections/g", lambda v: _f(v, 1), True, _auto_read_deflect)
    # PF/g
    _add_team_lb("pf_g", "PF/g (foul rate)", lambda v: _f(v, 1), False)
    # Net FTA differential
    _add_team_lb("net_fta", "Net FTA Differential", lambda v: f"{'+' if (v or 0) >= 0 else ''}{_f(v, 1)}", True)
    # Contest rate z
    _add_team_lb("contest_z", "Contest Rate z", lambda v: _f(v, 3), True, _auto_read_contest)
    # Avg defender distance z (lower = tighter coverage)
    _add_team_lb("def_dist_z", "Avg Defender Distance z (lower = tighter)", lambda v: _f(v, 3), False)
    # Tempo z
    _add_team_lb("tempo_z", "Tempo z", lambda v: _f(v, 3), True, _auto_read_tempo_z)
    # Spacing z
    _add_team_lb("spacing_z", "Spacing z", lambda v: _f(v, 3), True, _auto_read_spacing)
    # Transition share z
    _add_team_lb("trans_share_z", "Transition Share z", lambda v: _f(v, 3), True)

    lines.append("---\n")

    # ──────────── SECTION 2: PLAYER LEADERBOARDS
    lines.append("## Section 2 — Player Leaderboards\n")
    lines.append("*Top-10 per stat. Min 15 mpg unless noted. Wiki-links open the player card.*\n")

    def _add_player_lb(title: str, field: str, fmt_fn, min_min=15.0, note_fn=None,
                       min_field=None, min_val=None):
        nonlocal n_player_lb
        lines.append(f"### {title}\n")
        block = player_leaderboard(
            players, field, title, fmt_fn,
            min_minutes=min_min, note_fn=note_fn,
            min_field=min_field, min_val=min_val,
        )
        if block:
            lines.append(block)
            n_player_lb += 1
        else:
            lines.append("*No data for this dimension.*\n")

    # Usage %
    _add_player_lb("Usage % Leaders", "usage_rate", lambda v: _pct(v),
                   note_fn=lambda p: f"rank {int(p['usage_rank'])}th pct" if p.get("usage_rank") else "")

    # AST %
    _add_player_lb("AST % Leaders", "ast_pct", lambda v: _pct(v),
                   note_fn=lambda p: f"rank {int(p['ast_rank'])}th pct" if p.get("ast_rank") else "")

    # PIE
    _add_player_lb("PIE Leaders (all-around impact)", "pie", lambda v: _pct(v),
                   note_fn=lambda p: f"on/off {'+' if (p.get('on_off') or 0) >= 0 else ''}{_f(p.get('on_off'), 1)}")

    # On/off — highest
    _add_player_lb("On/Off Net Diff — Best", "on_off", lambda v: f"{'+' if v >= 0 else ''}{_f(v, 1)}",
                   note_fn=lambda p: f"PIE {_pct(p.get('pie'))}")

    # On/off — lowest (most negative)
    lines.append("### On/Off Net Diff — Worst (context: low-usage role players)\n\n")
    bot_onoff = sorted(
        [p for p in players if p.get("on_off") is not None and (p.get("minutes") or 0) >= 15],
        key=lambda p: p["on_off"]
    )[:10]
    if bot_onoff:
        rows_bot = [
            (f"#{i+1}", _player_wiki(p), p.get("team", "?"),
             f"{'+' if p['on_off'] >= 0 else ''}{_f(p['on_off'], 1)}", _pct(p.get("pie")))
            for i, p in enumerate(bot_onoff)
        ]
        lines.append(_lb_table(rows_bot, ["Rank", "Player", "Team", "On/Off", "PIE"]) + "\n\n")
        n_player_lb += 1

    # A/TO
    _add_player_lb("A/TO Ratio Leaders", "ato", lambda v: _f(v, 2),
                   min_field="ast_pts", min_val=3.0,
                   note_fn=lambda p: f"AST pts {_f(p.get('ast_pts'), 1)}")

    # Drives/g
    _add_player_lb("Drives/g Leaders", "drives", lambda v: _f(v, 1),
                   note_fn=lambda p: f"usage {_pct(p.get('usage_rate'))}")

    # AST pts created
    _add_player_lb("AST Points Created Leaders", "ast_pts", lambda v: _f(v, 1),
                   note_fn=lambda p: f"A/TO {_f(p.get('ato'), 2)}")

    # DREB%
    _add_player_lb("DREB% Leaders (big-man boards)", "dreb", lambda v: _pct(v),
                   note_fn=lambda p: f"min {_f(p.get('minutes'), 1)} mpg")

    # 3PT share leaders (min usage)
    _add_player_lb("3PT Volume Leaders (pts from 3)", "three_share", lambda v: _pct(v),
                   min_field="usage_rate", min_val=0.12,
                   note_fn=lambda p: f"catch-eFG {_pct(p.get('catch_efg'))}")

    # Most efficient catch-and-shoot (min catch_rank > 40 to ensure volume)
    _add_player_lb("Catch-and-Shoot eFG% (efficiency leaders)", "catch_efg", lambda v: _pct(v),
                   min_field="catch_rank", min_val=20.0,
                   note_fn=lambda p: f"3pt share {_pct(p.get('three_share'))}")

    # Best FG% suppression on defense (lower allowed FG = better)
    lines.append("### Best FG% Suppression on Defense (lowest FG% allowed)\n\n")
    best_fg_sup = sorted(
        [p for p in players if p.get("fg_allow") is not None and (p.get("minutes") or 0) >= 15],
        key=lambda p: p["fg_allow"]
    )[:10]
    if best_fg_sup:
        rows_fg = [
            (f"#{i+1}", _player_wiki(p), p.get("team", "?"), _pct(p.get("fg_allow")), "")
            for i, p in enumerate(best_fg_sup)
        ]
        lines.append(_lb_table(rows_fg, ["Rank", "Player", "Team", "FG% Allowed", "Context"]) + "\n\n")
        n_player_lb += 1

    # Best 3PT% suppression on defense
    lines.append("### Best 3PT% Suppression on Defense (lowest 3PT% allowed)\n\n")
    best_3pt_sup = sorted(
        [p for p in players if p.get("three_allow") is not None and (p.get("minutes") or 0) >= 15],
        key=lambda p: p["three_allow"]
    )[:10]
    if best_3pt_sup:
        rows_3pt = [
            (f"#{i+1}", _player_wiki(p), p.get("team", "?"), _pct(p.get("three_allow")), "")
            for i, p in enumerate(best_3pt_sup)
        ]
        lines.append(_lb_table(rows_3pt, ["Rank", "Player", "Team", "3PT% Allowed", "Context"]) + "\n\n")
        n_player_lb += 1

    # Gravity rank leaders
    _add_player_lb("Gravity Leaders (off-ball spacing threat)", "gravity", lambda v: _f(v, 2),
                   note_fn=lambda p: f"rank {int(p['gravity_rank'])}th pct" if p.get("gravity_rank") else "")

    lines.append("---\n")

    # ──────────── SECTION 3: CROSS-CUTS
    lines.append("## Section 3 — Cross-Cuts\n")

    # Net Rating (OffRtg - DefRtg)
    lines.append("### Best Net Rating (OffRtg − DefRtg)\n\n")
    net_teams = [
        (t, t["offrtg"] - t["defrtg"])
        for t in teams
        if t.get("offrtg") is not None and t.get("defrtg") is not None
    ]
    net_teams.sort(key=lambda x: x[1], reverse=True)
    if net_teams:
        nr_rows = [
            (f"#{i+1}", _team_wiki(t["abbr"]),
             _f(t.get("offrtg"), 1), _f(t.get("defrtg"), 1),
             f"{'+' if nr >= 0 else ''}{_f(nr, 1)}")
            for i, (t, nr) in enumerate(net_teams[:10])
        ]
        lines.append(_lb_table(nr_rows, ["Rank", "Team", "OffRtg", "DefRtg", "Net Rtg"]) + "\n\n")
        n_cross += 1

    # Most extreme offensive identity
    lines.append("### Most Extreme Offensive Identity\n")
    lines.append("*Rank by |tempo z| + |spacing z| + |transition share z| — highest = most stylistically distinct*\n\n")
    off_extreme = []
    for t in teams:
        s = sum(
            abs(t[k]) for k in ("tempo_z", "spacing_z", "trans_share_z")
            if t.get(k) is not None
        )
        if s > 0:
            off_extreme.append((t, s))
    off_extreme.sort(key=lambda x: x[1], reverse=True)
    if off_extreme:
        oe_rows = [
            (f"#{i+1}", _team_wiki(t["abbr"]),
             _f(t.get("tempo_z"), 2), _f(t.get("spacing_z"), 2),
             _f(t.get("trans_share_z"), 2), _f(s, 2))
            for i, (t, s) in enumerate(off_extreme[:10])
        ]
        lines.append(_lb_table(oe_rows, ["Rank", "Team", "Tempo z", "Spacing z", "Trans z", "Σ|z|"]) + "\n\n")
        n_cross += 1

    # Most extreme defensive identity
    lines.append("### Most Extreme Defensive Identity\n")
    lines.append("*Rank by Σ|axis z-scores| — highest = most stylistically distinct defense*\n\n")
    def_extreme = []
    for t in teams:
        s = sum(
            abs(t[k]) for k in ("drop_switch", "paint_prot", "perim_denial", "pace_ctrl", "iso_force", "closeout")
            if t.get(k) is not None
        )
        if s > 0:
            def_extreme.append((t, s))
    def_extreme.sort(key=lambda x: x[1], reverse=True)
    if def_extreme:
        de_rows = [
            (f"#{i+1}", _team_wiki(t["abbr"]),
             _f(t.get("drop_switch"), 2), _f(t.get("paint_prot"), 2),
             _f(t.get("perim_denial"), 2), _f(t.get("pace_ctrl"), 2),
             _f(s, 2))
            for i, (t, s) in enumerate(def_extreme[:10])
        ]
        lines.append(_lb_table(de_rows,
            ["Rank", "Team", "Drop/Switch", "Paint Prot", "Perim Denial", "Pace Ctrl", "Σ|z|"]) + "\n\n")
        n_cross += 1

    # Pace mismatches
    lines.append("### Pace Mismatches to Watch\n")
    lines.append("*Any team pair with pace gap > 4 possessions/g — these matchups are style-clash games.*\n\n")
    pace_teams = [(t, t["pace"]) for t in teams if t.get("pace") is not None]
    pace_teams.sort(key=lambda x: x[1], reverse=True)
    mismatches = []
    for i, (ta, pa) in enumerate(pace_teams):
        for tb, pb in pace_teams[i+1:]:
            gap = pa - pb
            if gap > 4.0:
                mismatches.append((ta, pa, tb, pb, gap))
    mismatches.sort(key=lambda x: x[4], reverse=True)
    if mismatches:
        mm_rows = [
            (f"#{i+1}", _team_wiki(a["abbr"]), _f(pa, 1),
             _team_wiki(b["abbr"]), _f(pb, 1), _f(gap, 1))
            for i, (a, pa, b, pb, gap) in enumerate(mismatches[:20])
        ]
        lines.append(_lb_table(mm_rows,
            ["#", "Fast Team", "Pace", "Slow Team", "Pace", "Gap"]) + "\n\n")
        n_cross += 1
    else:
        lines.append("*No pace mismatches > 4 poss/g found in current dataset.*\n\n")

    lines.append("---\n")
    lines.append(f"*Build summary: {n_team_lb} team leaderboards · {n_player_lb} player leaderboards · {n_cross} cross-cuts*\n")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────── entry point

def main():
    print("Loading team notes…", file=sys.stderr)
    teams = []
    for p in sorted(TEAMS_DIR.glob("*.md")):
        try:
            d = parse_team(p)
            teams.append(d)
        except Exception as e:
            print(f"[team-fail] {p.name}: {e}", file=sys.stderr)

    print("Loading player notes…", file=sys.stderr)
    players = []
    for p in sorted(PLAYERS_DIR.glob("*.md")):
        try:
            d = parse_player(p)
            if d:
                players.append(d)
        except Exception as e:
            print(f"[player-fail] {p.name}: {e}", file=sys.stderr)

    print(f"Loaded {len(teams)} teams, {len(players)} players", file=sys.stderr)

    md = build(teams, players)
    OUT_PATH.write_text(md, encoding="utf-8")
    print(f"Wrote {OUT_PATH}", file=sys.stderr)

    # Summary + first 200 lines
    # Parse counts from build() summary line embedded in the file
    import re as _re
    m = _re.search(r"Build summary: (\d+) team leaderboards · (\d+) player leaderboards · (\d+) cross-cuts", md)
    n_team_lb_final  = int(m.group(1)) if m else "?"
    n_player_lb_final = int(m.group(2)) if m else "?"
    n_cross_final    = int(m.group(3)) if m else "?"

    print(f"\n=== Summary ===")
    print(f"n_team_leaderboards  : {n_team_lb_final}")
    print(f"n_player_leaderboards: {n_player_lb_final}")
    print(f"n_cross_cuts         : {n_cross_final}")
    print(f"\n=== First 200 lines of output ===")
    preview = "\n".join(md.splitlines()[:200])
    print(preview)


if __name__ == "__main__":
    main()
