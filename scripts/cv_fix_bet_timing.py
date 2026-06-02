"""WHEN-TO-BET engine — find the optimal in-game moment to place each prop bet.

For one game we reconstruct the full chronological timeline of bettable prop
lines (pregame t0 + every in-play capture), and at each capture compute the
in-play projection from the snapshot known AT THAT TIME (carry-forward, NO
LOOKAHEAD). A bet becomes ELIGIBLE the first capture it passes the validated
iter61 filter (allowed direction + edge >= per-stat threshold + not line/dir
excluded) AND is +EV at a sane price.

Three ENTRY POLICIES decide WHEN to actually place each (player, stat) bet ONCE:
  a) FIRST_EDGE       — place at the first eligible capture.
  b) PEAK_EDGE        — lock the best entry price: place at the running-max-edge
                        eligible capture once it stops improving for K captures.
  c) CONFIDENCE_GATED — place at the first eligible capture AFTER the projection
                        has stabilised (|proj move| over last K captures < tol).

Every placed bet is graded 1u-flat vs the TRUE FINAL (the FINAL-status snapshot
with the MAX total score — snapshots are non-monotonic across capture sessions).
We emit per-policy hit%/ROI + a by-entry-stage breakdown, and a cross-game
learner picks, PER STAT, the policy+stage window with the best pooled ROI.

Run:  python scripts/cv_fix_bet_timing.py           # last completed game + learn
      python scripts/cv_fix_bet_timing.py <nba_gid>
"""
from __future__ import annotations

import glob
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("NBA_OFFLINE", "1")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CACHE_DIR = ROOT / "data" / "cache" / "cv_fix"
LIVE_DIR = ROOT / "data" / "live"
MODEL_PATH = CACHE_DIR / "bet_timing_model.json"

# Entry-timing policies the cross-game learner chooses between, PER STAT.
# KEY EMPIRICAL FINDING: the eligible SIDE (over/under) never flips within a
# prop once the model has an edge — so WHEN you bet cannot change whether you
# WIN, only the PRICE you get. The best "when" is therefore the best PRICE for
# your side; chasing the biggest EDGE (earliest, noisiest) gets the worst odds.
#   BEST_PRICE       — lock the best payout for your side (DEFAULT — the right
#                      "when": side is fixed, so optimise price)
#   FIRST_EDGE       — earliest eligible capture (rawest edge, usually worst price)
#   LATE_CONFIRM     — latest eligible capture, only if the edge PERSISTED
#   PEAK_EDGE        — lock the running-max edge (biggest disagreement w/ line)
#   CONFIDENCE_GATED — first eligible capture after the projection stabilises
POLICIES = ("BEST_PRICE", "FIRST_EDGE", "LATE_CONFIRM", "PEAK_EDGE", "CONFIDENCE_GATED")
_DEFAULT_POLICY = "BEST_PRICE"
STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_K = 3                 # stability / peak / persistence window (captures)
_MIN_POOL = 20         # cross-game sample guard before trusting a learned rule
_MIN_POLICY_N = 5      # a policy needs >= this many graded bets to be RANKED at
                       # all (stops an n=1 roi=+100 fluke from beating n=50 +15)
_BET_CAP = 10          # the AGENT places only its best-N bets, not every edge
# Garbage-time guard: late in a decided game the live model still extrapolates
# full-game pace ("on track for 30") but starters get pulled — so late OVERs on
# a blowout are systematically pace-mirages. Skip OVER bets once the lead is big
# and we're in the 2nd half.
_GARBAGE_MARGIN = 18
_GARBAGE_PERIOD = 3

# How much to TRUST the in-game read vs the pregame prior, by projection source.
# Grounded in measured pts-MAE-by-stage across both games: endQ1 ~4.7 (over-
# projects hot starts), endQ2 ~2.6, endQ3 ~1.3 (validated sharp). Early reads
# chase unsustainable hot starts -> blend them back toward the season-anchored
# pregame projection so we don't bet fake OVER edges. proj = w*in_game + (1-w)*pregame.
_INGAME_TRUST = {"endQ1": 0.40, "endQ2": 0.60, "endQ3": 0.85, "pace": 0.25}


# ─────────────────────────────── time helpers ──────────────────────────────
def _epoch(iso: str) -> float:
    """ISO ts -> epoch seconds. Naive timestamps are treated as UTC so that
    snapshot captured_at ('...+00:00') and line cap ('...' no tz) compare."""
    if not iso:
        return -1.0
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return -1.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _payout(odds) -> float:
    """Profit per 1u stake at American odds (DK-style)."""
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return 100.0 / 110.0
    return (o / 100.0) if o > 0 else (100.0 / abs(o))


# ─────────────────────────── snapshot / projection ─────────────────────────
def _load_snapshots(canon_ids):
    """All snapshots for the game, sorted by captured_at epoch.
    Returns [(epoch, captured_at, snap_dict)] and the TRUE-FINAL info."""
    snaps = []
    best_final = (-1, None)  # (total_score, snap)
    for gid in canon_ids:
        for p in LIVE_DIR.glob(f"{gid}_*.json"):
            try:
                s = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            cap = s.get("captured_at") or ""
            ep = _epoch(cap)
            if ep < 0:
                continue
            snaps.append((ep, cap, s))
            if "FINAL" in str(s.get("game_status") or "").upper():
                try:
                    tot = int(s.get("away_score") or 0) + int(s.get("home_score") or 0)
                except (TypeError, ValueError):
                    tot = 0
                if tot > best_final[0]:
                    best_final = (tot, s)
    snaps.sort(key=lambda t: t[0])
    return snaps, best_final[1]


class _CarryForward:
    """For a time T, return the projection map + period/clock from the latest
    snapshot whose captured_at <= T. No-lookahead by construction. Projections
    are memoised per snapshot captured_at (project_from_snapshot is not cheap)."""

    def __init__(self, snaps):
        self._eps = [s[0] for s in snaps]
        self._snaps = snaps
        self._proj_cache: dict = {}

    def margin_at(self, t_epoch: float):
        """Absolute score margin from the latest snapshot <= T (no-lookahead)."""
        idx = -1
        for i, ep in enumerate(self._eps):
            if ep <= t_epoch:
                idx = i
            else:
                break
        if idx < 0:
            return 0
        s = self._snaps[idx][2]
        try:
            return abs(int(s.get("away_score") or 0) - int(s.get("home_score") or 0))
        except (TypeError, ValueError):
            return 0

    def at(self, t_epoch: float):
        # rightmost snapshot with epoch <= t_epoch (linear; lists are small)
        idx = -1
        for i, ep in enumerate(self._eps):
            if ep <= t_epoch:
                idx = i
            else:
                break
        if idx < 0:
            return None, None, None, None
        snap_ep, cap, snap = self._snaps[idx]
        cached = self._proj_cache.get(cap)
        if cached is None:
            from api.courtvision_router import _project_at_snapshot_map  # lazy
            cached = _project_at_snapshot_map(snap)
            self._proj_cache[cap] = cached
        period = snap.get("period")
        try:
            period = int(period) if period is not None else None
        except (TypeError, ValueError):
            period = None
        return cached, period, snap.get("clock"), snap_ep


def _clock_secs(clk):
    try:
        m, s = str(clk).split(":")
        return int(m) * 60 + float(s)
    except (ValueError, AttributeError):
        return -1.0


class _BoundaryProjector:
    """The PBP-aware projection. live_engine's good in-game heads (learned-Q4
    minutes, foul/blowout residuals, heat-check shrinkage) ONLY fire at quarter
    BOUNDARY snapshots (start of Q2/Q3/Q4 = end of Q1/Q2/Q3). Mid-quarter
    snapshots fall through to naive pace extrapolation — which over-projects
    starters who get pulled (the garbage-time mirage). So we anchor every
    decision's PROJECTION to the latest quarter-boundary read <= T (carry the
    sharp number forward), while the LINE keeps moving in real time. No
    lookahead: boundary epoch <= capture epoch by construction.

    Empirically the boundary read is 5-10 pts sharper on stars than mid-quarter
    pace (Wemby 25.2 vs 36.0 pace, actual 28)."""

    def __init__(self, snaps):
        # boundary = start of period p (max clock) -> labelled endQ{p-1}
        self._bounds = []  # [(ep, label, snap)]
        for p in (2, 3, 4):
            cands = [(ep, cap, s) for ep, cap, s in snaps
                     if (s.get("period") in (p, str(p)))]
            if not cands:
                continue
            ep, cap, s = max(cands, key=lambda t: _clock_secs(t[2].get("clock")))
            # accept the earliest-available snapshot of period p as the boundary
            # read for end-of-Q(p-1). Allow down to 9:00 — books/snapshots don't
            # always capture exactly at 12:00 (this game's Q4 started at 10:55).
            if _clock_secs(s.get("clock")) >= 540:  # >= 9:00 into the period
                self._bounds.append((ep, f"endQ{p - 1}", s))
        self._bounds.sort(key=lambda t: t[0])
        self._proj_cache: dict = {}

    def available(self):
        return bool(self._bounds)

    def proj_at(self, t_epoch):
        """(proj_map, boundary_label, boundary_ep) for the latest boundary <= T,
        else (None, None, None)."""
        chosen = None
        for ep, label, s in self._bounds:
            if ep <= t_epoch:
                chosen = (ep, label, s)
            else:
                break
        if chosen is None:
            return None, None, None
        ep, label, s = chosen
        pm = self._proj_cache.get(label)
        if pm is None:
            from api.courtvision_router import _project_at_snapshot_map  # lazy
            pm = _project_at_snapshot_map(s)
            self._proj_cache[label] = pm
        return pm, label, ep


# ───────────────────────────── line timeline ───────────────────────────────
def _load_inplay(settled_date, canon_ids):
    """In-play prop captures via the router loader (cached). Rows already carry
    cap/name/disp/stat/line/over/under. Adds epoch + stage marker."""
    from api.courtvision_router import _load_inplay_line_history  # lazy
    rows = _load_inplay_line_history(settled_date, frozenset(canon_ids))
    out = []
    for r in rows:
        out.append({**r, "ep": _epoch(r["cap"]), "stage_src": "inplay"})
    return out


def _load_pregame_t0(canon_gid, settled_date, player_filter):
    """Pregame line capture (t0): slate q50 (`pred`) joined to the pregame
    sportsbook line. Keyed by (name_lower, stat). Best-effort — returns []
    if the slate / pregame book file is absent."""
    import csv
    # slate q50: find the slate file that contains this game
    pred = {}
    for sp in (ROOT / "data" / "predictions").glob("slate_*.csv"):
        try:
            with sp.open(encoding="utf-8", newline="") as fh:
                rd = list(csv.DictReader(fh))
        except Exception:
            continue
        if not any(str(r.get("game_id") or "") == canon_gid for r in rd):
            continue
        for r in rd:
            if str(r.get("game_id") or "") != canon_gid:
                continue
            nm = (r.get("player") or "").strip().lower()
            st = (r.get("stat") or "").strip().lower()
            try:
                pred[(nm, st)] = float(r.get("pred"))
            except (TypeError, ValueError):
                continue
        break
    if not pred:
        return []
    # pregame book lines (non-inplay) for this date, restricted to game players
    def _pf(x):
        try:
            return int(float(x))
        except (TypeError, ValueError):
            return None
    latest = {}
    for lp in (ROOT / "data" / "lines").glob(f"{settled_date}_*.csv"):
        if "inplay" in lp.name:
            continue
        try:
            with lp.open(encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    nm = (r.get("player_name") or "").strip().lower()
                    st = (r.get("stat") or "").strip().lower()
                    if nm not in player_filter:
                        continue
                    cap = (r.get("captured_at") or "").strip()
                    try:
                        line = float(r.get("line"))
                    except (TypeError, ValueError):
                        continue
                    k = (nm, st)
                    if k in latest and latest[k]["cap"] >= cap:
                        continue
                    latest[k] = {"cap": cap, "name": nm,
                                 "disp": (r.get("player_name") or "").strip(),
                                 "stat": st, "line": line,
                                 "over": _pf(r.get("over_price")),
                                 "under": _pf(r.get("under_price"))}
        except Exception:
            continue
    out = []
    for (nm, st), row in latest.items():
        out.append({**row, "ep": _epoch(row["cap"]) if row["cap"] else 0.0,
                    "stage_src": "pregame", "pregame_pred": pred.get((nm, st))})
    return out


# ───────────────────── variance-aware confidence (P(cover)) ────────────────
# The bet-card "confidence %" must be a real P(cover), not raw edge magnitude.
# A +1.5 edge on a high-variance FG3M (sigma~0.62) is NOT the same bet as a
# +1.5 edge on a tight BLK under — turning the edge into P(cover) via the
# stat/stage sigma, then shrinking toward the stat's realized base hit-rate,
# stops discrete volatile stats (fg3m/stl/blk) from reading a fake 0.99.

# Sensible per-stat sigma floors used when a stat/asset is missing from the
# calibration files. These are end-of-Q3 (in-game, narrow) scales.
_SIGMA_DEFAULT = {"pts": 6.0, "reb": 2.6, "ast": 1.6, "fg3m": 1.2,
                  "stl": 0.8, "blk": 0.7, "tov": 1.0}
# Per-stat reliability weight on P(cover) vs base hit-rate. Continuous,
# high-volume stats (pts/reb/ast) trust the Gaussian P(cover) more; discrete,
# low-count, fat-tailed stats (fg3m/stl/blk/tov) lean on the realized base rate.
_RELIABILITY_W = {"pts": 0.80, "reb": 0.80, "ast": 0.80,
                  "fg3m": 0.45, "stl": 0.45, "blk": 0.45, "tov": 0.45}
_LATE_STAGES = ("Q3", "Q4")          # endQ3 narrow sigma applies from Q3 on
_Z80 = 1.2816                        # q80 / z  -> 1-sigma (one-sided 80th pct)

# module-level sigma caches (load once)
_SIGMA_LATE: dict | None = None      # stat -> endQ3 in-game sigma
_SIGMA_EARLY: dict | None = None     # stat -> wider pregame/early sigma

# Monte-Carlo P(over) blend (CONTRACT: mc-adapter -> engine):
#   data/cache/cv_fix/mc_distributions_<settled_date>.json =
#     {player_name_lower: {stat: {mean, sigma, p10, p50, p90}}}
# When present we blend the MC P(over) 50/50 into the sigma-based confidence.
# When ABSENT (or player/stat missing) confidence is unchanged — no behaviour
# change. Cache is keyed by settled_date; the empty-dict sentinel means "loaded,
# no artifact for this date" so we don't stat() the file on every bet.
_MC_DIST_CACHE: dict = {}             # settled_date -> {player_lower: {stat: {...}}}


def _load_mc_distributions(settled_date) -> dict:
    """MC distribution artifact for a date, or {} if absent/unreadable. Cached
    per date (graceful — never raises)."""
    key = str(settled_date or "")
    cached = _MC_DIST_CACHE.get(key)
    if cached is not None:
        return cached
    out: dict = {}
    try:
        p = CACHE_DIR / f"mc_distributions_{key}.json"
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                out = raw
    except Exception:
        out = {}
    _MC_DIST_CACHE[key] = out
    return out


def _mc_norm_name(name) -> str:
    """IDENTICAL normalization to scripts/mc_to_predictions_cache._norm_name —
    the writer of the mc_distributions_<date>.json keys. Lowercase, strip every
    char that isn't [a-z0-9 ], then trim. Without this the MC blend silently
    never fires for hyphen/apostrophe players (Shai Gilgeous-Alexander,
    De'Aaron Fox) because the engine key still carried '-'/'\\'' but the artifact
    key did not."""
    return re.sub(r"[^a-z0-9 ]", "", str(name).lower()).strip()


def _mc_p_over(settled_date, player_lower, stat, line):
    """P(over line) from the MC distribution for (player, stat), or None if the
    artifact / player / stat / a usable sigma is missing. P = 1 - Phi((line-mean)/sigma)."""
    dist = _load_mc_distributions(settled_date)
    if not dist:
        return None
    try:
        rec = (dist.get(_mc_norm_name(player_lower)) or {}).get(str(stat or "").lower())
        if not rec:
            return None
        mean = float(rec.get("mean"))
        sig = float(rec.get("sigma"))
        if sig <= 0:
            return None
        return 1.0 - _phi((float(line) - mean) / sig)
    except (TypeError, ValueError):
        return None


def _load_late_sigmas() -> dict:
    """endQ3 (in-game, narrow) sigma per stat from the v2 quantile calibration."""
    global _SIGMA_LATE
    if _SIGMA_LATE is not None:
        return _SIGMA_LATE
    out = dict(_SIGMA_DEFAULT)
    try:
        d = json.loads((ROOT / "data" / "models" /
                        "per_player_quantile_calibration_v2.json").read_text(encoding="utf-8"))
        eq3 = d.get("endQ3") or {}
        for st in STATS:
            s = (eq3.get(st) or {}).get("sigma")
            if s is not None and float(s) > 0:
                out[st] = float(s)
    except Exception:
        pass
    _SIGMA_LATE = out
    return out


def _load_early_sigmas() -> dict:
    """Wider sigma for pregame/early stages. Prefer the realized residual q80
    (sigma = q80 / 1.2816) from prop_calibration_summary.json; else fall back
    to 1.8x the endQ3 in-game sigma (uncertainty is much higher pregame)."""
    global _SIGMA_EARLY
    if _SIGMA_EARLY is not None:
        return _SIGMA_EARLY
    late = _load_late_sigmas()
    out = {st: late[st] * 1.8 for st in STATS}
    try:
        d = json.loads((ROOT / "data" / "models" /
                        "prop_calibration_summary.json").read_text(encoding="utf-8"))
        for st in STATS:
            q80 = (d.get(st) or {}).get("q80")
            if q80 is not None and float(q80) > 0:
                out[st] = float(q80) / _Z80
    except Exception:
        pass
    _SIGMA_EARLY = out
    return out


def _phi(x: float) -> float:
    """Standard-normal CDF via math.erf (no scipy/numpy)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _calibrated_confidence(stat, proj, line, side, stage,
                           player_lower=None, settled_date=None) -> float:
    """Variance-aware P(cover) for the bet card, in [0.50, 0.88].

    1. P(cover) = Phi((proj-line)/sigma) for OVER, Phi((line-proj)/sigma) for
       UNDER — so a fixed edge on a wide-sigma stat is correctly LESS confident
       than the same edge on a tight stat.
    2. sigma is stage-aware: endQ3 (narrow, in-game) for Q3/Q4, wider for
       Pregame/Q1/Q2.
    3. Shrink toward the stat's realized base hit-rate so discrete volatile
       stats can't read 0.99: p = w*P_cover + (1-w)*base_hit.
    4. MC-CONFIDENCE BLEND (graceful): if a Monte-Carlo distribution artifact
       exists for (player, stat) on settled_date, blend its P(cover) 50/50 with
       the sigma-based one: p_final = 0.5*p_sigma + 0.5*p_mc. When the artifact
       or player/stat is missing the sigma-based confidence is used unchanged.
    5. Clamp to [0.50, 0.88]."""
    if (proj is None or line is None
            or not math.isfinite(proj) or not math.isfinite(line)):
        return 0.50
    st = (stat or "").lower()
    s = str(stage or "")
    sig = (_load_late_sigmas() if s in _LATE_STAGES else _load_early_sigmas()).get(
        st, _SIGMA_DEFAULT.get(st, 1.0))
    if sig <= 0:
        sig = _SIGMA_DEFAULT.get(st, 1.0)
    try:
        diff = (float(proj) - float(line)) if str(side).upper() == "OVER" \
            else (float(line) - float(proj))
    except (TypeError, ValueError):
        return 0.50
    p_cover = _phi(diff / sig)
    # shrink toward the stat's realized base hit-rate
    try:
        from src.prediction.bet_thresholds import kelly_b_hit_rate_for
        base_hit = float(kelly_b_hit_rate_for(st))
    except Exception:
        base_hit = 0.55
    w = _RELIABILITY_W.get(st, 0.60)
    p = w * p_cover + (1.0 - w) * base_hit
    # MC blend (no-op when the artifact / player / stat is absent): mirror the
    # MC P(over) for the UNDER side, then 50/50 average with the sigma estimate.
    p_mc_over = _mc_p_over(settled_date, player_lower, st, line)
    if p_mc_over is not None:
        p_mc = p_mc_over if str(side).upper() == "OVER" else (1.0 - p_mc_over)
        p = 0.5 * p + 0.5 * p_mc
    return max(0.50, min(0.88, p))


# ──────────────────────────── eligibility / EV ─────────────────────────────
def _evaluate(st, proj, line, over, under, stage="Pregame",
              player_lower=None, settled_date=None):
    """Apply the validated iter61 filter at a single capture. Returns a dict
    {side, edge, price, ev, prob} if the bet is eligible & +EV, else None.
    CONSTANT edge bar at every stage (loosening by stage bought noise)."""
    from src.prediction.bet_thresholds import (
        allowed_directions_for, edge_threshold_for,
        is_line_excluded, is_direction_line_excluded)
    if proj is None or not math.isfinite(proj):
        return None
    side = "OVER" if proj >= line else "UNDER"
    if side.lower() not in allowed_directions_for(st):
        return None
    thr = edge_threshold_for(st)
    edge = abs(proj - line)
    if edge < thr:
        return None
    if is_line_excluded(st, line) or is_direction_line_excluded(st, side.lower(), line):
        return None
    price = over if side == "OVER" else under
    if price is None or price > 450 or price < -1000:
        return None
    # Variance-aware confidence: a real P(cover) from the stat/stage sigma,
    # shrunk toward the realized base hit-rate (replaces the pure edge-magnitude
    # calibrate_p_win, which let high-variance FG3M overs out-rank safe unders).
    p = _calibrated_confidence(st, proj, line, side, stage,
                               player_lower=player_lower, settled_date=settled_date)
    pay = float(price) if price > 0 else (10000.0 / abs(price))
    ev = p * pay - (1.0 - p) * 100.0
    if ev <= 0:
        return None
    return {"side": side, "edge": round(edge, 3), "price": price,
            "ev": round(ev, 2), "prob": round(p, 4)}


def _stage_of(period, src):
    if src == "pregame" or period is None:
        return "Pregame"
    return f"Q{period}"


def _entry_label(period, clock, src):
    if src == "pregame" or period is None:
        return "Pregame"
    return f"Q{period} {clock}" if clock else f"Q{period}"


# ─────────────────────────── per-key timeline build ────────────────────────
def _build_key_captures(inplay, pregame, carry, boundary=None, settled_date=None):
    """{(name,stat): [capture,...] chronological}. Each capture is enriched
    with the no-lookahead projection + eligibility eval.

    PROJECTION SOURCE: prefer the PBP-aware quarter-boundary read (carried
    forward from the latest endQ1/Q2/Q3 <= T) — it's 5-10 pts sharper on stars
    than mid-quarter pace. Fall back to mid-quarter pace only before the first
    boundary exists (early Q1)."""
    by_key: dict = {}
    pregame_map: dict = {}
    for r in pregame:
        by_key.setdefault((r["name"], r["stat"]), []).append(r)
        pg = r.get("pregame_pred")
        if pg is not None:
            pregame_map[(r["name"], r["stat"])] = pg
    for r in inplay:
        by_key.setdefault((r["name"], r["stat"]), []).append(r)

    out: dict = {}
    for key, rows in by_key.items():
        rows.sort(key=lambda r: r["ep"])
        st = key[1]
        seq = []
        for r in rows:
            snap_ep = None
            proj_source = None
            if r["stage_src"] == "pregame":
                proj, period, clock = r.get("pregame_pred"), None, None
                proj_source = "pregame"
            else:
                # real-time period/clock/margin for ENTRY display + guard
                _pm_naive, period, clock, naive_ep = carry.at(r["ep"])
                proj = bproj_ep = None
                if boundary is not None:
                    bmap, blabel, bproj_ep = boundary.proj_at(r["ep"])
                    if bmap is not None and key in bmap:
                        proj, snap_ep, proj_source = bmap[key], bproj_ep, blabel
                if proj is None:
                    # Before the first quarter boundary (early Q1) we have NO
                    # PBP read. Do NOT use naive pace here: a 5-minute
                    # extrapolation gives absurd finals (8 pts in 5 min -> 52),
                    # which become huge fake edges that saturate confidence and
                    # poison selection. The PREGAME model prior is the correct,
                    # sane projection until the game tells us otherwise.
                    pg = pregame_map.get(key)
                    if pg is not None:
                        proj, snap_ep, proj_source = pg, naive_ep, "pregame_prior"
                    else:
                        proj = _pm_naive.get(key) if _pm_naive else None
                        snap_ep, proj_source = naive_ep, "pace"
                # SHRINK the in-game read toward the season-anchored pregame
                # prior — early reads over-project hot starts (endQ1 MAE ~4.7).
                # Trust grows toward endQ3 (MAE ~1.3) where no shrink is needed.
                pg_prior = pregame_map.get(key)
                if (pg_prior is not None and proj is not None
                        and proj_source in _INGAME_TRUST):
                    w = _INGAME_TRUST[proj_source]
                    proj = w * proj + (1.0 - w) * pg_prior
                # NO-LOOKAHEAD INVARIANT: the projection driving a decision at
                # time T may only come from a snapshot captured at or before T.
                if snap_ep is not None:
                    assert snap_ep <= r["ep"] + 1e-6, (
                        f"lookahead: snap {snap_ep} > capture {r['ep']} for {key}")
            ev = (_evaluate(st, proj, r["line"], r.get("over"), r.get("under"),
                            stage=_stage_of(period, r["stage_src"]),
                            player_lower=key[0], settled_date=settled_date)
                  if proj is not None else None)
            # Garbage-time guard: a late OVER in a blowout is a pace-mirage (the
            # model extrapolates minutes the starter won't actually play). Veto it.
            guarded = False
            if (ev and ev["side"] == "OVER" and r["stage_src"] != "pregame"
                    and period is not None and period >= _GARBAGE_PERIOD
                    and carry.margin_at(r["ep"]) >= _GARBAGE_MARGIN):
                ev, guarded = None, True
            seq.append({
                "cap": r["cap"], "ep": r["ep"], "src": r["stage_src"],
                "disp": r["disp"], "line": r["line"], "proj": proj,
                "proj_snap_ep": snap_ep, "guarded": guarded,
                "proj_source": proj_source,
                "period": period, "clock": clock,
                "stage": _stage_of(period, r["stage_src"]),
                "entry_label": _entry_label(period, clock, r["stage_src"]),
                "eval": ev,
            })
        out[key] = seq
    return out


# ──────────────────────────────── policies ─────────────────────────────────
def _pick_first_edge(seq):
    for c in seq:
        if c["eval"]:
            return c
    return None


def _pick_best_price(seq, k=_K):
    """THE principled 'when': lock the best PRICE for your side. Since the side
    never flips, betting can't change the win — only the payout — so we wait
    for the price to improve and commit once it stops improving for k captures
    (no-lookahead: best price SEEN so far, never a future one)."""
    best = None
    since = 0
    for c in seq:
        if not c["eval"]:
            continue
        if best is None or _payout(c["eval"]["price"]) > _payout(best["eval"]["price"]):
            best, since = c, 0
        else:
            since += 1
            if since >= k:
                return best
    return best


def _pick_late_confirm(seq, k=_K):
    """Enter at the LATEST eligible capture (model sharpest) — but only if the
    edge PERSISTED across >=k eligible captures. A one-shot edge that flickers
    in for a single capture is treated as noise and skipped. This is the
    'place the best bets later' hypothesis, made no-lookahead and noise-robust."""
    elig = [c for c in seq if c["eval"]]
    if len(elig) < k:
        return None
    return elig[-1]


def _pick_peak_edge(seq, k=_K):
    """Lock the best entry price: place at the running-max-edge eligible capture
    once it has not improved for k captures. No lookahead (entry = a past
    capture whose price we already observed)."""
    best = None          # capture with max edge so far
    since = 0            # captures seen since best improved
    for c in seq:
        if not c["eval"]:
            continue
        if best is None or c["eval"]["edge"] > best["eval"]["edge"]:
            best, since = c, 0
        else:
            since += 1
            if since >= k:
                return best  # stopped improving -> commit to the peak
    return best              # timeline ended; commit to best seen (if any)


def _pick_confidence_gated(seq, k=_K):
    """Place at the first eligible capture AFTER the projection stabilises:
    the spread of the last k projections is below the stat's edge threshold
    (i.e. the model has stopped moving). Tends later, only when an edge holds."""
    from src.prediction.bet_thresholds import edge_threshold_for
    projs = []
    for c in seq:
        if c["proj"] is not None:
            projs.append(c["proj"])
        # The stat's own edge threshold doubles as the stability tolerance:
        # once the projection has moved less than that over the last k captures
        # the model has "settled", so an edge that still survives is trusted.
        if c["eval"] and len(projs) >= k:
            window = projs[-k:]
            if (max(window) - min(window)) < edge_threshold_for(c.get("_stat", "")):
                return c
    return None


def _choose(seq, key, policy):
    st = key[1]
    for c in seq:
        c["_stat"] = st
    if policy == "BEST_PRICE":
        return _pick_best_price(seq)
    if policy == "FIRST_EDGE":
        return _pick_first_edge(seq)
    if policy == "LATE_CONFIRM":
        return _pick_late_confirm(seq)
    if policy == "PEAK_EDGE":
        return _pick_peak_edge(seq)
    if policy == "CONFIDENCE_GATED":
        return _pick_confidence_gated(seq)
    return None


# ───────────────────────── line-movement feature ───────────────────────────
def _game_secs_elapsed(period, clock):
    """Elapsed GAME seconds from tip for a capture. clock is time REMAINING in
    the period (e.g. '10:55'); elapsed = (period-1)*720 + (720 - remaining).
    Returns None for pregame / unparseable (so velocity falls back to wall-clock)."""
    if period is None:
        return None
    try:
        p = int(period)
    except (TypeError, ValueError):
        return None
    rem = _clock_secs(clock)
    if rem < 0:
        return None
    # regulation quarters are 720s; OT periods (>4) are 300s each.
    if p <= 4:
        return (p - 1) * 720.0 + (720.0 - rem)
    return 4 * 720.0 + (p - 5) * 300.0 + (300.0 - rem)


def _line_movement(seq, chosen_cap):
    """Line-movement summary across a (player,stat) timeline, framed against the
    chosen bet's side (CONTRACT fields):
      line_open            first capture's line
      line_current         last capture's line
      line_delta           current - open
      line_velocity_per_min  delta per MINUTE of game time elapsed between the
                             open and current capture (falls back to wall-clock
                             minutes, then to 0.0 if neither is available)
      line_dir_vs_proj     'toward' if the line moved the way our projection
                             favors (market agreeing), 'away' if against, 'flat'.
                             OVER: line rising => toward. UNDER: line falling => toward.
    Graceful: always returns the 5 fields; uses safe defaults when the timeline
    is degenerate (single capture, missing lines)."""
    side = (chosen_cap.get("eval") or {}).get("side", "OVER")
    rows = [c for c in seq if c.get("line") is not None]
    rows.sort(key=lambda c: c["ep"])
    if not rows:
        ln = chosen_cap.get("line")
        return {"line_open": ln, "line_current": ln, "line_delta": 0.0,
                "line_velocity_per_min": 0.0, "line_dir_vs_proj": "flat"}
    first, last = rows[0], rows[-1]
    try:
        line_open = float(first["line"])
        line_current = float(last["line"])
    except (TypeError, ValueError):
        ln = chosen_cap.get("line")
        return {"line_open": ln, "line_current": ln, "line_delta": 0.0,
                "line_velocity_per_min": 0.0, "line_dir_vs_proj": "flat"}
    delta = line_current - line_open
    # velocity per minute of GAME time; fall back to wall-clock minutes.
    g0 = _game_secs_elapsed(first.get("period"), first.get("clock"))
    g1 = _game_secs_elapsed(last.get("period"), last.get("clock"))
    mins = None
    if g0 is not None and g1 is not None and g1 > g0:
        mins = (g1 - g0) / 60.0
    if mins is None:
        wall = (last["ep"] - first["ep"]) / 60.0
        mins = wall if wall > 0 else None
    velocity = (delta / mins) if mins else 0.0
    # direction vs our projection: market AGREEING = 'toward'.
    if abs(delta) < 1e-9:
        direction = "flat"
    elif str(side).upper() == "OVER":
        direction = "toward" if delta > 0 else "away"
    else:  # UNDER: line falling toward/below our projection = market agrees
        direction = "toward" if delta < 0 else "away"
    return {"line_open": round(line_open, 2), "line_current": round(line_current, 2),
            "line_delta": round(delta, 2),
            "line_velocity_per_min": round(velocity, 4),
            "line_dir_vs_proj": direction}


# ─────────────────────────────── grading ───────────────────────────────────
def _grade(cap, key, actuals):
    """Build a graded bet row from a chosen capture."""
    st = key[1]
    ev = cap["eval"]
    side, line = ev["side"], cap["line"]
    actual = actuals.get(key)
    hit = None
    net = 0.0
    if actual is not None:
        if abs(actual - line) < 1e-9:
            # Push: bet is a wash — hit stays None, net stays 0.0.
            # _summarize already excludes rows where hit is None from n/hit_pct/ROI.
            pass
        else:
            hit = (actual > line) if side == "OVER" else (actual < line)
            net = _payout(ev["price"]) if hit else -1.0
    return {
        "player": cap["disp"], "stat": st, "side": side, "line": line,
        "price": ev["price"], "ev": ev["ev"], "model_prob": ev["prob"],
        "edge": ev["edge"], "proj": round(cap["proj"], 2) if cap["proj"] is not None else None,
        "entry_label": cap["entry_label"], "entry_stage": cap["stage"],
        "entry_cap": cap["cap"], "entry_ep": cap["ep"],
        "actual": actual, "hit": hit, "net_units": round(net, 3),
    }


def _summarize(bets):
    """Roll up a list of graded bets -> totals + by-stage breakdown."""
    graded = [b for b in bets if b["hit"] is not None]
    n = len(graded)
    hits = sum(1 for b in graded if b["hit"])
    net = round(sum(b["net_units"] for b in graded), 3)
    roi = round(net / n * 100.0, 2) if n else None
    by_stage = {}
    for b in graded:
        s = by_stage.setdefault(b["entry_stage"], {"n": 0, "hits": 0, "net": 0.0})
        s["n"] += 1
        s["hits"] += int(bool(b["hit"]))
        s["net"] += b["net_units"]
    # Order: Pregame first, then Q1..Qn (incl. OT periods Q5/Q6...) by quarter
    # number, then any unrecognised stage label alphabetically. Iterate the
    # UNION of stages actually present so OT bets are never silently dropped.
    def _stage_sort_key(stg):
        if stg == "Pregame":
            return (0, 0, "")
        if len(stg) > 1 and stg[0] == "Q" and stg[1:].isdigit():
            return (1, int(stg[1:]), "")
        return (2, 0, stg)

    stage_rows = []
    for stg in sorted(by_stage, key=_stage_sort_key):
        d = by_stage[stg]
        stage_rows.append({"stage": stg, "n": d["n"], "hits": d["hits"],
                           "hit_pct": round(d["hits"] / d["n"] * 100, 1),
                           "net_units": round(d["net"], 3),
                           "roi": round(d["net"] / d["n"] * 100, 1)})
    return {"n": n, "hits": hits,
            "hit_pct": round(hits / n * 100, 1) if n else None,
            "net_units": net, "roi": roi, "by_stage": stage_rows}


# ─────────────────────── projection accuracy by stage ──────────────────────
def _stage_accuracy(canon_gid, actuals):
    """pts-projection MAE at each quarter break (the 'model sharpens into Q3'
    signal that justifies the timing rationale)."""
    from api.courtvision_router import (_end_of_quarter_snapshots,
                                        _project_at_snapshot_map)
    eoq = _end_of_quarter_snapshots(canon_gid)
    out = []
    for period in (1, 2, 3, 4):
        snap = eoq.get(period)
        if not snap:
            continue
        pm = _project_at_snapshot_map(snap)
        errs = [abs(v - actuals[(nm, st)]) for (nm, st), v in pm.items()
                if (nm, st) in actuals and st == "pts"]
        if errs:
            out.append({"period": period, "pts_mae": round(sum(errs) / len(errs), 2)})
    return out


# ───────────────────────────── public engine ───────────────────────────────
def build_game_timing(canon_gid=None, settled_date=None, write=True):
    """Full timing analysis for one game. Returns the payload dict and (by
    default) persists it to data/cache/cv_fix/bet_timing_<gid>.json."""
    from api.courtvision_router import (_last_completed_game_date,
                                        _box_score_from_snapshot)
    from api._courtvision_odds import resolve_game_id

    if canon_gid is None:
        settled_date = settled_date or _last_completed_game_date()
        canon_gid = _resolve_last_game_gid(settled_date)
    alias = resolve_game_id(canon_gid)
    canon_ids = sorted(alias.get("canonical_ids", frozenset([canon_gid]))) or [canon_gid]

    snaps, true_final = _load_snapshots(canon_ids)
    if true_final is None and snaps:
        true_final = snaps[-1][2]  # no FINAL yet -> latest state (live)
    if settled_date is None and true_final is not None:
        from api.courtvision_router import _et_date_from_iso
        settled_date = _et_date_from_iso(true_final.get("captured_at") or "")

    # TRUE-FINAL actuals (max-total final snapshot)
    actuals: dict = {}
    away = home = ""
    score_away = score_home = None
    if true_final is not None:
        away = (true_final.get("away_team") or "").upper()
        home = (true_final.get("home_team") or "").upper()
        score_away = true_final.get("away_score")
        score_home = true_final.get("home_score")
        for pl in (true_final.get("players") or []):
            nm = (pl.get("name") or "").lower()
            if not nm:
                continue
            for st in STATS:
                v = pl.get(st)
                if v is not None:
                    try:
                        actuals[(nm, st)] = float(v)
                    except (TypeError, ValueError):
                        pass

    carry = _CarryForward(snaps)
    boundary = _BoundaryProjector(snaps)
    inplay = _load_inplay(settled_date, canon_ids)
    player_filter = {k[0] for k in actuals} or {r["name"] for r in inplay}
    pregame = _load_pregame_t0(canon_gid, settled_date, player_filter)
    key_caps = _build_key_captures(inplay, pregame, carry, boundary,
                                   settled_date=settled_date)

    # Per-policy: choose one entry per key, grade, summarize.
    policies_out: dict = {}
    chosen_by_key: dict = {}
    for pol in POLICIES:
        bets = []
        for key, seq in key_caps.items():
            cap = _choose(seq, key, pol)
            if cap is None:
                continue
            graded = _grade(cap, key, actuals)
            graded["policy"] = pol
            # LINE-MOVEMENT (CONTRACT): attach open/current/delta/velocity/dir
            # vs our projection so /results can show if the market confirmed us.
            graded.update(_line_movement(seq, cap))
            bets.append(graded)
            chosen_by_key.setdefault(key, {})[pol] = graded
        bets.sort(key=lambda b: b["entry_ep"])
        summ = _summarize(bets)
        summ["bets"] = bets
        policies_out[pol] = summ

    # Learned per-stat policy (falls back to FIRST_EDGE before enough samples).
    model = _load_or_default_model()
    candidates = []
    for key, per_pol in chosen_by_key.items():
        st = key[1]
        pol = (model.get(st) or {}).get("policy", _DEFAULT_POLICY)
        bet = per_pol.get(pol) or per_pol.get(_DEFAULT_POLICY) or per_pol.get("FIRST_EDGE")
        if bet:
            candidates.append(bet)
    # SELECTIVITY: the agent does NOT bet every edge — it places only its best-N
    # by CONVICTION. Rank by calibrated P(win) (raw EV over-weights plus-money
    # longshots, which on a blowout are the pace-mirage OVERs that all miss),
    # tie-broken by EV. Then render chronologically.
    candidates.sort(key=lambda b: (-(b["model_prob"] or 0), -(b["ev"] or 0)))
    chosen_bets = candidates[:_BET_CAP]
    chosen_bets.sort(key=lambda b: b["entry_ep"])
    chosen_summary = _summarize(chosen_bets)

    box = _box_score_from_snapshot(true_final) if true_final is not None else []

    # ── In-game projection on the box score: attach the model's IN-GAME read
    # (sharpest available PBP boundary, carried to end of game) next to each
    # player's actual, so the page proves the in-game model knew the result.
    ingame_map, ingame_label, _bep = (boundary.proj_at(10**18)
                                      if boundary.available() else (None, None, None))
    bet_players = {(b["player"] or "").lower() for b in chosen_bets}
    # Derive starters from minutes (top-5 per team): the scraper's is_starter
    # field is unreliable (uniformly True), so the snapshot ★ is meaningless.
    _by_team: dict = {}
    for row in box:
        _by_team.setdefault(row.get("team") or "", []).append(row)
    _starter_set = set()
    for _tm, _rows in _by_team.items():
        for _r in sorted(_rows, key=lambda r: -(r.get("min") or 0))[:5]:
            _starter_set.add(id(_r))
    ingame_errs = []
    for row in box:
        nm = (row["player_name"] or "").lower()
        pp = (ingame_map or {}).get((nm, "pts"))
        row["proj_pts"] = round(pp, 1) if pp is not None else None
        row["has_bet"] = nm in bet_players
        row["starter"] = id(row) in _starter_set
        if pp is not None and row.get("pts") is not None:
            try:
                ingame_errs.append(abs(float(pp) - float(row["pts"])))
            except (TypeError, ValueError):
                pass
    ingame_proj_mae = round(sum(ingame_errs) / len(ingame_errs), 2) if ingame_errs else None

    # ── WHEN-TO-BET summary (the equation/finding): the side never flips, so
    # timing only changes price -> bet at the best price for your side.
    flips = total = 0
    for seq in key_caps.values():
        sides = {c["eval"]["side"] for c in seq if c["eval"]}
        if sides:
            total += 1
            flips += int(len(sides) > 1)
    when_to_bet = {
        "rule": ("Bet at the BEST PRICE for your side. The side (over/under) is "
                 "fixed once an edge exists, so WHEN you bet changes only your "
                 "payout — not whether you win. Chasing the biggest edge (earliest, "
                 "noisiest) gets the worst odds."),
        "equation": "best_T = argmax over eligible captures of payout(price_T)  (side is constant)",
        "side_flip_pct": round(100 * flips / total, 1) if total else None,
        "policy_roi": {pol: policies_out[pol]["roi"] for pol in POLICIES},
        "default_policy": _DEFAULT_POLICY,
    }

    payload = {
        "game_id": canon_gid,
        "canonical_ids": canon_ids,
        "settled_date": settled_date,
        "away": away, "home": home,
        "score_away": score_away, "score_home": score_home,
        "true_final_captured_at": (true_final or {}).get("captured_at"),
        "n_snapshots": len(snaps),
        "n_inplay_captures": len(inplay),
        "stage_accuracy": _stage_accuracy(canon_gid, actuals) if actuals else [],
        "ingame_proj_mae": ingame_proj_mae,
        "ingame_proj_source": ingame_label,
        "when_to_bet": when_to_bet,
        "policies": policies_out,
        "chosen": {"policy_by_stat": {st: (model.get(st) or {}).get("policy", _DEFAULT_POLICY)
                                      for st in STATS},
                   "summary": chosen_summary, "bets": chosen_bets},
        "box_score": box,
    }
    if write:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / f"bet_timing_{canon_gid}.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _resolve_last_game_gid(settled_date):
    """NBA gid of the MOST-RECENTLY-completed game on settled_date.

    Tiebreak by LATEST FINAL capture (filename epoch), NOT max total score —
    multiple games can carry the same ET date (incl. stale re-captures of old
    games), and max-total would wrongly pick a higher-scoring earlier game.
    This mirrors _last_completed_game_date()'s latest-epoch semantics."""
    from api.courtvision_router import _et_date_from_iso
    best = (-1, None)  # (latest filename epoch, gid)
    latest_by_gid: dict = {}
    for p in LIVE_DIR.glob("*.json"):
        gid, _, ep = p.stem.rpartition("_")
        try:
            ep_i = int(ep)
        except ValueError:
            continue
        if gid and (gid not in latest_by_gid or ep_i > latest_by_gid[gid][0]):
            latest_by_gid[gid] = (ep_i, p)
    for gid, (ep_i, p) in latest_by_gid.items():
        try:
            s = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "FINAL" not in str(s.get("game_status") or "").upper():
            continue
        if settled_date and _et_date_from_iso(s.get("captured_at") or "") != settled_date:
            continue
        if ep_i > best[0]:
            best = (ep_i, gid)
    return best[1]


# ──────────────────────────── cross-game learner ───────────────────────────
def _load_or_default_model():
    try:
        return json.loads(MODEL_PATH.read_text(encoding="utf-8")).get("by_stat", {})
    except Exception:
        return {}


def learn_across_games(write=True):
    """Pool every bet_timing_<gid>.json and pick, PER STAT, the (policy, stage)
    with the best ROI on a large-enough sample. Writes bet_timing_model.json."""
    pooled: dict = {}  # stat -> policy -> list[bet]
    # NB: exclude bet_timing_model.json — the glob would otherwise pool the
    # model file itself as if it were a game (it has no `policies`).
    files = [f for f in sorted(glob.glob(str(CACHE_DIR / "bet_timing_*.json")))
             if not f.endswith("bet_timing_model.json")]
    for fp in files:
        try:
            data = json.loads(Path(fp).read_text(encoding="utf-8"))
        except Exception:
            continue
        for pol, summ in (data.get("policies") or {}).items():
            for b in summ.get("bets", []):
                if b.get("hit") is None:
                    continue
                pooled.setdefault(b["stat"], {}).setdefault(pol, []).append(b)

    by_stat: dict = {}
    for st in STATS:
        per_pol = pooled.get(st, {})
        best = None
        for pol, bets in per_pol.items():
            n = len(bets)
            # SAMPLE-WEIGHTING: a policy with too few graded bets is not a
            # trustworthy ROI estimate — skip it from RANKING so an n=1 roi=+100
            # fluke can't beat an n=50 roi=+15. If none qualify we fall through
            # to the _DEFAULT_POLICY (the stat-level trust guard still applies).
            if n < _MIN_POLICY_N:
                continue
            net = sum(b["net_units"] for b in bets)
            roi = net / n * 100.0 if n else 0.0
            # best stage window within this policy
            stage_pool: dict = {}
            for b in bets:
                stage_pool.setdefault(b["entry_stage"], []).append(b)
            stage_pref, stage_roi, stage_n = None, None, 0
            for stg, sbets in stage_pool.items():
                sroi = sum(x["net_units"] for x in sbets) / len(sbets) * 100.0
                if stage_pref is None or sroi > stage_roi:
                    stage_pref, stage_roi, stage_n = stg, round(sroi, 1), len(sbets)
            cand = {"policy": pol, "n": n, "roi": round(roi, 2),
                    "stage_pref": stage_pref, "stage_roi": stage_roi, "stage_n": stage_n}
            if best is None or cand["roi"] > best["roi"]:
                best = cand
        # Trust guard uses the WINNING policy's own sample size — NOT the sum
        # across policies (which counts the same opportunity once per policy).
        if best and best["n"] >= _MIN_POOL:
            by_stat[st] = {**best, "trusted": True}
        else:
            best_n = best["n"] if best else 0
            by_stat[st] = {"policy": _DEFAULT_POLICY, "n": best_n, "roi": None,
                           "stage_pref": None, "trusted": False,
                           "note": f"best policy has only {best_n} pooled bets "
                                   f"(<{_MIN_POOL}); default {_DEFAULT_POLICY}"}
    out = {"by_stat": by_stat, "n_games": len(files), "min_pool": _MIN_POOL}
    if write:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        MODEL_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


# ─────────────────────────── /results integration ──────────────────────────
def results_block_for_last_game():
    """Build the single settled-game block consumed by /results: a chronological
    bet log (each bet placed once at its chosen entry), agent summary, by-stage
    breakdown, projection accuracy, box score, final score. None if no game."""
    from api.courtvision_router import _last_completed_game_date
    settled_date = _last_completed_game_date()
    if not settled_date:
        return None
    gid = _resolve_last_game_gid(settled_date)
    if not gid:
        return None
    pay = build_game_timing(canon_gid=gid, settled_date=settled_date, write=True)
    ch = pay["chosen"]

    def _tier(p):
        if p is None:
            return ("Lean", 0)
        if p >= 0.70:
            return ("High", 3)
        if p >= 0.62:
            return ("Solid", 2)
        return ("Lean", 1)

    # Chronological timeline (WHEN each bet fires through the game).
    log = []
    for i, b in enumerate(sorted(ch["bets"], key=lambda x: x["entry_ep"])):
        tier, trank = _tier(b["model_prob"])
        log.append({
            "rank": i + 1,
            "player_name": b["player"], "stat": b["stat"], "side": b["side"],
            "line": b["line"], "odds": b["price"], "ev_pct": b["ev"],
            "model_prob": b["model_prob"], "conf_pct": round((b["model_prob"] or 0) * 100),
            "conf_tier": tier, "proj": b["proj"], "edge": b["edge"],
            "entry_label": b["entry_label"], "entry_stage": b["entry_stage"],
            "actual": b["actual"], "hit": b["hit"], "policy": b["policy"],
            # LINE-MOVEMENT (CONTRACT): did the market confirm our edge?
            "line_open": b.get("line_open"), "line_current": b.get("line_current"),
            "line_delta": b.get("line_delta"),
            "line_velocity_per_min": b.get("line_velocity_per_min"),
            "line_dir_vs_proj": b.get("line_dir_vs_proj"),
        })
    # TOP PLAYS (WHAT to bet) — same bets ranked by model confidence desc.
    top_plays = [dict(r, play_rank=j + 1) for j, r in enumerate(
        sorted(log, key=lambda r: -(r["model_prob"] or 0)))]
    summ = ch["summary"]
    return {
        "game_id": gid, "game_date": settled_date,
        "away": pay["away"], "home": pay["home"],
        "score_away": pay["score_away"], "score_home": pay["score_home"],
        "status": "final",
        "bet_log": log,
        "top_plays": top_plays,
        "powered_by": ["in-game PBP projection", "learned-Q4-minutes", "foul residual",
                       "blowout residual", "heat-check shrinkage", "period heads",
                       "isotonic edge calibration", "iter61 filter stack"],
        "agent_summary": {
            "n_bets": summ["n"], "n_hit": summ["hits"], "hit_pct": summ["hit_pct"],
            "net_units": summ["net_units"], "roi_pct": summ["roi"],
            "by_stage": summ["by_stage"],
        },
        "stage_accuracy": pay["stage_accuracy"],
        "policy_compare": {pol: {"n": pay["policies"][pol]["n"],
                                 "hit_pct": pay["policies"][pol]["hit_pct"],
                                 "net_units": pay["policies"][pol]["net_units"],
                                 "roi": pay["policies"][pol]["roi"]}
                           for pol in POLICIES},
        "policy_by_stat": ch["policy_by_stat"],
        "box_score": pay["box_score"],
        "n_inplay_captures": pay["n_inplay_captures"],
        "when_to_bet": pay["when_to_bet"],
        "ingame_proj_mae": pay["ingame_proj_mae"],
        "ingame_proj_source": pay["ingame_proj_source"],
    }


# ──────────────────────────────────── CLI ──────────────────────────────────
def _print_summary(pay):
    print(f"\n=== {pay['away']} @ {pay['home']}  {pay['settled_date']}  "
          f"({pay['score_away']}-{pay['score_home']})  gid={pay['game_id']} ===")
    print(f"snapshots={pay['n_snapshots']}  inplay_captures={pay['n_inplay_captures']}")
    print(f"projection pts-MAE by stage: " +
          ", ".join(f"Q{s['period']}={s['pts_mae']}" for s in pay["stage_accuracy"]))
    print(f"in-game model pts-MAE on final box ({pay.get('ingame_proj_source')}): "
          f"{pay.get('ingame_proj_mae')}")
    wtb = pay["when_to_bet"]
    print(f"\nWHEN TO BET: {wtb['rule']}")
    print(f"  equation: {wtb['equation']}")
    print(f"  side-flip rate this game: {wtb['side_flip_pct']}%  (0 => timing only affects PRICE)")
    print("\nPOLICY COMPARISON (1u flat, graded vs true final):")
    print(f"  {'policy':<18}{'n':>4}{'hit%':>7}{'net_u':>9}{'roi%':>8}")
    for pol in POLICIES:
        s = pay["policies"][pol]
        print(f"  {pol:<18}{s['n']:>4}{(s['hit_pct'] or 0):>7}{s['net_units']:>9}{(s['roi'] or 0):>8}")
        for st in s["by_stage"]:
            print(f"      {st['stage']:<8} n={st['n']:<3} hit%={st['hit_pct']:<6} "
                  f"net={st['net_units']:<7} roi%={st['roi']}")
    ch = pay["chosen"]
    print(f"\nCHOSEN (learned per-stat policy): n={ch['summary']['n']} "
          f"hit%={ch['summary']['hit_pct']} net={ch['summary']['net_units']}u "
          f"roi%={ch['summary']['roi']}")


def main(argv):
    gid = argv[1] if len(argv) > 1 else None
    pay = build_game_timing(canon_gid=gid)
    _print_summary(pay)
    model = learn_across_games()
    print("\n=== CROSS-GAME LEARNED MODEL (bet_timing_model.json) ===")
    print(f"games pooled: {model['n_games']}  (min pool to trust: {model['min_pool']})")
    for st, m in model["by_stat"].items():
        tag = "TRUSTED" if m.get("trusted") else "default"
        print(f"  {st:<5} -> {m['policy']:<16} stage={m.get('stage_pref')}  "
              f"n={m['n']} roi={m.get('roi')}  [{tag}]")
    # Re-emit chosen with the freshly-learned model so the persisted game file
    # reflects the current model.
    build_game_timing(canon_gid=pay["game_id"], settled_date=pay["settled_date"])
    print(f"\nwrote data/cache/cv_fix/bet_timing_{pay['game_id']}.json + bet_timing_model.json")


if __name__ == "__main__":
    import sys
    main(sys.argv)
