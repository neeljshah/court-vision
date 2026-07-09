"""scripts.platformkit.ingame.mlb_winprob_v3_prior -- pregame MARKET-PRICE prior for
mlb_winprob_v3.py (LOC-cap split; the orchestration module stays <=300 LOC by keeping
all prior-source loading/matching here).

WHY: v2 (commit 3aac11e8) was an honest REJECT with no pregame anchor -- it overshot to
0.970 in late|leading_big where the realized rate was 0.682. The fix is a prior anchor
built from information available BEFORE first pitch: the pre-game market price.

TWO independent prior sources (leak-legal, both strictly pregame):
  TRAIN (2022-2024) + VAL (2025): Polymarket day-docs under data/venue_history/polymarket/
    {mlb, mlb_2024plus}/*.jsonl -- {date, home, away, prices:[{ts, prob_home}]}. The pitch-
    states parquet carries NO wallclock (only a day-granularity `date` col), so a true
    "before first pitch" cutoff is not reconstructable here -- documented limitation, per
    mission: prior = the game's FIRST available price (early-in-day quote, can drift from
    the true pregame close; counted, never silently fabricated as a "real" close).
  EVAL (2026): Kalshi settled-market candles under data/venue_history/kalshi/mlb/
    <event_ticker>-<side>.jsonl -- here we DO have per-tick wallclock (the grade file's
    first captured tick ts), so the cutoff is the tighter "last traded candle strictly
    before the game's first captured tick".

MATCHING:
  Train/val: pitch_states `game_id` = "<date>-<home_abbr>-<away_abbr>-<n>" (VERIFIED
    against the parquet's own home_team/away_team columns -- NOT away-then-home, despite
    the away-home order used elsewhere in this codebase for Kalshi tickers; a first draft
    of this module got this backwards and silently matched 0/642 train games until caught).
    Parquet uses its own non-standard abbr set, see domains.mlb.team_name_resolver.
    LANDMINE: the mlb_2024plus PM corpus's own {"home":..., "away":...} fields are NOT
    reliably oriented -- spot-checked against data/domains/mlb/espn_boxscores.parquet,
    some games agree, some are flipped (e.g. 2025-04-11 ARI/MIL is reversed vs box truth,
    2025-04-02 TB/PIT is not). Fix: build_pm_prior_index keys by the UNORDERED team pair
    (frozenset) and stores which team PM itself calls "home" + that team's price; the join
    in attach_priors then orients using pitch_states' own VERIFIED home_team column, never
    trusting PM's home/away label directly. The 2023 "mlb" dailies dir was spot-checked
    clean (200/200 self-consistent) but is joined the same defensive way regardless.
  Eval: grade file game_id IS the Kalshi event_ticker (ticker-keyed games only; ESPN-
    numeric-keyed games have no ticker to parse -> no prior, has_prior=False). The ticker
    encodes date+away+home (ingame_outcome_label.parse_mlb_ticker, reused unchanged); the
    side file whose suffix normalizes to home_abbr carries P(home win) directly, the
    away-side file needs 1-prob.

Games with no matched prior NEVER get a fabricated number: prior_home=0.5 (neutral),
has_prior=False, both surfaced as an explicit feature (never a silent 0.0 read).

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no network at import (all reads
are local jsonl/parquet); never writes data/registry/; never flips a flag; never edits
ingame_outcome_label.py / live_grade.py / team_name_resolver.py; venue_history + grade
jsonl READ-ONLY.

Per-file test: covered by test_mlb_winprob_v3.py (imports this module directly).
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from domains.mlb.team_name_resolver import resolve as resolve_team_name
from scripts.platformkit.ingame import ingame_outcome_label as iol
from scripts.platformkit.ingame import live_grade as lg
from scripts.platformkit.ingame.ingame_clv_aggregate import discover_grade_files

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PM_DIRS: Tuple[Path, ...] = (
    _REPO_ROOT / "data" / "venue_history" / "polymarket" / "mlb",
    _REPO_ROOT / "data" / "venue_history" / "polymarket" / "mlb_2024plus",
)
DEFAULT_KALSHI_DIR = _REPO_ROOT / "data" / "venue_history" / "kalshi" / "mlb"

# team_name_resolver's corpus keys diverge from the pitch_states parquet's own
# abbr set in exactly these two cases (both verified against the on-disk parquet).
_RESOLVER_TO_PITCH_ABBR = {"CHC": "CUB", "SFG": "SFO"}

FEATURE_NAMES_PRIOR: Tuple[str, ...] = ("prior_logit", "has_prior")


def _logit(p: Any, eps: float = 1e-4) -> np.ndarray:
    arr = np.clip(np.asarray(p, dtype=float), eps, 1.0 - eps)
    return np.log(arr / (1.0 - arr))


def _corpus_abbr(name: Any) -> Optional[str]:
    key = resolve_team_name(str(name or ""))
    if key is None:
        return None
    return _RESOLVER_TO_PITCH_ABBR.get(key, key)


# -- train/val prior source: Polymarket day-docs -- #
def build_pm_prior_index(pm_dirs: Sequence[Path] = DEFAULT_PM_DIRS
                         ) -> Tuple[Dict[Tuple[str, frozenset], Tuple[str, float]], Dict[str, int]]:
    """{(date, frozenset({abbrA, abbrB})): (pm_home_abbr, prior_for_pm_home)} from every PM
    day-doc's FIRST price. Keyed by the UNORDERED team pair (not away/home order) because
    this corpus's own home/away labels are not reliably oriented -- the caller reorients
    at join time against a source it trusts (pitch_states' own home_team column). PM's
    literal "home" claim + its raw first price are both stored so that reorientation is
    possible without re-reading the file. Unmatchable team names / empty price series are
    skipped and counted, never guessed.
    """
    index: Dict[Tuple[str, frozenset], Tuple[str, float]] = {}
    counts = {"n_docs_seen": 0, "n_docs_matched": 0, "n_docs_unmatched_teams": 0,
              "n_docs_no_prices": 0}
    for d in pm_dirs:
        if not Path(d).is_dir():
            continue
        for path in sorted(Path(d).glob("*.jsonl")):
            if path.name.startswith("_"):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except Exception as exc:  # noqa: BLE001 -- one bad file is not a crash
                logger.debug("build_pm_prior_index: %s failed: %s", path, exc)
                continue
            for raw in lines:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    doc = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                counts["n_docs_seen"] += 1
                date = str(doc.get("date", ""))
                home_abbr = _corpus_abbr(doc.get("home"))
                away_abbr = _corpus_abbr(doc.get("away"))
                if not date or home_abbr is None or away_abbr is None:
                    counts["n_docs_unmatched_teams"] += 1
                    continue
                prices = doc.get("prices") or []
                if not prices:
                    counts["n_docs_no_prices"] += 1
                    continue
                try:
                    prior_for_pm_home = float(prices[0]["prob_home"])
                except (KeyError, TypeError, ValueError):
                    counts["n_docs_no_prices"] += 1
                    continue
                index[(date, frozenset({home_abbr, away_abbr}))] = (home_abbr, prior_for_pm_home)
                counts["n_docs_matched"] += 1
    return index, counts


def attach_priors(df: pd.DataFrame, index: Dict[Tuple[str, frozenset], Tuple[str, float]]
                  ) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Copy of df with prior_home/has_prior columns, joined off game_id's own
    "<date>-<home>-<away>-<n>" encoding (verified against the parquet's own
    home_team/away_team columns). Reorients the PM entry to THIS home team, never trusting
    PM's own home/away label. No match -> prior_home=0.5, has_prior=False.
    """
    counts = {"n_games": 0, "n_games_with_prior": 0}
    if df.empty:
        out = df.copy()
        out["prior_home"] = pd.Series(dtype=float)
        out["has_prior"] = pd.Series(dtype=bool)
        return out, counts
    game_ids = df["game_id"].astype(str)
    uniq = sorted(game_ids.unique())
    counts["n_games"] = len(uniq)
    lookup: Dict[str, Tuple[float, bool]] = {}
    for gid in uniq:
        parts = gid.split("-")
        if len(parts) < 5:
            lookup[gid] = (0.5, False)
            continue
        date, home, away = "-".join(parts[0:3]), parts[3], parts[4]
        entry = index.get((date, frozenset({home, away})))
        if entry is None:
            lookup[gid] = (0.5, False)
            continue
        pm_home_abbr, prior_for_pm_home = entry
        if pm_home_abbr == home:
            lookup[gid] = (float(prior_for_pm_home), True)
        elif pm_home_abbr == away:
            lookup[gid] = (1.0 - float(prior_for_pm_home), True)
        else:  # frozenset guarantees membership -- defensive only, never reached
            lookup[gid] = (0.5, False)
            continue
        counts["n_games_with_prior"] += 1
    out = df.copy()
    out["prior_home"] = game_ids.map(lambda g: lookup[g][0]).astype(float)
    out["has_prior"] = game_ids.map(lambda g: lookup[g][1])
    return out, counts


# -- eval (2026) prior source: Kalshi settled-market candles -- #
def _kalshi_home_prior(ticker: str, cutoff_ts: Optional[str], valid_abbrs: set,
                       kalshi_dir: Path) -> Optional[float]:
    """P(home win) from the last traded candle strictly before cutoff_ts, else None."""
    if not cutoff_ts:
        return None
    parsed = iol.parse_mlb_ticker(ticker, valid_abbrs)
    if parsed is None:
        return None
    _, away_abbr, home_abbr, _ = parsed
    for cand in sorted(Path(kalshi_dir).glob(ticker + "-*.jsonl")):
        suffix = cand.stem[len(ticker) + 1:]
        norm = iol._KALSHI_TO_ESPN.get(suffix, suffix)
        if norm not in (home_abbr, away_abbr):
            continue
        try:
            doc = json.loads(cand.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 -- unreadable candle file, never fatal
            logger.debug("_kalshi_home_prior: %s failed: %s", cand, exc)
            continue
        candles = doc.get("candles") or []
        before = [c for c in candles if str(c.get("ts", "")) < cutoff_ts]
        if not before:
            continue
        traded = [c for c in before if c.get("traded")]
        chosen = traded[-1] if traded else before[-1]
        try:
            prob_yes = float(chosen["prob"])
        except (KeyError, TypeError, ValueError):
            continue
        return prob_yes if norm == home_abbr else (1.0 - prob_yes)
    return None


def build_eval_priors(grade_dir: Optional[Path] = None, resolver: Any = None,
                      kalshi_dir: Optional[Path] = None
                      ) -> Tuple[Dict[str, Tuple[float, bool]], Dict[str, int]]:
    """{ticker (=grade game_id): (prior_home, has_prior)} for the 2026 eval corpus."""
    k_dir = Path(kalshi_dir) if kalshi_dir is not None else DEFAULT_KALSHI_DIR
    valid_abbrs = (getattr(resolver, "_abbrs", None) or set()) | set(iol._KALSHI_TO_ESPN)
    files = discover_grade_files(grade_dir, sport="mlb")
    out: Dict[str, Tuple[float, bool]] = {}
    counts = {"n_games": 0, "n_games_with_prior": 0}
    for path in files:
        try:
            pairs = lg._load_pairs(path)
        except Exception as exc:  # noqa: BLE001 -- one bad file is not a crash
            logger.debug("build_eval_priors: %s failed: %s", path, exc)
            continue
        if not pairs:
            continue
        ticker = str(pairs[0].get("game_id", path.stem))
        if ticker in out:
            continue
        counts["n_games"] += 1
        first_ts = min(str(p.get("ts", "")) for p in pairs if p.get("ts"))
        prior = _kalshi_home_prior(ticker, first_ts, valid_abbrs, k_dir)
        if prior is None:
            out[ticker] = (0.5, False)
        else:
            out[ticker] = (float(prior), True)
            counts["n_games_with_prior"] += 1
    return out, counts


# -- eval-tick assembly + diagnostic helper (kept here to keep mlb_winprob_v3.py <=300 LOC) -- #
def build_eval_ticks_with_prior(eval_ticks_fn: Any, grade_dir: Optional[Path] = None,
                                resolver: Any = None, kalshi_dir: Optional[Path] = None
                                ) -> Tuple[List[Dict[str, Any]], Dict[str, int], Dict[str, int]]:
    """eval_ticks_fn is mlb_winprob_v2.build_eval_ticks, passed in (not imported here) so
    this module never depends on v2's orchestration module -- only the reverse."""
    ticks, counts = eval_ticks_fn(grade_dir, resolver)
    eval_priors, prior_counts = build_eval_priors(grade_dir, resolver, kalshi_dir)
    for t in ticks:
        pr, has = eval_priors.get(t["game_id"], (0.5, False))
        t["prior_home"], t["has_prior"] = pr, has
    return ticks, counts, prior_counts


def mean_pred_vs_realized(ticks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not ticks:
        return None
    p = [t["model_prob"] for t in ticks]
    y = [t["outcome"] for t in ticks]
    return {"mean_pred": sum(p) / len(p), "realized_rate": sum(y) / len(y), "n_ticks": len(ticks)}


__all__ = [
    "DEFAULT_PM_DIRS", "DEFAULT_KALSHI_DIR", "FEATURE_NAMES_PRIOR",
    "build_pm_prior_index", "attach_priors", "build_eval_priors",
    "build_eval_ticks_with_prior", "mean_pred_vs_realized",
]
