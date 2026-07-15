"""calibration.json room: per-sport Brier/ECE scoreboard + CRPS-vs-market
verdicts + (if present) market-comparison scoreboards. Stdlib only.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from scripts.platformkit.showcase.common import FRONTEND, REPO, read_json, receipt, unavailable

CAL_SCOREBOARD = FRONTEND / "ops" / "calibration_scoreboard_latest.json"
CRPS_DIR = REPO / "scripts" / "platformkit" / "benchmarks" / "crps_market"
CRPS_PREGAME = CRPS_DIR / "last_run_mlb.json"
CRPS_INGAME = CRPS_DIR / "last_run_ingame_mlb.json"
BEAT_THE_LINE = FRONTEND / "ops" / "beat_the_line.json"
AFTER_COST = FRONTEND / "ops" / "after_cost_scoreboard.json"

_BANNED = ("roi", "bankroll", "pnl", "profit", "edge_pct")


def _has_banned(text: str) -> bool:
    low = text.lower()
    return any(tok in low for tok in _BANNED)


def _scrub(obj: Any) -> Any:
    """Drop any dict key/value pair whose key or stringified value contains
    a banned token. Never fabricates -- only omits."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and _has_banned(k):
                continue
            if isinstance(v, str) and _has_banned(v):
                continue
            out[k] = _scrub(v)
        return out
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


def _per_sport_rows(asof: str) -> list[dict]:
    data = read_json(CAL_SCOREBOARD)
    if not data:
        return []
    honesty_note = data.get("honesty_note", "")
    board = data.get("calibration_scoreboard", {})
    rows = []
    for row in board.get("per_sport", []):
        out = dict(row)
        out["framing"] = honesty_note
        out["label"] = "MEASURED"
        out["receipt"] = receipt(
            claim=f"{row.get('sport')} calibration: Brier {row.get('baseline_brier')} -> "
                  f"{row.get('improved_brier')} ({row.get('method')})",
            value=row.get("improved_brier"), label="MEASURED",
            artifact=CAL_SCOREBOARD, asof=asof)
        rows.append(out)
    return rows


def _crps_pregame(asof: str) -> dict | None:
    data = read_json(CRPS_PREGAME)
    if not data:
        return None
    out = dict(data)
    out["label"] = data.get("verdict", "UNKNOWN")
    out["receipt"] = receipt(
        claim="MLB pregame total_runs CRPS vs market (paired delta, no dollar edge)",
        value=data.get("paired_delta_mean"), label=out["label"],
        artifact=CRPS_PREGAME, asof=asof)
    return out


def _crps_ingame(asof: str) -> dict | None:
    data = read_json(CRPS_INGAME)
    if not data:
        return None
    checkpoints = data.get("checkpoints", {})
    verdicts = {cp.get("verdict") for cp in checkpoints.values()}
    label = verdicts.pop() if len(verdicts) == 1 else "MIXED"
    out = {k: v for k, v in data.items() if k != "checkpoints"}
    out["checkpoints"] = checkpoints
    out["label"] = label
    out["receipt"] = receipt(
        claim="MLB in-game CRPS vs market across ladder checkpoints (sharpness only)",
        value=len(checkpoints), label=label, artifact=CRPS_INGAME, asof=asof)
    return out


def _market_comparison(asof: str) -> dict:
    out: dict[str, Any] = {}
    beat = read_json(BEAT_THE_LINE)
    if beat:
        out["beat_the_line"] = _scrub(beat)
        out["beat_the_line_receipt"] = receipt(
            claim="Realized vs close-implied win rate by channel (excess win rate, not $ ROI)",
            value=None, label="MEASURED", artifact=BEAT_THE_LINE, asof=asof)
    after_cost = read_json(AFTER_COST)
    if after_cost:
        out["after_cost_scoreboard"] = _scrub(after_cost)
        out["after_cost_scoreboard_receipt"] = receipt(
            claim="After-cost unit scoreboard by channel", value=None,
            label="MEASURED", artifact=AFTER_COST, asof=asof)
    return out


def build() -> dict:
    per_sport = _per_sport_rows(date.today().isoformat())
    asof = date.today().isoformat()
    if not per_sport:
        return unavailable(f"missing or unreadable {CAL_SCOREBOARD}")

    result: dict[str, Any] = {"per_sport": per_sport, "reliability_bins": None,
                               "reliability_bins_note": "bins: v2"}

    crps: dict[str, Any] = {}
    pregame = _crps_pregame(asof)
    if pregame is not None:
        crps["pregame_mlb"] = pregame
    ingame = _crps_ingame(asof)
    if ingame is not None:
        crps["ingame_mlb"] = ingame
    result["crps"] = crps if crps else None

    market_comparison = _market_comparison(asof)
    result["market_comparison"] = market_comparison if market_comparison else None

    return result
