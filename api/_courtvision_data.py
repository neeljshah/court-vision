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
            # Read raw q10/q90 when present — used by grade_bet when CV_ROW_SIGMA=1.
            for _qcol in ("q10", "q90"):
                _raw = (r.get(_qcol) or "").strip()
                if _raw:
                    try:
                        base[_qcol] = float(_raw)
                    except ValueError:
                        pass
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
    sigma = stat_sigma[stat]  # flat default; always used when flag is OFF
    q50 = float(slate_row["q50"])
    # EX-1: per-row heteroscedastic sigma for REB, flag-gated (default OFF).
    # When CV_ROW_SIGMA=1 and the slate row carries monotone q10/q90, compute
    # sigma via the same production calibration path as _model_hit_prob in
    # compare_to_lines.py: apply_qcal -> (cq90 - cq10) / 2.5631.
    # EXCLUDED: PTS (no benefit), FG3M (unreliable reconstruction), AST (needs
    # separate re-validation under asymmetric sigma — do NOT enable here).
    if os.environ.get("CV_ROW_SIGMA", "0") == "1" and stat == "reb":
        _q10 = slate_row.get("q10")
        _q90 = slate_row.get("q90")
        if (_q10 is not None and _q90 is not None
                and float(_q10) <= q50 <= float(_q90)):
            from src.prediction.quantile_calibration import apply as _apply_qcal  # noqa: PLC0415
            _cq10, _cq90 = _apply_qcal(stat, float(_q10), q50, float(_q90))
            _rs = (_cq90 - _cq10) / 2.5631
            if _rs > 1e-6:
                sigma = _rs
    # CV_QUANTILE_CAL=1: apply split-conformal (CQR) calibration for all stats
    # except REB when CV_ROW_SIGMA is also ON (REB already calibrated above via
    # apply_qcal; don't double-calibrate). Flag OFF: no change to sigma.
    elif os.environ.get("CV_QUANTILE_CAL", "0") == "1":
        _q10 = slate_row.get("q10")
        _q90 = slate_row.get("q90")
        if (_q10 is not None and _q90 is not None):
            from src.prediction.quantile_calibration import apply_conformal as _apply_cfm  # noqa: PLC0415
            _cq10, _cq90 = _apply_cfm(stat, float(_q10), q50, float(_q90))
            _rs = (_cq90 - _cq10) / 2.5631
            if _rs > 1e-6:
                sigma = _rs
    line = float(line_row["line"])
    side = "OVER" if q50 >= line else "UNDER"
    p_over = 1.0 - normal_cdf((line - q50) / sigma)
    model_prob = p_over if side == "OVER" else 1.0 - p_over

    books = line_row.get("books") or [{
        "book": "Consensus",
        "over_odds": line_row.get("over_odds", -110),
        "under_odds": line_row.get("under_odds", -110),
    }]
    # Drop books we don't trust on price (Bovada posts late and stays wide).
    _EXCL = {"bov", "bovada"}
    books = [b for b in books if (b.get("book") or "").strip().lower() not in _EXCL] or books
    # "Best" book = the one paying most for the chosen side. Higher American
    # odds (more positive / less negative) = better for the bettor.
    side_key = "over_odds" if side == "OVER" else "under_odds"
    # Exclude glitch/invalid American odds (|odds| < 100, e.g. a scraped 0) from
    # best-price selection: a 0 would beat every minus-money book in max() and then
    # crash the payout division below (10000/abs(0)). Fall back to all books only if
    # none are valid (the payout guard then treats invalid odds as even-money).
    _valid_books = [b for b in books if abs(int(b.get(side_key) or 0)) >= 100]
    best = max(_valid_books or books, key=lambda b: int(b[side_key]))
    odds = int(best[side_key])
    all_books = [{"book": b["book"], "price": int(b[side_key])} for b in books]
    all_books.sort(key=lambda r: -r["price"])
    # Persist the FULL per-book over+under ladder so the live regrade can
    # reselect best_book/best_price when the model's side flips mid-game.
    # Without this, side-flip falls back to a fake "DraftKings -110" because
    # we lose the other side's prices.
    _books_full = [{
        "book": b["book"],
        "over_odds": int(b["over_odds"]),
        "under_odds": int(b["under_odds"]),
        "captured_at": b.get("captured_at") or "",
    } for b in books]

    # Freshness: age of the most recently captured quote across all books.
    # Gracefully defaults to None when no captured_at timestamps are present.
    _now_ts = time.time()
    _ages: list[float] = []
    for _b in _books_full:
        _ts = (_b.get("captured_at") or "").strip()
        if not _ts:
            continue
        try:
            _dt = datetime.fromisoformat(_ts.replace("Z", "+00:00"))
            _ages.append((_now_ts - _dt.timestamp()) / 60.0)
        except (ValueError, TypeError):
            pass
    freshest_book_age_min: float | None = round(min(_ages), 1) if _ages else None

    ev = _BETTING.evaluate(model_prob, odds, bankroll=bankroll)
    edge_units = q50 - line
    market_prob = float(ev["implied_prob"])
    # Guard against invalid American odds (|odds| < 100, e.g. a scraped 0): never
    # divide by abs(<100). Treat invalid odds as even-money (+100) rather than 500.
    payout = (float(odds) if odds >= 100
              else (10000.0 / abs(odds)) if odds <= -100
              else 100.0)
    ev_pct = model_prob * payout - (1.0 - model_prob) * 100.0
    kelly_dollars = float(ev.get("kelly_size") or 0.0)
    kelly_pct = (kelly_dollars / bankroll) * 100.0 if bankroll else 0.0
    # Plain-English narrative for the bet card. Built in three parts so any
    # reader can scan it: (1) the pick, (2) why, (3) the practical action.
    _STAT_FULL = {"pts": "points", "reb": "rebounds", "ast": "assists",
                  "fg3m": "three-pointers made", "stl": "steals",
                  "blk": "blocks", "tov": "turnovers"}
    stat_word = _STAT_FULL.get(stat, stat.upper())
    side_word = "under" if side == "UNDER" else "over"
    arrow = "below" if side == "UNDER" else "above"
    venue_phrase = "away at" if slate_row.get("venue") == "away" else "vs"
    confidence = "very high" if model_prob >= 0.80 else (
                 "high" if model_prob >= 0.70 else (
                 "moderate" if model_prob >= 0.60 else "slight"))
    price_phrase = f"+{odds}" if odds > 0 else str(odds)
    edge_abs = abs(edge_units)
    narrative = (
        f"Pick: bet {side_word} {line:g} {stat_word} for {slate_row['player_name']} "
        f"({slate_row['team']} {venue_phrase} {slate_row['opp']}). "
        f"Our model projects {q50:.1f} {stat_word}, which is {edge_abs:.2f} {arrow} the "
        f"sportsbook's {line:g} line. The model gives this a {model_prob*100:.0f}% chance to hit "
        f"({confidence} confidence). "
        f"Best price: {best['book']} at {price_phrase} — the market's implied probability there "
        f"is {market_prob*100:.0f}%, so the model sees a {(model_prob - market_prob)*100:+.1f}-point edge."
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
        "all_books": all_books, "_books_full": _books_full, "spark_last5": [],
        "freshest_book_age_min": freshest_book_age_min,
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
            # Guard against invalid American odds (|odds| < 100, e.g. a scraped 0):
            # never divide by abs(<100); treat invalid odds as even-money (+100).
            payout = (float(odds) if odds >= 100
                      else (10000.0 / abs(odds)) if odds <= -100
                      else 100.0)
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
        "/odds", "/arbs", "/api/docs",
        "/api/slate", "/api/parlays", "/api/bet/{bet_id}",
        "/api/plus_ev", "/api/auto_parlay", "/sse/live_edges",
        "/api/odds", "/api/odds/{date}.json", "/api/odds/{date}.csv",
        "/api/odds/best/{date}.json", "/api/odds/spread/{date}.json",
        "/api/odds/moves/{date}.json", "/api/odds/freshness/{date}",
        "/api/odds/history/{player}/{stat}",
        "/share/{slug}/qr.svg", "/healthz",
    ]
    # Scraper heartbeats: which books wrote a CSV today and how recent?
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    scrapers: dict[str, dict] = {}
    for book in ("pin", "bov", "fd", "dk", "mgm", "caesars", "pointsbet"):
        p = root / "data" / "lines" / f"{today}_{book}.csv"
        if p.exists():
            try:
                age_sec = time.time() - p.stat().st_mtime
                scrapers[book] = {"present": True, "age_seconds": round(age_sec, 1)}
            except OSError:
                scrapers[book] = {"present": True, "age_seconds": None}
    checks["scrapers_today"] = scrapers
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

    # Team-stats observability: did the JSON file ship and is the lookup working?
    checks["team_stats_loaded"] = (
        (root / "data" / "nba" / "team_stats_2025-26.json").exists()
        or (root / "data" / "nba" / "team_stats_2024-25.json").exists()
    )
    try:
        from api.courtvision_router import _team_stats_for as _tsf
        _okc = _tsf("OKC")
        checks["pace_lookup_works"] = float(_okc.get("pace", 0.0)) > 95.0
    except Exception as _exc:
        checks["pace_lookup_works"] = False
        checks["pace_lookup_error"] = str(_exc)[:120]

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
