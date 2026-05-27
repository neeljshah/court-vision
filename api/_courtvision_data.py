"""_courtvision_data.py — CSV loaders + bet grader + healthz + middleware.

Extracted from courtvision_router.py to keep the router file under 300 LOC.
Module surface is intentionally narrow: import these into the router only.
"""
from __future__ import annotations

import csv
import hashlib
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.prediction.betting_edge import BettingEdge
from api._team_colors import primary as _team_primary_color

_BETTING = BettingEdge()


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bet_id(date: str, player_id: str, stat: str, side: str, line: float) -> str:
    raw = f"{date}|{player_id}|{stat}|{side}|{line:.2f}"
    h = hashlib.sha1(raw.encode()).hexdigest()[:10]
    return f"{date}_{player_id}_{stat.upper()}_{side}_{line:g}_{h}"


def stars_available(injury_status: str) -> bool:
    bad = {"OUT", "DOUBTFUL", "NOT WITH TEAM", "QUESTIONABLE-EXCLUDED"}
    return (injury_status or "").strip().upper() not in bad


def load_slate_csv(path: Path, stats: tuple[str, ...]) -> dict[tuple[str, str], dict]:
    """Pivot long-format slate CSV → {(player_id, stat): row_with_q50}."""
    rows: dict[tuple[str, str], dict] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            stat = (r.get("stat") or "").lower()
            if stat not in stats:
                continue
            pid = str(r.get("player_id") or "").strip()
            if not pid:
                continue
            try:
                pred = float(r.get("pred") or "nan")
            except ValueError:
                continue
            if pred != pred:
                continue
            base = rows.setdefault((pid, stat), {
                "player_id": pid, "player_name": r.get("player") or "",
                "team": r.get("team") or "", "opp": r.get("opp") or "",
                "venue": (r.get("venue") or "").lower() or "home",
                "game_id": r.get("game_id") or "", "date": r.get("date") or "",
                "injury_status": r.get("injury_status") or "",
            })
            base["q50"] = pred
            base["stat"] = stat
    return rows


def load_lines_csv(path: Path) -> list[dict]:
    """Return one row per (player, stat, line) with grouped book quotes.

    Multiple CSV rows for the same prop (different books) are merged into
    `books: [{book, over_odds, under_odds}, ...]`. Different lines for the
    same (player, stat) are kept as separate output rows (alt-line ladder).
    """
    grouped: dict[tuple[str, str, float], dict] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                line = float(r.get("line") or "nan")
            except ValueError:
                continue
            if line != line:
                continue
            player = (r.get("player") or "").strip()
            stat = (r.get("stat") or "").strip().lower()
            key = (player.lower(), stat, round(line, 2))
            book = (r.get("book") or "").strip() or "Consensus"
            over_odds = int(r.get("over_odds") or -110)
            under_odds = int(r.get("under_odds") or -110)
            if key not in grouped:
                grouped[key] = {
                    "player": player, "stat": stat, "line": line,
                    "opp": (r.get("opp") or "").strip().upper(),
                    "venue": (r.get("venue") or "").strip().lower(),
                    "books": [],
                }
            grouped[key]["books"].append({
                "book": book, "over_odds": over_odds, "under_odds": under_odds,
            })
    return list(grouped.values())


def grade_bet(slate_row: dict, line_row: dict,
              stat_sigma: dict[str, float], bankroll: float) -> dict:
    """Combine a slate row (q50) and a grouped line row -> graded Bet dict.

    `line_row` must have a `books` list (see load_lines_csv). The graded Bet
    picks the most favorable book for the model-chosen side and exposes the
    full per-book ladder under `all_books`.
    """
    stat = slate_row["stat"]
    sigma = stat_sigma[stat]
    q50 = float(slate_row["q50"])
    line = float(line_row["line"])
    side = "OVER" if q50 >= line else "UNDER"
    p_over = 1.0 - normal_cdf((line - q50) / sigma)
    model_prob = p_over if side == "OVER" else 1.0 - p_over

    books = line_row.get("books") or [{
        "book": "Consensus",
        "over_odds": line_row.get("over_odds", -110),
        "under_odds": line_row.get("under_odds", -110),
    }]
    # "Best" book = the one paying most for the chosen side. Higher American
    # odds (more positive / less negative) = better for the bettor.
    side_key = "over_odds" if side == "OVER" else "under_odds"
    best = max(books, key=lambda b: int(b[side_key]))
    odds = int(best[side_key])
    all_books = [{"book": b["book"], "price": int(b[side_key])} for b in books]
    all_books.sort(key=lambda r: -r["price"])

    ev = _BETTING.evaluate(model_prob, odds, bankroll=bankroll)
    edge_units = q50 - line
    market_prob = float(ev["implied_prob"])
    payout = float(odds) if odds > 0 else (10000.0 / abs(odds))
    ev_pct = model_prob * payout - (1.0 - model_prob) * 100.0
    kelly_dollars = float(ev.get("kelly_size") or 0.0)
    kelly_pct = (kelly_dollars / bankroll) * 100.0 if bankroll else 0.0
    narrative = (
        f"{slate_row['player_name']} projects to {q50:.1f} {stat.upper()} "
        f"vs {slate_row['opp']}; model edges line {line:g} by {edge_units:+.2f}."
    )
    return {
        "bet_id": bet_id(slate_row["date"], slate_row["player_id"], stat, side, line),
        "game_id": slate_row["game_id"], "player_id": slate_row["player_id"],
        "player_name": slate_row["player_name"], "team": slate_row["team"],
        "opp": slate_row["opp"], "venue": slate_row["venue"],
        "prop_stat": stat.upper(), "side": side, "line": line,
        "q50": round(q50, 3), "edge_units": round(edge_units, 3),
        "model_prob": round(float(model_prob), 4),
        "market_prob": round(market_prob, 4),
        "ev_pct": round(ev_pct, 2), "kelly_pct": round(kelly_pct, 3),
        "kelly_stake_dollars": round(kelly_dollars, 2),
        "last_5_median": None, "last_10_median": None, "season_median": None,
        "opponent_def_rating_split": None, "minutes_proj": None, "pace_proj": None,
        "stars_available_flag": stars_available(slate_row.get("injury_status", "")),
        "top_features": [], "narrative_text": narrative,
        "best_book": best["book"], "best_price": odds,
        "all_books": all_books, "spark_last5": [],
        "team_color": _team_primary_color(slate_row["team"]),
        "opp_color": _team_primary_color(slate_row["opp"]),
    }


def share_text(slate: dict, shown: list[dict]) -> str:
    """Plain-text summary for /share copy-to-clipboard."""
    out = [f"🏀 CourtVision picks · {slate['date']}",
           f"{len(shown)} model-graded NBA prop bets, ranked by EV", ""]
    for i, b in enumerate(shown, start=1):
        s = "o" if b["side"] == "OVER" else "u"
        ev = b.get("ev_pct"); ev_s = f"EV {ev:+.1f}%" if ev is not None else "EV pending"
        v = "@" if b["venue"] == "away" else "vs"
        out.append(f"{i}. {b['player_name']} {b['prop_stat']} {s}{b['line']:g} "
                   f"({b['team']} {v} {b['opp']}) — {ev_s}")
    out += ["", "not financial advice · courtvision"]
    return "\n".join(out)


def plus_ev_rows(slate: dict, min_ev_pct: float) -> list[dict]:
    """Expand graded bets into one row per (bet, book) above min_ev_pct."""
    out: list[dict] = []
    for bet in slate.get("bets", []):
        if bet.get("model_prob") is None:
            continue
        model_prob = float(bet["model_prob"])
        for entry in bet.get("all_books") or []:
            odds = int(entry["price"])
            payout = float(odds) if odds > 0 else (10000.0 / abs(odds))
            ev = model_prob * payout - (1.0 - model_prob) * 100.0
            if ev < min_ev_pct:
                continue
            out.append({
                "bet_id": bet["bet_id"], "player_name": bet["player_name"],
                "team": bet["team"], "opp": bet["opp"],
                "prop_stat": bet["prop_stat"], "side": bet["side"],
                "line": bet["line"], "q50": bet["q50"],
                "book": entry["book"], "price": odds,
                "ev_pct": round(ev, 2), "model_prob": model_prob,
            })
    out.sort(key=lambda r: -r["ev_pct"])
    return out


def healthz_payload(root: Path, latest_slate_date: Optional[str]) -> dict:
    """Readiness check: DB / orchestrator heartbeat / model freshness / redis."""
    out: dict = {"status": "ok", "checks": {}}
    checks = out["checks"]

    db = root / "data" / "nba_ai.db"
    checks["db_exists"] = db.exists()
    if db.exists():
        checks["db_mtime"] = datetime.fromtimestamp(
            db.stat().st_mtime, tz=timezone.utc).isoformat()

    heartbeat = root / "data" / "live" / "orchestrator_heartbeat.json"
    if heartbeat.exists():
        try:
            age_min = (time.time() - heartbeat.stat().st_mtime) / 60.0
            checks["orchestrator_age_min"] = round(age_min, 1)
            checks["orchestrator_stale"] = age_min > 5.0
        except OSError:
            checks["orchestrator_stale"] = True
    else:
        checks["orchestrator_stale"] = None

    # Cap the glob to 50 files so /healthz stays cheap even with huge model dirs.
    latest = 0.0
    for i, p in enumerate((root / "data" / "models").glob("*.json")):
        if i >= 50:
            break
        try:
            latest = max(latest, p.stat().st_mtime)
        except OSError:
            pass
    if latest:
        checks["last_model_artifact_age_days"] = round(
            (time.time() - latest) / 86400.0, 1)

    checks["latest_slate_date"] = latest_slate_date

    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis  # type: ignore
            checks["redis_ping"] = bool(
                redis.from_url(redis_url, socket_connect_timeout=1.0).ping()
            )
        except Exception as exc:
            checks["redis_ping"] = False
            checks["redis_error"] = str(exc)[:80]
    else:
        checks["redis_configured"] = False

    checks["courtvision_routes"] = [
        "/tonight", "/parlays", "/share/{slug}", "/plus_ev", "/live",
        "/api/slate", "/api/parlays", "/api/bet/{bet_id}",
        "/api/plus_ev", "/api/auto_parlay", "/sse/live_edges",
        "/share/{slug}/qr.svg", "/healthz",
    ]
    # Diagnostic: are the data files + templates dir actually on disk?
    templates_dir = root / "api" / "templates"
    checks["templates_dir_exists"] = templates_dir.exists()
    checks["templates_count"] = (
        sum(1 for _ in templates_dir.glob("*.html")) if templates_dir.exists() else 0
    )
    qstats = root / "data" / "player_quarter_stats.parquet"
    checks["player_quarter_stats_exists"] = qstats.exists()
    pred_dir = root / "data" / "predictions"
    checks["predictions_count"] = (
        sum(1 for _ in pred_dir.glob("slate_*.csv")) if pred_dir.exists() else 0
    )
    return out


def slate_no_lines(slate_rows: dict[tuple[str, str], dict],
                   stats: tuple[str, ...], top_n: int) -> list[dict]:
    """When no lines CSV exists, surface top-N q50 props as placeholder bets."""
    flat = sorted(slate_rows.values(), key=lambda r: float(r.get("q50") or 0.0), reverse=True)
    out = []
    for r in flat[:top_n]:
        stat = r["stat"]
        out.append({
            "bet_id": bet_id(r["date"], r["player_id"], stat, "OVER", 0.0),
            "game_id": r["game_id"], "player_id": r["player_id"],
            "player_name": r["player_name"], "team": r["team"], "opp": r["opp"],
            "venue": r["venue"], "prop_stat": stat.upper(), "side": "OVER",
            "line": 0.0, "q50": round(float(r["q50"]), 3),
            "edge_units": 0.0, "model_prob": None, "market_prob": None,
            "ev_pct": None, "kelly_pct": None, "kelly_stake_dollars": None,
            "last_5_median": None, "last_10_median": None, "season_median": None,
            "opponent_def_rating_split": None, "minutes_proj": None, "pace_proj": None,
            "stars_available_flag": stars_available(r.get("injury_status", "")),
            "top_features": [],
            "narrative_text": f"{r['player_name']} projects to {float(r['q50']):.1f} {stat.upper()} vs {r['opp']}. Drop a lines CSV to grade EV.",
            "best_book": None, "best_price": None, "all_books": [], "spark_last5": [],
            "team_color": _team_primary_color(r["team"]),
            "opp_color": _team_primary_color(r["opp"]),
        })
    return out
