"""scripts.platformkit.ingame.live_grade -- the in-game GRADE BRIDGE (P3 clause-2).

The thin WIRING that closes the live in-game grade loop. For a LIVE game it PAIRS, at
each tick, our in-game model's number (predictor.predict_live, wrapped) with the REAL
captured venue in-play price, then feeds the pair through the EXISTING P1 CLV replay
harness (forward_capture.inplay_clv_replay) to produce an HONEST verdict.

REUSES, never rebuilds: model -> domains/<sport>/predictor.py predict_live (INJECTABLE
model_fn); price -> odds_provider.inplay_feed / snapshot daemon (INJECTABLE
market_fetch_fn); grader -> inplay_clv_replay.replay_series/load_series/ReplayResult;
atomic I/O -> the .tmp + os.replace append discipline of the snapshot daemons.

PAIRED ROW (one JSON per line, data/cache/ingame_grade/<sport>/<game_id>.jsonl):
  {"sport","game_id","ts","market_prob","model_prob","side","state_summary"} plus any
  ADDITIVE enrichment keys merged via the optional `extra` kwarg (LANE 3 persistence;
  see capture_pair_once) -- consumers read via .get(), so extra keys are inert to them.
model_prob was computed LIVE from state-as-of-that-tick -- never from the close -- so
replaying the stored model_prob at grade time is LEAK-FREE.

ALIGNMENT (binding -- a misaligned pair manufactures fake CLV): model_prob and
market_prob MUST be the SAME side's probability (HOME here). capture_pair_once records
the side it paired ("home"); an unconfirmed home-side market fetch -> SKIPPED, not graded.

HONESTY (binding): a SINGLE partial game is NEVER a beat (grade_game -> INSUFFICIENT_DATA
below min_ticks; the real test aggregates MANY games, see grade_game's TODO). PAPER /
measurement only -- no $ / ROI / stake / edge, CLV is probability space. Never fabricates
a prob; a missing/out-of-range model_prob or market_prob -> SKIP.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; no network at
import; never edits src/ or kernel/.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_live_grade.py -q
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.forward_capture import inplay_clv_replay as ic

logger = logging.getLogger(__name__)

# __file__ = scripts/platformkit/ingame/live_grade.py -> parents[3] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade"

# The side both numbers are aligned to (see ALIGNMENT in the module docstring).
PAIR_SIDE = "home"
CAPTURE_SCHEMA_VERSION = 2

# Injectable callback signatures (all default to the real chains, but every test path
# and the live smoke inject stubs so NO network is required for the tested code):
#   live_state_fn(sport, game_id) -> dict | None   (current score/clock/inning state)
#   model_fn(state)               -> float | None  (model P(home win) in [0,1])
#   market_fetch_fn(sport, gid)   -> float | None  (venue implied P(home win) in [0,1])
LiveStateFn = Callable[[str, str], Optional[Dict[str, Any]]]
ModelFn = Callable[[Dict[str, Any]], Optional[float]]
MarketFetchFn = Callable[[str, str], Optional[float]]


# --------------------------------------------------------------------------------------- #
# helpers                                                                                  #
# --------------------------------------------------------------------------------------- #
def _utc(now: Optional[datetime]) -> datetime:
    d = now if now is not None else datetime.now(timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return _utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def _prob(value: Any) -> Optional[float]:
    """Coerce to a prob in [0,1]; None if non-numeric / out of range (never fabricated)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if 0.0 <= v <= 1.0 else None


def _grade_path(sport: str, game_id: str, out_dir: Path) -> Path:
    return out_dir / str(sport).lower() / ("%s.jsonl" % str(game_id))


def _append_atomic(path: Path, line: str) -> None:
    """Append one line via a tmp file + os.replace (same discipline as the snapshot daemons).

    Reads the existing file, concats the new row, writes the whole thing to a sibling .tmp,
    then os.replace over the target so a reader never sees a partially-written line.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if path.is_file():
        with path.open("r", encoding="utf-8") as fh:
            existing = fh.read()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(existing)
        fh.write(line + "\n")
    os.replace(str(tmp), str(path))


def _count_pairs(path: Path) -> int:
    if not path.is_file():
        return 0
    n = 0
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            if raw.strip():
                n += 1
    return n


# --------------------------------------------------------------------------------------- #
# capture                                                                                  #
# --------------------------------------------------------------------------------------- #
def capture_pair_once(sport: str, game_id: str, *,
                      now: Optional[datetime] = None,
                      live_state_fn: LiveStateFn,
                      model_fn: ModelFn,
                      market_fetch_fn: MarketFetchFn,
                      out_dir: Optional[Path] = None,
                      extra: Optional[Dict[str, Any]] = None,
                      src_ts: Optional[str] = None) -> Dict[str, Any]:
    """Capture ONE paired (model_prob, market_prob) tick for a live game and persist it.

    Flow: live_state_fn(sport, game_id) -> state; model_fn(state) -> model P(home win);
    market_fetch_fn(sport, game_id) -> venue implied P(home win). Both probs are the HOME
    side (ALIGNMENT). If EITHER prob is missing / out of [0,1] the pair is SKIPPED (logged)
    and NOTHING is written -- a misaligned or half-missing pair would manufacture fake CLV.

    *extra* (LANE 3 persistence, optional): ADDITIONAL fields (e.g. inplay_capture_loop's
    enrichment dict) merged into the row -- ADDITIVE ONLY, a colliding key is dropped, not
    overwritten. Non-dict/None is a no-op. Readers use rec.get(k), so new keys are inert.

    On a good pair, atomically appends a row to
      data/cache/ingame_grade/<sport>/<game_id>.jsonl
    Returns a summary dict (status='captured' on a write, 'skipped' otherwise). Never raises.
    """
    nowdt = _utc(now)
    base = Path(out_dir) if out_dir is not None else DEFAULT_GRADE_DIR
    path = _grade_path(sport, game_id, base)
    summary: Dict[str, Any] = {
        "sport": str(sport).lower(), "game_id": str(game_id), "ts": _iso(nowdt),
        "side": PAIR_SIDE, "market_prob": None, "model_prob": None,
        "status": "skipped", "reason": "", "n_pairs_total": _count_pairs(path),
    }
    try:
        state = live_state_fn(sport, game_id)
        if not isinstance(state, dict):
            summary["reason"] = "no_live_state"
            return summary
        model_p = _prob(model_fn(state))
        market_p = _prob(market_fetch_fn(sport, game_id))
        # ALIGNMENT GUARD: skip rather than grade a mismatched / missing-side pair.
        if model_p is None or market_p is None:
            summary["reason"] = ("missing_model_prob" if model_p is None
                                 else "missing_market_prob")
            logger.info("capture_pair_once SKIP %s/%s: %s",
                        sport, game_id, summary["reason"])
            return summary
        row = {
            "sport": str(sport).lower(), "game_id": str(game_id), "ts": _iso(nowdt),
            "market_prob": market_p, "model_prob": model_p, "side": PAIR_SIDE,
            "state_summary": _state_summary(state), "src_ts": src_ts,
            "capture_schema_version": CAPTURE_SCHEMA_VERSION,
        }
        if isinstance(extra, dict):
            # ADDITIVE ONLY: a colliding key is DROPPED (never overwrites core keys).
            row.update({k: v for k, v in extra.items() if k not in row})
        _append_atomic(path, json.dumps(row, ensure_ascii=True))
        summary.update({"market_prob": market_p, "model_prob": model_p,
                        "status": "captured", "reason": "",
                        "n_pairs_total": _count_pairs(path)})
    except Exception as exc:  # noqa: BLE001 -- capture must never sink a caller loop
        logger.warning("capture_pair_once(%s/%s) failed: %s", sport, game_id, exc)
        summary["reason"] = "error: %s" % type(exc).__name__
    return summary


def _state_summary(state: Dict[str, Any]) -> str:
    """Compact ASCII state label for the row (score/clock/inning + DEEP MLB base-out),
    best-effort.  The outs/base/bos/re/count keys are ADDITIVE (present only on MLB ticks
    via ingame_baseout_mlb) so the captured series carries the high-signal in-game
    variables a score+inning summary discards -- the data deepens every tick."""
    parts: List[str] = []
    for k in ("home_score", "away_score", "elapsed", "elapsed_minutes",
              "minute", "inning", "half", "clock", "period",
              "outs", "base", "bos", "re", "count", "pitch_count", "tto"):
        if state.get(k) not in (None, ""):
            parts.append("%s=%s" % (k, state.get(k)))
    return " ".join(parts) if parts else "live"


# --------------------------------------------------------------------------------------- #
# grade                                                                                    #
# --------------------------------------------------------------------------------------- #
def _load_pairs(path: Path) -> List[Dict[str, Any]]:
    """Read the paired jsonl, keep rows with valid probs, sort by ts. Never raises."""
    rows: List[Dict[str, Any]] = []
    if not path.is_file():
        return rows
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            mk = _prob(rec.get("market_prob"))
            md = _prob(rec.get("model_prob"))
            if mk is None or md is None:
                continue  # ALIGNMENT/validity guard: never grade a half-missing pair
            rec["market_prob"], rec["model_prob"] = mk, md
            rows.append(rec)
    rows.sort(key=lambda r: str(r.get("ts", "")))
    return rows


def grade_game(path: str, *, eps: float = ic.EPS_DEFAULT,
               min_ticks: int = ic.MIN_TICKS_DEFAULT) -> Dict[str, Any]:
    """Grade ONE paired-capture file through the P1 CLV replay harness; honest verdict.

    Loads data/cache/ingame_grade/<sport>/<game_id>.jsonl (sorted by ts), builds a MARKET
    price series in the canonical inplay-tick schema, and a model_fn that REPLAYS the STORED
    model_prob for each tick (keyed by ts -- the model_prob was computed live from
    state-as-of-that-tick, so this is leak-free). Calls inplay_clv_replay.replay_series.

    HONESTY: a SINGLE partial game is NEVER a beat. Below *min_ticks* pairs the verdict is
    INSUFFICIENT_DATA -- an honest "can't tell yet", NOT a beat. The final tick is the in-play
    close and is excluded from scoring by the harness. A raw single-game positive-CLV verdict
    is DOWNGRADED to the neutral per-game token 'PER_GAME_CLV_POSITIVE' (raw_per_game_verdict
    keeps the original): 'BEAT' is reserved for the gated multi-game aggregate, never one game.

    TODO (the REAL test): a MULTI-GAME aggregate grader -- pool the per-tick CLVs across MANY
    settled games and only THEN read a verdict. One game's verdict is variance, not signal.

    Returns the ReplayResult-as-dict plus {n_pairs, path, side}. Never raises.
    """
    p = Path(path)
    try:
        pairs = _load_pairs(p)
    except Exception as exc:  # noqa: BLE001 -- a bad file is a cache miss, not a crash
        logger.warning("grade_game load failed %s: %s", path, exc)
        pairs = []
    n_pairs = len(pairs)

    # Canonical market tick series + a POSITIONAL stored-model lookup (ts-only keying
    # once collapsed same-SECOND ticks). pairs/series share order; replay_series hands
    # history=series[:i+1], so idx=len(history)-1 is a robust 1:1 lookup with no leak.
    model_by_pos: List[float] = []
    series: List[Dict[str, Any]] = []
    for r in pairs:
        ts = str(r.get("ts", ""))
        model_by_pos.append(float(r["model_prob"]))
        series.append({
            "sport": str(r.get("sport", "")), "game_id": str(r.get("game_id", "")),
            "venue": str(r.get("venue", "ingame_pair")),
            "market_type": str(r.get("market_type", "moneyline")),
            "side": str(r.get("side", PAIR_SIDE)),
            "ticker": str(r.get("ticker", r.get("game_id", ""))),
            "prob": float(r["market_prob"]), "ts": ts,
        })

    def _stored_model_fn(tick: Dict[str, Any], history: List[Dict[str, Any]]) -> float:
        # Leak-free: return the model_prob captured LIVE at THIS tick (never the close).
        # Positional lookup (index = len(history)-1) so same-second ticks keep their
        # own distinct model_prob -- no silent overwrite. Bounds-guarded fallback to
        # the tick's own market prob keeps a robust no-lean default.
        idx = len(history) - 1
        if 0 <= idx < len(model_by_pos):
            return model_by_pos[idx]
        return float(tick["prob"])

    result = ic.replay_series(series, _stored_model_fn, eps=eps, min_ticks=min_ticks)
    out = result.as_dict()
    out.update({"n_pairs": n_pairs, "path": str(p), "side": PAIR_SIDE,
                "edge_claimed": False})
    # SINGLE-FOLD-IS-ARTIFACT GUARD (L2): one game's positive CLV is variance, not a
    # proven beat -- 'BEAT' is RESERVED for the gated multi-game aggregate (MIN_GAMES,
    # clustered DM, two arms). Downgrade a raw single-game 'BEAT' to a NEUTRAL per-game
    # readout token so it can never be read/displayed as a proven beat; the aggregate
    # grader reads mean_clv / n_ticks_scored (NOT this string), so pooling is unchanged.
    out["per_game"] = True
    if out.get("verdict") == "BEAT":
        out["raw_per_game_verdict"] = "BEAT"
        out["verdict"] = "PER_GAME_CLV_POSITIVE"
    return out


__all__ = ["DEFAULT_GRADE_DIR", "PAIR_SIDE", "CAPTURE_SCHEMA_VERSION", "capture_pair_once", "grade_game"]
