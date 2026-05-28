"""decision_engine.py — event-driven bet ranker for Live Engine v2.

Subscribes to:
  * projection.updated   — fresh per-(player, stat) projection
  * lines.refreshed      — fresh book lines on disk

On every event, recomputes the top-N bets across the slate:
  1. Join projection rows to book lines (per player + stat).
  2. Compute hit probability via normal-CDF around the projected_final.
  3. Compute EV per dollar using American odds payout.
  4. Run the 8-gate filter chain (see ``_GATES``).
  5. Compute Kelly stake (fractional, capped at 25%).
  6. Pick the top N by EV.
  7. Emit ``bet.recommended`` with tier (S/A/B), edge, EV%, Kelly,
     and a 1-line WHY string.

Tiers
-----
S   EV >= 8% and projection delta >= 1.0 stat units
A   EV >= 4%
B   EV >= 4% (calibrated 2026-05-27; was 1% — raised to drop low-ROI Tier C emissions)
"""
from __future__ import annotations

import asyncio
import csv
import logging
import math
import os
import time
from src.live.time_utils import slate_date
from typing import Any, Dict, List, Optional, Tuple

from src.live.event_bus import (
    EventBus,
    TOPIC_BET_RECOMMENDED,
    TOPIC_LINES_REFRESHED,
    TOPIC_PROJECTION_UPDATED,
    get_bus,
)

log = logging.getLogger("decision_engine")

PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")

# Per-stat residual standard deviation (game-final) used for hit-prob CDF.
# Calibrated against historical full-game variances (production MAE table).
_STAT_SIGMA = {
    "pts": 5.0,
    "reb": 2.2,
    "ast": 1.6,
    "fg3m": 1.1,
    "stl": 0.9,
    "blk": 0.6,
    "tov": 1.1,
}

# Tiers — keep this with the top-of-file docstring.
TIER_S_EV = 0.08
TIER_A_EV = 0.04
TIER_B_EV = 0.04  # pre-calibration: 0.01  (calibrated 2026-05-27 — see vault/Reports/filter_calibration_2026-05-27.md)

# Per-period emit floor (keyed by period string: "2"=endQ1, "3"=endQ2, "4"=endQ3).
# Calibrated 2026-05-27: earlier quarters need stricter floors because projections
# are noisier mid-game; Q3 bets are already high-quality at 0.04 floor.
# Rationale: ROI grid over 50-game backtest (90,846 rows) shows monotonic ROI
# improvement as floor rises; per-quarter values set to maximize ROI at N>=100.
_EMIT_FLOOR_BY_PERIOD: Dict[str, float] = {
    "2": 0.12,  # endQ1 — most noise, highest floor (ROI +35.7% vs +30.3% at 0.01)
    "3": 0.12,  # endQ2 — (ROI +58.4% vs +50.5% at 0.01)
    "4": 0.12,  # endQ3 — (ROI +74.6% vs +71.0% at 0.01)
    # pre-calibration: global 0.01 for all periods  (calibrated 2026-05-27)
}

# Per-period EV ceiling (drops phantom edges from extrapolated projections).
# Q3 ceiling raised to 0.90: late-game projections are stable and high-EV bets
# are legitimate edges (ceiling=0.90 n=8319 ROI=70.5% vs ceiling=0.50 n=4368 ROI=59.5%).
_EV_CEILING_BY_PERIOD: Dict[str, float] = {
    "2": 0.50,  # endQ1 — keep global ceiling (noisier projections)
    "3": 0.50,  # endQ2 — keep global ceiling
    "4": 0.90,  # endQ3 — late-game high-EV bets are legitimate
    # pre-calibration: global 0.50 for all periods  (calibrated 2026-05-27)
}

# Kelly cap (fraction-of-bankroll ceiling per single bet).
_KELLY_CAP = 0.25


# ── pure math helpers ───────────────────────────────────────────────────
def american_payout(odds: int) -> float:
    """$ profit on a $1 stake at the given American odds."""
    o = int(odds)
    if o > 0:
        return o / 100.0
    return 100.0 / abs(o)


def normal_cdf(z: float) -> float:
    """Φ(z) — standard normal CDF using erf."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def hit_probability(proj_final: float, line: float, side: str,
                    sigma: float) -> float:
    """P(stat > line) for OVER; P(stat < line) for UNDER. Normal approx.

    stat is modelled as N(proj_final, sigma); so
    P(stat > line) = Phi((proj_final - line)/sigma).
    """
    if sigma <= 0:
        return 1.0 if (side == "over" and proj_final > line) else 0.0
    z = (proj_final - line) / sigma
    p_over = normal_cdf(z)
    return p_over if side == "over" else (1.0 - p_over)


def ev_per_dollar(p_hit: float, odds: int) -> float:
    """Per-dollar EV = p*payout − (1−p). Positive = profitable."""
    return p_hit * american_payout(odds) - (1.0 - p_hit)


def kelly_fraction(p_hit: float, odds: int, *, cap: float = _KELLY_CAP) -> float:
    """Kelly bet fraction. Clamped to [0, cap]."""
    b = american_payout(odds)
    if b <= 0:
        return 0.0
    q = 1.0 - p_hit
    f = (b * p_hit - q) / b
    return max(0.0, min(cap, f))


# ── 8-gate filter chain ────────────────────────────────────────────────
def _float_or(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default

def _gate_player_present(rec, line):    return rec.get("projected_final") is not None
def _gate_projection_sane(rec, line):
    """Reject `projected_final == 0.0` for stats where 0 is the model's
    sentinel for 'no output'. Without this, every UNDER bet against a
    real line collapses to ~100% hit probability, producing nonsense
    EVs like +205% the moment the live engine returns a default.
    A bench player projected at 0.3 PTS still passes; only an exact 0
    (sentinel) is rejected. Per-stat thresholds tune sensitivity."""
    pf = _float_or(rec.get("projected_final"), default=-1.0)
    if pf < 0:
        return False
    sane_floor = {"pts": 0.05, "reb": 0.05, "ast": 0.05, "fg3m": 0.01,
                  "stl": 0.01, "blk": 0.01, "tov": 0.01, "pra": 0.10}
    return pf > sane_floor.get(rec.get("stat"), 0.0)
def _gate_line_present(rec, line):
    v = line.get("line")
    if v in (None, ""):
        return False
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False
def _gate_sigma_known(rec, line):        return rec["stat"] in _STAT_SIGMA
def _gate_odds_sane(rec, line):
    o = line.get("over_price") or line.get("under_price")
    try:
        ov = int(o or 0)
    except (TypeError, ValueError):
        return False
    return -300 <= ov <= 300
def _gate_min_edge(rec, line):
    """Sanity: skip if projection within 0.05*sigma of the line."""
    delta = abs(_float_or(rec.get("projected_final")) - _float_or(line.get("line")))
    sigma = _STAT_SIGMA.get(rec["stat"], 1.0)
    return delta >= 0.05 * sigma
def _gate_not_settled(rec, line):
    return _float_or(rec.get("current")) < _float_or(line.get("line")) + 50
def _gate_market_open(rec, line):        return (line.get("market_status") or "open").lower() != "closed"
def _gate_stat_supported(rec, line):     return rec["stat"] in {"pts", "reb", "ast", "fg3m",
                                                                "stl", "blk", "tov", "pra"}

_GATES = [
    ("player_present", _gate_player_present),
    ("projection_sane", _gate_projection_sane),
    ("line_present", _gate_line_present),
    ("sigma_known", _gate_sigma_known),
    ("odds_sane", _gate_odds_sane),
    ("stat_supported", _gate_stat_supported),
    ("market_open", _gate_market_open),
    ("not_settled", _gate_not_settled),
    ("min_edge", _gate_min_edge),
]


def _passes_gates(rec: Dict[str, Any], line: Dict[str, Any]) -> Tuple[bool, str]:
    for name, fn in _GATES:
        try:
            if not fn(rec, line):
                return False, name
        except Exception:
            return False, name
    return True, "ok"


# Three-book consensus: a line is "trusted" only when Pinnacle, Bovada, and
# FanDuel all quote the same (player, stat, line). Bovada-only listings are
# treated as untrusted (stale quote / soft-book typo, not a real edge).
_REQUIRED_CONSENSUS_BOOKS = {"pin", "bov", "fd"}


def _filter_three_book_consensus(
        lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return only lines whose line-value is also quoted by every required
    book in the input set. ``lines`` is the per-(player, stat) flat list of
    book offers from LineCache.find."""
    from collections import defaultdict
    books_per_value: Dict[float, set] = defaultdict(set)
    for ln in lines:
        try:
            lv = float(ln.get("line"))
        except (TypeError, ValueError):
            continue
        books_per_value[lv].add((ln.get("book") or "").strip().lower())
    trusted: List[Dict[str, Any]] = []
    for ln in lines:
        try:
            lv = float(ln.get("line"))
        except (TypeError, ValueError):
            continue
        if _REQUIRED_CONSENSUS_BOOKS.issubset(books_per_value.get(lv, set())):
            trusted.append(ln)
    return trusted


# ── line cache ──────────────────────────────────────────────────────────
class LineCache:
    """In-memory cache of today's book lines indexed by (player_id, stat).

    Reloads on `refresh()`. The decision engine calls refresh on
    `lines.refreshed` events.
    """

    def __init__(self, lines_dir: str = LINES_DIR) -> None:
        self.lines_dir = lines_dir
        # {(player_id, stat): [line_dict, ...]} — one entry per book.
        self._by_key: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        self._loaded_files: List[str] = []

    def refresh(self, date_str: Optional[str] = None) -> int:
        """Reload all CSVs in lines_dir matching today's date. Returns row count."""
        date_str = date_str or slate_date().isoformat()
        self._by_key.clear()
        self._loaded_files.clear()
        if not os.path.isdir(self.lines_dir):
            return 0
        total = 0
        for fname in os.listdir(self.lines_dir):
            if not fname.startswith(date_str):
                continue
            if not fname.endswith(".csv"):
                continue
            path = os.path.join(self.lines_dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    for row in csv.DictReader(fh):
                        pid = (row.get("player_id") or
                               (row.get("player_name") or "").strip().lower())
                        if not pid:
                            continue
                        stat = (row.get("stat") or "").strip().lower()
                        if not stat:
                            continue
                        self._by_key.setdefault((str(pid), stat), []).append(row)
                        total += 1
            except (OSError, ValueError) as exc:
                log.warning("LineCache could not read %s: %s", fname, exc)
            self._loaded_files.append(fname)
        return total

    def find(self, player_id: Any, player_name: str,
             stat: str) -> List[Dict[str, Any]]:
        stat = (stat or "").strip().lower()
        out: List[Dict[str, Any]] = []
        if player_id is not None:
            out.extend(self._by_key.get((str(player_id), stat), []))
        if not out and player_name:
            out.extend(self._by_key.get((player_name.lower(), stat), []))
        return out


# ── tiering ─────────────────────────────────────────────────────────────
def classify_tier(ev: float, delta_abs: float = 0.0) -> str:
    if ev >= TIER_S_EV and delta_abs >= 1.0:
        return "S"
    if ev >= TIER_A_EV:
        return "A"
    if ev >= TIER_B_EV:
        return "B"
    return "C"


# ── why string ──────────────────────────────────────────────────────────
def build_why(rec: Dict[str, Any], line: Dict[str, Any], side: str,
              p_hit: float, ev: float, kelly: float, tier: str) -> str:
    book = line.get("book", "?")
    odds = line.get(f"{side}_price", "?")
    return (
        f"{tier}: {rec.get('name', rec.get('player_id'))} "
        f"{rec['stat'].upper()} {side.upper()} {line.get('line')} "
        f"@ {book} {odds} | proj {rec['projected_final']:.1f} "
        f"(p={p_hit*100:.1f}%, EV={ev*100:+.1f}%, K={kelly*100:.1f}%)"
    )


# ── risk gate (final filter before emit) ────────────────────────────────
def _risk_filter(bets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply RiskConfig / RiskState gate to a ranked list of bet candidates.

    Returns only the bets that pass.  All rejects are logged at INFO level.
    Failures in the risk module are non-fatal — if risk_controls can't be
    imported the full bet list is returned unchanged so the engine keeps
    running.
    """
    try:
        from database.bet_db import BetDB  # noqa: PLC0415
        from src.prediction.risk_controls import (  # noqa: PLC0415
            RiskConfig, RiskState, can_place_bet, evaluate_risk, read_kill_switch,
        )
    except Exception as exc:
        log.debug("risk_controls import failed (non-fatal): %s", exc)
        return bets

    try:
        db       = BetDB()
        cfg      = RiskConfig()
        today    = time.strftime("%Y-%m-%d")
        today_s  = db.daily_summary(today)
        bankroll = db.current_bankroll()
        open_bets = db.list_bets(status="pending", limit=500)
        open_count = len(open_bets)
        dd       = db.drawdown_pct(30)
        ks_on, ks_reason = read_kill_switch()

        state = RiskState(
            bankroll=bankroll,
            daily_pnl=today_s.get("total_pnl", 0.0),
            daily_stake=today_s.get("total_stake", 0.0),
            open_bet_count=open_count,
            drawdown_30d_pct=dd,
            kill_switch_engaged=ks_on,
            kill_reason=ks_reason,
        )

        # Portfolio-level kill: if kill switch or hard cap hit → emit nothing.
        portfolio = evaluate_risk(state, cfg)
        if not portfolio["ok"]:
            log.info("[risk] portfolio blocked, emitting 0 bets: %s",
                     portfolio["blocked_reasons"][0] if portfolio["blocked_reasons"] else "unknown")
            return []

        # Per-bet filter.
        passed: List[Dict[str, Any]] = []
        for bet in bets:
            proposed = {
                "player":   bet.get("name") or bet.get("player_id"),
                "game_id":  bet.get("game_id", ""),
                "stake":    bankroll * bet.get("kelly", 0.0),
                "p_hit":    bet.get("p_hit", 0.0),
                "ev_pct":   (bet.get("ev") or 0.0) * 100.0,
                "side":     bet.get("side", ""),
            }
            allowed, reasons = can_place_bet(proposed, state, cfg, open_bets)
            if allowed:
                passed.append(bet)
            else:
                log.info(
                    "[risk] blocked %s %s line=%s: %s",
                    bet.get("name"), bet.get("stat"),
                    bet.get("line"), reasons[0] if reasons else "unknown",
                )
        return passed

    except Exception as exc:
        log.warning("[risk] gate error (non-fatal, returning full list): %s", exc)
        return bets


# ── shadow DB logging ───────────────────────────────────────────────────
def _db_log_shadow_bet(payload: Dict[str, Any]) -> None:
    """Insert a recommended bet into the SQLite ledger as source='shadow'/status='intended'.

    Fire-and-forget: errors are logged but never propagate to the live path.
    Only runs when BET_DB_SHADOW_LOG env var is not set to '0'.
    """
    if os.environ.get("BET_DB_SHADOW_LOG", "1") == "0":
        return
    try:
        from database.bet_db import BetDB  # noqa: PLC0415
        game_id   = payload.get("game_id") or ""
        date_part = time.strftime("%Y-%m-%d")
        bet = {
            "date":        date_part,
            "game_id":     game_id,
            "player_id":   payload.get("player_id"),
            "player_name": payload.get("name") or str(payload.get("player_id") or ""),
            "stat":        payload.get("stat", ""),
            "line":        payload.get("line", 0.0),
            "side":        payload.get("side", ""),
            "book":        payload.get("book") or "unknown",
            "odds":        payload.get("odds", 0),
            "stake":       payload.get("kelly", 0.0),  # fractional Kelly (not $)
            "kelly_size":  payload.get("kelly"),
            "model_ev_pct": payload.get("ev"),
            "model_p_hit":  payload.get("p_hit"),
            "status":      "intended",
            "source":      "shadow",
            "notes":       payload.get("why"),
        }
        BetDB().insert_bet(bet)
    except Exception as exc:
        log.debug("shadow DB log failed (non-fatal): %s", exc)


# ── engine ──────────────────────────────────────────────────────────────
class DecisionEngine:
    """Subscribe to projection + line events; emit top-N bet recommendations."""

    def __init__(self, *,
                 bus: Optional[EventBus] = None,
                 line_cache: Optional[LineCache] = None,
                 top_n: int = 5,
                 emit_floor_ev: float = TIER_B_EV,
                 throttle_ms: int = 250) -> None:
        self.bus = bus or get_bus()
        self.line_cache = line_cache or LineCache()
        self.top_n = top_n
        # emit_floor_ev: scalar overrides per-period lookup (used in tests / legacy callers).
        # In normal operation the per-period dict _EMIT_FLOOR_BY_PERIOD takes precedence.
        self.emit_floor_ev = emit_floor_ev
        self.throttle_ms = throttle_ms
        # Latest rows per game so we can rerank when lines refresh.
        self._latest_rows: Dict[str, List[Dict[str, Any]]] = {}
        # Track last emit time so we don't spam on rapid event bursts.
        self._last_emit_ts: float = 0.0
        self._registered = False
        # Make initial refresh attempt safe — never fails the loop start.
        try:
            self.line_cache.refresh()
        except Exception as exc:  # noqa: BLE001
            log.warning("initial line refresh failed: %s", exc)

    def register(self) -> None:
        if self._registered:
            return
        self.bus.subscribe(TOPIC_PROJECTION_UPDATED, self._on_projection)
        self.bus.subscribe(TOPIC_LINES_REFRESHED, self._on_lines)
        self._registered = True

    # ── handlers ────────────────────────────────────────────────────
    async def _on_projection(self, topic: str, event: Dict[str, Any]) -> None:
        game_id = event.get("game_id")
        rows = event.get("rows") or []
        if not game_id or not rows:
            return
        # Merge into the per-game cache (replace by (player_id, stat) key).
        existing = self._latest_rows.setdefault(game_id, [])
        index = {(r.get("player_id"), r.get("stat")): i
                 for i, r in enumerate(existing)}
        for r in rows:
            key = (r.get("player_id"), r.get("stat"))
            if key in index:
                existing[index[key]] = r
            else:
                index[key] = len(existing)
                existing.append(r)
        await self._maybe_rerank(game_id, reason=event.get("reason") or topic)

    async def _on_lines(self, topic: str, event: Dict[str, Any]) -> None:
        try:
            self.line_cache.refresh(event.get("date"))
        except Exception as exc:  # noqa: BLE001
            log.warning("line refresh failed: %s", exc)
            return
        for gid in list(self._latest_rows.keys()):
            await self._maybe_rerank(gid, reason="lines.refreshed")

    # ── ranking ─────────────────────────────────────────────────────
    async def _maybe_rerank(self, game_id: str, *, reason: str) -> None:
        now_ms = time.time() * 1000.0
        if now_ms - self._last_emit_ts < self.throttle_ms:
            return
        self._last_emit_ts = now_ms
        bets = self.rank_for_game(game_id)
        if not bets:
            return

        # ── risk gate (final filter before emit) ─────────────────
        bets = _risk_filter(bets)
        if not bets:
            return

        # Emit each top bet so consumers (alerts, dashboard) can filter.
        for bet in bets[: self.top_n]:
            payload = {**bet, "game_id": game_id, "reason": reason}
            await self.bus.publish(TOPIC_BET_RECOMMENDED, payload)
            _db_log_shadow_bet(payload)

    def rank_for_game(self, game_id: str) -> List[Dict[str, Any]]:
        _shadow_on = os.environ.get("SHADOW_LOG_ENABLED", "1") == "1"
        if _shadow_on:
            from src.prediction import shadow_logger as _sl  # lazy — avoids import cycle

        rows = self._latest_rows.get(game_id) or []
        out: List[Dict[str, Any]] = []
        phantom_drops = 0
        _ts = time.strftime("%Y-%m-%dT%H:%M:%S")

        for rec in rows:
            stat = (rec.get("stat") or "").strip().lower()
            if not stat:
                continue

            # Collect all lines BEFORE consensus filter so we can log drops.
            all_lines = self.line_cache.find(
                rec.get("player_id"), rec.get("name") or "", stat)
            trusted_lines = _filter_three_book_consensus(all_lines)

            # Log lines that failed three-book consensus.
            if _shadow_on:
                trusted_set = {id(ln) for ln in trusted_lines}
                for ln in all_lines:
                    if id(ln) not in trusted_set:
                        for side in ("over", "under"):
                            odds_raw = ln.get(f"{side}_price")
                            if odds_raw in (None, ""):
                                continue
                            _sl.log_evaluation(
                                ts=_ts, game_id=game_id,
                                period=rec.get("period"),
                                clock_remaining=rec.get("clock_remaining"),
                                player_id=rec.get("player_id"),
                                name=rec.get("name"),
                                team=rec.get("team"),
                                stat=stat, side=side,
                                line=ln.get("line"),
                                book=ln.get("book"),
                                odds=odds_raw,
                                model_proj=rec.get("projected_final"),
                                current_stat=rec.get("current"),
                                sigma=_STAT_SIGMA.get(stat),
                                raw_ev=None, kelly=None, tier=None,
                                gate_status="blocked",
                                gate_blocked_by="three_book_consensus",
                                source="in_play_decision",
                            )

            for line in trusted_lines:
                for side in ("over", "under"):
                    odds = line.get(f"{side}_price")
                    if odds in (None, ""):
                        continue
                    try:
                        odds_int = int(odds)
                    except (TypeError, ValueError):
                        continue
                    ok, gate_name = _passes_gates(rec, line)
                    if not ok:
                        if _shadow_on:
                            _sl.log_evaluation(
                                ts=_ts, game_id=game_id,
                                period=rec.get("period"),
                                clock_remaining=rec.get("clock_remaining"),
                                player_id=rec.get("player_id"),
                                name=rec.get("name"),
                                team=rec.get("team"),
                                stat=stat, side=side,
                                line=line.get("line"),
                                book=line.get("book"),
                                odds=odds_int,
                                model_proj=rec.get("projected_final"),
                                current_stat=rec.get("current"),
                                sigma=_STAT_SIGMA.get(stat),
                                raw_ev=None, kelly=None, tier=None,
                                gate_status="blocked",
                                gate_blocked_by=gate_name,
                                source="in_play_decision",
                            )
                        continue
                    try:
                        line_val = float(line["line"])
                        proj = float(rec["projected_final"])
                    except (TypeError, ValueError):
                        continue
                    sigma = _STAT_SIGMA[stat]
                    p = hit_probability(proj, line_val, side, sigma)
                    ev = ev_per_dollar(p, odds_int)
                    delta_abs = abs(rec.get("delta") or 0.0)
                    kelly = kelly_fraction(p, odds_int)
                    tier = classify_tier(ev, delta_abs)
                    # Per-period emit floor: earlier quarters are noisier so
                    # need a stricter floor. Fall back to scalar self.emit_floor_ev
                    # when caller passed an explicit override (e.g., tests).
                    _period_str = str(rec.get("period") or "")
                    _floor = max(
                        _EMIT_FLOOR_BY_PERIOD.get(_period_str, TIER_B_EV),
                        self.emit_floor_ev,
                    )
                    if ev < _floor:
                        if _shadow_on:
                            _sl.log_evaluation(
                                ts=_ts, game_id=game_id,
                                period=rec.get("period"),
                                clock_remaining=rec.get("clock_remaining"),
                                player_id=rec.get("player_id"),
                                name=rec.get("name"),
                                team=rec.get("team"),
                                stat=stat, side=side,
                                line=line_val,
                                book=line.get("book"),
                                odds=odds_int,
                                model_proj=proj,
                                current_stat=rec.get("current"),
                                sigma=sigma,
                                raw_ev=ev, kelly=kelly, tier=tier,
                                gate_status="blocked",
                                gate_blocked_by="ev_floor",
                                source="in_play_decision",
                            )
                        continue
                    # Per-period EV ceiling: real markets rarely offer phantom-high
                    # EV on a prop. Calibrated 2026-05-27: Q3 ceiling raised to 0.90
                    # because late-game high-EV bets are legitimate (ROI 70.5%).
                    # Q1/Q2 remain at 0.50 to guard against noisy early-game projections.
                    _ceiling = _EV_CEILING_BY_PERIOD.get(_period_str, 0.50)
                    if ev > _ceiling:
                        phantom_drops += 1
                        log.debug(
                            "drop phantom edge: %s %s %s line=%s proj=%s "
                            "ev=%.0f%%",
                            rec.get("name"), stat, side, line_val, proj,
                            ev * 100,
                        )
                        if _shadow_on:
                            _sl.log_evaluation(
                                ts=_ts, game_id=game_id,
                                period=rec.get("period"),
                                clock_remaining=rec.get("clock_remaining"),
                                player_id=rec.get("player_id"),
                                name=rec.get("name"),
                                team=rec.get("team"),
                                stat=stat, side=side,
                                line=line_val,
                                book=line.get("book"),
                                odds=odds_int,
                                model_proj=proj,
                                current_stat=rec.get("current"),
                                sigma=sigma,
                                raw_ev=ev, kelly=kelly, tier=tier,
                                gate_status="blocked",
                                gate_blocked_by="ev_ceiling_per_period",
                                source="in_play_decision",
                            )
                        continue
                    if _shadow_on:
                        _sl.log_evaluation(
                            ts=_ts, game_id=game_id,
                            period=rec.get("period"),
                            clock_remaining=rec.get("clock_remaining"),
                            player_id=rec.get("player_id"),
                            name=rec.get("name"),
                            team=rec.get("team"),
                            stat=stat, side=side,
                            line=line_val,
                            book=line.get("book"),
                            odds=odds_int,
                            model_proj=proj,
                            current_stat=rec.get("current"),
                            sigma=sigma,
                            raw_ev=ev, kelly=kelly, tier=tier,
                            gate_status="passed",
                            gate_blocked_by="",
                            source="in_play_decision",
                        )
                    out.append({
                        "player_id": rec.get("player_id"),
                        "name": rec.get("name"),
                        "team": rec.get("team"),
                        "stat": stat,
                        "side": side,
                        "line": line_val,
                        "book": line.get("book"),
                        "odds": odds_int,
                        "projected_final": proj,
                        "current": rec.get("current"),
                        "delta": rec.get("delta"),
                        "p_hit": p,
                        "ev": ev,
                        "kelly": kelly,
                        "tier": tier,
                        "source": "in_play_decision",
                        "why": build_why(rec, line, side, p, ev, kelly, tier),
                    })
        out.sort(key=lambda b: b["ev"], reverse=True)
        if phantom_drops:
            log.info(
                "in-play rank %s: dropped %d phantom edges (model >50%% EV)",
                game_id, phantom_drops,
            )
        return out
