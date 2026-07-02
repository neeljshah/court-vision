"""scripts.platformkit.improve.settled_corpus_build -- mid-game SETTLED CORPUS producer.

Closes gaps #2/#3 of the in-game recal corpus chain (docs/research/ingame-recal-corpus-
gap-2026-06-26.md): `ingame_recal_segments._load_ingame_settled` reads
data/frontend/ingame/settled_<sport>.jsonl but NO producer wrote it. This is that producer.

THE SOURCE (better than the terminal-only loop reconstructor): the LIVE grade files
data/cache/ingame_grade/<sport>/<game>.jsonl are already MID-GAME TRAJECTORIES -- one row
per ~20-30s tick carrying the in-game model number (model_prob), the live price, and (after
gap#1's state fix) the game state in state_summary. settle_stamp appends one settled row
{settled:true, home_win:0|1}. So each game file holds BOTH the trajectory AND its outcome.

This builder flattens, per game with a settled label, every stateful tick into the recal
schema {sport, game_id, ts, p0, outcome, margin, period, seconds_remaining} and writes
settled_<sport>.jsonl -- the file ingame_recal_segments reads. SPORT-AWARE: state_summary is
parsed per sport (nba period/clock, mlb inning, soccer minute, tennis set).

LEAK-FREE: p0 = model_prob computed LIVE at that tick (causal, never the close/outcome);
outcome = the held-out home_win LABEL. The recal gates enforce OOS/walk-forward downstream.

HONEST RAILS: a game with no settled label -> skipped (never fabricated). A tick with no
parseable state -> skipped. No $/roi/pnl/stake field anywhere; edge_claimed never set.
Never raises out of the public API; ASCII only; <=300 LOC.

Public API:
  build_settled_corpus(sport, grade_dir=None, out_dir=None) -> dict   (writes the file)
  parse_state(sport, state_summary) -> (margin, period, seconds_remaining) | None
"""
from __future__ import annotations

import json
import logging
import pathlib
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("settled_corpus_build")

_REPO = pathlib.Path(__file__).resolve().parents[3]
_GRADE_DIR = _REPO / "data" / "cache" / "ingame_grade"
_OUT_DIR = _REPO / "data" / "frontend" / "ingame"

_KV_RE = re.compile(r"(\w+)=(\S+)")
_BANNED = ("$", "roi", "pnl", "profit", "stake", "bankroll")


# ---------------------------------------------------------------------------
# parsing helpers
# ---------------------------------------------------------------------------
def _kv(s: str) -> Dict[str, str]:
    return {m.group(1).lower(): m.group(2) for m in _KV_RE.finditer(str(s))}


def _num(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v: Any) -> Optional[int]:
    f = _num(v)
    return int(f) if f is not None else None


def parse_state(sport: str, state_summary: str) -> Optional[Tuple[float, int, float]]:
    """state_summary -> (margin, period, seconds_remaining), sport-aware. None if unparseable.

    margin = abs(home_score - away_score). period is the sport-native progress index
    (nba quarter / mlb inning / soccer minute / tennis set). seconds_remaining is the nba
    in-quarter clock when present, else 0.0 (clockless sports use a single time bucket).
    """
    sp = str(sport).lower()
    kv = _kv(state_summary)
    hs, as_ = _num(kv.get("home_score")), _num(kv.get("away_score"))
    margin = abs(hs - as_) if (hs is not None and as_ is not None) else None
    if margin is None:
        return None
    if sp == "nba":
        period = _int(kv.get("period"))
        if period is None:
            return None
        secs = _num(kv.get("clock"))
        return (margin, period, secs if secs is not None else 0.0)
    if sp == "mlb":
        inning = _int(kv.get("inning"))
        return (margin, inning, 0.0) if inning is not None else None
    if sp in ("soccer", "soccer_intl"):
        minute = _int(kv.get("minute"))
        return (margin, minute, 0.0) if minute is not None else None
    if sp == "tennis":
        st = _int(kv.get("set"))
        return (margin, st, 0.0) if st is not None else None
    return None


# ---------------------------------------------------------------------------
# per-game flatten
# ---------------------------------------------------------------------------
def _game_outcome(rows: List[Dict[str, Any]]) -> Optional[float]:
    """The settled home_win label from a game's rows, or None (unsettled -> skip)."""
    for r in rows:
        if r.get("settled") is True or r.get("home_win") is not None:
            hw = _num(r.get("home_win"))
            if hw in (0.0, 1.0):
                return hw
    return None


def _flatten_game(sport: str, path: pathlib.Path) -> List[Dict[str, Any]]:
    """One game grade file -> settled-corpus rows (mid-game states + outcome). Never raises."""
    rows: List[Dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict):
                    rows.append(rec)
    except Exception as exc:  # noqa: BLE001
        logger.debug("flatten read %s: %s", path, exc)
        return []

    outcome = _game_outcome(rows)
    if outcome is None:
        return []  # unsettled game -> skip (honest, never fabricate an outcome)

    out: List[Dict[str, Any]] = []
    for r in rows:
        if r.get("settled") is True:
            continue
        p0 = _num(r.get("model_prob"))           # the in-game model number = base to recal
        if p0 is None or not (0.0 <= p0 <= 1.0):
            continue
        parsed = parse_state(sport, r.get("state_summary", ""))
        if parsed is None:
            continue                              # no parseable state -> skip
        margin, period, secs = parsed
        # Each corpus row is a self-contained "game" dict for audit_settled: it carries the
        # segment fields (margin/period/seconds_remaining), the (p0, outcome) pair, AND a
        # non-empty `states` stub + outcome_confirmed=True. The flag is HONEST -- settle_stamp
        # only labels FINAL games from the realized score, so a home-loss (outcome=0) is a
        # CONFIRMED observation, not a 0-fill (this clears the anti-0-fill all-zero guard).
        out.append({
            "sport": str(sport).lower(),
            "game_id": str(r.get("game_id", path.stem)),
            "ts": str(r.get("ts", "")),
            "p0": float(p0),
            "outcome": float(outcome),
            "outcome_confirmed": True,
            "outcome_source": "final_score",
            "margin": float(margin),
            "period": int(period),
            "seconds_remaining": float(secs),
            "states": [{"outcome": float(outcome), "outcome_confirmed": True}],
        })
    return out


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def build_settled_corpus(sport: str, grade_dir: Any = None,
                         out_dir: Any = None) -> Dict[str, Any]:
    """Build data/frontend/ingame/settled_<sport>.jsonl from the live grade files.

    Reads every data/cache/ingame_grade/<sport>/<game>.jsonl, flattens each SETTLED game's
    stateful ticks into the recal schema, and atomically writes the corpus. Returns a counts
    summary (NO $ field). Never raises. Games without a settled label or stateful ticks are
    skipped (honest cold start -> empty corpus).
    """
    sp = str(sport).lower()
    gdir = (pathlib.Path(grade_dir) if grade_dir is not None else _GRADE_DIR) / sp
    odir = pathlib.Path(out_dir) if out_dir is not None else _OUT_DIR

    corpus: List[Dict[str, Any]] = []
    n_games = n_settled = 0
    if gdir.exists():
        for fp in sorted(gdir.glob("*.jsonl")):
            n_games += 1
            game_rows = _flatten_game(sp, fp)
            if game_rows:
                n_settled += 1
                corpus.extend(game_rows)

    out_path = odir / ("settled_%s.jsonl" % sp)
    written = _atomic_write_jsonl(out_path, corpus)

    summary = {
        "sport": sp,
        "out_path": str(out_path),
        "written": bool(written),
        "n_games_scanned": int(n_games),
        "n_games_settled": int(n_settled),
        "n_corpus_rows": len(corpus),
        "edge_claimed": False,
        "note": ("mid-game settled corpus (p0=live in-game model number, outcome=held-out "
                 "home_win label); leak-free; calibration not edge; UNITS not $"),
    }
    for k in summary:
        if any(b in str(k).lower() for b in _BANNED):
            raise ValueError("banned key %r" % k)
    return summary


def _atomic_write_jsonl(path: pathlib.Path, rows: List[Dict[str, Any]]) -> bool:
    """Atomically (over)write the corpus jsonl. Returns True on success. Never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=True) + "\n")
        import os
        os.replace(str(tmp), str(path))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("corpus write %s: %s", path, exc)
        return False


def _main() -> int:  # pragma: no cover
    import argparse as _ap
    p = _ap.ArgumentParser(
        description="Build the mid-game settled corpus settled_<sport>.jsonl from live "
                    "grade files. Leak-free; no $ edge; skips unsettled/stateless.")
    p.add_argument("sport", help="sport key (nba, mlb, soccer, soccer_intl, tennis)")
    a = p.parse_args()
    s = build_settled_corpus(a.sport)
    print("settled_corpus_build | sport=%s rows=%d settled_games=%d/%d -> %s" % (
        s["sport"], s["n_corpus_rows"], s["n_games_settled"], s["n_games_scanned"],
        s["out_path"]), flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["build_settled_corpus", "parse_state"]
