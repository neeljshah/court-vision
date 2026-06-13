"""clv_view.py — dashboard row shapers for the HONEST CLV tracker.

This is the ONLY CLV file permitted to import the read-only HTML renderer
``scripts.platformkit.frontend.board_html``.  It turns settled/unsettled
PickCLV records (from clv.py) into plain row dicts the board renderer can
display, and optionally writes a self-contained static page to a gitignored
local path.

Honest framing: CLV is backward-looking — did your bet-time price beat the
closing price?  Positive = you beat the close.  It is a record of past
prices, not a forward edge and not realized P/L.  Markets are efficient; no
model edge is claimed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from scripts.platformkit.frontend import clv as _clv

# board_html is imported defensively so this module still loads (and tests for
# the pure row shapers still run) on a tree where board_html's deps are absent.
try:  # pragma: no cover - exercised indirectly
    from scripts.platformkit.frontend import board_html as _board_html
except Exception:  # pragma: no cover
    _board_html = None  # type: ignore[assignment]

_HONEST_NOTE = (
    "CLV is backward-looking: did your bet-time price beat the closing price? "
    "Positive = you beat the close. A record of past prices, not a forward "
    "edge and not realized P/L. Markets are efficient; no model edge is claimed."
)

_ROW_KEYS = (
    "sport", "event_id", "market", "side", "bet_decimal",
    "close_decimal", "clv_pct", "ev_delta_usd", "line_clv", "settled",
)


def _round(val: Any, n: int = 4) -> Any:
    if val is None:
        return None
    try:
        return round(float(val), n)
    except (TypeError, ValueError):
        return val


def clv_board_rows(
    picks: Optional[list] = None, root: Optional[Path] = None
) -> list[dict]:
    """Shape PickCLV records into board-renderable row dicts.

    Each row carries the CLV columns plus board_html-friendly aliases so the
    generic renderer (which reads ``home``/``away``/``model_prob`` etc.) does
    not crash on these rows.
    """
    if picks is None:
        picks = _clv.load_picks(root=root)
    rows: list[dict] = []
    for p in picks:
        clv_pct = _round(p.clv_pct, 4)
        row = {
            "sport": p.sport,
            "event_id": p.event_id,
            "market": p.market,
            "side": p.side,
            "bet_decimal": _round(p.bet_decimal, 4),
            "close_decimal": _round(p.close_decimal, 4),
            "clv_pct": clv_pct,
            "ev_delta_usd": _round(p.ev_delta_usd, 4),
            "line_clv": _round(p.line_clv, 4),
            "settled": bool(p.settled),
            # board_html aliases (so the generic renderer is tolerant) ────────
            "home": p.event_id,
            "away": f"{p.market} {p.side}".strip(),
            "date": "",
            "model_prob": None,
            "market_fair_prob": None,
            # diff column on the board doubles as the CLV fraction (diagnostic)
            "edge_vs_market": (clv_pct / 100.0) if clv_pct is not None else None,
            "best_book": "",
            "best_line": p.close_decimal if p.settled else p.bet_decimal,
            "calibration_tag": "settled" if p.settled else "open",
        }
        rows.append(row)
    return rows


def clv_dashboard(root: Optional[Path] = None) -> dict:
    """Return a board-shaped dict: {"clv": [row, ...]}."""
    return {"clv": clv_board_rows(root=root)}


def write_clv_html(
    root: Optional[Path] = None, out_path: Optional[Path] = None
) -> Optional[Path]:
    """Render the CLV dashboard to a gitignored-local HTML file.

    Returns the written path, or None if board_html is unavailable.  Defensive:
    only writes when the board_html API fits.
    """
    if _board_html is None:
        return None
    base = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    dest = Path(out_path) if out_path is not None else base / "vault" / "Frontend" / "clv.html"
    board = clv_dashboard(root=root)
    if hasattr(_board_html, "write_html"):
        _board_html.write_html(board, dest, honest_note=_HONEST_NOTE)
        return dest
    if hasattr(_board_html, "render_board_html"):
        html_str = _board_html.render_board_html(board, honest_note=_HONEST_NOTE)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html_str, encoding="utf-8")
        return dest
    return None


if __name__ == "__main__":  # pragma: no cover
    import json

    print(json.dumps(clv_dashboard(), indent=2, default=str))
