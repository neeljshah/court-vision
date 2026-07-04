"""scripts.platformkit.ingame.tail_hypothesis_ledger_2024plus -- LANE 4: the
2 new corpus rows (polymarket_2024plus_nba, polymarket_2024plus_mlb) added to
tail_hypothesis_ledger.py, split into this sibling module to keep the main
ledger file under the 300 LOC cap. Same composition contract as the parent
module: reads an existing verdict artifact verbatim, computes nothing new,
degrades to an honest ABSENT row on a missing/unreadable file.

Source artifacts (built by polymarket_game_slug_backfill.py +
polymarket_tail_validation.py --window 2024plus):
  data/venue_history/polymarket/nba_2024plus_tail_validation.json
  data/venue_history/polymarket/mlb_2024plus_tail_validation.json

PROVENANCE (binding): physically separate corpus/file from the 2023 "dailies"
polymarket_2023 corpus and from every forward gate. Never pooled with either.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no network; read-only against
data/; never writes data/registry/; no flag flip; edge_claimed always False.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_tail_hypothesis_ledger_2024plus.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

# Historical VALIDATION corpora only (never forward gates, which are mostly
# still INSUFFICIENT_FORWARD and are not the "independent historical corpus"
# the pre-registered synthesis condition refers to).
HISTORICAL_VALIDATION_CORPORA = (
    "polymarket_2023", "kalshi_historical",
    "polymarket_2024plus_nba", "polymarket_2024plus_mlb",
)


def rows_polymarket_2024plus(sport: str, *, repo_root: Path, hypotheses: List[Dict[str, str]],
                              read_json, absent_row) -> List[Dict[str, Any]]:
    """The alternate-slug 2024+ Polymarket corpus (physically separate
    directory/file from the 2023 dailies corpus -- see
    polymarket_game_slug_backfill.py / polymarket_tail_validation.py
    window="2024plus"). One row pair (H1, H2) per sport (nba, mlb).
    *repo_root* is the CALLER's (possibly monkeypatched) _REPO_ROOT -- never a
    module-local constant here, so tests that patch the parent module's
    _REPO_ROOT transparently redirect this module too, with no separate
    monkeypatch target. *read_json*/*absent_row* are the parent module's
    helpers, passed in so this module never re-implements or drifts from that
    read/absent logic."""
    corpus_name = "polymarket_2024plus_%s" % sport
    path = Path(repo_root) / "data" / "venue_history" / "polymarket" / ("%s_2024plus_tail_validation.json" % sport)
    doc = read_json(path)
    rows: List[Dict[str, Any]] = []
    for h in hypotheses:
        if doc is None:
            rows.append(absent_row(h["id"], corpus_name, "polymarket_historical_validation_2024plus",
                                    sport, path))
            continue
        band = doc.get("bands", {}).get(h["band"], {}).get("pooled")
        if not band:
            rows.append(absent_row(h["id"], corpus_name, "polymarket_historical_validation_2024plus",
                                    sport, path))
            continue
        rows.append({
            "hypothesis": h["id"], "corpus": corpus_name,
            "provenance": "polymarket_historical_validation_2024plus", "sport": sport,
            "n_games": band.get("n_games"), "status": "PRESENT",
            "verdict": band.get("venue_verdict"),
            "key_numbers": {
                "mean_market": band.get("mean_market"),
                "realized_rate": band.get("realized_rate"),
                "venue_gap": band.get("venue_gap"),
                "venue_gap_ci95": band.get("venue_gap_ci95"),
                "n_ticks": band.get("n_ticks"),
            },
            "caveats": [
                "independent historical validation corpus (2024+ alternate-slug "
                "family) -- never pooled with the 2023 dailies corpus, the "
                "forward gate, or the other sport",
                doc.get("note", "")[:200],
            ],
        })
    return rows


def h1_all_calibrated_outside_thin_pm2023(rows: List[Dict[str, Any]]) -> bool:
    """True iff every PRESENT H1 row in an independent historical VALIDATION
    corpus, other than the original thin PM-MLB-2023 pocket (n=14), reads
    CALIBRATED. Read-only check over rows already built; computes no new
    statistic, just inspects verdict strings already copied from artifacts."""
    n_checked = 0
    for r in rows:
        if r["hypothesis"] != "H1_longshot_underpriced" or r["status"] != "PRESENT":
            continue
        if r["corpus"] not in HISTORICAL_VALIDATION_CORPORA or r["corpus"] == "polymarket_2023":
            continue  # not a historical validation corpus, or the known thin pocket
        n_checked += 1
        if r["verdict"] != "CALIBRATED":
            return False
    return n_checked > 0


__all__ = [
    "rows_polymarket_2024plus", "h1_all_calibrated_outside_thin_pm2023",
    "HISTORICAL_VALIDATION_CORPORA",
]
