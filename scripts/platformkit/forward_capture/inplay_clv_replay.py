"""OFFLINE in-play CLV replay harness -- did a live engine's repriced number BEAT the close?

This is the in-game sibling of clv.py. Where clv.py grades ONE logged pregame prediction
against ONE captured devigged close, this harness replays a captured IN-PLAY price SERIES for
one market and asks, tick-by-tick and leak-free, whether the engine's live repriced number
anticipated the in-play CLOSING line -- i.e. whether you could have BEAT the close by taking
the engine's side at the obtainable price.

CONVENTION (matches src/betting/clv.py and forward_capture/clv.py): CLV is reported in
PROBABILITY space, positive = you BEAT the close (got a better/earlier number than where the
market closed). There is NO $ / ROI / stake / edge figure here -- only calibration-style CLV.

CANONICAL TICK SCHEMA (one captured series = list[dict], one market, sorted by ts):
    {"sport": str, "game_id": str, "venue": str, "market_type": str, "side": str,
     "ticker": str, "prob": float (market implied YES prob in [0,1]), "ts": str (ISO-8601 UTC)}

LEAK FLOOR: model_fn sees only history_so_far = series[:i+1] (ticks up to and INCLUDING the
current one) -- never the eventual outcome, never the close. The close is derived AFTER scoring
from the last tick; the model never receives it.

CLV MATH (per scored tick i, excluding the final close tick):
    edge_i           = model_prob_i - market_prob_i        # model's divergence from price
    realized_move_i  = close_prob    - market_prob_i        # how the market moved toward close
    clv_realized_i   = +|realized_move_i| if sign(edge_i)==sign(realized_move_i)
                       else -|realized_move_i|
  -> positive when the model leaned the SAME direction the market later moved (you beat the
     obtainable price); negative when it leaned the wrong way.

VERDICT (gated, honest):
    BEAT   if mean_clv > +eps AND hit_rate > 0.5 AND n_scored >= MIN_TICKS
    BEHIND if mean_clv < -eps
    INSUFFICIENT_DATA if n_scored < MIN_TICKS  (an honest "can't tell yet", NOT a beat)
    MATCH  otherwise (within noise)

Stdlib only. ASCII only. <=300 LOC. Per-file test: tests/platformkit/test_inplay_clv_replay.py.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Callable, List, Optional

# A model_fn repriced-number callback. Signature:
#   model_fn(tick: dict, history_so_far: list[dict]) -> float (model YES prob in [0,1])
# history_so_far is series[:i+1] -- ticks up to AND INCLUDING `tick`. Leak-free: it must NEVER
# look at the eventual outcome or the close.
ModelFn = Callable[[dict, List[dict]], float]

EPS_DEFAULT = 0.005
MIN_TICKS_DEFAULT = 8

REQUIRED_KEYS = ("sport", "game_id", "venue", "market_type", "side", "ticker", "prob", "ts")


# --------------------------------------------------------------------------------------- #
# Loading / validation                                                                    #
# --------------------------------------------------------------------------------------- #
def load_series(path: str) -> List[dict]:
    """Read a JSONL fixture of canonical tick-dicts, sort by ts, validate prob in [0,1].

    One JSON object per line (the captured series for ONE market). Blank lines are skipped.
    Raises ValueError on a malformed prob or a missing required key so a bad fixture fails
    loudly rather than silently producing a bogus verdict.
    """
    ticks: List[dict] = []
    with open(path, encoding="utf-8") as fh:
        for ln, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {ln}: bad JSON: {exc}") from exc
            _validate_tick(rec, ln)
            ticks.append(rec)
    ticks.sort(key=lambda t: str(t["ts"]))
    return ticks


def _validate_tick(rec: dict, ctx) -> None:
    if not isinstance(rec, dict):
        raise ValueError(f"{ctx}: tick is not an object")
    for k in REQUIRED_KEYS:
        if k not in rec:
            raise ValueError(f"{ctx}: missing required key {k!r}")
    p = rec["prob"]
    try:
        p = float(p)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{ctx}: prob is not a float: {rec['prob']!r}") from exc
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"{ctx}: prob {p} out of [0,1]")


# --------------------------------------------------------------------------------------- #
# Baseline model                                                                          #
# --------------------------------------------------------------------------------------- #
def naive_market_follow_model(tick: dict, history: List[dict]) -> float:
    """Baseline: the model IS the market (model_prob == market_prob).

    A model that just copies the obtainable price has edge_i == 0 on every tick, so it can
    never lean toward the close -> it MUST yield MATCH / INSUFFICIENT_DATA, never BEAT. Used as
    the correctness anchor: if this ever scores BEAT, the harness sign logic is broken.
    """
    return float(tick["prob"])


# --------------------------------------------------------------------------------------- #
# Result                                                                                  #
# --------------------------------------------------------------------------------------- #
@dataclass
class ReplayResult:
    """One in-play replay verdict for ONE market. mean_clv is PROBABILITY space; no $ field."""
    verdict: str          # BEAT | BEHIND | MATCH | INSUFFICIENT_DATA
    mean_clv: float       # mean clv_realized over scored ticks (probability space)
    hit_rate: float       # fraction of scored ticks where model leaned toward the close
    n_ticks_scored: int   # ticks scored (final close tick excluded)
    span_seconds: float   # wall-clock span of the scored series
    market_type: str
    game_id: str
    venue: str

    def as_dict(self) -> dict:
        return asdict(self)


def _sign(x: float, eps: float = 1e-12) -> int:
    if x > eps:
        return 1
    if x < -eps:
        return -1
    return 0


def _span_seconds(ticks: List[dict]) -> float:
    """Wall-clock span of the series in seconds; 0.0 if timestamps are unparsable."""
    if len(ticks) < 2:
        return 0.0
    from datetime import datetime

    def _parse(ts: str):
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            return None

    a, b = _parse(ticks[0]["ts"]), _parse(ticks[-1]["ts"])
    if a is None or b is None:
        return 0.0
    return abs((b - a).total_seconds())


# --------------------------------------------------------------------------------------- #
# The harness                                                                             #
# --------------------------------------------------------------------------------------- #
def replay_series(series: List[dict],
                  model_fn: ModelFn,
                  eps: float = EPS_DEFAULT,
                  min_ticks: int = MIN_TICKS_DEFAULT) -> ReplayResult:
    """Replay a captured in-play price series vs an engine's repriced number; honest verdict.

    series:    list of canonical tick-dicts for ONE market, sorted by ts (already sorted by
               load_series; re-sorted here defensively).
    model_fn:  model_fn(tick, history_so_far) -> model YES prob in [0,1]. LEAK-FREE -- it is
               handed history_so_far = series[:i+1] only (no outcome, no close).
    eps:       deadband around 0 for the BEAT/BEHIND/MATCH call (default 0.005).
    min_ticks: below this many scored ticks the verdict is INSUFFICIENT_DATA (default 8) -- an
               honest "can't tell", never a BEAT.

    The CLOSE = the last tick's market prob (the in-play closing line). The final tick is
    EXCLUDED from scoring (you cannot beat the close at the close). Returns a ReplayResult.
    """
    ticks = sorted(series, key=lambda t: str(t["ts"]))
    n = len(ticks)
    meta = _meta(ticks)
    if n < 2:
        return ReplayResult("INSUFFICIENT_DATA", 0.0, 0.0, 0, 0.0, *meta)

    close_prob = float(ticks[-1]["prob"])
    clvs: List[float] = []
    hits = 0
    for i in range(n - 1):  # exclude the final close tick
        tick = ticks[i]
        market_prob = float(tick["prob"])
        model_prob = float(model_fn(tick, ticks[: i + 1]))
        model_prob = min(1.0, max(0.0, model_prob))  # clamp defensively to [0,1]

        edge = model_prob - market_prob
        realized_move = close_prob - market_prob
        mag = abs(realized_move)
        if _sign(edge) == 0 or _sign(realized_move) == 0:
            clv = 0.0  # no lean (model==market) or no move -> neither beat nor behind
        elif _sign(edge) == _sign(realized_move):
            clv = mag
            hits += 1
        else:
            clv = -mag
        clvs.append(clv)

    n_scored = len(clvs)
    mean_clv = sum(clvs) / n_scored if n_scored else 0.0
    hit_rate = hits / n_scored if n_scored else 0.0
    span = _span_seconds(ticks)

    verdict = _verdict(mean_clv, hit_rate, n_scored, eps, min_ticks)
    return ReplayResult(verdict, float(mean_clv), float(hit_rate), int(n_scored),
                        float(span), *meta)


def _verdict(mean_clv: float, hit_rate: float, n_scored: int,
             eps: float, min_ticks: int) -> str:
    if n_scored < min_ticks:
        return "INSUFFICIENT_DATA"
    if mean_clv > eps and hit_rate > 0.5:
        return "BEAT"
    if mean_clv < -eps:
        return "BEHIND"
    return "MATCH"


def _meta(ticks: List[dict]):
    if not ticks:
        return ("", "", "")
    t0 = ticks[0]
    return (str(t0.get("market_type", "")), str(t0.get("game_id", "")),
            str(t0.get("venue", "")))


# --------------------------------------------------------------------------------------- #
# Reporting                                                                               #
# --------------------------------------------------------------------------------------- #
def format_report(result: ReplayResult) -> str:
    """ASCII summary of one in-play replay verdict. No $ figure -- CLV is probability space."""
    r = result
    lines = [
        "=== In-play CLV replay (offline, honest) ===",
        f"market    : {r.market_type}",
        f"game_id   : {r.game_id}",
        f"venue     : {r.venue}",
        f"verdict   : {r.verdict}",
        f"mean_clv  : {r.mean_clv:+.4f}  (probability space; + = beat the close)",
        f"hit_rate  : {r.hit_rate:.3f}  (lean-toward-close fraction)",
        f"n_scored  : {r.n_ticks_scored}  (final close tick excluded)",
        f"span_sec  : {r.span_seconds:.1f}",
        "units     : probability (CLV / calibration only -- never dollars)",
    ]
    return "\n".join(lines)


__all__ = [
    "ReplayResult", "ModelFn", "replay_series", "load_series",
    "naive_market_follow_model", "format_report",
    "EPS_DEFAULT", "MIN_TICKS_DEFAULT",
]
