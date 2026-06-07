"""Routed in-game player-line ensemble — per-(stat, game-time) head selection.

WHY THIS MODULE EXISTS
----------------------
No single in-game player-line head wins everywhere on the HELD-OUT walk-forward
curve. Measured truth (``.planning/ingame/eval_curve_v2.json`` — leak-free,
train-dates < test-dates, n=399 dated PBP games, the curve for the head that is
ACTUALLY deployed: the v2 clock-conditioned SBS head served via
``project_player_lines_v2``):

  * Before the first measured grid point (game-elapsed < 360s ~ first 6 min):
    NO held-out v2 measurement exists that early, and the larger n=598 curve
    (``eval_curve.json``) + the standing gate both say defer to **pregame-L5**
    (season form). So the router uses pregame-L5 in that opening window.
  * 06min(midQ1) -> 18min(midQ2): the **v2** head is the held-out per-cell
    winner on every stat.
  * From ~endQ2 onward a few low-variance stats (blk, then fg3m, then late pts/
    stl) cross over to the **production snapshot** projector, and by midQ4 the
    snapshot wins most of them. The exact crossover is PER STAT.

This module does NOT hand-pick those boundaries. It LOADS the held-out curve,
computes the per-(stat, bucket) arg-min over the three DEPLOYABLE heads
(pregame_l5 / v2 / snapshot), and routes to that winner — with a smooth linear
blend across the bucket midpoints so the served value has no discontinuity as the
game clock advances.

HARD HONESTY
------------
  * The routing weights come ONLY from the held-out eval curve (loaded at import
    from ``eval_curve_v2.json``); they are NOT fit on any test set here.
  * The router can never beat the best individual head at a bucket by more than
    that head — at a bucket CENTER the blend weight is 1.0 on the measured
    winner, so the routed value == the winning head there (verified in tests).
    Between centers it linearly interpolates to the neighbouring bucket's winner.
  * A routed head is a WIN only if, evaluated walk-forward on held-out games over
    the full game-time grid, it is >= the best individual head at each bucket AND
    beats production overall. That claim is for the eval harness
    (``scripts/ingame/eval_routed_ensemble.py``) to substantiate; this module is
    the deployable router, gated default-OFF.
  * Granularity: per-EVENT (a state row), NOT per-second. The clock only changes
    WHICH heads are blended and the blend weight; the point value moves on real
    state. No sub-event resolution is claimed.

GATING
------
Everything is behind ``CV_INGAME_SBS`` (default OFF) via the canonical
``src.ingame.sbs_shadow.is_enabled``. With the flag OFF, ``project_player_lines_
routed`` returns the production snapshot projection for that player (byte-equal to
what the production head would serve), so wiring it changes no served value until
an operator opts in. ADDITIVE; no live default touched.

GPU: the v2 head probes cuda with CPU fallback (inherited from the v2 loader);
the L5 and snapshot heads are pure CPU arithmetic.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Canonical flag + clock/grid helpers (ONE flag reader for the whole SBS surface).
from src.ingame.sbs_shadow import (
    SBS_FLAG,
    is_enabled,
    PLAYER_STATS,
    GRID_SEC,
    GRID_LABELS,
    parse_clock_remaining_sec,
    game_elapsed_sec,
)

ROOT = Path(__file__).resolve().parent.parent.parent
EVAL_CURVE_V2 = ROOT / ".planning" / "ingame" / "eval_curve_v2.json"

# The three DEPLOYABLE heads, in the eval-curve key namespace. (v2_pace is the
# eval key for the served v2 head; the live snapshot lacks team FGA/FGM so the
# served path uses the v2 CORE feature subset, but the head/model is the same
# clock-conditioned v2 booster the curve measured — we route on the v2 column.)
HEADS: Tuple[str, ...] = ("pregame_l5", "v2", "snapshot")

# Map a HEADS name -> the column name(s) it may appear under in the eval curve.
# We try each in order and take the first present. The DEPLOYED head is v2_core
# (the live path uses the core feature subset, not the pace variant which requires
# team FGA/FGM unavailable in the live snapshot). Route on v2_core only so that
# endQ3 stl/tov are not mis-routed to "v2" when the deployed head cannot match
# v2_pace MAE there.
_EVAL_KEYS_FOR_HEAD: Dict[str, Tuple[str, ...]] = {
    "pregame_l5": ("pregame_l5",),
    "v2": ("v2_core",),
    "snapshot": ("snapshot",),
}

# Game-elapsed centre (seconds) of each eval bucket == the GRID_SEC value itself
# (the curve buckets a snapshot to the NEAREST grid point, so the grid point is
# the bucket centre). Sorted ascending.
_BUCKET_CENTERS: Tuple[int, ...] = tuple(sorted(GRID_SEC))

# Below the first measured grid centre we have NO held-out v2 evidence; defer to
# pregame-L5 (season form). This mirrors sbs_shadow.grid_bucket_for's "pregame"
# decision for elapsed < first grid point.
_PREGAME_FALLBACK_HEAD = "pregame_l5"


# --------------------------------------------------------------------------- #
# Routing table — derived from the HELD-OUT eval curve (NOT hand-fit).
# --------------------------------------------------------------------------- #
def _load_curve(path: Path = EVAL_CURVE_V2) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _head_value_in_cell(cell: Dict[str, Any], head: str) -> Optional[float]:
    """Pull a head's held-out MAE from one (stat, bucket) cell, or None."""
    for k in _EVAL_KEYS_FOR_HEAD[head]:
        v = cell.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def build_routing_table(
    curve: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[int, str]]:
    """Per-(stat, bucket-centre-sec) held-out arg-min head.

    Returns ``{stat: {grid_sec: winning_head_name}}``. The winner at a bucket is
    the head with the LOWEST held-out MAE among the deployable HEADS in that
    cell. Buckets/stats absent from the curve are simply omitted (the resolver
    falls back to the nearest present bucket / pregame).
    """
    if curve is None:
        curve = _load_curve()
    pc = curve.get("player_curve", {})
    # label -> grid_sec
    label_to_sec = {lbl: sec for sec, lbl in GRID_LABELS.items()}

    table: Dict[str, Dict[int, str]] = {s: {} for s in PLAYER_STATS}
    for label, per_stat in pc.items():
        sec = label_to_sec.get(label)
        if sec is None:
            continue
        for stat in PLAYER_STATS:
            cell = per_stat.get(stat)
            if not cell:
                continue
            scored = {
                h: _head_value_in_cell(cell, h)
                for h in HEADS
            }
            scored = {h: v for h, v in scored.items() if v is not None}
            if not scored:
                continue
            table[stat][sec] = min(scored, key=scored.get)
    return table


# Built once at import from the held-out curve. If the curve file is missing
# (e.g. a fresh clone without .planning/), we degrade to an evidence-free table
# that routes everything to the production snapshot (safe: == production).
try:
    ROUTING_TABLE: Dict[str, Dict[int, str]] = build_routing_table()
except Exception:  # pragma: no cover - missing curve in a bare clone
    ROUTING_TABLE = {s: {} for s in PLAYER_STATS}


# --------------------------------------------------------------------------- #
# Blend resolver — smooth handoff across bucket centres.
# --------------------------------------------------------------------------- #
def _lateq4_v2_on() -> bool:
    """CV_INGAME_LATEQ4_V2 — read per-call so golive's env + tests both take effect."""
    return os.environ.get("CV_INGAME_LATEQ4_V2", "").strip().lower() in ("1", "true", "yes", "on")


# Late-Q4 buckets = 42min/44min/46min game-elapsed (>= 42*60s). The held-out curve
# (n=399) routes pts/reb to `snapshot` here, but on the 1987-game fast cache the v2
# head is BOTH lower-MAE (-11/-12%) AND mean-preserving (bias +-0.04). Re-routing
# late-Q4 pts/reb -> v2 PASSES the 200g AND 500g gate (full -1.26%, pts -1.50/reb
# -1.56%, ast unchanged, mean-preserving = bet-safe). See
# docs/_audits/INGAME_ENSEMBLE_OPTIMALITY.md. Gated default-OFF (byte-identical).
_LATEQ4_SEC = 42 * 60
_LATEQ4_STATS = ("pts", "reb")


def _winner_at_center(stat: str, sec: int) -> str:
    """The held-out winning head for ``stat`` at an exact bucket centre.

    Falls back to the production snapshot if that (stat, centre) is absent from
    the routing table (no held-out evidence -> defer to production).
    """
    base = ROUTING_TABLE.get(stat, {}).get(sec, "snapshot")
    if (_lateq4_v2_on() and stat in _LATEQ4_STATS and sec >= _LATEQ4_SEC
            and base == "snapshot"):
        return "v2"
    return base


def route_weights(stat: str, game_elapsed: float) -> Dict[str, float]:
    """Blend weights over the deployable heads at a game-elapsed-seconds moment.

    Behaviour (all from the held-out routing table + a linear handoff):
      * elapsed <= first bucket centre's "pregame zone": before the FIRST measured
        centre we linearly hand off from the pregame-L5 fallback (at elapsed=0) to
        the first centre's measured winner (at that centre).
      * AT a bucket centre: weight 1.0 on that centre's measured winner (so the
        routed value == the winning head exactly there).
      * BETWEEN two centres: linear interpolation between the two centres' winners
        (a straight-line blend in weight space).
      * AFTER the last centre: weight 1.0 on the last centre's winner (held flat;
        the game is essentially over by the buzzer and the late winner dominates).

    Returns a dict over HEADS summing to 1.0 (heads not involved get 0.0).
    """
    centers = _BUCKET_CENTERS
    w = {h: 0.0 for h in HEADS}
    if not centers:
        w["snapshot"] = 1.0
        return w

    t = float(game_elapsed)
    first, last = centers[0], centers[-1]

    # Opening window: blend pregame-fallback -> first measured winner.
    if t <= first:
        win_first = _winner_at_center(stat, first)
        if t <= 0:
            frac = 0.0
        else:
            frac = max(0.0, min(1.0, t / float(first)))
        w[_PREGAME_FALLBACK_HEAD] += (1.0 - frac)
        w[win_first] += frac
        return w

    # After the last centre: hold the last winner.
    if t >= last:
        w[_winner_at_center(stat, last)] = 1.0
        return w

    # Between two adjacent centres: find the bracketing pair and lerp.
    for i in range(len(centers) - 1):
        lo, hi = centers[i], centers[i + 1]
        if lo <= t <= hi:
            win_lo = _winner_at_center(stat, lo)
            win_hi = _winner_at_center(stat, hi)
            frac = (t - lo) / float(hi - lo) if hi > lo else 1.0
            frac = max(0.0, min(1.0, frac))
            w[win_lo] += (1.0 - frac)
            w[win_hi] += frac
            return w

    # Unreachable, but be safe.
    w["snapshot"] = 1.0
    return w


# --------------------------------------------------------------------------- #
# Per-head value producers (live-deployable).
# --------------------------------------------------------------------------- #
def _l5_value(state_row: Dict[str, Any], stat: str) -> Optional[float]:
    """pregame-L5 projection for a stat: the player's L5 mean.

    Reads the L5 dict the featurizer attached as ``_l5`` (set by
    ``snapshot_to_v2_rows``), else the ``p_prior_<stat>`` column it derived from
    the same L5 mean. None if neither is available (rookie debut: no prior).
    Floored at current accumulation so a projection never drops below reality.
    """
    cur = float(state_row.get(f"p_{stat}_so_far", 0.0) or 0.0)
    l5 = state_row.get("_l5")
    val: Optional[float] = None
    if isinstance(l5, dict) and stat in l5 and l5[stat] is not None:
        val = float(l5[stat])
    else:
        prior = state_row.get(f"p_prior_{stat}")
        if prior is not None:
            # 0.0 here means "no prior recorded" (rookie) -> treat as missing so
            # the router falls through to another head rather than projecting 0.
            pv = float(prior)
            val = pv if pv != 0.0 else None
    if val is None:
        return None
    return max(cur, val)


def _v2_values(
    state_row: Dict[str, Any],
    *,
    projector=None,
) -> Dict[str, float]:
    """SBS v2 head projection for every stat (floored at current by the head)."""
    from src.ingame.continuous_projection import project_player_lines_v2

    return project_player_lines_v2(state_row, projector=projector)


_REG_PERIOD_LEN = 720   # sec in a regulation period (mirrors eval_second_by_second)
_OT_PERIOD_LEN = 300


def _snapshot_values(state_row: Dict[str, Any]) -> Dict[str, float]:
    """Production snapshot projector for every stat from a v2-namespace row.

    Translates the v2 state-row keys (p_<stat>_so_far / game_remaining_min /
    period / score_margin) into the (player_row, game_row) shape the production
    ``baseline_player_snapshot`` expects, then calls it. This is the SAME math as
    ``scripts.predict_in_game.project_snapshot`` for one player (pace x foul x
    blowout), floored at current.

    ``baseline_player_snapshot`` -> ``_grid_period_clock`` reads
    ``elapsed_sec_in_period``, which a live v2 row does not carry, so we derive it
    here from (period, game_remaining_min) against the regulation/OT period grid.
    """
    from scripts.ingame.eval_second_by_second import baseline_player_snapshot

    player_row = {"min_so_far": float(state_row.get("p_min_so_far", 0.0) or 0.0)}
    for s in PLAYER_STATS:
        player_row[s] = float(state_row.get(f"p_{s}_so_far", 0.0) or 0.0)

    period = int(state_row.get("period", 1) or 1)
    if period < 1:
        period = 1
    rem_sec = float(state_row.get("game_remaining_min", 0.0) or 0.0) * 60.0
    # game-elapsed seconds implied by remaining time (reg = 2880, OT extends).
    reg_total = _REG_PERIOD_LEN * 4
    total_sec = reg_total if period <= 4 else reg_total + _OT_PERIOD_LEN * (period - 4)
    elapsed_total = max(0.0, total_sec - rem_sec)
    # elapsed within the CURRENT period (clamped to that period's length).
    if period <= 4:
        period_start = _REG_PERIOD_LEN * (period - 1)
        period_len = _REG_PERIOD_LEN
    else:
        period_start = reg_total + _OT_PERIOD_LEN * (period - 5)
        period_len = _OT_PERIOD_LEN
    elapsed_in_period = min(period_len, max(0.0, elapsed_total - period_start))

    game_row = {
        "period": period,
        "elapsed_sec_in_period": elapsed_in_period,
        "game_remaining_sec": rem_sec,
        "score_margin": float(state_row.get("score_margin", 0.0) or 0.0),
    }
    pf = float(state_row.get("p_pf_so_far", 0.0) or 0.0)
    return baseline_player_snapshot(player_row, game_row, pf)


def _game_elapsed_from_row(state_row: Dict[str, Any]) -> float:
    """Game-elapsed seconds implied by a v2 state row.

    Prefers an explicit ``_grid_sec`` stamp (set by snapshot_to_v2_rows). Else
    derives it from period + game_remaining_min against a 48-min regulation game
    (OT extends total). Pure function of the row's clock fields.
    """
    gs = state_row.get("_grid_sec")
    if gs is not None:
        try:
            return float(gs)
        except (TypeError, ValueError):
            pass
    period = int(state_row.get("period", 1) or 1)
    rem_min = float(state_row.get("game_remaining_min", 0.0) or 0.0)
    reg_total_min = 48.0
    total_min = reg_total_min if period <= 4 else reg_total_min + 5.0 * (period - 4)
    elapsed_min = max(0.0, total_min - rem_min)
    return elapsed_min * 60.0


# --------------------------------------------------------------------------- #
# Public entry
# --------------------------------------------------------------------------- #
def project_player_lines_routed(
    state_row: Dict[str, Any],
    game_time: Optional[float] = None,
    *,
    projector=None,
    return_detail: bool = False,
) -> Dict[str, Any]:
    """Route/blend the per-stat final projection for ONE player's state row.

    Args:
        state_row: a leak-free v2-namespace player state row (the dict shape
            ``src.ingame.sbs_shadow.snapshot_to_v2_rows`` emits: clock features +
            ``p_<stat>_so_far`` + ``p_prior_<stat>`` / ``_l5``). Extra keys are
            ignored; missing box keys default to 0.0.
        game_time: game-ELAPSED seconds. If None, derived from the row's clock
            fields (``_grid_sec`` if present, else period + game_remaining_min).
        projector: optional pre-loaded ``UnifiedPlayerLineProjector`` for the v2
            head (skips disk load; used by tests / a warm server). Only loaded if
            the route actually needs the v2 head at this game_time.
        return_detail: if True, also return the per-stat blend weights and the
            component head values that produced each projection (for grading /
            debugging). Default False (lean payload).

    Returns:
        * Flag OFF -> ``{stat: snapshot_projection}`` for every stat — byte-equal
          to what the production snapshot head serves (pure pass-through; the v2
          head is never loaded). ADDITIVE: no served value changes.
        * Flag ON  -> ``{stat: routed_final_float}`` for every stat, each the
          held-out-weighted blend of the deployable heads at ``game_time``.
          When ``return_detail`` is True, returns
          ``{"projected": {...}, "weights": {stat: {head: w}},
             "components": {stat: {head: value}}, "game_elapsed": float}``.

    Every projection is floored at the player's current accumulation
    (``p_<stat>_so_far``) so it can never regress below what already happened.
    """
    elapsed = float(game_time) if game_time is not None else _game_elapsed_from_row(
        state_row
    )

    # ---- DISABLED: pure pass-through to the production snapshot head. ----
    if not is_enabled():
        snap = _snapshot_values(state_row)
        proj = {s: float(snap.get(s, 0.0)) for s in PLAYER_STATS}
        if return_detail:
            return {
                "projected": proj,
                "weights": {s: {"snapshot": 1.0} for s in PLAYER_STATS},
                "components": {s: {"snapshot": proj[s]} for s in PLAYER_STATS},
                "game_elapsed": elapsed,
                "enabled": False,
            }
        return proj

    # ---- ENABLED: blend the deployable heads per the held-out routing table. ----
    # Decide up front which component heads any stat will need at this moment, so
    # we only pay for the v2 head load/predict when a route actually uses it.
    weights_per_stat: Dict[str, Dict[str, float]] = {
        s: route_weights(s, elapsed) for s in PLAYER_STATS
    }
    need_v2 = any(w.get("v2", 0.0) > 0.0 for w in weights_per_stat.values())
    need_snap = any(w.get("snapshot", 0.0) > 0.0 for w in weights_per_stat.values())

    v2_vals = _v2_values(state_row, projector=projector) if need_v2 else {}
    snap_vals = _snapshot_values(state_row) if need_snap else {}

    proj: Dict[str, float] = {}
    components: Dict[str, Dict[str, float]] = {}
    weights_out: Dict[str, Dict[str, float]] = {}
    for stat in PLAYER_STATS:
        cur = float(state_row.get(f"p_{stat}_so_far", 0.0) or 0.0)
        w = dict(weights_per_stat[stat])

        comp: Dict[str, float] = {}
        if w.get("pregame_l5", 0.0) > 0.0:
            lv = _l5_value(state_row, stat)
            comp["pregame_l5"] = lv  # may be None (no prior)
        if w.get("v2", 0.0) > 0.0:
            comp["v2"] = float(v2_vals.get(stat, cur))
        if w.get("snapshot", 0.0) > 0.0:
            comp["snapshot"] = float(snap_vals.get(stat, cur))

        # If a weighted head produced no value (e.g. L5 missing for a rookie),
        # redistribute its weight to the remaining available heads so the blend
        # stays a proper convex combination (never silently projects 0).
        usable = {h: v for h, v in comp.items() if v is not None}
        wsum = sum(w[h] for h in usable) if usable else 0.0
        if not usable or wsum <= 0.0:
            # last-resort: production snapshot (always computable).
            val = float(snap_vals.get(stat) if need_snap else
                        _snapshot_values(state_row).get(stat, cur))
            proj[stat] = max(cur, val)
            weights_out[stat] = {"snapshot": 1.0}
            components[stat] = {"snapshot": proj[stat]}
            continue

        blended = sum((w[h] / wsum) * usable[h] for h in usable)
        proj[stat] = max(cur, float(blended))
        weights_out[stat] = {h: w[h] / wsum for h in usable}
        components[stat] = {h: float(v) for h, v in usable.items()}

    if return_detail:
        return {
            "projected": proj,
            "weights": weights_out,
            "components": components,
            "game_elapsed": elapsed,
            "enabled": True,
        }
    return proj


__all__ = [
    "SBS_FLAG",
    "is_enabled",
    "PLAYER_STATS",
    "HEADS",
    "EVAL_CURVE_V2",
    "ROUTING_TABLE",
    "build_routing_table",
    "route_weights",
    "project_player_lines_routed",
]
