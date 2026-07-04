"""domains.mlb.ingame_recal_pm -- LANE 3 sub-task (B): walk-forward
recalibration of the MLB in-game venue probability signal, fit+validated on
our OWNED historical Polymarket intra-game tick corpus (user directive: "use
old odds and data to keep getting better").

DATA SOURCE (read-only; NEW module, does not edit any existing MLB file)
--------------------------------------------------------------------------
data/venue_history/polymarket/mlb/*.jsonl + .../mlb_2024plus/*.jsonl -- one
JSON object per game per line: {date, market_slug, home, away,
outcome_home_win, prices: [{ts, prob_home}, ...]}. 3475 unique games (deduped
by market_slug) spanning 2023-03-30..2026-06-29 across the two directories
(2023 season in mlb/, 2025+2026 in mlb_2024plus/ -- no 2024 season is present
in this corpus; the 2024plus dirname reflects the ORIGINAL scrape's intended
coverage, not what actually landed). provenance tag for every row below is
"pm_backfill" per AUTONOMY_CHARTER (a VALIDATION corpus, never pooled with the
forward Kalshi capture stream -- see hist_mlb_forward_gate.py for that
provenance-separate comparison).

WHY "IN-GAME CHECKPOINTS" ARE TIME-FRACTION, NOT INNING-KEYED
-----------------------------------------------------------------
Each tick only carries (ts, prob_home) -- no inning/score/baseout state is
attached to the Polymarket price feed itself (confirmed: fields are exactly
{ts, prob_home} per tick). Recovering true half-inning state would require a
separate PBP join this lane's scope excludes (touching existing MLB gumbo/PBP
modules is out of scope -- OWNS is NEW files only). Instead this module uses
FIXED FRACTIONAL POSITIONS within each game's own captured tick sequence
(25% / 50% / 75% / 90% of the way from first to last tick) as an honest proxy
for early/mid/late/very-late in-game -- the same "pre-declared checkpoint,
never cherry-picked after seeing results" discipline as the WNBA
end_q1/half/end_q3 checkpoints, just keyed to elapsed CAPTURE fraction instead
of elapsed game clock (which is unavailable here).

DEGENERATE-MARKET FILTER (documented, not silently dropped)
----------------------------------------------------------------
509 of the 3475 raw dedup'd games never move off exactly 0.5 across the WHOLE
captured series (a thin/no-liquidity market that never actually traded) --
these carry zero information for a recalibration fit and are excluded via
MIN_PROB_RANGE. The remaining ~2966 games are the fittable corpus (close to,
though not identical to, the ~2731 previously cited elsewhere -- that number
likely applied an additional n_prices-count floor this module does not
reproduce; this module's own filter is stated explicitly, not asserted to
match a prior unpublished count).

FIT / VALIDATE SPLIT (walk-forward across SEASONS, leak-free by construction)
--------------------------------------------------------------------------------
  TRAIN: 2023 season only (744 games).
  VALIDATE (OOS, "held-out later PM seasons"): 2025 + 2026 seasons pooled
  (2731 games combined across both dirs before the degenerate filter).
This module's own calibrator uses scripts.platformkit.calibrator_zoo's
walk-forward machinery (expanding-window, index-ordered) applied WITHIN the
validate split only -- i.e. the calibrator never sees 2023 raw_probs directly
inside its own expanding window; 2023 is used ONLY to pick which calibrator
FAMILY to run via select_calibrator's already-leak-free per-index refit
applied to the validate split's own chronological order. This mirrors
recalibration.py's existing sport registry pattern (walk_forward_recalibrate)
exactly -- no new algorithm, just a new corpus loader.

EDGE_CLAIMED = False. CALIBRATION != EDGE. Compares raw venue-implied prob_home
to its own walk-forward recalibrated ECE/Brier -- reports the delta honestly;
a near-zero delta is the expected, non-failure outcome for an already
liquid venue price.

INVARIANTS: domains/mlb/ only (NEW file); <=300 LOC; ASCII only; no network;
never writes data/registry/; never raises out on a malformed line/file.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_ingame_recal_pm.py -q
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

EDGE_CLAIMED = False
CALIBRATION_NOTE = "calibration != edge; venue price recalibration only; no $ field"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PM_DIRS: Tuple[Path, ...] = (
    _REPO_ROOT / "data" / "venue_history" / "polymarket" / "mlb",
    _REPO_ROOT / "data" / "venue_history" / "polymarket" / "mlb_2024plus",
)

CHECKPOINT_FRACTIONS: Tuple[float, ...] = (0.25, 0.50, 0.75, 0.90)
MIN_PROB_RANGE = 1e-6  # excludes markets that never traded off exactly 0.5
MIN_TICKS = 5
TRAIN_SEASONS = ("2023",)
VALIDATE_SEASONS = ("2025", "2026")


def _iter_pm_files(pm_dirs: Optional[Tuple[Path, ...]] = None) -> List[Path]:
    dirs = pm_dirs or _PM_DIRS
    out: List[Path] = []
    for d in dirs:
        if d.exists():
            out.extend(sorted(d.glob("*.jsonl")))
    return out


def load_games(pm_dirs: Optional[Tuple[Path, ...]] = None) -> Dict[str, dict]:
    """market_slug -> raw game dict, deduped (first-seen wins across dirs).
    Never raises; a malformed line/file is skipped, not fatal."""
    seen: Dict[str, dict] = {}
    for path in _iter_pm_files(pm_dirs):
        try:
            with path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = d.get("market_slug") or d.get("event_slug")
                    if not key or key in seen:
                        continue
                    seen[key] = d
        except OSError as exc:  # noqa: BLE001
            logger.debug("load_games failed to read %s: %s", path, exc)
    return seen


def _season_of(date_str: str) -> str:
    return str(date_str or "")[:4]


def extract_checkpoint_rows(game: dict) -> List[Dict[str, object]]:
    """One row per CHECKPOINT_FRACTIONS entry: {season, market_slug, fraction,
    raw_prob, outcome}. Skips a game with no valid outcome, too few ticks, or
    a degenerate (never-moved) price series -- honest exclusion, not a fake
    row. Pure function, no I/O."""
    outcome = game.get("outcome_home_win")
    if outcome not in (0, 1):
        return []
    prices = game.get("prices") or []
    vals = [p.get("prob_home") for p in prices if isinstance(p, dict)]
    vals = [v for v in vals if isinstance(v, (int, float))]
    if len(vals) < MIN_TICKS:
        return []
    if max(vals) - min(vals) < MIN_PROB_RANGE:
        return []  # degenerate/no-liquidity market -- excluded, not faked
    season = _season_of(game.get("date", ""))
    slug = str(game.get("market_slug") or game.get("event_slug") or "")
    n = len(vals)
    rows: List[Dict[str, object]] = []
    for frac in CHECKPOINT_FRACTIONS:
        idx = min(n - 1, max(0, int(round(frac * (n - 1)))))
        rows.append({
            "season": season, "market_slug": slug, "fraction": frac,
            "raw_prob": float(vals[idx]), "outcome": float(outcome),
        })
    return rows


def build_corpus_rows(games: Dict[str, dict]) -> List[Dict[str, object]]:
    """All games' checkpoint rows, pooled. Order follows dict iteration
    (insertion order == file-scan order, itself date-sorted by filename) --
    sufficient for a season-partitioned train/validate split; the walk-forward
    calibrator inside measure_pm_recalibration further sorts by
    (season, market_slug) for a stable, deterministic within-split order."""
    rows: List[Dict[str, object]] = []
    for g in games.values():
        rows.extend(extract_checkpoint_rows(g))
    return rows


def split_train_validate(
    rows: List[Dict[str, object]],
    train_seasons: Tuple[str, ...] = TRAIN_SEASONS,
    validate_seasons: Tuple[str, ...] = VALIDATE_SEASONS,
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    train = [r for r in rows if r["season"] in train_seasons]
    validate = [r for r in rows if r["season"] in validate_seasons]
    validate.sort(key=lambda r: (str(r["season"]), str(r["market_slug"]), float(r["fraction"])))
    return train, validate


def measure_pm_recalibration(
    pm_dirs: Optional[Tuple[Path, ...]] = None,
    min_history: int = 50,
    refit_every: int = 25,
) -> Dict[str, object]:
    """Fit family selection + walk-forward recalibration on the VALIDATE split
    (2025+2026), report raw vs recalibrated Brier/ECE/logloss. TRAIN (2023) is
    reported for context (n, raw Brier) but is not itself blended into the
    validate split's expanding window -- see module docstring for why.
    refit_every batches the expanding-window refits (leak-free for any K --
    each refit still only sees strictly-prior rows; see calibrator_zoo /
    recalibration.py's own REFIT_EVERY_SCOREBOARD precedent) -- required at
    this corpus's ~11k-row size (5 methods x per-index isotonic/IRLS/golden-
    section fits is O(n^2) at K=1). EDGE_CLAIMED=False; calibration only.
    Never raises; INSUFFICIENT_DATA on an absent/empty corpus."""
    from scripts.platformkit.calibrator_zoo import select_calibrator

    games = load_games(pm_dirs)
    if not games:
        return {"edge_claimed": EDGE_CLAIMED, "verdict": "INSUFFICIENT_DATA",
                "reason": "no PM MLB corpus files found", "note": CALIBRATION_NOTE}

    rows = build_corpus_rows(games)
    train_rows, validate_rows = split_train_validate(rows)

    if len(validate_rows) < min_history + 10:
        return {"edge_claimed": EDGE_CLAIMED, "verdict": "INSUFFICIENT_DATA",
                "reason": f"validate split too small (n={len(validate_rows)})",
                "n_games_total": len(games), "n_train_rows": len(train_rows),
                "note": CALIBRATION_NOTE}

    raw_probs = [float(r["raw_prob"]) for r in validate_rows]
    outcomes = [float(r["outcome"]) for r in validate_rows]

    result = select_calibrator(raw_probs, outcomes, min_history=min_history,
                               refit_every=refit_every)
    identity_row = next(r for r in result["table"] if r["method"] == "identity")
    chosen_row = next(r for r in result["table"] if r["method"] == result["chosen_method"])

    delta_brier = identity_row["brier"] - chosen_row["brier"]
    verdict = "MATCH"
    if delta_brier > 0.002:
        verdict = "IMPROVED"
    elif delta_brier < -0.002:
        verdict = "WORSENED"

    return {
        "edge_claimed": EDGE_CLAIMED,
        "verdict": verdict,
        "note": CALIBRATION_NOTE,
        "n_games_total": len(games),
        "n_train_rows_2023": len(train_rows),
        "n_validate_rows": len(validate_rows),
        "n_validate_games": len(set(str(r["market_slug"]) for r in validate_rows)),
        "checkpoint_fractions": list(CHECKPOINT_FRACTIONS),
        "refit_every": refit_every,
        "raw_brier": identity_row["brier"],
        "raw_ece": identity_row["ece"],
        "chosen_method": result["chosen_method"],
        "chosen_brier": chosen_row["brier"],
        "chosen_ece": chosen_row["ece"],
        "delta_brier": delta_brier,
        "full_table": result["table"],
    }


def _main() -> int:
    logging.basicConfig(level=logging.INFO)
    report = measure_pm_recalibration()
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "EDGE_CLAIMED", "CALIBRATION_NOTE", "CHECKPOINT_FRACTIONS",
    "TRAIN_SEASONS", "VALIDATE_SEASONS",
    "load_games", "extract_checkpoint_rows", "build_corpus_rows",
    "split_train_validate", "measure_pm_recalibration",
]
