"""scripts.platformkit.ingame.aggregate_clv_to_corpus -- the THIN ADAPTER that hands the
multi-game aggregate grader's per-game model-vs-close OUTCOME-Brier evidence to the
execution-in-the-loop SECOND CORPUS (improve.clv_corpus.build_close_corpus).

WHY a separate module: inplay_aggregate_grade POOLS settled games and reads a verdict;
clv_corpus builds the ratchet's SECOND corpus, but ONLY when the candidate genuinely
BEATS THE CLOSE on held-out OUTCOME-Brier (its P1 keystone). The shapes differ -- the
aggregate grader works off on-disk paired-capture files, clv_corpus consumes a list of
``settled`` game dicts with per-state {model_p, close_p, outcome, is_true_close}. This
adapter is the loss-free MAP between them; it adds NO new statistics and NEVER copies
clv_corpus's reject logic (that stays the single source of truth).

THE MAP (leak-free, P1-preserving):
  * per game -> reuse the EXISTING leak-free loader live_grade._load_pairs (validity /
    alignment guarded). Each scored state contributes one corpus state:
        model_p        = that tick's LIVE-captured model_prob (state-as-of-that-tick),
        close_p        = the FINAL captured tick's market_prob (the in-play CLOSE -- the
                         held-out yardstick, exactly inplay_clv_replay's ticks[-1] close),
        outcome        = the settled binary {0,1} home win (read off the grade rows),
        is_true_close  = True ONLY when the capture marked the close real (default True;
                         a row flagged is_true_close False -> the game is dropped, never
                         graded against a proxy close -- clv_corpus P3 still binds).
  * the final close tick is EXCLUDED from the scored states (it is the yardstick, not a
    prediction to grade), mirroring the replay harness which never scores ticks[-1].
  * a game with no settled outcome, <2 usable states, or a non-true close -> SKIPPED.

WHY P1 IS PRESERVED (the only thing that matters here): this adapter only RESHAPES rows;
the model-BEATS-close-on-OUTCOME-Brier DM-by-game decision is made entirely inside
build_close_corpus. A shrink-toward-close / market-copy pool has model_p == close_p on
every state -> per-state outcome-Brier d == 0 -> build_close_corpus returns None (NO
corpus). This adapter cannot manufacture a corpus a market-copy pool would not earn.

INERT BY DEFAULT (the loop never ships): build_close_corpus / inject_corpus are
sentinel-gated (improve.pipeline_flag.pipeline_enabled). With the human-only
PIPELINE_ENABLED sentinel ABSENT, build_close_corpus returns None and the candidate is
returned UNCHANGED -- the daemon's downstream verdict stays NO_CANDIDATE /
REPLICATION_PENDING. This adapter NEVER creates the sentinel, flips a flag, writes
data/registry/, or claims a $ edge. UNITS / PROBABILITY only; NO $/roi/pnl field; NEVER
raises (any failure -> empty settled / candidate unchanged). <=300 LOC; ASCII only.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_aggregate_clv_to_corpus.py -q
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scripts.platformkit.ingame import inplay_aggregate_grade as ag
from scripts.platformkit.ingame import live_grade as lg
from scripts.platformkit.improve.clv_corpus import build_close_corpus, CLV_CORPUS_ID
from scripts.platformkit.improve.clv_corpus_inject import inject_corpus

logger = logging.getLogger(__name__)

# Minimum scored (non-close) states a game must contribute to be usable evidence.
_MIN_STATES = 2


def _is_true_close_game(rows: Sequence[Dict[str, Any]]) -> bool:
    """True unless ANY captured row explicitly flags is_true_close False (P3 guard).

    The capture path may not stamp is_true_close at all (older / proxy-free rows) -- in
    that case the close is treated as real (True). A SINGLE row flagged False marks the
    game's close as a proxy, so the whole game is dropped (never graded against a proxy).
    """
    for r in rows:
        if r.get("is_true_close") is False:
            return False
    return True


def game_to_settled(path: Path) -> Optional[Dict[str, Any]]:
    """Map ONE on-disk paired-capture file -> a clv_corpus ``settled`` game dict, or None.

    Reuses the leak-free live_grade._load_pairs + aggregate grader's outcome reader. The
    final captured tick is the in-play CLOSE (close_p / yardstick) and is EXCLUDED from
    the scored states; every earlier scored state carries its own live model_p graded
    against that one close and the settled outcome. Returns None when the game has no
    settled outcome, a proxy close, or < _MIN_STATES scored states. Never raises.
    """
    try:
        pairs = lg._load_pairs(Path(path))
    except Exception as exc:  # noqa: BLE001 -- a torn file is a miss, not a crash
        logger.debug("game_to_settled load failed %s: %s", path, exc)
        return None
    if len(pairs) < (_MIN_STATES + 1):  # need >=_MIN_STATES states + 1 close tick
        return None
    if not _is_true_close_game(pairs):
        return None  # P3: proxy close -> drop the game (never grade against it)

    outcome = ag._settled_outcome(Path(path))
    if outcome is None:
        return None  # no settled outcome -> cannot grade outcome-Brier honestly

    close_p = float(pairs[-1]["market_prob"])  # the in-play close (held-out yardstick)
    gid = str(pairs[0].get("game_id", Path(path).stem))
    states: List[Dict[str, Any]] = []
    for r in pairs[:-1]:  # exclude the close tick -- it is the yardstick, not a prediction
        states.append({
            "model_p": float(r["model_prob"]),
            "close_p": close_p,
            "outcome": float(outcome),
            "is_true_close": True,
            "game_id": gid,
        })
    if len(states) < _MIN_STATES:
        return None
    return {"game_id": gid, "is_true_close": True, "states": states}


def build_settled_from_grades(grade_dir: Optional[Path] = None, *,
                              sport: Optional[str] = None,
                              paths: Optional[Sequence[Path]] = None
                              ) -> List[Dict[str, Any]]:
    """Discover (or take injected) per-game grade files and map each to a settled game dict.

    Reuses ag.discover_grade_files for discovery so this adapter never re-implements the
    walk. Games that yield None (no outcome / proxy close / too few states) are dropped.
    Returns a list consumable directly by build_close_corpus. Never raises.
    """
    files = list(paths) if paths is not None else ag.discover_grade_files(grade_dir, sport)
    settled: List[Dict[str, Any]] = []
    for p in files:
        g = game_to_settled(Path(p))
        if g is not None:
            settled.append(g)
    return settled


def build_corpus_from_grades(grade_dir: Optional[Path] = None, *,
                             sport: Optional[str] = None,
                             paths: Optional[Sequence[Path]] = None,
                             alpha: float = 0.05,
                             require_enabled: bool = True
                             ) -> Optional[Dict[str, Any]]:
    """Map on-disk grades -> settled games -> build_close_corpus (the SECOND corpus), or None.

    This is the single call a wire-in would make. It RESHAPES only; the model-BEATS-close
    -on-OUTCOME-Brier DM-by-game decision (and every P1 reject -- shrink-to-close, all-proxy,
    too-few-clusters) lives entirely inside build_close_corpus. INERT when the sentinel is
    absent: build_close_corpus returns None (require_enabled gate) -> None here. Never raises.
    """
    try:
        settled = build_settled_from_grades(grade_dir, sport=sport, paths=paths)
        if not settled:
            return None
        return build_close_corpus(settled, alpha=alpha, require_enabled=require_enabled)
    except Exception as exc:  # noqa: BLE001 -- purity: any failure -> no corpus
        logger.debug("build_corpus_from_grades failed -> None: %s", exc)
        return None


def inject_grades_corpus(candidate: Optional[Dict[str, Any]],
                         grade_dir: Optional[Path] = None, *,
                         sport: Optional[str] = None,
                         paths: Optional[Sequence[Path]] = None,
                         alpha: float = 0.05,
                         require_enabled: bool = True
                         ) -> Optional[Dict[str, Any]]:
    """Build the grades-derived settled corpus and inject it via the EXISTING bridge.

    Thin convenience over clv_corpus_inject.inject_corpus: maps grades -> settled, then lets
    the verified bridge append the SECOND corpus (or leave the candidate UNCHANGED when the
    sentinel is absent / there is no model-beats-close corpus). Returns the candidate
    UNCHANGED on the inert path -- byte-compatible with the daemon's corpora:[] baseline.
    vs_close STAYS UNPROVEN here (the bridge enforces P2). Never raises.
    """
    if candidate is None:
        return None
    try:
        settled = build_settled_from_grades(grade_dir, sport=sport, paths=paths)
        return inject_corpus(candidate, settled, alpha=alpha,
                             require_enabled=require_enabled)
    except Exception as exc:  # noqa: BLE001 -- purity: leave candidate UNCHANGED
        logger.debug("inject_grades_corpus failed -> candidate unchanged: %s", exc)
        return candidate


__all__ = [
    "game_to_settled", "build_settled_from_grades",
    "build_corpus_from_grades", "inject_grades_corpus", "CLV_CORPUS_ID",
]
