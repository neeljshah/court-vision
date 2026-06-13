"""domains.soccer.atlas_h2h — Obsidian head-to-head (fixture/rivalry) note generator.

Reads matches.parquet and emits into *out_dir* (default vault/Sports/Soccer/Matchups/):
  _Matchups_Index.md        — top-N fixtures by meetings with [[wikilinks]]
  <Team A> vs <Team B>.md   — one per recurring fixture with real H2H stats

Canonical ordering: lexicographic sort of both team names — same _slug as
domains.soccer.atlas so [[Teams/...]] wikilinks resolve into the existing graph.

F5 compliance: stdlib + pandas + domains.soccer.* only. No fabricated stats,
no edge/betting language.
"""
from __future__ import annotations

import datetime
import pathlib
from collections import Counter
from typing import Dict, List, Tuple

import pandas as pd

from domains.soccer.config import LEAGUES
from scripts.platformkit.atlas.obsidian_emit import slug as _slug, write_note

_DEFAULT_CORPUS: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "domains" / "soccer"
)
_MIN_H2H_MEETINGS: int = 4
_RECENT_N: int = 8


# --- helpers -----------------------------------------------------------------

def _team_link(team: str) -> str:
    return f"[[Teams/{_slug(team)}|{team}]]"


def _pct(num: int, den: int) -> str:
    return f"{num / den * 100:.1f}%" if den else "N/A"


def _fpg(total: float, n: int) -> str:
    return f"{total / n:.2f}" if n else "N/A"


def _load_matches(corpus_dir: pathlib.Path) -> pd.DataFrame:
    path = corpus_dir / "matches.parquet"
    if not path.exists():
        raise FileNotFoundError(f"matches.parquet not found at {path}")
    df = pd.read_parquet(path)
    required = {"date", "season", "div", "home_team", "away_team",
                "fthg", "ftag", "total_goals", "target_over25", "ftr"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"matches.parquet missing columns: {missing}")
    df["date"] = pd.to_datetime(df["date"])
    return df


# --- H2H computation ---------------------------------------------------------

def _canonical_pair(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def _build_pair_index(df: pd.DataFrame, top_n: int) -> List[Tuple[Tuple[str, str], int]]:
    """Return top_n (pair, count) tuples filtered to >= _MIN_H2H_MEETINGS."""
    counts: Counter = Counter()
    for idx in range(len(df)):
        row = df.iloc[idx]
        counts[_canonical_pair(row["home_team"], row["away_team"])] += 1
    return [(p, c) for p, c in counts.most_common(top_n) if c >= _MIN_H2H_MEETINGS]


def _h2h_stats(df: pd.DataFrame, team_a: str, team_b: str) -> Dict:
    mask = (
        ((df["home_team"] == team_a) & (df["away_team"] == team_b)) |
        ((df["home_team"] == team_b) & (df["away_team"] == team_a))
    )
    sub = df[mask].copy().sort_values("date")
    n = len(sub)
    if n == 0:
        return {}

    a_wins = int(
        ((sub["home_team"] == team_a) & (sub["ftr"] == "H")).sum() +
        ((sub["away_team"] == team_a) & (sub["ftr"] == "A")).sum()
    )
    draws = int((sub["ftr"] == "D").sum())
    b_wins = n - a_wins - draws

    def _gf(row: pd.Series, team: str) -> int:
        return int(row["fthg"]) if row["home_team"] == team else int(row["ftag"])

    goals_a = int(sub.apply(lambda r: _gf(r, team_a), axis=1).sum())
    goals_b = int(sub.apply(lambda r: _gf(r, team_b), axis=1).sum())
    over25 = int(sub["target_over25"].sum())

    a_home = sub[sub["home_team"] == team_a]
    a_away = sub[sub["away_team"] == team_a]
    a_home_w = int((a_home["ftr"] == "H").sum())
    a_away_w = int((a_away["ftr"] == "A").sum())

    div_ctr = Counter(sub["div"].tolist())
    primary_div = div_ctr.most_common(1)[0][0] if div_ctr else ""
    seasons = sorted(sub["season"].unique().tolist())

    recent = []
    for _, rr in sub.tail(_RECENT_N).iterrows():
        recent.append({
            "date": str(rr["date"])[:10],
            "home": rr["home_team"], "away": rr["away_team"],
            "score": f"{int(rr['fthg'])}-{int(rr['ftag'])}",
        })

    return {
        "team_a": team_a, "team_b": team_b, "n": n,
        "a_wins": a_wins, "draws": draws, "b_wins": b_wins,
        "goals_a": goals_a, "goals_b": goals_b, "over25": over25,
        "a_home_n": len(a_home), "a_home_w": a_home_w,
        "a_away_n": len(a_away), "a_away_w": a_away_w,
        "div_ctr": div_ctr, "primary_div": primary_div,
        "seasons": seasons, "recent": recent,
    }


# --- renderers ---------------------------------------------------------------

def _render_fixture(st: Dict) -> str:
    a, b, n = st["team_a"], st["team_b"], st["n"]
    league = LEAGUES.get(st["primary_div"], st["primary_div"])
    seasons = st["seasons"]
    sr = f"{min(seasons)}–{max(seasons)}" if seasons else "N/A"
    today = datetime.date.today().isoformat()

    L: List[str] = [
        "---", f'teams: ["{a}", "{b}"]', f'league: "{league}"',
        f'div_code: "{st["primary_div"]}"', f"total_meetings: {n}",
        f"seasons_covered: {sr}", f"generated: {today}",
        "tags:", "  - sport/soccer", "  - matchup/fixture", "---", "",
        f"# {a} vs {b}", "", "Up: [[_Matchups_Index|Matchup Index]]", "",
        f"Teams: {_team_link(a)} · {_team_link(b)}", "",
        "## Head-to-Head Record", "",
        "| Metric | Value |", "|--------|-------|",
        f"| Total Meetings | {n} |",
        f"| {a} W / D / {b} W | {st['a_wins']} / {st['draws']} / {st['b_wins']} |",
        f"| {a} Goals | {st['goals_a']} ({_fpg(st['goals_a'], n)}/game) |",
        f"| {b} Goals | {st['goals_b']} ({_fpg(st['goals_b'], n)}/game) |",
        f"| Over-2.5 Matches | {st['over25']}/{n} ({_pct(st['over25'], n)}) |", "",
        "## Venue Split (within this fixture)", "",
        "*How each side performs as host in this specific matchup.*", "",
        "| Venue | Matches | Host Wins |", "|-------|---------|-----------|",
        f"| {a} at home | {st['a_home_n']} | {st['a_home_w']} ({_pct(st['a_home_w'], st['a_home_n'])}) |",
        f"| {b} at home | {st['a_away_n']} | {st['a_away_w']} ({_pct(st['a_away_w'], st['a_away_n'])}) |",
        "",
    ]

    if len(st["div_ctr"]) > 1:
        L += ["## Competitions", ""]
        for div, cnt in st["div_ctr"].most_common():
            L.append(f"- {LEAGUES.get(div, div)} (`{div}`): {cnt} meetings")
        L.append("")

    if st["recent"]:
        L += [f"## Recent Meetings (last {len(st['recent'])})", "",
              "| Date | Home | Score | Away |", "|------|------|-------|------|"]
        for rm in reversed(st["recent"]):
            L.append(f"| {rm['date']} | {rm['home']} | {rm['score']} | {rm['away']} |")
        L.append("")

    L.append("#sport/soccer #matchup/fixture")
    return "\n".join(L) + "\n"


def _render_index(fixture_stats: List[Dict], n_corpus: int) -> str:
    today = datetime.date.today().isoformat()
    n = len(fixture_stats)
    L: List[str] = [
        "---", "type: matchups-index", "sport: soccer",
        f"fixtures_listed: {n}", f"corpus_matches: {n_corpus}",
        f"generated: {today}", "tags:", "  - sport/soccer", "  - matchup", "---", "",
        "# Soccer Matchups Index", "",
        "Up: [[_Index|Soccer Index]]", "",
        f"Top {n} recurring fixtures by total corpus meetings.", "",
        "| # | Fixture | League | Meetings | A W / D / B W | Over-2.5% |",
        "|---|---------|--------|----------|---------------|-----------|",
    ]
    for i, st in enumerate(fixture_stats, 1):
        a, b = st["team_a"], st["team_b"]
        link = f"[[{a} vs {b}|{a} vs {b}]]"
        league = LEAGUES.get(st["primary_div"], st["primary_div"])
        L.append(
            f"| {i} | {link} | {league} | {st['n']} "
            f"| {st['a_wins']} / {st['draws']} / {st['b_wins']} "
            f"| {_pct(st['over25'], st['n'])} |"
        )
    L += ["", "## Team Links", "",
          "Each fixture note links back to both team notes in the Teams/ folder.", "",
          "#sport/soccer #matchup"]
    return "\n".join(L) + "\n"


# --- public API --------------------------------------------------------------

def build_h2h(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = _DEFAULT_CORPUS,
    top_n: int = 150,
) -> List[pathlib.Path]:
    """Generate Obsidian H2H matchup notes into *out_dir*. Idempotent.

    Parameters
    ----------
    out_dir:     Destination directory; created if absent.
    corpus_dir:  Contains matches.parquet. Defaults to data/domains/soccer/.
    top_n:       Maximum number of fixture notes (by total meetings).

    Returns
    -------
    list[pathlib.Path]  Paths of every written note.
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = _load_matches(corpus_dir)
    pair_list = _build_pair_index(df, top_n)

    fixture_stats: List[Dict] = []
    for pair, _ in pair_list:
        st = _h2h_stats(df, pair[0], pair[1])
        if st:
            fixture_stats.append(st)

    written: List[pathlib.Path] = []

    idx_path = out_dir / "_Matchups_Index.md"
    written.append(write_note(idx_path, _render_index(fixture_stats, len(df))))

    for st in fixture_stats:
        p = out_dir / f"{st['team_a']} vs {st['team_b']}.md"
        written.append(write_note(p, _render_fixture(st)))

    return written
