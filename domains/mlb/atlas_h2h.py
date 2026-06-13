"""domains.mlb.atlas_h2h — Head-to-head matchup atlas generator for MLB.

Reads the real corpus (games.parquet) and emits Obsidian Markdown notes for
every team-vs-team matchup into ``vault/Sports/MLB/Matchups/``.

Public API::

    from pathlib import Path
    from domains.mlb.atlas_h2h import build_h2h
    paths = build_h2h(Path("vault/Sports/MLB/Matchups"))

All numbers are derived from the real data — no fabricated stats.
No betting/edge language: descriptive scouting intelligence only.

Import contract (F5-clean): stdlib + pathlib + pandas + domains.mlb.* +
scripts.platformkit.atlas.obsidian_emit only.
"""
from __future__ import annotations

import math
import pathlib
from typing import Any, Dict, List, Tuple

import pandas as pd

from domains.mlb.config import LEAGUE_MAP, resolve_league
from scripts.platformkit.atlas.obsidian_emit import frontmatter as _fm_dict, write_note

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_DEFAULT_CORPUS = _REPO_ROOT / "data" / "domains" / "mlb"
_DEFAULT_OUT = _REPO_ROOT / "vault" / "Sports" / "MLB" / "Matchups"


# ---------------------------------------------------------------------------
# Tiny format helpers
# ---------------------------------------------------------------------------

def _pct(v: float, d: int = 1) -> str:
    return "n/a" if (v is None or (isinstance(v, float) and math.isnan(v))) else f"{v*100:.{d}f}%"


def _ff(v: float, d: int = 2) -> str:
    return "n/a" if (v is None or (isinstance(v, float) and math.isnan(v))) else f"{v:.{d}f}"


def _wl(name: str) -> str:
    return f"[[{name}]]"


def _safe_league(team: str, season: int) -> str:
    try:
        return resolve_league(team, season)
    except KeyError:
        return LEAGUE_MAP.get(team, "UNK")


def _canon(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a < b else (b, a)


# ---------------------------------------------------------------------------
# Data loading + pair-level aggregation
# ---------------------------------------------------------------------------

def _load(corpus_dir: pathlib.Path) -> pd.DataFrame:
    p = corpus_dir / "games.parquet"
    if not p.exists():
        raise FileNotFoundError(f"games.parquet not found in {corpus_dir}")
    df = pd.read_parquet(p)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _build_pairs(games: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for _, g in games.iterrows():
        ht, at = str(g["home_team"]), str(g["away_team"])
        hw = int(g["target_home_win"])
        season = int(g["season"])
        hl = str(g["home_league"])
        al = _safe_league(at, season)
        ta, tb = _canon(ht, at)
        is_a_home = ta == ht
        rows.append(dict(
            team_a=ta, team_b=tb,
            a_won=hw if is_a_home else 1 - hw,
            a_is_home=1 if is_a_home else 0,
            a_runs=float(g["home_runs"] if is_a_home else g["away_runs"]),
            b_runs=float(g["away_runs"] if is_a_home else g["home_runs"]),
            season=season, date=g["date"],
            a_league=hl if is_a_home else al,
            b_league=al if is_a_home else hl,
        ))
    return pd.DataFrame(rows)


def _aggregate(pairs: pd.DataFrame) -> Dict[Tuple[str, str], Dict[str, Any]]:
    result: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for (ta, tb), g in pairs.groupby(["team_a", "team_b"]):
        n = len(g)
        aw = int(g["a_won"].sum())
        bw = n - aw
        ah = g[g["a_is_home"] == 1]
        bh = g[g["a_is_home"] == 0]
        result[(ta, tb)] = dict(
            total_games=n, a_wins=aw, b_wins=bw,
            a_win_pct=aw / n if n else float("nan"),
            b_win_pct=bw / n if n else float("nan"),
            a_rpg=float(g["a_runs"].mean()),
            b_rpg=float(g["b_runs"].mean()),
            a_home_games=len(ah),
            a_home_wins=int(ah["a_won"].sum()) if not ah.empty else 0,
            b_home_games=len(bh),
            b_home_wins=int((1 - bh["a_won"]).sum()) if not bh.empty else 0,
            a_league=str(g["a_league"].mode().iloc[0]) if n else "UNK",
            b_league=str(g["b_league"].mode().iloc[0]) if n else "UNK",
        )
    return result


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_matchup(
    ta: str, tb: str, s: Dict[str, Any],
    season_rows: List[Tuple[int, int, int, int]],
    recent: List[Dict[str, Any]],
) -> str:
    al, bl = s["a_league"], s["b_league"]
    scope = f"Intra-league ({al})" if al == bl else f"Interleague ({al} vs {bl})"
    tags = ["sport/mlb", "matchup"] + [f"league/{x.lower()}" for x in sorted({al, bl} - {"UNK"})]
    ahg, ahw = s["a_home_games"], s["a_home_wins"]
    bhg, bhw = s["b_home_games"], s["b_home_wins"]
    sparse = "\n> *Sparse split (fewer than 5 games — treat with caution).*\n" if (ahg < 5 or bhg < 5) else ""

    lines = [
        _fm_dict({"team_a": ta, "team_b": tb, "league_a": al, "league_b": bl,
                  "scope": scope, "total_games": s["total_games"], "tags": tags}),
        "", f"# {ta} vs {tb}", "",
        f"{_wl(f'Teams/{ta}')} | {_wl(f'Teams/{tb}')} | {_wl('Matchups/_Matchups_Index')}",
        "", f"**Scope:** {scope}", "",
        "## Head-to-Head Summary", "",
        "| Metric | Value |", "|--------|-------|",
        f"| Total games | {s['total_games']} |",
        f"| {ta} wins | {s['a_wins']} ({_pct(s['a_win_pct'])}) |",
        f"| {tb} wins | {s['b_wins']} ({_pct(s['b_win_pct'])}) |",
        f"| {ta} runs/game (H2H) | {_ff(s['a_rpg'])} |",
        f"| {tb} runs/game (H2H) | {_ff(s['b_rpg'])} |",
        "", "## Home/Away Split in This Matchup", sparse,
        "| Side | Home Games | Home Wins | Home Win % |",
        "|------|------------|-----------|------------|",
        f"| {ta} | {ahg} | {ahw} | {_pct(ahw/ahg if ahg else float('nan'))} |",
        f"| {tb} | {bhg} | {bhw} | {_pct(bhw/bhg if bhg else float('nan'))} |",
    ]

    if season_rows:
        lines += ["", "## By-Season Record", "",
                  f"| Season | Games | {ta} W | {tb} W |",
                  "|--------|-------|" + "-"*(len(ta)+3) + "|" + "-"*(len(tb)+3) + "|"]
        for yr, ag, aw, bw in sorted(season_rows):
            lines.append(f"| {yr} | {ag} | {aw} | {bw} |")

    if recent:
        lines += ["", "## Recent Games (latest 10)", "",
                  "| Date | Home | Away | Score |",
                  "|------|------|------|-------|"]
        for r in recent[:10]:
            lines.append(
                f"| {str(r['date'])[:10]} | {r['home_team']} | {r['away_team']}"
                f" | {r['home_runs']}-{r['away_runs']} |"
            )

    lines += ["", "#sport/mlb #matchup"]
    return "\n".join(lines) + "\n"


def _render_index(pairs: pd.DataFrame, stats: Dict[Tuple[str, str], Dict[str, Any]], top_n: int) -> str:
    header = [
        _fm_dict({"sport": "mlb", "note_type": "matchup_index", "top_n": top_n, "tags": ["sport/mlb", "matchup"]}),
        "", "# MLB Head-to-Head Matchup Index", "", f"up:: {_wl('_Index')}", "",
        f"Top {min(top_n, len(stats))} matchups by total games (real corpus 2010-2021, {len(pairs):,} total games).",
        "", "| Matchup | Team A | Team B | Games | A-W — B-W | A Win % |",
        "|---------|--------|--------|-------|-----------|---------|",
    ]
    rows = []
    for (ta, tb), s in list(stats.items())[:top_n]:
        rows.append(
            f"| {_wl(f'Matchups/{ta} vs {tb}')} | {_wl(f'Teams/{ta}')} | {_wl(f'Teams/{tb}')}"
            f" | {s['total_games']} | {s['a_wins']}-{s['b_wins']} | {_pct(s['a_win_pct'])} |"
        )
    return "\n".join(header + rows + ["", "#sport/mlb #matchup"]) + "\n"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_h2h(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = _DEFAULT_CORPUS,
    top_n: int = 150,
) -> List[pathlib.Path]:
    """Generate head-to-head Obsidian notes from the real MLB corpus.

    Parameters
    ----------
    out_dir:       Directory to write Matchup notes into.  Created if absent.
    corpus_dir:    Directory containing ``games.parquet``.
    top_n:         Max matchups in the index table (all pairs get individual notes).

    Returns
    -------
    list[pathlib.Path]  Absolute paths of every file written (idempotent).
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    games = _load(corpus_dir)
    pairs = _build_pairs(games)

    stats = _aggregate(pairs)
    sorted_stats = sorted(stats.items(), key=lambda kv: kv[1]["total_games"], reverse=True)

    # Per-pair season rows
    season_by_pair: Dict[Tuple[str, str], List[Tuple[int, int, int, int]]] = {}
    for (ta, tb), g in pairs.groupby(["team_a", "team_b"]):
        srows = []
        for season, sg in g.groupby("season"):
            ag = len(sg); aw = int(sg["a_won"].sum())
            srows.append((int(season), ag, aw, ag - aw))
        season_by_pair[(ta, tb)] = srows

    # Per-pair recent games (up to 10, most recent first)
    recent_by_pair: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for _, g in games.sort_values("date", ascending=False).iterrows():
        ht, at = str(g["home_team"]), str(g["away_team"])
        key = _canon(ht, at)
        bucket = recent_by_pair.setdefault(key, [])
        if len(bucket) < 10:
            bucket.append(dict(
                date=g["date"], home_team=ht, away_team=at,
                home_runs=int(g["home_runs"]), away_runs=int(g["away_runs"]),
            ))

    written: List[pathlib.Path] = []
    for (ta, tb), s in sorted_stats:
        path = out_dir / f"{ta} vs {tb}.md"
        write_note(path, _render_matchup(
            ta, tb, s,
            season_by_pair.get((ta, tb), []),
            recent_by_pair.get((ta, tb), []),
        ))
        written.append(path)

    index_path = out_dir / "_Matchups_Index.md"
    write_note(index_path, _render_index(pairs, dict(sorted_stats), top_n))
    written.append(index_path)
    return written
