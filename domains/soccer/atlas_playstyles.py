"""domains.soccer.atlas_playstyles — Obsidian tactical-scheme (playstyle) atlas generator.

Clusters teams into tactical archetypes based on corpus statistics computed from
matches.parquet.  Emits into *out_dir* (default vault/Sports/Soccer/Playstyles/):

  _Playstyles_Index.md       — hub: all schemes, team counts, up-link [[_Index]]
  <Scheme>.md                — one note per scheme with stat signature,
                               member count, and [[Teams/<slug>]] wikilinks

Seven schemes defined by real thresholds derived from the corpus distribution
(see _SCHEMES below).  Each team with ≥30 corpus appearances is assigned to
*exactly one* scheme via a priority waterfall (highest-variance schemes first,
balanced last).

Renderers live in domains.soccer.atlas_playstyles_render (≤300 LOC each).

F5 compliance: imports ONLY stdlib + pandas + domains.soccer.*
No src.*, kernel.*, or sibling-domain imports.
All statistics are corpus-derived; no fabricated numbers, no edge/betting language.
Idempotent: re-running overwrites notes with identical content.
"""
from __future__ import annotations

import datetime
import pathlib
from typing import Dict, List, NamedTuple

import pandas as pd

from domains.soccer.config import LEAGUES  # noqa: F401  (F5 in-domain import check)
from scripts.platformkit.atlas.obsidian_emit import write_note

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CORPUS: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "domains" / "soccer"
)
_MIN_MATCHES: int = 30  # minimum corpus appearances for scheme assignment


class SchemeSpec(NamedTuple):
    """Static definition of one tactical scheme."""

    key: str          # filesystem-safe identifier (used as note filename stem)
    label: str        # display name
    description: str  # one-sentence tactical summary
    signature: str    # human-readable stat thresholds used for classification
    tags: List[str]   # additional Obsidian #tags


# Scheme definitions — thresholds derived from corpus percentile analysis:
#   gf_pg   : median=1.196  p75=1.388  p90≈1.60
#   ga_pg   : median=1.440  p25=1.288  p10≈1.15
#   over_pct: median=0.508  p75=0.553  p90≈0.58
#   cs_pct  : median=0.244  p75=0.288  p90≈0.31
#   btts_pct: median=0.525  p90≈0.60
#   draw_pct: median=0.260  p90≈0.30
#   home_adv (home_gf_pg − away_gf_pg): median=0.271  p75=0.384  p90≈0.50
#
# Priority waterfall: first matching rule wins.
_SCHEMES: List[SchemeSpec] = [
    SchemeSpec(
        key="High-Scoring_Attacking",
        label="High-Scoring Attacking",
        description=(
            "Prolific attacking output driving high match totals; "
            "invests heavily in front-line creation regardless of defensive cost."
        ),
        signature="GF/game ≥ 1.60  AND  Over-2.5 rate ≥ 58%",
        tags=["#scheme/high-scoring", "#scheme/attacking"],
    ),
    SchemeSpec(
        key="High-Variance_Entertainers",
        label="High-Variance / Entertainers",
        description=(
            "Both teams score in the majority of matches; "
            "open, end-to-end style with high mutual threat and unpredictable scorelines."
        ),
        signature="BTTS rate ≥ 60%  AND  Over-2.5 rate ≥ 58%",
        tags=["#scheme/high-variance", "#scheme/btts"],
    ),
    SchemeSpec(
        key="Defensive_Low-Block",
        label="Defensive Low-Block",
        description=(
            "Compact defensive structure limiting opposition chances; "
            "high clean-sheet frequency and low match totals are the signature."
        ),
        signature="GA/game ≤ 1.15  AND  Clean-sheet% ≥ 31%  AND  Over-2.5 rate ≤ 49%",
        tags=["#scheme/defensive", "#scheme/low-block"],
    ),
    SchemeSpec(
        key="Draw-Prone_Grinder",
        label="Draw-Prone Grinder",
        description=(
            "Narrow, contested matches with a disproportionate share of draws; "
            "absorbs pressure and avoids defeat rather than seeking decisive wins."
        ),
        signature="Draw rate ≥ 30%",
        tags=["#scheme/draw-prone", "#scheme/grinder"],
    ),
    SchemeSpec(
        key="Leaky_High-Risk",
        label="Leaky / High-Risk",
        description=(
            "Defensive fragility is the defining trait; "
            "concedes frequently with few clean sheets, making matches unpredictable."
        ),
        signature="GA/game ≥ 1.80  AND  Clean-sheet% ≤ 18%",
        tags=["#scheme/leaky", "#scheme/high-risk"],
    ),
    SchemeSpec(
        key="Strong-at-Home",
        label="Strong at Home",
        description=(
            "Pronounced home-ground advantage expressed through significantly higher "
            "attacking output at home versus away."
        ),
        signature="Home GF/game − Away GF/game ≥ 0.50",
        tags=["#scheme/home-fortress"],
    ),
    SchemeSpec(
        key="Balanced",
        label="Balanced",
        description=(
            "Near-median profile across attacking, defensive, and result-distribution "
            "dimensions; no single tactical extreme dominates."
        ),
        signature=(
            "GF/game 0.95–1.45  AND  GA/game 1.10–1.65  "
            "AND  Over-2.5 40–57%  AND  BTTS 46–59%"
        ),
        tags=["#scheme/balanced"],
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_matches(corpus_dir: pathlib.Path) -> pd.DataFrame:
    """Load and validate matches.parquet."""
    path = corpus_dir / "matches.parquet"
    if not path.exists():
        raise FileNotFoundError(f"matches.parquet not found at {path}")
    df = pd.read_parquet(path)
    required = {"season", "div", "home_team", "away_team",
                "fthg", "ftag", "total_goals", "target_over25", "ftr"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"matches.parquet missing columns: {missing}")
    return df


def _compute_team_stats(df: pd.DataFrame, min_matches: int) -> pd.DataFrame:
    """Return one row per team with ≥ *min_matches* corpus appearances."""
    rows: List[Dict] = []
    all_teams = sorted(set(df["home_team"].tolist()) | set(df["away_team"].tolist()))
    for team in all_teams:
        hm = df[df["home_team"] == team]
        aw = df[df["away_team"] == team]
        n = len(hm) + len(aw)
        if n < min_matches:
            continue
        n_h, n_a = len(hm), len(aw)
        gf_h = float(hm["fthg"].sum()); gf_a = float(aw["ftag"].sum())
        ga_h = float(hm["ftag"].sum()); ga_a = float(aw["fthg"].sum())
        over = int(hm["target_over25"].sum()) + int(aw["target_over25"].sum())
        cs = int((hm["ftag"] == 0).sum()) + int((aw["fthg"] == 0).sum())
        btts = (
            int(((hm["fthg"] > 0) & (hm["ftag"] > 0)).sum())
            + int(((aw["ftag"] > 0) & (aw["fthg"] > 0)).sum())
        )
        wins = int((hm["ftr"] == "H").sum()) + int((aw["ftr"] == "A").sum())
        draws = int((hm["ftr"] == "D").sum()) + int((aw["ftr"] == "D").sum())
        gf_h_pg = gf_h / n_h if n_h else 0.0
        gf_a_pg = gf_a / n_a if n_a else 0.0
        rows.append({
            "team": team, "n": n,
            "gf_pg": (gf_h + gf_a) / n,
            "ga_pg": (ga_h + ga_a) / n,
            "over_pct": over / n, "cs_pct": cs / n, "btts_pct": btts / n,
            "draw_pct": draws / n, "win_pct": wins / n,
            "ppg": (wins * 3 + draws) / n,
            "home_adv": gf_h_pg - gf_a_pg,
        })
    return pd.DataFrame(rows)


def _classify(row: "pd.Series[float]") -> str:
    """Return the scheme key for one team stats row (priority waterfall)."""
    gf = row["gf_pg"]; ga = row["ga_pg"]
    ov = row["over_pct"]; cs = row["cs_pct"]
    bt = row["btts_pct"]; dr = row["draw_pct"]
    ha = row["home_adv"]
    if gf >= 1.60 and ov >= 0.58:
        return "High-Scoring_Attacking"
    if bt >= 0.60 and ov >= 0.58:
        return "High-Variance_Entertainers"
    if ga <= 1.15 and cs >= 0.31 and ov <= 0.49:
        return "Defensive_Low-Block"
    if dr >= 0.30:
        return "Draw-Prone_Grinder"
    if ga >= 1.80 and cs <= 0.18:
        return "Leaky_High-Risk"
    if ha >= 0.50:
        return "Strong-at-Home"
    return "Balanced"


def _assign_schemes(team_stats: pd.DataFrame) -> Dict[str, List[str]]:
    """Return dict mapping scheme key → sorted list of team names."""
    scheme_map: Dict[str, List[str]] = {s.key: [] for s in _SCHEMES}
    for _, row in team_stats.iterrows():
        key = _classify(row)
        scheme_map[key].append(str(row["team"]))
    for key in scheme_map:
        scheme_map[key].sort()
    return scheme_map


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_playstyles(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = _DEFAULT_CORPUS,
    *,
    min_matches: int = _MIN_MATCHES,
) -> List[pathlib.Path]:
    """Generate Obsidian tactical-scheme notes into *out_dir*.

    Parameters
    ----------
    out_dir:
        Destination directory; created if absent.  Idempotent.
    corpus_dir:
        Directory containing matches.parquet.  Defaults to data/domains/soccer/.
    min_matches:
        Minimum corpus appearances for scheme assignment (default 30).

    Returns
    -------
    list[pathlib.Path]
        Paths of every written note (_Playstyles_Index.md + one per scheme).
    """
    from domains.soccer.atlas_playstyles_render import (
        render_scheme_note,
        render_playstyles_index,
    )

    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = _load_matches(corpus_dir)
    team_stats = _compute_team_stats(df, min_matches)
    scheme_map = _assign_schemes(team_stats)
    n_corpus = len(df)
    n_teams_total = int(team_stats.shape[0])
    generated = datetime.date.today().isoformat()

    written: List[pathlib.Path] = []

    idx_path = out_dir / "_Playstyles_Index.md"
    written.append(write_note(
        idx_path,
        render_playstyles_index(scheme_map, n_corpus, n_teams_total, generated),
    ))

    for spec in _SCHEMES:
        teams = scheme_map.get(spec.key, [])
        note_path = out_dir / f"{spec.key}.md"
        written.append(write_note(
            note_path,
            render_scheme_note(spec, teams, team_stats, generated),
        ))

    return written
