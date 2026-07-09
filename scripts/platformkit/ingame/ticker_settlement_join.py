"""scripts.platformkit.ingame.ticker_settlement_join -- shadow-grade JOIN backfill
(gap-audit-CD-6): closes the "no grade row has model_prob + market_prob + outcome +
close_source together" gap.

THE GAP (traced, matches state_bucket_benchmark.py's own docstring finding): tick
capture (live_grade.capture_pair_once) writes per-tick (model_prob, market_prob) rows
keyed by KALSHI TICKER (inplay_capture_loop._process_game: "gid is a Kalshi ticker,
not an ESPN id"). settle_stamp.stamp_final's FINAL label instead fires off
settled_finals.settled_since, keyed by ESPN's own numeric game id -- a DIFFERENT id
space. Same directory, two disjoint files per real game: a ticker file with ticks and
no label, an ESPN-id file with a label and no ticks -- never joined on disk.
(state_bucket_benchmark.py already works around this in-memory for its one MLB pass;
this module makes the join a DURABLE artifact every consumer can read.)

THE FIX (reuse only): 1) per-sport ticker-keyed outcome resolver, ticker-in/label-out,
no ESPN id needed -- ingame_outcome_label.MlbOutcomeResolver (mlb, the SAME one
state_bucket_benchmark trusts), soccer_outcome.SoccerOutcomeResolver (soccer_intl,
draws=0.5), nba/tennis/kbo/npb/wnba_outcome_resolver. 2) close-proxy: clv.
kx_ticker_close.derive_close (last-tick venue price, close_kind ALWAYS "last_tick").
3) label stamp: settle_stamp.stamp_final (idempotent; now carries close_source too).
Nothing here re-derives an outcome or close price -- it only JOINS existing numbers.

OUTPUT: one row per valid tick -> data/cache/ingame_grade_joined/<sport>/<TICKER>.jsonl
  {"sport","game_id","ts","model_prob","market_prob","side","state_summary",
   "outcome","close_source","close_prob","close_ts","edge_claimed":False}
Full, current rebuild of that ticker's file each run (idempotent, never a growing
duplicate append). The SOURCE grade file also gets an idempotent settle_stamp.

HONESTY: an unresolved/ambiguous/not-final ticker, or a resolver with no corpus, is
SKIPPED -- never a fabricated outcome/close. No $/ROI/edge; edge_claimed always False.

INVARIANTS: scripts/platformkit/ingame/ only; <=300 LOC; ASCII; no network at import
(a resolver's live-fallback tier, if any, only fires inside its own .home_win call);
never writes data/registry/; never edits live_grade.py / state_bucket_benchmark.py /
any resolver module (read-only imports of each).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ticker_settlement_join.py -q
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit.ingame import live_grade as _lg
from scripts.platformkit.ingame import settle_stamp as _settle
from scripts.platformkit.clv import kx_ticker_close as _kx

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade"
DEFAULT_JOINED_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade_joined"

# provenance label per sport's resolver -- purely descriptive, recorded in
# close_source so a joined row can be traced back to its outcome corpus.
_CLOSE_SOURCE_LABEL: Dict[str, str] = {
    "mlb": "ingame_outcome_label:espn_boxscores_parquet",
    "soccer_intl": "soccer_outcome:espn_finals_parquet",
    "nba": "nba_outcome_resolver:games_parquet",
    "tennis": "tennis_outcome_resolver:espn_matches_parquet",
    "kbo": "kbo_outcome_resolver:kbo_results_parquet",
    "npb": "npb_outcome_resolver:npb_results_parquet",
    "wnba": "wnba_outcome_resolver:scoreboard_parquet",
}


# sport -> (module under scripts.platformkit.ingame, resolver class name). Every
# resolver here already exists and shares the ticker-in/label-out contract; this
# table is the only per-sport code a new sport needs to add.
_RESOLVER_MODULE: Dict[str, Tuple[str, str]] = {
    "mlb": ("ingame_outcome_label", "MlbOutcomeResolver"),
    "soccer_intl": ("soccer_outcome", "SoccerOutcomeResolver"),
    "nba": ("nba_outcome_resolver", "NbaOutcomeResolver"),
    "tennis": ("tennis_outcome_resolver", "TennisOutcomeResolver"),
    "kbo": ("kbo_outcome_resolver", "KboOutcomeResolver"),
    "npb": ("npb_outcome_resolver", "NpbOutcomeResolver"),
    "wnba": ("wnba_outcome_resolver", "WnbaOutcomeResolver"),
}


def _build_resolver(sport: str, **kw: Any) -> Any:
    """Lazily import + instantiate *sport*'s outcome resolver (see _RESOLVER_MODULE).
    Raises on an unknown sport / import failure -- caller (backfill_sport) catches."""
    mod_name, cls_name = _RESOLVER_MODULE[sport]
    mod = __import__("scripts.platformkit.ingame.%s" % mod_name, fromlist=[cls_name])
    return getattr(mod, cls_name)(**kw)


def _is_ticker(stem: str) -> bool:
    """A Kalshi ticker is a non-numeric venue id (mirrors kx_ticker_close._is_kx_ticker)."""
    s = str(stem or "").strip()
    return bool(s) and not s.isdigit()


def _prob01(value: Any) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if 0.0 <= v <= 1.0 else None


def _outcome_for(sport: str, resolver: Any, ticker: str) -> Optional[float]:
    """Outcome label for one ticker via that sport's resolver: strict {0.0,1.0}
    everywhere except soccer, where a draw is kept as 0.5 (distinct from an
    unresolved/None game). None on unresolved/ambiguous/not-final. Never raises."""
    try:
        if sport == "soccer_intl":
            fs = resolver.final_score(ticker)
            if fs is None:
                return None
            hs, aws = fs
            return 1.0 if hs > aws else (0.0 if hs < aws else 0.5)
        hw = resolver.home_win(ticker)
        return float(hw) if hw is not None else None
    except Exception as exc:  # noqa: BLE001 -- an unresolvable ticker is an honest skip
        logger.debug("_outcome_for(%s/%s) failed: %s", sport, ticker, exc)
        return None


def _load_ticks(path: Path) -> List[Dict[str, Any]]:
    """Every row with a valid (model_prob, market_prob) pair, file order. Mirrors
    live_grade._load_pairs' own validity filter so this join can never disagree
    with what the grader itself scores."""
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
            mp, md = _prob01(rec.get("market_prob")), _prob01(rec.get("model_prob"))
            if mp is None or md is None:
                continue
            rec["market_prob"], rec["model_prob"] = mp, md
            rows.append(rec)
    return rows


def _write_full(path: Path, lines: List[str]) -> None:
    """Full, current rebuild of *path* (never a growing duplicate append -- a
    re-run of the same ticker just overwrites its own joined file with the
    latest tick set)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")


def join_ticker_file(sport: str, path: Path, resolver: Any, *,
                     joined_dir: Optional[Path] = None,
                     grade_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Join ONE ticker's tick file to its settlement outcome + close-proxy.

    Writes data/cache/ingame_grade_joined/<sport>/<TICKER>.jsonl (one row per valid
    tick) and idempotently settle_stamps the SOURCE grade file too. Returns a summary
    dict; never raises."""
    sport = str(sport).lower()
    ticker = path.stem
    summary: Dict[str, Any] = {"sport": sport, "ticker": ticker, "status": "skipped",
                               "n_ticks": 0, "n_joined": 0}
    ticks = _load_ticks(path)
    summary["n_ticks"] = len(ticks)
    if not ticks:
        summary["reason"] = "no_valid_ticks"
        return summary

    outcome = _outcome_for(sport, resolver, ticker)
    if outcome is None:
        summary["reason"] = "unresolved_outcome"
        return summary
    close_source = _CLOSE_SOURCE_LABEL.get(sport, "%s_outcome_resolver" % sport)
    close = _kx.derive_close(path)  # reused last-tick close proxy

    out_lines = []
    for r in ticks:
        row = {
            "sport": sport, "game_id": ticker, "ts": r.get("ts"),
            "model_prob": r["model_prob"], "market_prob": r["market_prob"],
            "side": r.get("side", _lg.PAIR_SIDE), "state_summary": r.get("state_summary", ""),
            "outcome": outcome, "close_source": close_source,
            "close_prob": close["close_prob"] if close else None,
            "close_ts": close["close_ts"] if close else None,
            "edge_claimed": False,
        }
        out_lines.append(json.dumps(row, ensure_ascii=True))

    jdir = Path(joined_dir) if joined_dir is not None else DEFAULT_JOINED_DIR
    out_path = jdir / sport / ("%s.jsonl" % ticker)
    _write_full(out_path, out_lines)
    summary.update({"status": "joined", "n_joined": len(out_lines), "path": str(out_path)})

    # Additive, idempotent: stamp the SOURCE file too (only for a strict 0/1 label --
    # a soccer draw is never coerced into a fake home_win) so existing consumers that
    # already scan that convention (state_bucket_benchmark et al) gain the label too.
    try:
        if outcome in (0.0, 1.0):
            _settle.stamp_final(sport, ticker, home_win=outcome,
                                close_source=close_source, grade_dir=grade_dir)
    except Exception as exc:  # noqa: BLE001 -- a passthrough stamp failure never sinks the join
        logger.debug("stamp_final passthrough failed for %s/%s: %s", sport, ticker, exc)
    return summary


def backfill_sport(sport: str, *, grade_dir: Optional[Path] = None,
                   joined_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Join every ticker-keyed grade file for *sport*. Returns {sport, n_files,
    n_joined, join_rate, results}. Never raises; an unknown sport or missing/empty
    resolver corpus yields an honest zero, not a crash."""
    sport = str(sport).lower()
    gdir = Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR
    sport_dir = gdir / sport
    empty = {"sport": sport, "n_files": 0, "n_joined": 0, "join_rate": 0.0, "results": []}
    if sport not in _RESOLVER_MODULE or not sport_dir.is_dir():
        return empty
    try:
        resolver = _build_resolver(sport)
    except Exception as exc:  # noqa: BLE001 -- a resolver ctor failure is an honest empty result
        logger.warning("backfill_sport(%s) resolver init failed: %s", sport, exc)
        return dict(empty, reason="resolver_init_failed")
    if not getattr(resolver, "available", True):
        return dict(empty, reason="resolver_unavailable")

    ticker_files = [p for p in sorted(sport_dir.glob("*.jsonl")) if _is_ticker(p.stem)]
    results = [join_ticker_file(sport, p, resolver, joined_dir=joined_dir, grade_dir=grade_dir)
              for p in ticker_files]
    n_files = len(ticker_files)
    n_joined = sum(1 for r in results if r["status"] == "joined")
    return {"sport": sport, "n_files": n_files, "n_joined": n_joined,
            "join_rate": (n_joined / n_files) if n_files else 0.0, "results": results}


def backfill_all(sports: Optional[List[str]] = None, **kw: Any) -> Dict[str, Dict[str, Any]]:
    """backfill_sport() for every sport in *sports* (default: every sport with a
    registered resolver). Never raises; one sport failing never blocks another."""
    for_sports = sports or list(_RESOLVER_MODULE)
    out: Dict[str, Dict[str, Any]] = {}
    for s in for_sports:
        try:
            out[s] = backfill_sport(s, **kw)
        except Exception as exc:  # noqa: BLE001 -- one sport's failure never blocks the rest
            logger.warning("backfill_all(%s) failed: %s", s, exc)
            out[s] = {"sport": s, "n_files": 0, "n_joined": 0, "join_rate": 0.0,
                     "results": [], "reason": "error: %s" % type(exc).__name__}
    return out


def demo() -> None:  # pragma: no cover -- manual smoke, not part of the test suite
    """Tiny self-check: a synthetic ticker file joins against an injected resolver."""
    import tempfile

    class _StubResolver:
        available = True

        def home_win(self, ticker: str) -> Optional[int]:
            return 1

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        grade_dir = base / "grade"
        p = grade_dir / "mlb" / "KXMLBGAME-26JUL011235CWSBAL.jsonl"
        p.parent.mkdir(parents=True)
        with p.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps({"sport": "mlb", "game_id": p.stem, "ts": "2026-07-01T12:00:00Z",
                                 "model_prob": 0.6, "market_prob": 0.55, "side": "home"}) + "\n")
        summary = join_ticker_file("mlb", p, _StubResolver(),
                                   joined_dir=base / "joined", grade_dir=grade_dir)
        assert summary["status"] == "joined" and summary["n_joined"] == 1, summary
        joined_row = json.loads((base / "joined" / "mlb" / p.name).read_text(encoding="utf-8").strip())
        assert joined_row["outcome"] == 1.0 and joined_row["model_prob"] == 0.6
        assert joined_row["close_source"] == _CLOSE_SOURCE_LABEL["mlb"]
    print("ticker_settlement_join demo OK")


if __name__ == "__main__":  # pragma: no cover
    demo()


__all__ = [
    "DEFAULT_GRADE_DIR", "DEFAULT_JOINED_DIR", "join_ticker_file",
    "backfill_sport", "backfill_all",
]
