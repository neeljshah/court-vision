"""probe_R29_V2_backfill_complete.py — Measures the R29_V2 backfill outcome.

R28_U1 shipped ``scripts/backfill_linescores_played_games.py`` but only
processed 175/977 2025-26 stubs before its 35-min cap. R29_V2 reruns the
backfill end-to-end and records pre/post counts so the improvement loop
can see the data gain.

Reads:
  * ``data/nba/linescores_all.json`` (post state)
  * ``data/nba/linescores_all.json.bak_R28_U1`` (pre state)
  * ``data/nba/season_games_2024-25.json`` /  ``season_games_2025-26.json``
    (denominator for coverage_pct)

Writes:
  * ``data/cache/probe_R29_V2_results.json`` with
      - before / after row + stub counts per season
      - coverage_pct_2025_26_before / _after
      - new_real_2025_26 (stubs replaced)
      - new_rows_2025_26 / new_rows_2024_25 (brand-new rows added)
      - runtime_minutes (if main backfill log present)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, PROJECT_DIR)


def _resolve_root() -> str:
    cand = os.environ.get("NBA_AI_ROOT") or r"C:\Users\neelj\nba-ai-system"
    return cand if os.path.isdir(os.path.join(cand, "data", "nba")) else PROJECT_DIR


ROOT_DIR = _resolve_root()
DATA_NBA = os.path.join(ROOT_DIR, "data", "nba")
LS_PATH = os.path.join(DATA_NBA, "linescores_all.json")
BAK_PATH = LS_PATH + ".bak_R28_U1"
CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
RESULTS_PATH = os.path.join(CACHE_DIR, "probe_R29_V2_results.json")

_CUTOFF = "2026-05-25"


def _season(gid: str) -> str:
    if gid.startswith("00224"):
        return "2024-25"
    if gid.startswith("00225"):
        return "2025-26"
    return "other"


def _is_stub(row) -> bool:
    if not isinstance(row, dict):
        return True
    s = 0
    for side in ("home", "away"):
        for i in range(1, 5):
            try:
                s += int(row.get(f"{side}_q{i}", 0) or 0)
            except (TypeError, ValueError):
                pass
    return s == 0


def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _summarize(payload: dict) -> dict:
    counts = {
        "2024-25_total": 0, "2024-25_stub": 0, "2024-25_real": 0,
        "2025-26_total": 0, "2025-26_stub": 0, "2025-26_real": 0,
    }
    for gid, row in payload.items():
        s = _season(gid)
        if s not in ("2024-25", "2025-26"):
            continue
        counts[f"{s}_total"] += 1
        if _is_stub(row):
            counts[f"{s}_stub"] += 1
        else:
            counts[f"{s}_real"] += 1
    return counts


def _played_count(season: str) -> int:
    """Number of scheduled games in this season with game_date <= _CUTOFF."""
    p = os.path.join(DATA_NBA, f"season_games_{season}.json")
    if not os.path.exists(p):
        return 0
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    rows = d.get("rows", d) if isinstance(d, dict) else d
    n = 0
    for r in rows:
        gd = str(r.get("game_date", "") or "")
        if gd and gd <= _CUTOFF:
            n += 1
    return n


def main() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    after_payload = _load_json(LS_PATH)
    before_payload = _load_json(BAK_PATH)

    before = _summarize(before_payload)
    after = _summarize(after_payload)

    played_2024_25 = _played_count("2024-25")
    played_2025_26 = _played_count("2025-26")

    # Coverage % = real (non-stub) rows / scheduled played games.
    def _pct(real: int, denom: int) -> float:
        return (real / denom * 100.0) if denom else 0.0

    cov_pre_2526 = _pct(before["2025-26_real"], played_2025_26)
    cov_post_2526 = _pct(after["2025-26_real"], played_2025_26)
    cov_pre_2425 = _pct(before["2024-25_real"], played_2024_25)
    cov_post_2425 = _pct(after["2024-25_real"], played_2024_25)

    common_keys = set(before_payload) & set(after_payload)
    stubs_pre_common = sum(
        1 for gid in common_keys
        if _season(gid) == "2025-26" and _is_stub(before_payload[gid])
    )
    stubs_post_common = sum(
        1 for gid in common_keys
        if _season(gid) == "2025-26" and _is_stub(after_payload[gid])
    )
    stubs_replaced_2025_26 = stubs_pre_common - stubs_post_common

    new_keys = set(after_payload) - set(before_payload)
    new_rows_2025_26 = sum(1 for gid in new_keys if _season(gid) == "2025-26")
    new_rows_2024_25 = sum(1 for gid in new_keys if _season(gid) == "2024-25")

    results = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "before": before,
        "after": after,
        "played_2024_25_le_cutoff": played_2024_25,
        "played_2025_26_le_cutoff": played_2025_26,
        "cutoff_date": _CUTOFF,
        "coverage_pct_2025_26_before": round(cov_pre_2526, 2),
        "coverage_pct_2025_26_after": round(cov_post_2526, 2),
        "coverage_pct_2024_25_before": round(cov_pre_2425, 2),
        "coverage_pct_2024_25_after": round(cov_post_2425, 2),
        "stubs_replaced_2025_26": stubs_replaced_2025_26,
        "new_rows_2025_26": new_rows_2025_26,
        "new_rows_2024_25": new_rows_2024_25,
        "total_new_completed_games": stubs_replaced_2025_26
            + new_rows_2025_26 + new_rows_2024_25,
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
