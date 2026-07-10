"""scripts.platformkit.data_frontier.profile_completeness -- sport-blind
completeness auditor over the SHARED PROFILE SCHEMA (entity_id, entity_name,
window, attribute, raw_value, percentile, rating_2k, n, ingredients, status,
sources) that every domains/<sport>/profiles/build_profiles.py writes to
data/cache/profiles/<sport>_player_profiles.parquet.

Answers 'know every little detail of each player' as a number: per sport x
attribute, what % of the ACTIVE roster has that attribute filled, how stale
each window is, and an all-null-column canary (n>0 rows but raw_value 100%
null -- looks covered, isn't).

ACTIVE-ROSTER PROXY (ponytail: documented ceiling, not a new data fetch):
"active" = entities appearing in this store's OWN most-recent window(s), where
"most-recent" = the max 4-digit year found anywhere in the window strings
(_window_year). This is sport-blind (no per-sport roster feed to plumb in) but
has a real ceiling: a currently-active player with ZERO profiled attributes
this window is invisible to this metric. Upgrade path if that's ever found to
matter: join against each sport's own roster/gamelog source
(data/domains/<sport>/*.parquet) instead of the profile store's own coverage.

CLI: python -m scripts.platformkit.data_frontier.profile_completeness
Per-file test: python -m pytest scripts/platformkit/data_frontier/test_profile_completeness.py -q
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
_PROFILES_DIR = REPO_ROOT / "data" / "cache" / "profiles"
_OUT_PATH = REPO_ROOT / "data" / "frontend" / "ops" / "profile_completeness.json"

# sport -> profile store filename. None = no player-level store built yet (an
# honest gap, not a bug -- domains/soccer/profiles/build_profiles.py is
# TEAM-level only today; see module docstring there).
SPORT_STORES: dict[str, Optional[str]] = {
    "nba": "nba_player_profiles.parquet",
    "wnba": "wnba_player_profiles.parquet",
    "mlb": "mlb_player_profiles.parquet",
    "tennis": "tennis_player_profiles.parquet",
    "soccer": None,
}

_YEAR_RE = re.compile(r"(\d{4})")
_ASOF_RE = re.compile(r"asof_(\d{4}-\d{2}-\d{2})")
# ~1 season + grace. A single max-year cut would starve every attribute still
# on last season's (complete) window the moment a sparser in-progress
# current-year window exists (e.g. MLB's partial season_2026 fielding sample
# outranking the completed, much-larger season_2025 batting sample) --
# ponytail: tune here if a sport's own cadence needs a different window.
_ACTIVE_STALENESS_DAYS = 400


def _window_year(window: str) -> Optional[int]:
    years = [int(y) for y in _YEAR_RE.findall(window)]
    return max(years) if years else None


def active_window_set(windows: list[str], today: Optional[date] = None) -> set[str]:
    """Every window within _ACTIVE_STALENESS_DAYS of today -- see module
    docstring for the proxy + its ceiling. Falls back to "everything" if no
    window in the store has any recoverable year at all."""
    today = today or date.today()
    stale = {w: staleness_days(w, today) for w in windows}
    known = {w: d for w, d in stale.items() if d is not None}
    if not known:
        return set(windows)
    return {w for w, d in known.items() if d <= _ACTIVE_STALENESS_DAYS}


def staleness_days(window: str, today: date) -> Optional[int]:
    """asof_YYYY-MM-DD windows: exact day diff. season/year windows: whole
    years since the window's own year, in days (approx, no leap-day fuss --
    this is a staleness SIGNAL, not a settlement clock). None if no year
    is recoverable from the window string at all (e.g. tennis's 'last10')."""
    m = _ASOF_RE.search(window)
    if m:
        return (today - date.fromisoformat(m.group(1))).days
    y = _window_year(window)
    return None if y is None else (today.year - y) * 365


def audit_sport(sport: str, store_path: Optional[Path], today: date) -> dict[str, Any]:
    if store_path is None or not store_path.exists():
        return {"sport": sport, "status": "NO_PLAYER_STORE", "attributes": []}
    df = pd.read_parquet(store_path, columns=["entity_id", "window", "attribute", "raw_value", "status"])
    windows = sorted(df["window"].unique())
    active_windows = active_window_set(windows, today)
    active_universe = int(df.loc[df["window"].isin(active_windows), "entity_id"].nunique())

    rows = []
    for (attr, window), g in df.groupby(["attribute", "window"]):
        n_covered = int(g["entity_id"].nunique())
        is_active = window in active_windows
        rows.append({
            "attribute": attr, "window": window, "is_active_window": is_active,
            "n_covered": n_covered,
            "coverage_pct_of_active": round(100.0 * n_covered / active_universe, 2)
                                      if is_active and active_universe else None,
            "staleness_days": staleness_days(window, today),
            "all_null": bool(g["raw_value"].isna().all()),
            "status": g["status"].iloc[0] if len(g) else None,
        })
    all_null_rows = [r for r in rows if r["all_null"]]
    return {
        "sport": sport, "status": "OK", "n_windows": len(windows),
        "active_windows": sorted(active_windows), "active_universe_n": active_universe,
        "n_attributes": int(df["attribute"].nunique()),
        "all_null_count": len(all_null_rows),
        "all_null_attrs": [f"{r['attribute']}@{r['window']}" for r in all_null_rows],
        "attributes": rows,
    }


def _mlb_milb_freshness() -> Optional[dict[str, Any]]:
    """MLB-only enrichment: MiLB active-roster debut-watch (roster-freshness +
    debut flags), see scripts/platformkit/data_frontier/milb_statsapi.debut_watch."""
    try:
        from scripts.platformkit.data_frontier.milb_statsapi import debut_watch
        return debut_watch()
    except Exception as exc:  # noqa: BLE001 -- enrichment is best-effort, never blocks the audit
        return {"status": "ERROR", "error": str(exc)}


def build_report(profiles_dir: Path = _PROFILES_DIR, today: Optional[date] = None) -> dict[str, Any]:
    today = today or date.today()
    sports = {sport: audit_sport(sport, profiles_dir / fname if fname else None, today)
              for sport, fname in SPORT_STORES.items()}
    if sports.get("mlb", {}).get("status") == "OK":
        sports["mlb"]["milb_roster_freshness"] = _mlb_milb_freshness()
    return {"generated_at": datetime.now().isoformat(), "sports": sports}


def write_report(report: dict[str, Any], out_path: Path = _OUT_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="ascii", errors="replace")
    return out_path


def print_docs_table(report: dict[str, Any]) -> None:
    print(f"{'sport':<10}{'status':<18}{'n_attrs':>9}{'active_n':>10}{'all_null':>10}")
    for sport, r in report["sports"].items():
        if r["status"] != "OK":
            print(f"{sport:<10}{r['status']:<18}{'-':>9}{'-':>10}{'-':>10}")
            continue
        print(f"{sport:<10}{'OK':<18}{r['n_attributes']:>9}{r['active_universe_n']:>10}{r['all_null_count']:>10}")


def main() -> int:
    report = build_report()
    out_path = write_report(report)
    print_docs_table(report)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


__all__ = ["build_report", "write_report", "audit_sport", "active_window_set",
           "staleness_days", "SPORT_STORES"]
