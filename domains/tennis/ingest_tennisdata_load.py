"""domains.tennis.ingest_tennisdata_load — season-file loading + name normalisation keys.

Extracted from ingest_tennisdata.py (pure move — zero logic change).

Covers:
- URL templates and column constants
- _read_season_file / load_raw_season_files
- _add_norm_keys / _add_match_norm_keys
- _norm_round / _ROUND_MAP

F5 compliance: ONLY stdlib + numpy/pandas + domains.tennis.* imports.
"""
from __future__ import annotations

import pathlib

import pandas as pd

from domains.tennis.name_aliases import normalize_td, normalize_sackmann, ALIASES, candidate_keys


# ---------------------------------------------------------------------------
# tennis-data.co.uk URL templates (fetch deferred — for reference)
# ---------------------------------------------------------------------------

_TD_ATP_URL = "http://www.tennis-data.co.uk/{year}/{year}.xlsx"
_TD_WTA_URL = "http://www.tennis-data.co.uk/{year}w/{year}.xlsx"

# ---------------------------------------------------------------------------
# Column mapping (varies slightly year-by-year; tolerate missing → NA)
# ---------------------------------------------------------------------------

_REQUIRED_COLS = ["Date", "Winner", "Loser"]
_PRICE_COLS = ["B365W", "B365L", "PSW", "PSL", "MaxW", "MaxL", "AvgW", "AvgL"]
_OPTIONAL_COLS = [
    "Tournament", "Surface", "Round", "Best of", "WRank", "LRank", "Comment",
]

# Round label → Sackmann round code (best-effort; unmapped → None)
_ROUND_MAP: dict[str, str] = {
    "the final": "F",
    "final": "F",
    "semifinals": "SF",
    "semifinal": "SF",
    "quarterfinals": "QF",
    "quarterfinal": "QF",
    "3rd round": "R16",
    "round of 16": "R16",
    "4th round": "R16",
    "3rd round qualifying": "Q3",
    "2nd round qualifying": "Q2",
    "1st round qualifying": "Q1",
    "2nd round": "R32",
    "1st round": "R64",
    "round of 32": "R32",
    "round of 64": "R64",
    "round of 128": "R128",
    "robin round": "RR",
    "round robin": "RR",
}


def _norm_round(r: str | None) -> str | None:
    if not r:
        return None
    return _ROUND_MAP.get(str(r).strip().lower())


# ---------------------------------------------------------------------------
# CSV / XLSX loading
# ---------------------------------------------------------------------------

def _read_season_file(path: pathlib.Path) -> pd.DataFrame:
    """Read a single tennis-data season file (.xlsx or .csv) into a raw DataFrame.

    Missing optional columns are filled with NA.  Raises on missing required cols.
    """
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        raw = pd.read_excel(path, engine="openpyxl")
    elif suffix == ".csv":
        raw = pd.read_csv(path, low_memory=False)
    else:
        raise ValueError(f"Unsupported file type: {path}")

    # Drop completely empty rows (some workbooks have trailing blank rows)
    raw = raw.dropna(how="all").reset_index(drop=True)

    # Ensure optional cols exist (fill NA if absent)
    for col in _OPTIONAL_COLS + _PRICE_COLS:
        if col not in raw.columns:
            raw[col] = pd.NA

    missing_req = [c for c in _REQUIRED_COLS if c not in raw.columns]
    if missing_req:
        raise ValueError(f"Required columns missing in {path.name}: {missing_req}")

    return raw


def load_raw_season_files(
    paths: list[pathlib.Path],
    tour: str,
    year: int,
) -> pd.DataFrame:
    """Load one or more season files and tag with tour/year metadata."""
    frames = [_read_season_file(p) for p in paths]
    df = pd.concat(frames, ignore_index=True)
    df["_tour"] = tour
    df["_year"] = year
    return df


# ---------------------------------------------------------------------------
# Name normalisation key column
# ---------------------------------------------------------------------------

def _add_norm_keys(df: pd.DataFrame) -> pd.DataFrame:
    """Add _norm_winner/_norm_loser (primary key) and _cands_winner/_cands_loser (candidate sets)."""
    df = df.copy()
    df["_norm_winner"] = df["Winner"].fillna("").apply(
        lambda n: ALIASES.get(normalize_td(n), normalize_td(n))
    )
    df["_norm_loser"] = df["Loser"].fillna("").apply(
        lambda n: ALIASES.get(normalize_td(n), normalize_td(n))
    )
    df["_cands_winner"] = df["Winner"].fillna("").apply(
        lambda n: candidate_keys(n, "td") if n else {""}
    )
    df["_cands_loser"] = df["Loser"].fillna("").apply(
        lambda n: candidate_keys(n, "td") if n else {""}
    )
    return df


# ---------------------------------------------------------------------------
# Matches-DataFrame normalisation (needs norm keys for join)
# ---------------------------------------------------------------------------

def _add_match_norm_keys(matches: pd.DataFrame) -> pd.DataFrame:
    """Add _norm_p1/_norm_p2 (primary key) and _cands_p1/_cands_p2 (candidate sets)."""
    matches = matches.copy()
    matches["_norm_p1"] = matches["p1_name"].fillna("").apply(
        lambda n: ALIASES.get(normalize_sackmann(n), normalize_sackmann(n))
    )
    matches["_norm_p2"] = matches["p2_name"].fillna("").apply(
        lambda n: ALIASES.get(normalize_sackmann(n), normalize_sackmann(n))
    )
    matches["_cands_p1"] = matches["p1_name"].fillna("").apply(
        lambda n: candidate_keys(n, "sackmann") if n else {""}
    )
    matches["_cands_p2"] = matches["p2_name"].fillna("").apply(
        lambda n: candidate_keys(n, "sackmann") if n else {""}
    )
    return matches
