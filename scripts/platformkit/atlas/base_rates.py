"""scripts.platformkit.atlas.base_rates — Cross-sport outcome base-rate meta-generator.

Emits vault/Sports/_Base_Rates.md: computed, person-free cross-sport table of OUTCOME BASE RATES
from real corpora.  Per sport: market shape, n, unconditional base rate, per-season breakdown.
Gracefully skips any sport whose corpus files are absent.

HONEST: base rates = descriptive context for the graph, NOT predictions or edges.  No edge claimed.
PERSON-FREE: no individual names.  Py 3.9.  F5-clean (no src.*/kernel.*/domains.* at module level).
"""
from __future__ import annotations

import pathlib
import time
from typing import Dict, List, Optional, Tuple

from scripts.platformkit.atlas.obsidian_emit import frontmatter, write_note

_OUT_FILENAME = "_Base_Rates.md"

# (sport_id, display, market_shape, target_description, loader_module, target_col, date_col)
# NBA excluded: no FeatureBundle adapter/signal_catalog; NBA uses a separate gate path.
_SPORT_SPECS: List[Tuple[str, str, str, str, str, str, str]] = [
    ("tennis_atp", "Tennis (ATP)", "Head-to-head ML — binary win/loss",
     "P(listed player-1 wins the match)", "domains.tennis.elo", "winner", "date"),
    ("soccer_fd", "Soccer (football-data)", "O/U 2.5 goals — binary total",
     "P(match total goals >= 3, i.e. Over 2.5)", "domains.soccer.ratings", "target_over25", "date"),
    ("mlb_sbro", "MLB (SBRO archive)", "Home/away ML — binary home-win",
     "P(home team wins the game)", "domains.mlb.ratings", "target_home_win", "date"),
    ("nba_espn", "NBA (ESPN ML)", "Home/away ML — binary home-win",
     "P(home team wins the game)", "domains.basketball_nba.ratings", "home_win", "date"),
]

# Per-sport group-by column (year for tennis; season for the others)
_GROUPBY_COL: Dict[str, str] = {"tennis_atp": "year", "soccer_fd": "season", "mlb_sbro": "season", "nba_espn": "season"}


# ---------------------------------------------------------------------------
# Data loaders — dynamically imported so absent packages skip gracefully
# ---------------------------------------------------------------------------

def _load_tennis(repo_root: pathlib.Path) -> Optional[object]:
    """Return walk_forward DataFrame for tennis (winner remapped 1→1.0/2→0.0), or None."""
    try:
        import importlib
        import pandas as pd  # type: ignore[import]
        mod = importlib.import_module("domains.tennis.elo")
        df = pd.read_parquet(repo_root / "data" / "domains" / "tennis" / "matches.parquet")
        wf = mod.walk_forward_elo(df).copy()
        wf["winner"] = (wf["winner"] == 1).astype(float)
        wf["year"] = pd.to_datetime(wf["date"]).dt.year
        return wf
    except Exception:  # noqa: BLE001
        return None


def _load_soccer(repo_root: pathlib.Path) -> Optional[object]:
    """Return walk_forward DataFrame for soccer, or None if corpus absent."""
    try:
        import importlib
        import pandas as pd  # type: ignore[import]
        mod = importlib.import_module("domains.soccer.ratings")
        df = pd.read_parquet(repo_root / "data" / "domains" / "soccer" / "matches.parquet")
        return mod.walk_forward_goals(df)
    except Exception:  # noqa: BLE001
        return None


def _load_mlb(repo_root: pathlib.Path) -> Optional[object]:
    """Return walk_forward DataFrame for MLB; derives target_home_win if absent, or None."""
    try:
        import importlib
        import pandas as pd  # type: ignore[import]
        mod = importlib.import_module("domains.mlb.ratings")
        df = pd.read_parquet(repo_root / "data" / "domains" / "mlb" / "games.parquet")
        wf = mod.walk_forward_elo(df)
        if "target_home_win" not in wf.columns:
            wf = wf.copy()
            wf["target_home_win"] = (wf["home_runs"].astype(float) > wf["away_runs"].astype(float)).astype(float)
        return wf
    except Exception:  # noqa: BLE001
        return None


def _load_nba(repo_root: pathlib.Path) -> Optional[object]:
    """Return the NBA games frame (carries home_win + season) for base-rate compute, or None."""
    try:
        import pandas as pd  # type: ignore[import]
        df = pd.read_parquet(repo_root / "data" / "domains" / "basketball_nba" / "games.parquet")
        wf = df.copy()
        wf["home_win"] = wf["home_win"].astype(float)
        return wf
    except Exception:  # noqa: BLE001
        return None


_LOADERS = {"tennis_atp": _load_tennis, "soccer_fd": _load_soccer, "mlb_sbro": _load_mlb, "nba_espn": _load_nba}


# ---------------------------------------------------------------------------
# Computation helpers
# ---------------------------------------------------------------------------

def _compute(wf: object, target_col: str, group_col: str) -> Tuple[int, float, List[Tuple[str, int, float]]]:
    """Return (n, overall_rate, [(group_label, n, rate), ...]) from a DataFrame."""
    import pandas as pd  # type: ignore[import]
    df = wf  # type: ignore[assignment]
    col = df[target_col].dropna()
    n_total = len(col)
    if n_total == 0:
        return 0, float("nan"), []
    overall = float(col.mean())
    groups: List[Tuple[str, int, float]] = []
    if group_col in df.columns:
        for grp, sub in df.groupby(group_col):
            sub_col = sub[target_col].dropna()
            if len(sub_col) == 0:
                continue
            try:
                label = str(int(grp))           # numeric season (e.g. 2024)
            except (TypeError, ValueError):
                label = str(grp)                  # string season (e.g. "2022-23" for NBA)
            groups.append((label, len(sub_col), float(sub_col.mean())))
    groups.sort(key=lambda x: x[0])
    return n_total, overall, groups


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _section_header() -> List[str]:
    return [
        "## What These Numbers Are", "",
        "> **Honest framing:** unconditional outcome frequencies from each sport's real corpus.",
        "> Descriptive context for the person-free graph — NOT model predictions, NOT edges,",
        "> NOT forward-looking probability estimates.  Markets are efficient; no durable",
        "> pregame edge is claimed.  REJECT = honest success criterion.", "",
        "> Per-season rows show how the base rate shifts across the corpus span.",
        "> Variation within a sport is sampling noise, not evidence of model value.", "",
    ]


def _section_summary(results: List[Tuple[str, str, str, str, int, float]]) -> List[str]:
    L: List[str] = [
        "## Cross-Sport Base Rate Summary", "",
        "| Sport | Market Shape | Target | n | Base Rate |",
        "|-------|-------------|--------|---|-----------|",
    ]
    for _, display, shape, target_desc, n, rate in results:
        rate_str = f"{rate:.4f}" if rate == rate else "N/A"  # nan check
        L.append(f"| {display} | {shape} | {target_desc} | {n:,} | {rate_str} |")
    L.append("")
    return L


def _section_per_sport_breakdown(
    results: List[Tuple[str, str, str, str, int, float]],
    groups_map: Dict[str, List[Tuple[str, int, float]]],
    group_col_map: Dict[str, str],
) -> List[str]:
    L: List[str] = ["## Per-Sport Season Breakdown", ""]
    for sport_id, display, shape, target_desc, n_total, overall in results:
        groups = groups_map.get(sport_id, [])
        group_label = "Season" if group_col_map.get(sport_id) == "season" else "Year"
        L += [f"### {display}", "", f"- **Market:** {shape}", f"- **Target:** {target_desc}",
              f"- **Corpus n:** {n_total:,}", f"- **Overall base rate:** {overall:.4f}", ""]
        if groups:
            L += [f"| {group_label} | n | Base Rate |", f"|{'-' * (len(group_label) + 2)}|---|-----------|"]
            for grp_lbl, grp_n, grp_rate in groups:
                L.append(f"| {grp_lbl} | {grp_n:,} | {grp_rate:.4f} |")
            L.append("")
        else:
            L += ["> No season/year grouping available.", ""]
    return L


def _section_skipped(skipped: List[str]) -> List[str]:
    if not skipped:
        return []
    L = ["## Skipped Sports (corpus absent)", ""]
    for s in skipped:
        L.append(f"- **{s}** — corpus files not found; run the domain ingest script to populate.")
    L.append("")
    return L


def _section_links() -> List[str]:
    return [
        "## Source Notes", "",
        "- [[_Hub]] — multi-sport registry (Up)",
        "- [[_World_Model]] — cross-sport platform knowledge synthesis",
        "- [[_Signals_Hub]] — cross-sport signal-discovery aggregator",
        "- [[_GraphStats]] — memory-graph statistics",
        "",
    ]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_base_rates(vault_sports_dir: Optional[pathlib.Path] = None) -> pathlib.Path:
    """Compute per-sport outcome base rates and write vault/Sports/_Base_Rates.md.

    Gracefully skips sports whose corpora are absent.  PERSON-FREE; no edge claimed.
    """
    if vault_sports_dir is None:
        repo_root = pathlib.Path(__file__).resolve().parents[3]
        vault_sports_dir = repo_root / "vault" / "Sports"
    else:
        repo_root = pathlib.Path(vault_sports_dir).resolve().parents[1]

    vault_sports_dir = pathlib.Path(vault_sports_dir)
    if not vault_sports_dir.is_dir():
        raise FileNotFoundError(f"vault/Sports dir not found: {vault_sports_dir}")

    results: List[Tuple[str, str, str, str, int, float]] = []
    groups_map: Dict[str, List[Tuple[str, int, float]]] = {}
    skipped: List[str] = []

    for sport_id, display, shape, target_desc, _mod, target_col, _dcol in _SPORT_SPECS:
        loader = _LOADERS.get(sport_id)
        if loader is None:
            skipped.append(display)
            continue
        wf = loader(repo_root)
        if wf is None:
            skipped.append(display)
            continue
        group_col = _GROUPBY_COL.get(sport_id, "season")
        try:
            n_total, overall, groups = _compute(wf, target_col, group_col)
        except Exception:  # noqa: BLE001
            skipped.append(display)
            continue
        if n_total == 0:
            skipped.append(display)
            continue
        results.append((sport_id, display, shape, target_desc, n_total, overall))
        groups_map[sport_id] = groups

    group_col_map = {sid: _GROUPBY_COL.get(sid, "season") for sid, *_ in _SPORT_SPECS}
    fm = frontmatter({
        "tags":            ["base-rates", "meta", "cross-sport", "honest"],
        "generated":       time.strftime("%Y-%m-%d"),
        "sports_computed": len(results),
        "sports_skipped":  len(skipped),
    })
    L: List[str] = [
        fm, "",
        "# Cross-Sport Outcome Base Rates", "",
        "> **Auto-generated** by `scripts/platformkit/atlas/base_rates.py`"
        " — do not hand-edit.  Re-run `build_base_rates()` to refresh.", "",
        "> **Honest framing:** base rates are descriptive context for the person-free"
        " graph, NOT predictions or edges.  No edge claimed.", "",
        "Up: [[_Hub]]", "", "---", "",
    ]
    L += _section_header()
    L += ["---", ""]
    L += _section_summary(results)
    L += ["---", ""]
    L += _section_per_sport_breakdown(results, groups_map, group_col_map)
    skipped_section = _section_skipped(skipped)
    if skipped_section:
        L += ["---", ""]
        L += skipped_section
    L += ["---", ""]
    L += _section_links()
    L += [
        "---", "",
        f"*Generated {time.strftime('%Y-%m-%d %H:%M:%S')} · "
        f"{len(results)} sport(s) computed · {len(skipped)} skipped · person-free · no edge claimed*",
        "", "_PRIVATE research.  Base rates = descriptive context only.  No edge claimed._",
    ]
    return write_note(vault_sports_dir / _OUT_FILENAME, "\n".join(L) + "\n")


if __name__ == "__main__":
    import sys
    vault_arg = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    print(f"Written: {build_base_rates(vault_arg)}")
