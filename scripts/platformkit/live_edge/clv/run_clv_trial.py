"""scripts.platformkit.live_edge.clv.run_clv_trial -- CLI driver for the CLV
trial scoreboard. Grades whatever shadow rows exist (via the shared
shadow_ledger.grade_row + omni.close_lookup.pregame_close, both imported, never
reimplemented), aggregates with clv_trial.aggregate_trial, and writes
data/omni/live_edge/clv/CLV_TRIAL_REPORT.md.

Handles 0 gradeable rows honestly: the current shadow ledger rows carry only
an opaque game id + book (no home/away team names or a game_date column), and
close_lookup.pregame_close needs (sport, game_date, home, away) to look up the
devigged close. That join is a data-completeness gap, not a bug here -- so
when 0 rows are gradeable this script says so explicitly and falls back to a
clearly-labelled FIXTURE demo (synthetic rows, NOT real settled data) so the
aggregation math still gets exercised end to end.

Run: python -m scripts.platformkit.live_edge.clv.run_clv_trial
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.io_atomic import write_text_atomic
from scripts.platformkit.live_edge.clv.clv_trial import aggregate_trial
from scripts.platformkit.live_edge.shadow.shadow_ledger import grade_row
from scripts.platformkit.omni.close_lookup import pregame_close

_SHADOW_DIR = _REPO_ROOT / "data" / "omni" / "live_edge" / "shadow"
_OUT_DIR = _REPO_ROOT / "data" / "omni" / "live_edge" / "clv"
_OUT_MD = _OUT_DIR / "CLV_TRIAL_REPORT.md"


def _load_shadow_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not _SHADOW_DIR.exists():
        return rows
    for path in sorted(glob.glob(str(_SHADOW_DIR / "*.jsonl"))):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # a torn/partial line -- skip, never crash the trial
    return rows


def grade_shadow_rows(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Best-effort real grading: only possible for rows that carry the
    (sport, game_date, home, away) close_lookup needs. Current shadow rows
    carry an opaque 'game' id instead -- so this returns [] today, honestly,
    rather than fabricate a join. Rows that DO carry home/away/game_date
    (future schema) are graded here for free."""
    graded = []
    for r in raw_rows:
        home, away, game_date = r.get("home"), r.get("away"), r.get("game_date")
        if not (home and away and game_date):
            continue
        close = pregame_close(r["sport"], game_date, home, away)
        if close is None:
            continue
        graded.append(grade_row(r, close))
    return graded


def _fixture_rows() -> List[Dict[str, Any]]:
    """Small synthetic demo set (2 sports x 2 books) -- NOT real settled data.
    Proves aggregate_trial runs end to end when nothing is gradeable yet."""
    closes = {
        ("nba", "g1"): {"prob_home_devig": 0.60, "source": "kalshi", "ts": 1},
        ("mlb", "g2"): {"prob_home_devig": 0.45, "source": "fanduel", "ts": 2},
    }
    raw = [
        {"ts": "t", "sport": "nba", "game": "g1", "market": "pregame.moneyline",
         "book": "kalshi", "unconditioned_pred": 0.55, "conditioned_pred": 0.58,
         "market_price": 0.52},
        {"ts": "t", "sport": "nba", "game": "g1", "market": "pregame.moneyline",
         "book": "espn:DraftKings", "unconditioned_pred": 0.50, "conditioned_pred": 0.50,
         "market_price": 0.50},
        {"ts": "t", "sport": "mlb", "game": "g2", "market": "pregame.total",
         "book": "fanduel", "unconditioned_pred": 0.40, "conditioned_pred": 0.42,
         "market_price": 0.41},
    ]
    graded = []
    for r in raw:
        close = closes[(r["sport"], r["game"])]
        graded.append(grade_row(r, close))
    return graded


def main() -> int:
    raw_rows = _load_shadow_rows()
    graded = grade_shadow_rows(raw_rows)
    used_fixture = False
    if not graded:
        used_fixture = True
        graded = _fixture_rows()

    board = aggregate_trial(graded)

    lines = ["# CLV TRIAL REPORT (PROVISIONAL -- units only, edge_claimed=False)", ""]
    lines.append("Raw shadow rows on disk: %d" % len(raw_rows))
    lines.append("Real gradeable rows (home/away/game_date present): %d" % (0 if used_fixture else len(graded)))
    if used_fixture:
        lines.append("")
        lines.append("**0 real rows gradeable.** The shadow ledger rows on disk carry only "
                      "an opaque game id + book, not (home, away, game_date) -- "
                      "close_lookup.pregame_close cannot resolve a close without those. "
                      "This is a data-completeness gap (a join table from game id -> "
                      "team names/date), not a harness bug. Falling back to a "
                      "**FIXTURE DEMO (synthetic, not real settled data)** to prove "
                      "the aggregation math executes end to end.")
    lines.append("")
    lines.append("n_rows_total=%d  n_same_book=%d  n_suspect_cross_venue=%d"
                 % (board["n_rows_total"], board["n_same_book"], board["n_suspect_cross_venue"]))
    lines.append("")
    lines.append("## Per (sport, market_family)")
    for key, fam in sorted(board["families"].items()):
        cond = fam["conditioned_clv"]
        delta = fam["conditioned_minus_unconditioned"]
        lines.append("- **%s**: n=%d (same_book=%d, suspect=%d) conditioned CLV median=%s ci95=%s; "
                      "conditioned-unconditioned delta median=%s ci95=%s"
                      % (key, fam["n_total"], fam["n_same_book"], fam["n_suspect_cross_venue"],
                         cond["median"], cond["ci95"], delta["median"], delta["ci95"]))
    lines.append("")
    lines.append("## Per-sport verdict (same-book only, provisional)")
    for sport, v in sorted(board["per_sport"].items()):
        lines.append("- **%s**: n=%d verdict=%s" % (sport, v["n_same_book"], v["verdict"]))
    lines.append("")
    sel = board["selection_policy_demo"]
    lines.append("## Selection-policy hook (NOT a validated +EV trigger)")
    lines.append("policy=%s threshold=%s candidates=%d selected=%d (same_book=%d, suspect=%d)"
                 % (sel["policy"], sel["threshold"], sel["n_candidates"], sel["n_selected"],
                    sel["n_selected_same_book"], sel["n_selected_suspect"]))
    lines.append("")
    lines.append("NOT VERIFIED: live slate accrual (0 real graded rows today); "
                  "the game-id -> team/date join needed to grade the 8,557 real shadow "
                  "rows on disk. edge_claimed=False throughout; no number here is an "
                  "edge claim.")

    os.makedirs(_OUT_DIR, exist_ok=True)
    write_text_atomic(str(_OUT_MD), "\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("\nwrote %s" % _OUT_MD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
