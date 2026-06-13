"""scripts.platformkit.frontend.build_board — runner that writes board.json + board.html.

Usage
-----
    python -m scripts.platformkit.frontend.build_board          # writes to vault/Frontend/
    python -m scripts.platformkit.frontend.build_board --out /tmp/board_out/
    python -m scripts.platformkit.frontend.build_board --last-n-days 30
    python -m scripts.platformkit.frontend.build_board --max-rows 100 --future-only

The script:
  1. Calls build_all_board() from board.py (skips sports whose corpus is absent).
     Default window: max_rows_per_sport=200 so board.html stays small + openable.
  2. Writes vault/Frontend/board.json  (raw board data, UTF-8).
  3. Writes vault/Frontend/board.html  (self-contained sortable HTML via board_html.py).
  4. Prints a short per-sport summary: row count + 3 sample rows (date, model_prob,
     market_fair_prob) so the caller can verify real numbers.
  5. Reports JSON and HTML file sizes.

vault/ is gitignored-local so the HTML is safe to open in a browser.

HONEST: markets are efficient — NO model edge is claimed anywhere in this module.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Repo-root discovery (three parents above this file: scripts/platformkit/frontend/)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Default output directory (gitignored-local)
_DEFAULT_OUT = _REPO_ROOT / "vault" / "Frontend"

# Default window: cap each sport at 200 rows so the HTML is small + openable.
_DEFAULT_MAX_ROWS = 200

# Banned edge-claim phrases checked in the JSON data layer (belt-and-suspenders).
# "lock" is intentionally omitted here because board_html.py's CSS legitimately
# uses "inline-block"; we only gate multi-word betting claims in the data layer.
_BANNED_WORDS = (
    "guaranteed",
    "beat the market",
    "+EV edge",
    "profit",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build(
    out_dir: Optional[Path] = None,
    *,
    last_n_days: Optional[int] = None,
    max_rows_per_sport: Optional[int] = _DEFAULT_MAX_ROWS,
    future_only: bool = False,
) -> Dict[str, List[Dict[str, Any]]]:
    """Build and write board.json + board.html; return the board dict.

    Parameters
    ----------
    out_dir:
        Directory to write files into.  Defaults to vault/Frontend/.
        Created if it doesn't exist.
    last_n_days:
        Keep only rows whose date >= (corpus_max_date - last_n_days).
        Forwarded to build_all_board().
    max_rows_per_sport:
        If last_n_days is None, keep the most-recent N rows per sport.
        Defaults to 200 so board.html is small and openable.
        Pass None to disable row-count capping (may produce a large HTML).
    future_only:
        Keep only rows with date > corpus_max_date.  Forwarded to
        build_all_board().  Typically returns 0 rows on historical corpora.

    Returns
    -------
    dict[sport_id -> list[row]] — the board data (may have empty lists for
    absent corpora).
    """
    from scripts.platformkit.frontend.board import (
        HONEST_NOTE,
        build_all_board,
        to_json,
    )
    from scripts.platformkit.frontend.board_html import render_board_html

    out = Path(out_dir) if out_dir is not None else _DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)

    # Build the board (gracefully skips absent corpora; window applied per sport)
    board = build_all_board(
        repo_root=_REPO_ROOT,
        last_n_days=last_n_days,
        max_rows_per_sport=max_rows_per_sport,
        future_only=future_only,
    )

    # Belt-and-suspenders: no banned words in the serialised board
    _assert_no_banned_words(board)

    # Write JSON
    json_path = out / "board.json"
    to_json(board, json_path)

    # Write HTML
    html_path = out / "board.html"
    html_str = render_board_html(board, honest_note=HONEST_NOTE)
    html_path.write_text(html_str, encoding="utf-8")
    logger.info("HTML written to %s", html_path)

    # Print summary (includes file sizes)
    _print_summary(board, json_path, html_path)

    return board


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _assert_no_banned_words(board: Dict[str, List[Dict[str, Any]]]) -> None:
    """Raise ValueError if any banned edge-claim phrase appears in the board JSON."""
    serialized = json.dumps(board).lower()
    for phrase in _BANNED_WORDS:
        if phrase.lower() in serialized:
            raise ValueError(
                f"Board output contains banned edge-claim phrase: {phrase!r}"
            )


def _fmt_bytes(n: int) -> str:
    """Human-readable byte count."""
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 ** 2:.2f} MB"


def _print_summary(
    board: Dict[str, List[Dict[str, Any]]],
    json_path: Path,
    html_path: Path,
) -> None:
    """Print a concise per-sport summary with sample rows and file sizes."""
    json_size = json_path.stat().st_size if json_path.exists() else 0
    html_size = html_path.stat().st_size if html_path.exists() else 0

    print("\n" + "=" * 60)
    print("Platform Board — build summary")
    print("=" * 60)
    print(f"  JSON : {json_path}  ({_fmt_bytes(json_size)})")
    print(f"  HTML : {html_path}  ({_fmt_bytes(html_size)})")
    print()

    for sport_id in sorted(board):
        rows = board[sport_id]
        if not rows:
            print(f"  {sport_id:22s}  corpus absent — skipped")
            continue

        n = len(rows)
        sample = rows[:3]
        print(f"  {sport_id:22s}  {n:>5d} rows")
        for i, row in enumerate(sample):
            date = row.get("date", "?")
            mp = row.get("model_prob")
            mfp = row.get("market_fair_prob")
            mp_str = f"{mp:.3f}" if mp is not None else "None"
            mfp_str = f"{mfp:.3f}" if mfp is not None else "None"
            print(
                f"    [{i}] date={date}  "
                f"model_prob={mp_str}  market_fair_prob={mfp_str}"
            )

    print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build multi-sport board.json + board.html into vault/Frontend/."
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output directory (default: vault/Frontend/)",
    )
    p.add_argument(
        "--last-n-days",
        type=int,
        default=None,
        metavar="N",
        dest="last_n_days",
        help="Keep only rows within the last N days of the corpus.",
    )
    p.add_argument(
        "--max-rows",
        type=int,
        default=_DEFAULT_MAX_ROWS,
        metavar="N",
        dest="max_rows_per_sport",
        help=f"Max rows per sport when --last-n-days not set (default: {_DEFAULT_MAX_ROWS}).",
    )
    p.add_argument(
        "--future-only",
        action="store_true",
        dest="future_only",
        help="Keep only rows dated after the corpus ceiling (usually returns 0 rows).",
    )
    p.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable INFO logging.",
    )
    return p.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        build(
            out_dir=args.out,
            last_n_days=args.last_n_days,
            max_rows_per_sport=args.max_rows_per_sport,
            future_only=args.future_only,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
