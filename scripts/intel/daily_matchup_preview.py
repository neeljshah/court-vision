"""daily_matchup_preview.py — Pregame matchup preview generator.

Fuses scheme identity, Scheme-Effects-Matrix, player scheme lines,
H2H coverage, Stopper Index, and Q4-fade into a scout-readable
markdown note with wikilinks to existing vault nodes.

READ-ONLY on all inputs; writes only to vault/Intelligence/Previews/.
No model/edge claims — scouting context only.

CLI:
  python scripts/intel/daily_matchup_preview.py --home OKC --away PHX [--date 2026-04-12]
  python scripts/intel/daily_matchup_preview.py --slate 2026-04-12
  python scripts/intel/daily_matchup_preview.py --slate today
  python scripts/intel/daily_matchup_preview.py --game-id 0022500968
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date as _date
from typing import Dict, List, Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Path constants (mirror build_matchup_intelligence.py)
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "data", "cache")
INTEL = os.path.join(CACHE, "intel")
NBA = os.path.join(ROOT, "data", "nba")
OUT = os.path.join(ROOT, "vault", "Intelligence", "Previews")
VAULT = os.path.join(ROOT, "vault", "Intelligence")

# ---------------------------------------------------------------------------
# Fallback constants (§11)
# ---------------------------------------------------------------------------

SCHEME_SLUG: Dict[str, str] = {
    "DROP COVERAGE": "drop_coverage",
    "SWITCH HEAVY": "switch_heavy",
    "HELP DEFENSE": "help_defense",
    "ISO FORCE": "iso_force",
    "PACE CONTROL": "pace_control",
    "PAINT-FIRST DEFENSE": "paint_first_defense",
    "BALANCED": "balanced",
    "ACTIVE CLOSEOUTS": "active_closeouts",
    "PERIMETER DENIAL": "perimeter_denial",
}

SCHEME_MATRIX_FALLBACK: Dict[str, Dict[str, float]] = {
    "balanced":             {"PG": -0.16, "SG":  0.09, "SF": -0.27, "PF": -0.36, "C": -1.07},
    "drop_coverage":        {"PG":  0.08, "SG":  0.09, "SF":  0.26, "PF":  0.28, "C":  0.07},
    "help_defense":         {"PG":  0.69, "SG":  0.58, "SF":  0.89, "PF":  0.46, "C":  0.41},
    "iso_force":            {"PG":  0.45, "SG":  0.19, "SF":  0.43, "PF":  0.52, "C":  1.09},
    "pace_control":         {"PG":  0.22, "SG":  0.47, "SF":  0.14, "PF": -0.20, "C": -0.08},
    "paint_first_defense":  {"PG":  0.15, "SG": -0.10, "SF":  0.03, "PF":  0.05, "C":  0.13},
    "switch_heavy":         {"PG":  0.39, "SG":  0.34, "SF":  0.40, "PF":  0.44, "C":  0.14},
    "active_closeouts":     {"PG":  0.05, "SG":  0.37, "SF":  0.29, "PF": -0.49, "C": -0.35},
    "perimeter_denial":     {"PG":  0.88, "SG":  0.66, "SF":  0.51, "PF":  0.56, "C":  1.20},
}

TEAM_TRIS = {
    "ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
}

# ---------------------------------------------------------------------------
# slug / _name_map — copied verbatim from build_matchup_intelligence.py
# ---------------------------------------------------------------------------

def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def _name_map() -> Dict[int, str]:
    m: Dict[int, str] = {}
    for season in ("2023-24", "2024-25", "2025-26"):
        p = os.path.join(NBA, f"player_avgs_{season}.json")
        if os.path.exists(p):
            for nm, info in json.load(open(p, encoding="utf-8")).items():
                pid = info.get("player_id")
                if pid is not None:
                    m[int(pid)] = nm.title()
    return m


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TeamScheme:
    dominant: str
    all_tags: List[str]
    conf: str
    scheme_page_slug: str  # slug of the [[Schemes/...]] link


@dataclass
class ScorerInfo:
    pid: int
    name: str
    pos_bucket: str          # PG / SG / SF / PF / C / ?
    pts: float
    ast: float
    reb: float
    fg3m: float


@dataclass
class H2HRow:
    def_pid: int
    def_name: str
    poss: float
    ppp: float
    rel: float
    verdict: str             # tough / neutral / feasts
    stopper_rank: Optional[int]
    stopper_ppp: Optional[float]


@dataclass
class ScorerPreview:
    scorer: ScorerInfo
    scheme_delta: Optional[float]            # matrix Δ vs baseline
    scheme_effect_read: str                  # suppressed / advantaged / neutral
    scheme_line_pts: Optional[float]         # pts in opp scheme
    scheme_line_ts: Optional[float]
    scheme_line_n: Optional[int]
    best_scheme: str
    worst_scheme: str
    ts_gap: float
    h2h: List[H2HRow]
    q4_minus_q1: Optional[float]
    q4_fade_flag: Optional[bool]


@dataclass
class SidePreview:
    off_tri: str
    def_tri: str
    def_scheme: TeamScheme
    scorers: List[ScorerPreview]
    stopper_flags: List[dict]  # {name, rank, ppp, fg_pct, fg3_pct}


@dataclass
class Sources:
    season_reg: Dict[str, dict]   # pid_str -> season line
    season_playoffs: Dict[str, dict]
    scheme_lines: Dict[str, dict]  # pid_str -> scheme lines
    roster: Dict[str, List[int]]   # tri -> [pid, ...]
    positions_df: pd.DataFrame     # player_id, player_name, position
    coverage_df: pd.DataFrame      # 2025-26 season rows
    stopper_top30: Dict[str, dict]   # name -> {rank, ppp, fg_pct, fg3_pct}
    stopper_exploited: Dict[str, dict]
    stopper_pid_lookup: Dict[int, dict]  # def_pid -> stopper row (if in top30)
    scheme_matrix: Dict[str, Dict[str, float]]  # slug -> {PG..C}
    name_map: Dict[int, str]
    schedule: List[dict]
    intel_cache: Dict[int, dict]   # pid -> player_<pid>.json (lazy loaded)


# ---------------------------------------------------------------------------
# Source loading
# ---------------------------------------------------------------------------

def _load_intel(pid: int) -> dict:
    p = os.path.join(INTEL, f"player_{pid}.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def load_sources(season: str = "2025-26") -> Sources:
    # S1: season box lines
    season_path = os.path.join(INTEL, "season_2025_26.json")
    if not os.path.exists(season_path):
        print(f"BLOCKED: missing {season_path}", file=sys.stderr)
        sys.exit(1)
    season_data = json.load(open(season_path, encoding="utf-8"))
    season_reg = season_data.get("reg", {})
    season_playoffs = season_data.get("playoffs", {})

    # S2: player scheme lines
    scheme_lines_path = os.path.join(INTEL, "player_scheme_lines.json")
    scheme_lines: Dict[str, dict] = {}
    if os.path.exists(scheme_lines_path):
        scheme_lines = json.load(open(scheme_lines_path, encoding="utf-8"))

    # S5: rosters
    roster_path = os.path.join(INTEL, "_roster_2025_26.json")
    if not os.path.exists(roster_path):
        print(f"BLOCKED: missing {roster_path}", file=sys.stderr)
        sys.exit(1)
    roster = json.load(open(roster_path, encoding="utf-8"))

    # S6: player positions
    pos_path = os.path.join(CACHE, "player_profile_features.parquet")
    if not os.path.exists(pos_path):
        print(f"BLOCKED: missing {pos_path}", file=sys.stderr)
        sys.exit(1)
    positions_df = pd.read_parquet(pos_path, columns=["player_id", "player_name", "position"])

    # S3: coverage
    cov_path = os.path.join(CACHE, "coverage_faced_allseasons.parquet")
    if not os.path.exists(cov_path):
        print(f"BLOCKED: missing {cov_path}", file=sys.stderr)
        sys.exit(1)
    cov_all = pd.read_parquet(cov_path)
    coverage_df = cov_all[cov_all["season"] == "2025-26"].copy()

    # S7: Stopper Index
    stopper_path = os.path.join(VAULT, "Scouts", "_Stopper_Index_2025-26.md")
    stopper_top30: Dict[str, dict] = {}
    stopper_exploited: Dict[str, dict] = {}
    stopper_pid_lookup: Dict[int, dict] = {}
    if os.path.exists(stopper_path):
        _stopper_t30, _stopper_ex = parse_stopper_index(stopper_path)
        stopper_top30 = _stopper_t30
        stopper_exploited = _stopper_ex
        # build pid lookup via name_map later (after name_map loaded)

    # S4: scheme matrix
    matrix_path = os.path.join(VAULT, "Schemes", "_Scheme_Effects_Matrix.md")
    scheme_matrix = parse_scheme_matrix(matrix_path)

    # S10: name_map
    name_map = _name_map()

    # Build stopper pid lookup: cross-ref name_map reverse
    name_to_pid: Dict[str, int] = {v.lower(): k for k, v in name_map.items()}
    for name, row in stopper_top30.items():
        pid_candidate = name_to_pid.get(name.lower())
        if pid_candidate:
            stopper_pid_lookup[pid_candidate] = row
    for name, row in stopper_exploited.items():
        pid_candidate = name_to_pid.get(name.lower())
        if pid_candidate:
            stopper_pid_lookup.setdefault(pid_candidate, row)

    # S8: schedule
    sched_path = os.path.join(NBA, "games_2025-26.json")
    schedule: List[dict] = []
    if os.path.exists(sched_path):
        schedule = json.load(open(sched_path, encoding="utf-8"))

    return Sources(
        season_reg=season_reg,
        season_playoffs=season_playoffs,
        scheme_lines=scheme_lines,
        roster=roster,
        positions_df=positions_df,
        coverage_df=coverage_df,
        stopper_top30=stopper_top30,
        stopper_exploited=stopper_exploited,
        stopper_pid_lookup=stopper_pid_lookup,
        scheme_matrix=scheme_matrix,
        name_map=name_map,
        schedule=schedule,
        intel_cache={},
    )


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_stopper_index(path: str) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    """Parse _Stopper_Index_2025-26.md into top-30 and most-exploited dicts.

    Returns (top30_dict, exploited_dict) keyed by defender name.
    top30 rows: {rank, ppp, fg_pct, fg3_pct, poss}
    exploited rows: {rank, ppp, fg_pct, poss}
    """
    top30: Dict[str, dict] = {}
    exploited: Dict[str, dict] = {}
    try:
        text = open(path, encoding="utf-8").read()
    except Exception:
        return top30, exploited

    # Top 30 section: | # | Defender | Poss | Pts/Poss | FG% allowed | 3P% allowed | ...
    in_top30 = False
    in_exploited = False
    for line in text.splitlines():
        stripped = line.strip()
        if "## Top 30 stoppers" in stripped:
            in_top30 = True
            in_exploited = False
            continue
        if "## Most-exploited" in stripped:
            in_exploited = True
            in_top30 = False
            continue
        if stripped.startswith("##") and (in_top30 or in_exploited):
            in_top30 = False
            in_exploited = False
            continue

        if in_top30:
            m = re.match(r"\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|", stripped)
            if m:
                rank = int(m.group(1))
                name = m.group(2).strip()
                poss = float(m.group(3))
                ppp = float(m.group(4))
                fg_pct = int(m.group(5))
                fg3_pct = int(m.group(6))
                top30[name] = {"rank": rank, "poss": poss, "ppp": ppp,
                               "fg_pct": fg_pct, "fg3_pct": fg3_pct}

        if in_exploited:
            m = re.match(r"\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*(\d+)\s*\|", stripped)
            if m:
                rank = int(m.group(1))
                name = m.group(2).strip()
                poss = float(m.group(3))
                ppp = float(m.group(4))
                fg_pct = int(m.group(5))
                exploited[name] = {"rank": rank, "poss": poss, "ppp": ppp, "fg_pct": fg_pct}

    return top30, exploited


def parse_scheme_matrix(path: str) -> Dict[str, Dict[str, float]]:
    """Parse _Scheme_Effects_Matrix.md into {slug: {PG,SG,SF,PF,C: float}}.

    Falls back to SCHEME_MATRIX_FALLBACK if file missing or parse fails.
    """
    result: Dict[str, Dict[str, float]] = {}
    if not os.path.exists(path):
        return dict(SCHEME_MATRIX_FALLBACK)
    try:
        text = open(path, encoding="utf-8").read()
        # Header row: | Scheme | PG | SG | SF | PF | C |
        header_found = False
        for line in text.splitlines():
            stripped = line.strip()
            if re.match(r"\|.*Scheme.*\|.*PG.*\|.*SG.*\|.*SF.*\|.*PF.*\|.*C.*\|", stripped):
                header_found = True
                continue
            if not header_found:
                continue
            if stripped.startswith("|---") or stripped.startswith("| ---"):
                continue
            # data row: | [[Schemes/xxx]] | val | val | val | val | val |
            m = re.match(
                r"\|\s*\[\[Schemes/(\w+)\]\]\s*\|\s*([+-]?[\d.]+)\s*\|\s*([+-]?[\d.]+)\s*\|\s*([+-]?[\d.]+)\s*\|\s*([+-]?[\d.]+)\s*\|\s*([+-]?[\d.]+)\s*\|",
                stripped)
            if m:
                sch = m.group(1)
                vals = [float(m.group(i)) for i in range(2, 7)]
                result[sch] = dict(zip(["PG", "SG", "SF", "PF", "C"], vals))
    except Exception:
        pass

    if not result:
        return dict(SCHEME_MATRIX_FALLBACK)
    return result


def parse_team_scheme(tri: str) -> TeamScheme:
    """Parse Teams/<TRI>.md: anchor '## Scheme Tag', then extract dominant tag.

    Canonical field is '- **Dominant tag:** X' (§14 — picks Dominant tag,
    not Scheme page which can diverge for historical notes like BOS).
    """
    path = os.path.join(VAULT, "Teams", f"{tri}.md")
    dominant = "UNKNOWN"
    all_tags: List[str] = []
    conf = "unknown"
    scheme_page_slug = ""

    if not os.path.exists(path):
        return TeamScheme(dominant=dominant, all_tags=all_tags, conf=conf,
                          scheme_page_slug=scheme_page_slug)

    text = open(path, encoding="utf-8").read()
    in_scheme_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "## Scheme Tag":
            in_scheme_section = True
            continue
        if in_scheme_section and stripped.startswith("##"):
            break

        if in_scheme_section:
            m_dom = re.match(r"-\s*\*\*Dominant tag:\*\*\s*(.+)", stripped)
            if m_dom:
                dominant = m_dom.group(1).strip()
                continue

            m_all = re.match(r"-\s*\*\*All tags:\*\*\s*(.+)", stripped)
            if m_all:
                all_tags = [t.strip() for t in m_all.group(1).split("|")]
                continue

            m_conf = re.match(r"-\s*\*\*Confidence:\*\*\s*(\w+)", stripped)
            if m_conf:
                conf = m_conf.group(1).strip().lower()
                continue

            # **Scheme page:** [[Schemes/<slug>|...]]  (may be without leading -)
            m_page = re.search(r"\[\[Schemes/(\w+)", stripped)
            if m_page and "Scheme page" in stripped:
                scheme_page_slug = m_page.group(1)
                continue

    # If no scheme_page_slug from note, derive from dominant tag
    if not scheme_page_slug and dominant != "UNKNOWN":
        scheme_page_slug = SCHEME_SLUG.get(dominant, slug(dominant))

    return TeamScheme(dominant=dominant, all_tags=all_tags, conf=conf,
                      scheme_page_slug=scheme_page_slug)


def parse_team_top_scorers(tri: str) -> List[Tuple[str, float, float]]:
    """Parse '<!-- TEAM-ID-2526-START -->' block for top scorers.

    Returns list of (name, pts, ast) from the '- **Top scorers:** ...' line.
    Pattern: 'Name 22.5p/7.9a · ...'
    """
    path = os.path.join(VAULT, "Teams", f"{tri}.md")
    if not os.path.exists(path):
        return []

    text = open(path, encoding="utf-8").read()
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if "<!-- TEAM-ID-2526-START -->" in stripped:
            in_block = True
            continue
        if "<!-- TEAM-ID-2526-END -->" in stripped:
            break
        if not in_block:
            continue
        if "Top scorers:" in stripped:
            # Extract everything after "Top scorers:"
            parts_str = stripped.split("Top scorers:")[-1].strip()
            entries = [e.strip() for e in parts_str.split("·")]
            result: List[Tuple[str, float, float]] = []
            for entry in entries:
                m = re.match(r"^(.*?)\s+([\d.]+)p/([\d.]+)a$", entry.strip())
                if m:
                    name = m.group(1).strip()
                    pts = float(m.group(2))
                    ast = float(m.group(3))
                    result.append((name, pts, ast))
            return result
    return []


# ---------------------------------------------------------------------------
# Position bucket heuristic (§10)
# ---------------------------------------------------------------------------

def position_bucket(coarse_pos: str, season_ast: float, season_fg3m: float) -> str:
    """Map player_profile_features.position to PG/SG/SF/PF/C.

    Heuristic (§10):
    - Guard → PG if ast>=4 else SG
    - Guard-Forward / Forward-Guard → SG
    - Forward → SF if ast>=2.5 or fg3m>=1.5 else PF
    - Forward-Center / Center-Forward → PF
    - Center → C
    - Unknown / None → ?
    """
    if not coarse_pos:
        return "?"
    p = str(coarse_pos).strip()
    if p == "Guard":
        return "PG" if season_ast >= 4.0 else "SG"
    if p in ("Guard-Forward", "Forward-Guard"):
        return "SG"
    if p == "Forward":
        return "SF" if (season_ast >= 2.5 or season_fg3m >= 1.5) else "PF"
    if p in ("Forward-Center", "Center-Forward"):
        return "PF"
    if p == "Center":
        return "C"
    return "?"


# ---------------------------------------------------------------------------
# Resolver helpers
# ---------------------------------------------------------------------------

def _get_season_line(pid: int, sources: Sources, is_playoff: bool = False) -> Optional[dict]:
    """Return season box line dict for a player (reg or playoffs)."""
    pid_str = str(pid)
    block = sources.season_playoffs if is_playoff else sources.season_reg
    return block.get(pid_str)


def _get_pos_bucket(pid: int, sources: Sources) -> Tuple[str, str]:
    """Return (coarse_position, bucket) for a player id."""
    pos_row = sources.positions_df[sources.positions_df["player_id"] == pid]
    if pos_row.empty:
        return "", "?"
    coarse = str(pos_row.iloc[0]["position"])
    # Get season line for AST/FG3M tiebreak
    line = _get_season_line(pid, sources)
    ast = float(line.get("ast", 0)) if line else 0.0
    fg3m = float(line.get("fg3m", 0)) if line else 0.0
    bucket = position_bucket(coarse, ast, fg3m)
    return coarse, bucket


def _player_note_exists(pid: int, name: str) -> bool:
    """Check if vault Players/<pid>_<slug>.md exists."""
    fn = f"{pid}_{slug(name)}.md"
    path = os.path.join(VAULT, "Players", fn)
    return os.path.exists(path)


def _player_link(pid: int, name: str) -> str:
    """Return wikilink or plain name. Verifies the file exists."""
    if _player_note_exists(pid, name):
        return f"[[Players/{pid}_{slug(name)}|{name}]]"
    return name


def resolve_scorer_ids(
    tri: str,
    scorer_names: List[Tuple[str, float, float]],
    sources: Sources,
    is_playoff: bool = False,
) -> List[ScorerInfo]:
    """Match scorer names to pids via season_2025_26 + roster.

    Falls back to name matching across season_reg for the team.
    """
    block = sources.season_playoffs if is_playoff else sources.season_reg
    team_players = {
        k: v for k, v in block.items()
        if v.get("team") == tri
    }

    result: List[ScorerInfo] = []
    for name, pts, ast in scorer_names:
        pid: Optional[int] = None
        matched_line: Optional[dict] = None

        name_lower = name.lower()
        for pid_str, line in team_players.items():
            if line.get("name", "").lower() == name_lower:
                pid = int(pid_str)
                matched_line = line
                break

        # Fuzzy fallback: check roster pids
        if pid is None:
            for roster_pid in sources.roster.get(tri, []):
                nm = sources.name_map.get(roster_pid, "")
                if nm.lower() == name_lower:
                    pid = roster_pid
                    matched_line = _get_season_line(pid, sources, is_playoff)
                    break

        if pid is None:
            # Keep scorer by name only, skip pid-dependent sections
            result.append(ScorerInfo(
                pid=-1, name=name, pos_bucket="?",
                pts=pts, ast=ast, reb=0.0, fg3m=0.0,
            ))
            continue

        line_data = matched_line or {}
        reb = float(line_data.get("reb", 0.0))
        fg3m_val = float(line_data.get("fg3m", 0.0))
        _, bucket = _get_pos_bucket(pid, sources)

        result.append(ScorerInfo(
            pid=pid, name=name, pos_bucket=bucket,
            pts=pts, ast=ast, reb=reb, fg3m=fg3m_val,
        ))

    return result


# ---------------------------------------------------------------------------
# Analytic: scheme line lookup (S2)
# ---------------------------------------------------------------------------

def player_vs_opp_scheme(
    pid: int, opp_scheme: str, sources: Sources
) -> dict:
    """Look up player's scheme line for opp_scheme from player_scheme_lines.json.

    Returns dict with by_scheme line, best, worst, ts_gap.
    Keys normalized to str(int(pid)).
    """
    pid_str = str(int(pid))
    entry = sources.scheme_lines.get(pid_str, {})
    if not entry:
        return {}

    best = entry.get("best", "")
    worst = entry.get("worst", "")
    ts_gap = float(entry.get("ts_gap", 0.0))
    by_scheme = entry.get("by_scheme", {})
    opp_line = by_scheme.get(opp_scheme, {})

    return {
        "best": best,
        "worst": worst,
        "ts_gap": ts_gap,
        "this_scheme": opp_scheme,
        "this_scheme_pts": opp_line.get("pts_pg"),
        "this_scheme_ts": opp_line.get("ts_pct"),
        "this_scheme_n": opp_line.get("n_games"),
        "this_scheme_ast": opp_line.get("ast_pg"),
        "this_scheme_tov": opp_line.get("tov_pg"),
    }


# ---------------------------------------------------------------------------
# Analytic: H2H from coverage parquet (S3)
# ---------------------------------------------------------------------------

def h2h_vs_opp_defenders(
    scorer_pid: int,
    opp_roster_ids: List[int],
    sources: Sources,
    min_poss: float = 18.0,
) -> List[H2HRow]:
    """Build H2H matchup rows for scorer vs opp defenders.

    Baseline PPP = sum(pts)/sum(poss) across ALL scorer's 2025-26 coverage rows.
    verdict: rel < 0.85 → tough; rel > 1.15 → feasts; else neutral.
    Returns sorted by poss desc then def_name.
    """
    cov = sources.coverage_df
    scorer_rows = cov[cov["off_player_id"] == scorer_pid]

    if scorer_rows.empty:
        return []

    # Compute baseline PPP from all season rows
    total_pts = scorer_rows["pts"].sum()
    total_poss = scorer_rows["poss"].sum()
    baseline_ppp = (total_pts / total_poss) if total_poss > 0 else 0.0

    # Filter to opp roster defenders with min_poss
    opp_set = set(opp_roster_ids)
    relevant = scorer_rows[
        scorer_rows["def_player_id"].isin(opp_set) &
        (scorer_rows["poss"] >= min_poss)
    ].copy()

    if relevant.empty:
        return []

    rows: List[H2HRow] = []
    for _, row in relevant.iterrows():
        def_pid = int(row["def_player_id"])
        def_name = str(row["def_player_name"])
        poss = float(row["poss"])
        pts_per_poss = float(row["pts_per_poss"])
        rel = round(pts_per_poss / baseline_ppp, 2) if baseline_ppp > 0 else 0.0

        if rel < 0.85:
            verdict = "tough"
        elif rel > 1.15:
            verdict = "feasts"
        else:
            verdict = "neutral"

        # Stopper index lookup
        stopper_row = sources.stopper_pid_lookup.get(def_pid)
        stopper_rank = stopper_row.get("rank") if stopper_row else None
        stopper_ppp = stopper_row.get("ppp") if stopper_row else None

        rows.append(H2HRow(
            def_pid=def_pid,
            def_name=def_name,
            poss=round(poss, 1),
            ppp=round(pts_per_poss, 2),
            rel=rel,
            verdict=verdict,
            stopper_rank=stopper_rank,
            stopper_ppp=stopper_ppp,
        ))

    rows.sort(key=lambda r: (-r.poss, r.def_name))
    return rows


# ---------------------------------------------------------------------------
# Analytic: stopper flags (S7)
# ---------------------------------------------------------------------------

def stopper_flags(
    opp_roster_ids: List[int], sources: Sources
) -> List[dict]:
    """Find which opp defenders appear in Stopper Index top-30 or most-exploited.

    Returns list sorted by stopper rank (ascending, exploited last).
    """
    flags = []
    # name_map reverse for roster lookups
    for def_pid in opp_roster_ids:
        row = sources.stopper_pid_lookup.get(def_pid)
        if row:
            def_name = sources.name_map.get(def_pid, f"pid:{def_pid}")
            is_exploited = def_name in sources.stopper_exploited
            is_top30 = def_name in sources.stopper_top30
            role = "top30" if is_top30 else ("exploited" if is_exploited else "")
            if role:
                flags.append({
                    "pid": def_pid,
                    "name": def_name,
                    "rank": row.get("rank", 99),
                    "ppp": row.get("ppp"),
                    "fg_pct": row.get("fg_pct"),
                    "fg3_pct": row.get("fg3_pct"),
                    "role": role,
                })
    flags.sort(key=lambda x: (0 if x["role"] == "top30" else 1, x["rank"]))
    return flags


# ---------------------------------------------------------------------------
# Analytic: Q4 notes (S9)
# ---------------------------------------------------------------------------

def q4_notes(scorer_pid: int, sources: Sources) -> dict:
    """Load quarter_shape from player_<pid>.json (S9)."""
    if scorer_pid not in sources.intel_cache:
        sources.intel_cache[scorer_pid] = _load_intel(scorer_pid)
    data = sources.intel_cache.get(scorer_pid, {})
    qs = data.get("quarter_shape", {})
    return {
        "q4_minus_q1": qs.get("q4_minus_q1"),
        "q4_fade_flag": qs.get("q4_fade_flag"),
    }


# ---------------------------------------------------------------------------
# Analytic: scheme effect per position
# ---------------------------------------------------------------------------

def _scheme_effect_read(delta: float) -> str:
    if delta <= -0.20:
        return "suppressed"
    if delta >= 0.20:
        return "advantaged"
    return "neutral"


# ---------------------------------------------------------------------------
# Build one side
# ---------------------------------------------------------------------------

def build_one_side(
    off_tri: str,
    def_tri: str,
    sources: Sources,
    top_n: int = 4,
    min_poss: float = 18.0,
    is_playoff: bool = False,
) -> SidePreview:
    # 1. Opponent scheme
    def_scheme_info = parse_team_scheme(def_tri)
    def_scheme_name = def_scheme_info.dominant  # e.g. "DROP COVERAGE"
    def_scheme_slug_key = SCHEME_SLUG.get(def_scheme_name, slug(def_scheme_name))

    # 2. Top scorers from vault note (then resolve to pids)
    scorer_tuples = parse_team_top_scorers(off_tri)[:top_n]
    scorers_info = resolve_scorer_ids(off_tri, scorer_tuples, sources, is_playoff)

    # Scheme matrix row for def scheme
    matrix_row = sources.scheme_matrix.get(def_scheme_slug_key, {})

    # Opp roster for H2H / stopper lookups
    opp_roster_ids = sources.roster.get(def_tri, [])

    # 3+4+5+6: build per-scorer preview
    scorer_previews: List[ScorerPreview] = []
    for scorer in scorers_info:
        bucket = scorer.pos_bucket
        delta = matrix_row.get(bucket) if bucket != "?" else None

        sch_info = player_vs_opp_scheme(scorer.pid, def_scheme_name, sources) if scorer.pid > 0 else {}
        h2h_rows = h2h_vs_opp_defenders(scorer.pid, opp_roster_ids, sources, min_poss) if scorer.pid > 0 else []
        q4 = q4_notes(scorer.pid, sources) if scorer.pid > 0 else {}

        scorer_previews.append(ScorerPreview(
            scorer=scorer,
            scheme_delta=round(delta, 2) if delta is not None else None,
            scheme_effect_read=_scheme_effect_read(delta) if delta is not None else "?",
            scheme_line_pts=sch_info.get("this_scheme_pts"),
            scheme_line_ts=sch_info.get("this_scheme_ts"),
            scheme_line_n=sch_info.get("this_scheme_n"),
            best_scheme=sch_info.get("best", ""),
            worst_scheme=sch_info.get("worst", ""),
            ts_gap=sch_info.get("ts_gap", 0.0),
            h2h=h2h_rows,
            q4_minus_q1=q4.get("q4_minus_q1"),
            q4_fade_flag=q4.get("q4_fade_flag"),
        ))

    # Sort by pts desc then pid for determinism
    scorer_previews.sort(key=lambda sp: (-sp.scorer.pts, sp.scorer.pid))

    # Stopper flags for opp defenders
    s_flags = stopper_flags(opp_roster_ids, sources)

    return SidePreview(
        off_tri=off_tri,
        def_tri=def_tri,
        def_scheme=def_scheme_info,
        scorers=scorer_previews,
        stopper_flags=s_flags,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _fmt_delta(d: Optional[float]) -> str:
    if d is None:
        return "—"
    return f"+{d:.2f}" if d >= 0 else f"{d:.2f}"


def _scheme_link(scheme_name: str) -> str:
    """Return [[Schemes/<slug>|SCHEME NAME]] or plain text if unknown."""
    sl = SCHEME_SLUG.get(scheme_name, slug(scheme_name))
    path = os.path.join(VAULT, "Schemes", f"{sl}.md")
    if os.path.exists(path):
        return f"[[Schemes/{sl}|{scheme_name}]]"
    return scheme_name


def render_note(
    away: str,
    home: str,
    game_date: str,
    side_away: SidePreview,
    side_home: SidePreview,
    sources: Sources,
    game_id: Optional[str] = None,
    as_of: Optional[str] = None,
    is_playoff: bool = False,
) -> str:
    generated = as_of or str(_date.today())
    lines: List[str] = []

    # Frontmatter
    lines.append("---")
    lines.append("type: matchup_preview")
    lines.append(f"date: {game_date}")
    lines.append(f"away: {away}")
    lines.append(f"home: {home}")
    if game_id:
        lines.append(f"game_id: {game_id}")
    lines.append(f"generated: {generated}")
    lines.append("generator: scripts/intel/daily_matchup_preview.py")
    lines.append("season: 2025-26")
    lines.append("---")
    lines.append("")

    # Title
    lines.append(f"# {away} @ {home} — Pregame Matchup Preview ({game_date})")
    lines.append("> Scouting synthesis from the intelligence layer. NOT a betting signal — see caveat at foot.")
    lines.append(f"Engine: [[_Matchup_Effect_Engine]] · Teams: [[Teams/{away}]] vs [[Teams/{home}]]")
    lines.append("")

    if is_playoff:
        lines.append("> ⚠️ **Playoff slate** — season-aggregate priors carry less weight in playoffs.")
        lines.append("> AST edge **breaks in playoffs** (per memory/feedback notes) — do not use for playoff prop betting.")
        lines.append("")

    # Scheme Identities section
    lines.append("## Scheme Identities")
    for tri, scheme_info in [(away, side_away.def_scheme if away == side_away.off_tri else side_home.def_scheme),
                              (home, side_home.def_scheme if home == side_home.off_tri else side_away.def_scheme)]:
        # Find the scheme for each team as DEFENSE
        # away team's scheme = side_home.def_scheme (home is defending away)
        # home team's scheme = side_away.def_scheme (away is attacking home)
        pass

    away_scheme = side_away.def_scheme   # PHX attacking OKC → OKC is the def scheme side of side_away... wait
    # Clarification: side_away = (off=away, def=home) → def_scheme is HOME's scheme
    # side_home = (off=home, def=away) → def_scheme is AWAY's scheme
    away_team_scheme = side_home.def_scheme  # AWAY's own defensive scheme (when defending)
    home_team_scheme = side_away.def_scheme  # HOME's own defensive scheme (when defending)

    lines.append(
        f"- **{away}:** {_scheme_link(away_team_scheme.dominant)} (conf {away_team_scheme.conf})"
        f" — see [[Teams/{away}]]"
    )
    lines.append(
        f"- **{home}:** {_scheme_link(home_team_scheme.dominant)} (conf {home_team_scheme.conf})"
        f" — see [[Teams/{home}]]"
    )
    lines.append("")

    # Render each attacking direction
    for side, attacker, defender in [(side_away, away, home), (side_home, home, away)]:
        def_scheme_name = side.def_scheme.dominant
        lines.extend(_render_side(side, attacker, defender, def_scheme_name, sources))
        lines.append("")

    # Caveat
    lines.append("---")
    lines.append("> **CAVEAT:** season-aggregate descriptive priors — scouting/game-planning only, NOT a validated")
    lines.append("> betting signal. Only durable pregame prop edge is gated AST ~+5% (reg-season only).")
    lines.append("> H2H single-pairings are small-sample tails (see [[Matchups/_Lockdown_And_Feast_2025-26]]).")
    lines.append("> Source README: [[_GAME_INTELLIGENCE_README]].")

    return "\n".join(lines) + "\n"


def _render_side(
    side: SidePreview,
    attacker: str,
    defender: str,
    def_scheme_name: str,
    sources: Sources,
) -> List[str]:
    lines: List[str] = []
    scheme_slug_key = SCHEME_SLUG.get(def_scheme_name, slug(def_scheme_name))
    scheme_link = _scheme_link(def_scheme_name)

    lines.append(f"## {attacker} attacking {defender} ({def_scheme_name})")

    # Scheme-effect table
    lines.append("")
    lines.append(f"### Scheme-effect read (position × scheme, from [[Schemes/_Scheme_Effects_Matrix]])")
    lines.append("")
    lines.append("| Scorer | Pos | Δ pts vs base | Read |")
    lines.append("|--------|-----|---------------|------|")

    for sp in side.scorers:
        s = sp.scorer
        link = _player_link(s.pid, s.name) if s.pid > 0 else s.name
        delta_str = _fmt_delta(sp.scheme_delta)
        lines.append(f"| {link} | {s.pos_bucket} | {delta_str} | {sp.scheme_effect_read} |")

    # Scorers vs opp scheme
    lines.append("")
    lines.append(f"### Scorers vs {defender}'s scheme (from player_scheme_lines)")
    lines.append("")
    for sp in side.scorers:
        s = sp.scorer
        link = _player_link(s.pid, s.name) if s.pid > 0 else s.name
        if sp.scheme_line_pts is not None:
            n_tag = f" n={sp.scheme_line_n}" if sp.scheme_line_n is not None else ""
            ts_tag = f" (.{int(round(sp.scheme_line_ts*1000)):03d} TS" if sp.scheme_line_ts is not None else ""
            ts_close = ")" if sp.scheme_line_ts is not None else ""
            pts_str = f"{sp.scheme_line_pts:.1f}p"
            note_parts = []
            if sp.best_scheme and sp.best_scheme == def_scheme_name:
                note_parts.append(f"this is his BEST scheme")
            elif sp.worst_scheme and sp.worst_scheme == def_scheme_name:
                note_parts.append(f"this is his WORST scheme")
            if sp.best_scheme:
                note_parts.append(f"best={sp.best_scheme}")
            if sp.worst_scheme:
                note_parts.append(f"worst={sp.worst_scheme}")
            if sp.ts_gap > 0:
                note_parts.append(f"ts_gap {sp.ts_gap:.3f}")
            note_str = f" — {', '.join(note_parts)}" if note_parts else ""
            lines.append(
                f"- {link}: vs {def_scheme_name} {pts_str}"
                f"{ts_tag}{n_tag}{ts_close}{note_str}"
            )
        else:
            lines.append(f"- {link}: no scheme-split data for {def_scheme_name}")

    # H2H table
    lines.append("")
    lines.append(
        f"### H2H — who guards them (2025-26, ≥{int(sources.coverage_df['poss'].min())} poss threshold; "
        f"<0.85 tough / >1.15 feasts; small-sample leads)"
    )
    lines.append("")

    has_any_h2h = any(sp.h2h for sp in side.scorers)
    if has_any_h2h:
        lines.append("| Scorer | Defender | Poss | PPP | vs self | Read | Stopper rank |")
        lines.append("|--------|----------|------|-----|---------|------|--------------|")
        for sp in side.scorers:
            s = sp.scorer
            scorer_link = _player_link(s.pid, s.name) if s.pid > 0 else s.name
            for h in sp.h2h:
                stopper_str = f"#{h.stopper_rank}" if h.stopper_rank is not None else "—"
                lines.append(
                    f"| {scorer_link} | {h.def_name} | {h.poss:.0f} | {h.ppp:.2f} | {h.rel:.2f} | {h.verdict} | {stopper_str} |"
                )
    else:
        lines.append("*No H2H coverage rows ≥ threshold for this matchup.*")

    # Tough / Feasts summary
    tough: List[str] = []
    feasts: List[str] = []
    for sp in side.scorers:
        s = sp.scorer
        for h in sp.h2h:
            if h.verdict == "tough":
                tough.append(f"{s.name} vs {h.def_name} ({h.rel:.2f}×)")
            elif h.verdict == "feasts":
                feasts.append(f"{s.name} vs {h.def_name} ({h.rel:.2f}×)")

    if tough:
        lines.append(f"- **Toughest covers:** {' · '.join(tough)}")
    if feasts:
        lines.append(f"- **Feasts vs:** {' · '.join(feasts)}")

    # Stopper-Index flags
    lines.append("")
    lines.append(f"### Stopper Index flags ([[Scouts/_Stopper_Index_2025-26]])")
    lines.append("")
    if side.stopper_flags:
        for sf in side.stopper_flags:
            ppp_str = f" ({sf['ppp']:.3f} pts/poss)" if sf.get("ppp") is not None else ""
            fg_str = f", FG% allowed {sf['fg_pct']}%" if sf.get("fg_pct") is not None else ""
            fg3_str = f", 3P% {sf['fg3_pct']}%" if sf.get("fg3_pct") is not None else ""
            role_str = f"top-30 stopper #{sf['rank']}" if sf["role"] == "top30" else f"most-exploited #{sf['rank']}"
            def_link = _player_link(sf["pid"], sf["name"])
            lines.append(f"- {def_link} — {role_str}{ppp_str}{fg_str}{fg3_str}")
    else:
        lines.append("*No top-30 stoppers or most-exploited defenders on this roster.*")

    # Q4 / closer notes
    lines.append("")
    lines.append("### Late-game / Q4")
    lines.append("")
    q4_lines: List[str] = []
    for sp in side.scorers:
        s = sp.scorer
        q4m1 = sp.q4_minus_q1
        fade = sp.q4_fade_flag
        if q4m1 is None:
            q4_lines.append(f"- {s.name}: no quarter data")
            continue
        if fade:
            q4_lines.append(
                f"- {s.name}: **Q4 fade** (Q4−Q1 {q4m1:+.2f}) — decline in closing scoring"
            )
        elif q4m1 is not None and q4m1 >= 0.5:
            q4_lines.append(
                f"- {s.name}: Q4 closer (Q4−Q1 {q4m1:+.2f}) — elevated late-game output"
            )
        else:
            q4_lines.append(
                f"- {s.name}: Q4−Q1 {q4m1:+.2f} (no fade)"
            )
    lines.extend(q4_lines)

    return lines


# ---------------------------------------------------------------------------
# Note writer
# ---------------------------------------------------------------------------

def write_note(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _preview_path(game_date: str, away: str, home: str, out_dir: str) -> str:
    return os.path.join(out_dir, f"{game_date}_{away}@{home}.md")


# ---------------------------------------------------------------------------
# Schedule / slate helpers
# ---------------------------------------------------------------------------

def _parse_schedule_game(
    game_date: str,
    sources: Sources,
    game_id: Optional[str] = None,
) -> List[Tuple[str, str, str]]:
    """Return list of (away, home, game_id) for a given date.

    Deduplicates by game_id, takes the '@'-row to parse AWAY @ HOME.
    """
    results: List[Tuple[str, str, str]] = []
    seen_ids: set = set()
    for g in sources.schedule:
        if g.get("GAME_DATE") != game_date:
            continue
        gid = g.get("GAME_ID", "")
        if game_id and gid != game_id:
            continue
        if gid in seen_ids:
            continue
        matchup = g.get("MATCHUP", "")
        if "@" not in matchup:
            continue
        m = re.match(r"^([A-Z]{2,4})\s*@\s*([A-Z]{2,4})", matchup.strip())
        if not m:
            continue
        seen_ids.add(gid)
        results.append((m.group(1), m.group(2), gid))
    return results


def _first_playoff_date(tri: str, sources: Sources) -> Optional[str]:
    """Heuristic: playoffs block in season data implies a playoff window."""
    block = sources.season_playoffs
    for pid_str, line in block.items():
        if line.get("team") == tri:
            last_game = line.get("last_game", "")
            if last_game:
                return last_game  # not a perfect heuristic but workable
    return None


def _is_playoff_date(tri: str, game_date: str, sources: Sources) -> bool:
    """Return True if game_date is after 2026-04-12 (first playoff date 2025-26)."""
    # NBA 2025-26 playoffs typically start mid-April
    PLAYOFF_START = "2026-04-12"
    return game_date >= PLAYOFF_START


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_preview(
    away: str,
    home: str,
    game_date: str,
    sources: Sources,
    out_dir: str = OUT,
    top_n: int = 4,
    min_poss: float = 18.0,
    game_id: Optional[str] = None,
    as_of: Optional[str] = None,
) -> str:
    """Generate one preview note and return the output path."""
    for tri in (away, home):
        if tri not in TEAM_TRIS:
            print(f"BLOCKED: unknown team {tri}", file=sys.stderr)
            sys.exit(1)
        if tri not in sources.roster:
            print(f"BLOCKED: {tri} not in _roster_2025_26.json", file=sys.stderr)
            sys.exit(1)

    is_playoff = _is_playoff_date(away, game_date, sources)

    side_away = build_one_side(away, home, sources, top_n, min_poss, is_playoff)
    side_home = build_one_side(home, away, sources, top_n, min_poss, is_playoff)

    note = render_note(
        away=away,
        home=home,
        game_date=game_date,
        side_away=side_away,
        side_home=side_home,
        sources=sources,
        game_id=game_id,
        as_of=as_of,
        is_playoff=is_playoff,
    )

    out_path = _preview_path(game_date, away, home, out_dir)
    write_note(out_path, note)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate pregame matchup preview notes.")
    parser.add_argument("--home", help="Home team tri (single-game mode)")
    parser.add_argument("--away", help="Away team tri (single-game mode)")
    parser.add_argument("--date", help="Game date YYYY-MM-DD (single-game mode)")
    parser.add_argument("--slate", help="Date or 'today' for all games on a date")
    parser.add_argument("--game-id", dest="game_id", help="NBA game_id")
    parser.add_argument("--out-dir", default=OUT, help=f"Output directory (default: {OUT})")
    parser.add_argument("--season", default="2025-26")
    parser.add_argument("--min-poss", type=float, default=18.0, dest="min_poss",
                        help="Min possessions gate for H2H (default 18)")
    parser.add_argument("--top-n-scorers", type=int, default=4, dest="top_n",
                        help="Top N scorers per team (default 4)")
    parser.add_argument("--as-of", dest="as_of", help="Override 'generated' date for reproducibility")
    args = parser.parse_args()

    today = str(_date.today())

    sources = load_sources(args.season)

    if args.slate:
        slate_date = today if args.slate == "today" else args.slate
        games = _parse_schedule_game(slate_date, sources)
        if not games:
            print(f"No games found for {slate_date}", file=sys.stderr)
            sys.exit(0)
        for away, home, gid in games:
            if away not in TEAM_TRIS or home not in TEAM_TRIS:
                print(f"Skipping unknown tri: {away} vs {home}", file=sys.stderr)
                continue
            if away not in sources.roster or home not in sources.roster:
                print(f"Skipping {away}@{home}: missing roster", file=sys.stderr)
                continue
            try:
                path = generate_preview(
                    away=away, home=home,
                    game_date=slate_date,
                    sources=sources,
                    out_dir=args.out_dir,
                    top_n=args.top_n,
                    min_poss=args.min_poss,
                    game_id=gid,
                    as_of=args.as_of,
                )
                print(path)
            except Exception as e:
                print(f"Error generating {away}@{home}: {e}", file=sys.stderr)

    elif args.game_id:
        # Find game in schedule
        found = False
        for g in sources.schedule:
            if g.get("GAME_ID") != args.game_id:
                continue
            matchup = g.get("MATCHUP", "")
            if "@" not in matchup:
                continue
            m = re.match(r"^([A-Z]{2,4})\s*@\s*([A-Z]{2,4})", matchup.strip())
            if not m:
                continue
            away, home = m.group(1), m.group(2)
            game_date = g.get("GAME_DATE", args.date or today)
            path = generate_preview(
                away=away, home=home,
                game_date=game_date,
                sources=sources,
                out_dir=args.out_dir,
                top_n=args.top_n,
                min_poss=args.min_poss,
                game_id=args.game_id,
                as_of=args.as_of,
            )
            print(path)
            found = True
            break
        if not found:
            print(f"BLOCKED: game_id {args.game_id} not found in schedule", file=sys.stderr)
            sys.exit(1)

    else:
        if not args.home or not args.away:
            parser.error("Provide --home + --away, --slate, or --game-id")
        game_date = args.date or today
        path = generate_preview(
            away=args.away, home=args.home,
            game_date=game_date,
            sources=sources,
            out_dir=args.out_dir,
            top_n=args.top_n,
            min_poss=args.min_poss,
            game_id=args.game_id,
            as_of=args.as_of,
        )
        print(path)


if __name__ == "__main__":
    main()
