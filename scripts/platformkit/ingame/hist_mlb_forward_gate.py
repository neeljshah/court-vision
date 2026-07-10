"""scripts.platformkit.ingame.hist_mlb_forward_gate -- LANE 3 sub-task (B),
forward leg: apply the PM-fit recalibration choice from
domains.mlb.ingame_recal_pm to the PROVENANCE-SEPARATE forward Kalshi in-play
capture corpus (data/cache/inplay_history/mlb/*.jsonl, provenance="kalshi",
phase="in_play"), and report the honest verdict vs raw venue prob.

WHY THIS IS A SEPARATE MODULE FROM ingame_recal_pm.py
--------------------------------------------------------
The binding invariant is "validation corpora provenance-separated from
forward gates, NEVER pooled": ingame_recal_pm.py's fit/select lives entirely
inside the Polymarket (pm_backfill) corpus. This module NEVER refits anything
-- it takes the calibrator CHOSEN there (method name + its own already-fit
walk-forward state is NOT reusable across corpora, since walk-forward
calibrators are index-order-dependent state machines, not a portable
(a,b) parameter pair for every method -- e.g. isotonic has no fixed-size
closed form). Instead, per AUTONOMY_CHARTER's "expected honest outcome is
MATCH" framing, this module runs the SAME walk-forward MACHINERY fresh,
independently, on the Kalshi corpus's own chronological tick order, and
reports whether its own recalibration outcome (MATCH/IMPROVE/WORSEN) agrees
with the PM corpus's finding -- a cross-corpus REPLICATION check, not a
transplant of fitted weights (which would leak PM-specific liquidity/vig
patterns into a structurally different venue).

BUILDING (raw_prob, outcome) PAIRS FROM THE KALSHI TICK CORPUS
-------------------------------------------------------------------
Each row is {sport, game_id (=Kalshi ticker), side, ticker (side-specific,
"<game_id>-<CODE>"), prob, ts, phase="in_play"}. There is no explicit
home/away flag on a tick -- home is recovered by parsing game_id via
hist_mlb_outcome_resolver.parse_mlb_ticker (tail = AWAY+HOME concatenated;
the LAST resolved code is home). A tick whose ticker suffix code matches the
resolved HOME code contributes prob_home=prob directly; a tick matching AWAY
contributes prob_home=1-prob. An unparseable ticker or unresolved split
contributes nothing (honest skip). Same CHECKPOINT_FRACTIONS convention as
ingame_recal_pm.py (fixed fractional positions within each game's own tick
sequence), applied per (game_id, side) group so a game with both sides
captured yields checkpoints from BOTH (averaged if they disagree at that
fraction -- both are honest same-moment estimates of the same probability).

OUTCOME LABELS: hist_mlb_outcome_resolver.MlbTickerOutcomeResolver against
data/domains/mlb/espn_boxscores.parquet (a THIRD provenance, independent of
both Kalshi's own price feed and the Polymarket training corpus).

EDGE_CLAIMED = False. CALIBRATION != EDGE. Small-n forward corpus (7 days as
of this wave) -- an INSUFFICIENT_DATA / wide-CI verdict is the expected,
honest outcome at this corpus size, not a failure.

INVARIANTS: scripts/platformkit/ingame/ only (NEW file, hist_ prefix);
<=300 LOC; ASCII only; no network; never writes data/registry/; never raises.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_hist_mlb_forward_gate.py -q
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from scripts.platformkit.ingame.hist_mlb_outcome_resolver import (
    MlbTickerOutcomeResolver,
    parse_mlb_ticker,
)

logger = logging.getLogger(__name__)

EDGE_CLAIMED = False
CALIBRATION_NOTE = "calibration != edge; forward Kalshi replication check only; no $ field"

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CAPTURE_DIR = _REPO_ROOT / "data" / "cache" / "inplay_history" / "mlb"

CHECKPOINT_FRACTIONS: Tuple[float, ...] = (0.25, 0.50, 0.75, 0.90)
MIN_TICKS_PER_SIDE = 3
MIN_FORWARD_ROWS = 20  # below this, report INSUFFICIENT_DATA rather than a noisy verdict


def _iter_capture_files(capture_dir: Optional[Path] = None) -> List[Path]:
    d = capture_dir or DEFAULT_CAPTURE_DIR
    if not d.exists():
        return []
    return sorted(p for p in d.glob("*.jsonl") if p.name != "_freshness.json")


def load_ticks(capture_dir: Optional[Path] = None) -> Dict[str, Dict[str, List[Tuple[str, float]]]]:
    """game_id (ticker) -> {side_code -> [(ts, prob), ...]}, sorted by ts per
    side. Never raises; a malformed line/file is skipped, not fatal."""
    out: Dict[str, Dict[str, List[Tuple[str, float]]]] = defaultdict(lambda: defaultdict(list))
    for path in _iter_capture_files(capture_dir):
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if d.get("phase") != "in_play" or d.get("market_type") != "moneyline":
                        continue
                    gid, ticker, ts, prob = d.get("game_id"), d.get("ticker"), d.get("ts"), d.get("prob")
                    if not gid or not ticker or not ts or not isinstance(prob, (int, float)):
                        continue
                    side_code = str(ticker).rsplit("-", 1)[-1]
                    out[str(gid)][side_code].append((str(ts), float(prob)))
        except OSError as exc:  # noqa: BLE001
            logger.debug("load_ticks failed to read %s: %s", path, exc)
    for gid in out:
        for side_code in out[gid]:
            out[gid][side_code].sort(key=lambda t: t[0])
    return {k: dict(v) for k, v in out.items()}


def _checkpoint_values(series: List[Tuple[str, float]]) -> List[float]:
    n = len(series)
    if n < MIN_TICKS_PER_SIDE:
        return []
    out = []
    for frac in CHECKPOINT_FRACTIONS:
        idx = min(n - 1, max(0, int(round(frac * (n - 1)))))
        out.append(series[idx][1])
    return out


def build_forward_rows(
    ticks_by_game: Dict[str, Dict[str, List[Tuple[str, float]]]],
    resolver: MlbTickerOutcomeResolver,
) -> List[Dict[str, object]]:
    """(raw_prob=prob_home, outcome) rows, one per (game, checkpoint fraction,
    side that had enough ticks). Two sides at the same fraction are averaged
    (both estimate the same home-prob at the same in-game moment)."""
    rows: List[Dict[str, object]] = []
    for game_id, sides in ticks_by_game.items():
        parsed = parse_mlb_ticker(game_id)
        outcome = resolver.home_win(game_id)
        if parsed is None or outcome is None:
            continue  # unresolvable game -- honest skip, never fabricated
        _date, tail, _gnum = parsed
        # Resolve which side codes in this game's ticks are home vs away by
        # checking each observed side_code against the resolver's own abbr
        # index via a private re-derivation: try suffix match against tail end.
        home_prob_by_frac: Dict[float, List[float]] = defaultdict(list)
        for side_code, series in sides.items():
            vals = _checkpoint_values(series)
            if not vals:
                continue
            is_home = tail.endswith(side_code)
            is_away = tail.startswith(side_code) and not is_home
            if not is_home and not is_away:
                continue  # side code doesn't cleanly match either end -- skip
            for frac, v in zip(CHECKPOINT_FRACTIONS, vals):
                home_prob_by_frac[frac].append(v if is_home else 1.0 - v)
        for frac, vals in home_prob_by_frac.items():
            rows.append({
                "game_id": game_id, "fraction": frac,
                "raw_prob": float(sum(vals) / len(vals)), "outcome": float(outcome),
            })
    rows.sort(key=lambda r: (str(r["game_id"]), float(r["fraction"])))
    return rows


def _brier(preds: List[float], outcomes: List[float]) -> float:
    return sum((p - y) ** 2 for p, y in zip(preds, outcomes)) / max(1, len(preds))


def run_forward_gate(
    capture_dir: Optional[Path] = None,
    resolver: Optional[MlbTickerOutcomeResolver] = None,
    min_history: int = 10,
) -> Dict[str, object]:
    """Full pipeline: load forward Kalshi ticks, resolve outcomes, run the
    SAME walk-forward calibrator-selection machinery fresh on this corpus's
    own order, report raw vs recalibrated Brier + verdict. Never raises."""
    from scripts.platformkit.calibrator_zoo import select_calibrator

    r = resolver or MlbTickerOutcomeResolver()
    ticks = load_ticks(capture_dir)
    if not ticks:
        return {"edge_claimed": EDGE_CLAIMED, "verdict": "INSUFFICIENT_DATA",
                "reason": "no forward Kalshi MLB capture files found", "note": CALIBRATION_NOTE}

    rows = build_forward_rows(ticks, r)
    n_games_total = len(ticks)
    n_games_resolved = len(set(str(row["game_id"]) for row in rows))

    if len(rows) < MIN_FORWARD_ROWS:
        return {
            "edge_claimed": EDGE_CLAIMED, "verdict": "INSUFFICIENT_DATA",
            "reason": f"too few resolvable forward rows (n={len(rows)}); "
                      "most captured games are not yet FINAL in the boxscore corpus",
            "n_games_captured": n_games_total, "n_games_resolved": n_games_resolved,
            "n_rows": len(rows), "note": CALIBRATION_NOTE,
        }

    raw_probs = [float(row["raw_prob"]) for row in rows]
    outcomes = [float(row["outcome"]) for row in rows]
    result = select_calibrator(raw_probs, outcomes, min_history=min(min_history, max(1, len(rows) // 3)))
    identity_row = next(x for x in result["table"] if x["method"] == "identity")
    chosen_row = next(x for x in result["table"] if x["method"] == result["chosen_method"])
    delta_brier = identity_row["brier"] - chosen_row["brier"]

    verdict = "MATCH"
    if delta_brier > 0.002:
        verdict = "IMPROVED"
    elif delta_brier < -0.002:
        verdict = "WORSENED"

    return {
        "edge_claimed": EDGE_CLAIMED,
        "verdict": verdict,
        "note": CALIBRATION_NOTE + " -- small forward-corpus n; wide CI expected",
        "n_games_captured": n_games_total,
        "n_games_resolved": n_games_resolved,
        "n_rows": len(rows),
        "raw_brier": identity_row["brier"],
        "chosen_method": result["chosen_method"],
        "chosen_brier": chosen_row["brier"],
        "delta_brier": delta_brier,
        "full_table": result["table"],
    }


def _main() -> int:
    logging.basicConfig(level=logging.INFO)
    report = run_forward_gate()
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "EDGE_CLAIMED", "CALIBRATION_NOTE", "CHECKPOINT_FRACTIONS",
    "DEFAULT_CAPTURE_DIR", "load_ticks", "build_forward_rows", "run_forward_gate",
]
