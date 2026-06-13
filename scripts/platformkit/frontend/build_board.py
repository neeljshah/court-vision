"""scripts.platformkit.frontend.build_board — runner that writes board.json + board.html.

Usage
-----
    python -m scripts.platformkit.frontend.build_board          # writes to vault/Frontend/
    python -m scripts.platformkit.frontend.build_board --out /tmp/board_out/

The script:
  1. Calls build_all_board() from board.py (skips sports whose corpus is absent).
  2. Writes vault/Frontend/board.json  (raw board data, UTF-8).
  3. Writes vault/Frontend/board.html  (self-contained sortable HTML via board_html.py).
  4. Prints a short per-sport summary: row count + 3 sample rows (date, model_prob,
     market_fair_prob) so the caller can verify real numbers.

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

def build(out_dir: Optional[Path] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Build and write board.json + board.html; return the board dict.

    Parameters
    ----------
    out_dir:
        Directory to write files into.  Defaults to vault/Frontend/.
        Created if it doesn't exist.

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

    # Build the board (gracefully skips absent corpora)
    board = build_all_board(repo_root=_REPO_ROOT)

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

    # Print summary
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


def _print_summary(
    board: Dict[str, List[Dict[str, Any]]],
    json_path: Path,
    html_path: Path,
) -> None:
    """Print a concise per-sport summary with sample rows."""
    print("\n" + "=" * 60)
    print("Platform Board — build summary")
    print("=" * 60)
    print(f"  JSON : {json_path}")
    print(f"  HTML : {html_path}")
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
        build(out_dir=args.out)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
