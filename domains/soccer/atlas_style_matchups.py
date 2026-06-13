"""domains.soccer.atlas_style_matchups — Scheme-vs-scheme tactical matchup matrix.

For every match in matches.parquet, looks up the tactical scheme of both the
home and away team (using the same _classify / _compute_team_stats logic as
atlas_playstyles) then tallies outcomes by scheme pairing.

Emits into *out_dir* (default vault/Sports/Soccer/Style_Matchups/):
  _Style_Matchups_Index.md   — hub with all pairs, meeting counts, summary rates
  <SchemeA>_vs_<SchemeB>.md  — one per pair with ≥ min_pair_meetings meetings

Each pair note contains: home-win / draw / away-win rates, over-2.5 rate,
total meetings, YAML frontmatter, [[Playstyles/<Scheme>]] wikilinks, and #tags.

Renderers live in domains.soccer.atlas_style_matchups_render (≤300 LOC each).

F5 compliance: stdlib + pandas + domains.soccer.* only.
No src.*, kernel.*, or sibling-domain imports.
All statistics are corpus-derived; no edge/betting language; no individual player names.
Idempotent: re-running overwrites with identical content.
"""
from __future__ import annotations

import datetime
import pathlib
from typing import Dict, List, NamedTuple, Tuple

import pandas as pd

from scripts.platformkit.atlas.obsidian_emit import write_note
from domains.soccer.atlas_playstyles import (
    _SCHEMES,
    _classify,
    _compute_team_stats,
    _load_matches,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CORPUS: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "domains" / "soccer"
)
_MIN_TEAM_MATCHES: int = 30   # minimum corpus appearances for scheme assignment
_MIN_PAIR_MEETINGS: int = 50  # minimum meetings for a pair note to be emitted


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class PairStats(NamedTuple):
    """Aggregate statistics for one ordered (home_scheme, away_scheme) pairing."""

    home_scheme: str   # key from _SCHEMES
    away_scheme: str   # key from _SCHEMES
    n: int             # total meetings
    home_wins: int
    draws: int
    away_wins: int
    over25: int        # count of matches with total goals > 2.5

    @property
    def home_win_rate(self) -> float:
        return self.home_wins / self.n if self.n else 0.0

    @property
    def draw_rate(self) -> float:
        return self.draws / self.n if self.n else 0.0

    @property
    def away_win_rate(self) -> float:
        return self.away_wins / self.n if self.n else 0.0

    @property
    def over25_rate(self) -> float:
        return self.over25 / self.n if self.n else 0.0


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def _build_team_scheme_map(df: pd.DataFrame) -> Dict[str, str]:
    """Return {team_name: scheme_key} for every team with ≥ _MIN_TEAM_MATCHES."""
    team_stats = _compute_team_stats(df, _MIN_TEAM_MATCHES)
    return {
        str(row["team"]): _classify(row)
        for _, row in team_stats.iterrows()
    }


def _tally_pair_stats(
    df: pd.DataFrame,
    team_scheme: Dict[str, str],
) -> List[PairStats]:
    """Tally outcomes by (home_scheme, away_scheme) pair across the corpus."""
    scheme_keys = [s.key for s in _SCHEMES]
    tallies: Dict[Tuple[str, str], Dict[str, int]] = {}
    for hs in scheme_keys:
        for as_ in scheme_keys:
            tallies[(hs, as_)] = {"n": 0, "hw": 0, "d": 0, "aw": 0, "ov": 0}

    for _, row in df.iterrows():
        home = str(row["home_team"])
        away = str(row["away_team"])
        hs = team_scheme.get(home)
        as_ = team_scheme.get(away)
        if hs is None or as_ is None:
            continue  # team below threshold — skip
        t = tallies[(hs, as_)]
        t["n"] += 1
        ftr = str(row["ftr"])
        if ftr == "H":
            t["hw"] += 1
        elif ftr == "D":
            t["d"] += 1
        else:
            t["aw"] += 1
        t["ov"] += int(row["target_over25"])

    result: List[PairStats] = []
    for (hs, as_), t in tallies.items():
        if t["n"] == 0:
            continue
        result.append(
            PairStats(
                home_scheme=hs, away_scheme=as_, n=t["n"],
                home_wins=t["hw"], draws=t["d"], away_wins=t["aw"], over25=t["ov"],
            )
        )
    result.sort(key=lambda p: (-p.n, p.home_scheme, p.away_scheme))
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_style_matchups(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = _DEFAULT_CORPUS,
    *,
    min_pair_meetings: int = _MIN_PAIR_MEETINGS,
) -> List[pathlib.Path]:
    """Generate Obsidian scheme-vs-scheme matchup notes into *out_dir*.

    Parameters
    ----------
    out_dir:
        Destination directory; created if absent. Idempotent.
    corpus_dir:
        Directory containing matches.parquet. Defaults to data/domains/soccer/.
    min_pair_meetings:
        Minimum match count for a pairing to get its own note (default 50).

    Returns
    -------
    list[pathlib.Path]
        Paths of every written note (_Style_Matchups_Index.md + per-pair notes).
    """
    from domains.soccer.atlas_style_matchups_render import render_index, render_pair_note

    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = _load_matches(corpus_dir)
    team_scheme = _build_team_scheme_map(df)
    all_pairs = _tally_pair_stats(df, team_scheme)
    noted_pairs = [p for p in all_pairs if p.n >= min_pair_meetings]
    generated = datetime.date.today().isoformat()

    written: List[pathlib.Path] = []

    idx_path = out_dir / "_Style_Matchups_Index.md"
    written.append(write_note(idx_path, render_index(noted_pairs, len(df), generated)))

    for ps in noted_pairs:
        stem = f"{ps.home_scheme}_vs_{ps.away_scheme}"
        note_path = out_dir / f"{stem}.md"
        written.append(write_note(note_path, render_pair_note(ps, generated)))

    return written
