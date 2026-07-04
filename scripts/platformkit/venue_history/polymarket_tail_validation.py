"""scripts.platformkit.venue_history.polymarket_tail_validation -- LANE 1 STEP 3:
independent multi-month tail-band validation on the Polymarket historical corpus.

Reuses the SAME band math as scripts/platformkit/ingame/ingame_tail_scan.py
(_band_stats: game-clustered bootstrap CI over venue price vs realized outcome)
via import -- no reimplementation, no drift between the forward-gate math and
this validation math.

THIS IS NOT THE FORWARD GATE. ingame_tail_gate.py pre-registers H1/H2 on the
LIVE captured in-play corpus (data/cache/ingame_grade/) and is the only file
that may report a forward CONFIRMED/REJECTED verdict for the acting hypothesis.
This module runs the SAME two bands against the PHYSICALLY SEPARATE Polymarket
historical corpus (data/venue_history/polymarket/) and writes its own artifact
labeled provenance=polymarket_historical_validation. The two are NEVER pooled;
this is the first independent (different venue, different season, different
capture path) look at whether the venue-bias hypothesis class replicates.

_band_stats also computes a model-vs-market Brier delta; we have no live model
price for 2023 historical Polymarket ticks, so model=market is passed through
(a neutral stand-in) and delta_brier/model_verdict are DROPPED from this
artifact as not applicable -- only venue_gap/venue_verdict (venue price vs
realized outcome) are reported, which is the actual quantity under test here.

Per-md5-half split: same convention as ingame_tail_scan (deterministic
game-id hash split) for a crude internal replication check within this one
corpus, NOT a train/test split of anything.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no data/registry write; no
flag flip; edge_claimed always False.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/venue_history/test_polymarket_tail_validation.py -q
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.platformkit.ingame.ingame_tail_scan import _band_stats  # reuse, no drift

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CORPUS_DIR = _REPO_ROOT / "data" / "venue_history" / "polymarket"
DEFAULT_OUT = _REPO_ROOT / "data" / "venue_history" / "polymarket" / "mlb_tail_validation.json"

# Pre-registered bands under test (ingame_tail_bias_prereg_2026_07_03): H1
# longshot-underpriced, H2 mid-fav-overpriced. Chosen on the ORIGINAL live
# discovery sample, not this corpus -- reused here verbatim, no re-picking.
H1_BAND = "[0.10,0.20)"
H2_BAND = "[0.65,0.80)"
BAND_EDGES: List[float] = [0.0, 0.10, 0.20, 0.35, 0.50, 0.65, 0.80, 0.90, 1.0]
MIN_GAMES_BAND = 8


def _band_label(p: float) -> str:
    for lo, hi in zip(BAND_EDGES, BAND_EDGES[1:]):
        if lo <= p < hi or (hi == 1.0 and p == 1.0):
            close = "]" if hi == 1.0 else ")"
            return "[%.2f,%.2f%s" % (lo, hi, close)
    return "UNK"


def _md5_half(game_id: str) -> int:
    """Deterministic 2-way split of a game id -- same convention as other
    md5-half splits in this codebase (crude internal replication check)."""
    return int(hashlib.md5(game_id.encode("utf-8")).hexdigest(), 16) % 2


def _load_corpus_rows(corpus_dir: Path, sport: str) -> List[Tuple[str, float, int]]:
    """Read every *.jsonl game-day file under corpus_dir/sport and return
    [(game_id, price_home, outcome_home_win)] for every tick with a resolved
    outcome. Unresolved games (outcome_home_win is None) are excluded, never
    guessed. game_id = event_slug + market_slug (unique per game)."""
    base = Path(corpus_dir) / sport.lower()
    rows: List[Tuple[str, float, int]] = []
    if not base.is_dir():
        return rows
    files = sorted(f for f in base.glob("*.jsonl") if not f.name.startswith("_"))
    for f in files:
        try:
            with f.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    outcome = d.get("outcome_home_win")
                    if outcome not in (0, 1):
                        continue
                    game_id = "%s|%s" % (d.get("event_slug", ""), d.get("market_slug", ""))
                    for pt in d.get("prices") or []:
                        p = pt.get("prob_home")
                        if not isinstance(p, (int, float)) or not (0.0 < float(p) < 1.0):
                            continue
                        rows.append((game_id, float(p), int(outcome)))
        except OSError:
            continue
    return rows


def _venue_only_stats(rows: List[Tuple[str, float, float, int]]) -> Dict[str, Any]:
    """_band_stats output filtered to the venue-price fields only (drop the
    model/delta_brier fields, which are not meaningful here -- see module doc)."""
    full = _band_stats(rows, iters=2000, seed=13)
    return {
        "n_ticks": full["n_ticks"], "n_games": full["n_games"],
        "mean_market": full["mean_market"], "realized_rate": full["realized_rate"],
        "venue_gap": full["venue_gap"], "venue_gap_ci95": full.get("venue_gap_ci95"),
        "venue_verdict": full["venue_verdict"],
    }


def validate(sport: str = "mlb", corpus_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Run the H1/H2 band validation against the Polymarket historical corpus.
    Returns the full result dict (also written to disk by write_artifact)."""
    all_rows = _load_corpus_rows(corpus_dir or DEFAULT_CORPUS_DIR, sport)
    n_games_total = len({r[0] for r in all_rows})
    bands: Dict[str, Any] = {}
    for label in (H1_BAND, H2_BAND):
        band_rows_all = [(gid, p, p, o) for gid, p, o in all_rows if _band_label(p) == label]
        halves: Dict[str, Any] = {}
        for half_name, half_idx in (("half_0", 0), ("half_1", 1)):
            half_rows = [r for r in band_rows_all if _md5_half(r[0]) == half_idx]
            n_g = len({r[0] for r in half_rows})
            if n_g < MIN_GAMES_BAND:
                halves[half_name] = {
                    "n_ticks": len(half_rows), "n_games": n_g,
                    "venue_verdict": "INSUFFICIENT_DATA",
                }
            else:
                halves[half_name] = _venue_only_stats(half_rows)
        pooled = (_venue_only_stats(band_rows_all)
                  if len({r[0] for r in band_rows_all}) >= MIN_GAMES_BAND
                  else {"n_ticks": len(band_rows_all),
                        "n_games": len({r[0] for r in band_rows_all}),
                        "venue_verdict": "INSUFFICIENT_DATA"})
        bands[label] = {"pooled": pooled, "halves": halves}
    return {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "component": "m_polymarket_tail_validation",
        "provenance": "polymarket_historical_validation",
        "sport": sport, "venue": "polymarket",
        "note": ("independent multi-season historical validation of the H1/H2 "
                 "in-play tail-band venue-bias hypothesis (ingame_tail_bias_prereg_2026_07_03) "
                 "on a PHYSICALLY SEPARATE corpus; never pooled with the forward "
                 "pre-registered gate (ingame_tail_gate.py); model/delta_brier "
                 "not applicable here (no live model price for 2023 history)"),
        "n_games_total_corpus": n_games_total,
        "min_games_band": MIN_GAMES_BAND,
        "bands": bands, "edge_claimed": False,
    }


def write_artifact(result: Dict[str, Any], out_path: Optional[Path] = None) -> Path:
    p = Path(out_path) if out_path is not None else DEFAULT_OUT
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=1), encoding="utf-8")
    tmp.replace(p)
    return p


def main() -> None:
    result = validate()
    print("polymarket historical tail validation (%s): %d games in corpus" %
          (result["sport"], result["n_games_total_corpus"]))
    for label in (H1_BAND, H2_BAND):
        b = result["bands"][label]
        pooled = b["pooled"]
        print("  %-14s pooled n_games=%s verdict=%s" % (
            label, pooled.get("n_games"), pooled.get("venue_verdict")))
        for half_name, half in b["halves"].items():
            print("      %-8s n_games=%s verdict=%s" % (
                half_name, half.get("n_games"), half.get("venue_verdict")))
    path = write_artifact(result)
    print("artifact: %s" % path)
    print("NOTE: historical VALIDATION corpus only -- never pooled with the forward gate.")


if __name__ == "__main__":
    main()


__all__ = ["validate", "write_artifact", "H1_BAND", "H2_BAND", "MIN_GAMES_BAND"]
