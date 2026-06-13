"""domains.mlb.atlas_playstyles — MLB team playstyle-archetype atlas generator.

Reads games.parquet and clusters each franchise (≥100 corpus games) into
run-scoring / run-prevention identity archetypes.  Emits Obsidian Markdown
into vault/Sports/MLB/Playstyles/.

Public API: build_playstyles(out_dir, corpus_dir) -> list[Path]

6 archetypes: Power/Run-Scoring · Pitching-Led/Run-Prevention · Balanced
Contender · High-Variance Offense · Low-Scoring Grinder · Run-Deficit.
Teams may appear in multiple archetypes.  Real data only; no betting language.

Import contract (F5-clean): stdlib + pathlib + pandas + domains.mlb.* +
scripts.platformkit.atlas.obsidian_emit only.
"""
from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Tuple

import pandas as pd

from domains.mlb.atlas_playstyles_render import (
    render_archetype,
    render_playstyles_index,
    render_unclassified_stub,
)
from scripts.platformkit.atlas.obsidian_emit import write_note

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_DEFAULT_CORPUS = _REPO_ROOT / "data" / "domains" / "mlb"
_DEFAULT_OUT = _REPO_ROOT / "vault" / "Sports" / "MLB" / "Playstyles"

_MIN_GAMES = 100  # exclude franchises with too few corpus games

# ---------------------------------------------------------------------------
# Archetype definitions
# ---------------------------------------------------------------------------
# Each archetype: (slug, name, description, signature_dict, classifier_fn)
# The classifier receives a row dict of per-team stats and returns True/False.

_ARCHETYPES: List[Tuple[str, str, str, Dict[str, str], Any]] = [
    (
        "power_run_scoring",
        "Power / Run-Scoring",
        "Offense-first franchises that consistently produce high run totals and positive run differentials. High-scoring games are a recurring identity signature.",
        {"Runs Scored / G": "≥ 4.65", "Run Differential / G": "> 0", "High-Score Game Rate (6+ RS)": "≥ 33%"},
        lambda r: r["rs"] >= 4.65 and r["rd"] > 0 and r["high_score_rate"] >= 0.33,
    ),
    (
        "pitching_run_prevention",
        "Pitching-Led / Run-Prevention",
        "Franchises that limit opponent run production as their primary identity. Positive run differentials are driven by pitching and defense, not offensive firepower.",
        {"Runs Allowed / G": "≤ 4.10", "Run Differential / G": "> 0"},
        lambda r: r["ra"] <= 4.10 and r["rd"] > 0,
    ),
    (
        "balanced_contender",
        "Balanced Contender",
        "Franchises with above-average runs scored and below-median runs allowed, sustaining a positive run differential through competence on both sides of the game.",
        {"Runs Scored / G": "≥ 4.35", "Runs Allowed / G": "≤ 4.35", "Run Differential / G": "≥ +0.20", "Win %": "≥ 51%"},
        lambda r: r["rs"] >= 4.35 and r["ra"] <= 4.35 and r["rd"] >= 0.20 and r["wp"] >= 0.51,
    ),
    (
        "high_variance_offense",
        "High-Variance Offense",
        "Above-average scorers with wide game-to-game run variability. Their identity swings between high-scoring bursts and offensive quiet games — large RS standard deviation is the hallmark.",
        {"Runs Scored / G": "≥ 4.40", "RS Standard Deviation": "≥ 3.30"},
        lambda r: r["rs"] >= 4.40 and r["rs_std"] >= 3.30,
    ),
    (
        "low_scoring_grinder",
        "Low-Scoring Grinder",
        "Franchises that produce and allow few runs per game. Both sides of the game are suppressed; games tend to be tightly contested with one-run decisions common.",
        {"Runs Scored / G": "≤ 4.10", "Runs Allowed / G": "≤ 4.40", "One-Run Game Rate": "≥ 29%"},
        lambda r: r["rs"] <= 4.10 and r["ra"] <= 4.40 and r["one_run_rate"] >= 0.29,
    ),
    (
        "run_deficit_rebuilding",
        "Run-Deficit / Rebuilding",
        "Franchises with persistently negative run differentials across the corpus. Allowing more runs than scoring is the primary driver of below-.500 records.",
        {"Run Differential / G": "≤ −0.35", "Win %": "< 48%"},
        lambda r: r["rd"] <= -0.35 and r["wp"] < 0.48,
    ),
]


# ---------------------------------------------------------------------------
# Data loading + stats
# ---------------------------------------------------------------------------


def _load_games(corpus_dir: pathlib.Path) -> pd.DataFrame:
    """Load games.parquet; raise FileNotFoundError if absent."""
    p = corpus_dir / "games.parquet"
    if not p.exists():
        raise FileNotFoundError(f"games.parquet not found in {corpus_dir}")
    return pd.read_parquet(p)


def _compute_team_stats(games: pd.DataFrame) -> pd.DataFrame:
    """Derive per-franchise playstyle statistics from the full corpus.

    Returns a DataFrame indexed by team code with columns:
      n, rs, ra, rd, wp, rs_std, ra_std,
      high_score_rate, low_score_rate, one_run_rate,
      hwp, awp, home_adv
    """
    rows: List[Dict[str, Any]] = []
    for _, g in games.iterrows():
        ht = str(g["home_team"])
        at = str(g["away_team"])
        hr = float(g["home_runs"])
        ar = float(g["away_runs"])
        hw = int(g["target_home_win"])
        rows.append({"team": ht, "rs": hr, "ra": ar, "win": hw, "is_home": 1})
        rows.append({"team": at, "rs": ar, "ra": hr, "win": 1 - hw, "is_home": 0})

    dft = pd.DataFrame(rows)

    # Base aggregates
    agg = dft.groupby("team").agg(
        n=("win", "count"),
        wins=("win", "sum"),
        rs=("rs", "mean"),
        ra=("ra", "mean"),
        rs_std=("rs", "std"),
        ra_std=("ra", "std"),
    ).copy()
    agg["rd"] = agg["rs"] - agg["ra"]
    agg["wp"] = agg["wins"] / agg["n"]

    # Rate columns — computed per-row then averaged
    dft["is_high"] = (dft["rs"] >= 6).astype(int)
    dft["is_low"] = (dft["rs"] <= 2).astype(int)
    dft["is_one_run"] = ((dft["rs"] - dft["ra"]).abs() == 1).astype(int)

    rates = dft.groupby("team").agg(
        high_score_rate=("is_high", "mean"),
        low_score_rate=("is_low", "mean"),
        one_run_rate=("is_one_run", "mean"),
    )
    agg = agg.join(rates)

    # Home/away win%
    home_df = dft[dft["is_home"] == 1].groupby("team")["win"].mean().rename("hwp")
    away_df = dft[dft["is_home"] == 0].groupby("team")["win"].mean().rename("awp")
    agg = agg.join(home_df).join(away_df)
    agg["home_adv"] = agg["hwp"] - agg["awp"]

    # Filter sparse franchises
    agg = agg[agg["n"] >= _MIN_GAMES].copy()
    return agg


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _classify(stats: pd.DataFrame) -> Dict[str, List[str]]:
    """Return {archetype_slug: [team, ...]} mapping.

    A team may appear in multiple archetypes if it satisfies multiple
    classifier predicates.
    """
    assignment: Dict[str, List[str]] = {slug: [] for slug, *_ in _ARCHETYPES}
    for team in stats.index:
        row = stats.loc[team].to_dict()
        for slug, _name, _desc, _sig, classifier in _ARCHETYPES:
            if classifier(row):
                assignment[slug].append(team)
    return assignment


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_playstyles(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = _DEFAULT_CORPUS,
) -> List[pathlib.Path]:
    """Generate Obsidian playstyle-archetype notes from the real MLB corpus.

    Parameters
    ----------
    out_dir:
        Directory to write notes into.  Created if absent.
    corpus_dir:
        Directory containing ``games.parquet``.

    Returns
    -------
    list[pathlib.Path]
        Absolute paths of every file written (idempotent).
    """
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    games = _load_games(corpus_dir)
    stats = _compute_team_stats(games)
    assignment = _classify(stats)

    seasons = sorted(int(s) for s in games["season"].unique())
    corpus_span = f"{min(seasons)}–{max(seasons)}" if seasons else "n/a"

    written: List[pathlib.Path] = []

    # --- Per-archetype notes ---
    archetypes_meta: List[Dict[str, Any]] = []
    for slug, name, description, signature, _classifier in _ARCHETYPES:
        teams = sorted(assignment.get(slug, []))
        team_rows = [
            {
                "team": t,
                "rs": float(stats.loc[t, "rs"]),
                "ra": float(stats.loc[t, "ra"]),
                "rd": float(stats.loc[t, "rd"]),
                "wp": float(stats.loc[t, "wp"]),
                "one_run_rate": float(stats.loc[t, "one_run_rate"]),
            }
            for t in teams
            if t in stats.index
        ]
        content = render_archetype(
            archetype_slug=slug,
            archetype_name=name,
            description=description,
            signature=signature,
            teams=teams,
            team_rows=team_rows,
            corpus_span=corpus_span,
        )
        note_path = out_dir / f"{slug}.md"
        write_note(note_path, content)
        written.append(note_path)

        archetypes_meta.append(
            {
                "slug": slug,
                "name": name,
                "team_count": len(teams),
                "description_short": name + " identity",
            }
        )

    # --- unclassified stub (target for [[Playstyles/unclassified]] links) ---
    unclassified_path = out_dir / "unclassified.md"
    write_note(unclassified_path, render_unclassified_stub(corpus_span=corpus_span))
    written.append(unclassified_path)

    # --- _Playstyles_Index ---
    all_classified = sorted(
        set(t for teams in assignment.values() for t in teams)
    )
    index_content = render_playstyles_index(
        archetypes=archetypes_meta,
        corpus_span=corpus_span,
        n_teams_classified=len(all_classified),
    )
    index_path = out_dir / "_Playstyles_Index.md"
    write_note(index_path, index_content)
    written.append(index_path)

    return written
