"""
board_html.py — render a self-contained static HTML board page.

Usage
-----
    from scripts.platformkit.frontend.board_html import render_board_html, write_html

    html = render_board_html(board, honest_note="...")
    write_html(board, "out/board.html")

The `board` argument is dict[str, list[dict]] — keys are sport names, values
are lists of row dicts emitted by board.py.  Expected row keys:
    sport, date, home, away, model_prob, market_fair_prob, edge_vs_market,
    best_book, best_line, clv_placeholder, calibration_tag

This module intentionally does NOT import board.py at module level.
"""
from __future__ import annotations

import html
import os
from pathlib import Path
from typing import Any

_DEFAULT_HONEST_NOTE = (
    "Calibrated predictions + best available market lines — "
    "markets are efficient, NO model edge is claimed; "
    "value = line-shopping / devig / CLV."
)

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f1117;
    color: #e2e8f0;
    padding: 24px 16px;
    min-height: 100vh;
}
.banner {
    background: #1e293b;
    border: 1px solid #334155;
    border-left: 4px solid #f59e0b;
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 24px;
    font-size: 0.85rem;
    color: #94a3b8;
    line-height: 1.5;
}
.banner strong { color: #fbbf24; }
h1 {
    font-size: 1.4rem;
    font-weight: 700;
    color: #f1f5f9;
    margin-bottom: 6px;
}
.subtitle { font-size: 0.8rem; color: #64748b; margin-bottom: 20px; }
.sport-section { margin-bottom: 36px; }
.sport-label {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #64748b;
    margin-bottom: 8px;
}
table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
    background: #1e293b;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid #334155;
}
thead { background: #0f172a; }
th {
    padding: 10px 12px;
    text-align: left;
    font-weight: 600;
    color: #94a3b8;
    font-size: 0.75rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    white-space: nowrap;
    cursor: pointer;
    user-select: none;
    border-bottom: 1px solid #334155;
}
th:hover { color: #e2e8f0; background: #1e293b; }
th.sorted-asc::after { content: " ▲"; color: #60a5fa; }
th.sorted-desc::after { content: " ▼"; color: #60a5fa; }
td {
    padding: 10px 12px;
    border-bottom: 1px solid #1e2d3d;
    color: #cbd5e1;
    white-space: nowrap;
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: #263447; }
.prob { font-weight: 600; color: #60a5fa; }
.diff-pos { color: #34d399; }
.diff-neg { color: #f87171; }
.diff-zero { color: #94a3b8; }
.tag {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.7rem;
    font-weight: 600;
    background: #1e3a5f;
    color: #7dd3fc;
}
.none-val { color: #475569; }
"""

_SORT_JS = """
(function () {
  document.querySelectorAll('table').forEach(function (tbl) {
    var ths = tbl.querySelectorAll('thead th');
    var dir = {};
    ths.forEach(function (th, ci) {
      th.addEventListener('click', function () {
        var asc = dir[ci] !== true;
        dir = {}; dir[ci] = asc;
        ths.forEach(function (h) {
          h.classList.remove('sorted-asc', 'sorted-desc');
        });
        th.classList.add(asc ? 'sorted-asc' : 'sorted-desc');
        var tbody = tbl.querySelector('tbody');
        var rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort(function (a, b) {
          var av = a.cells[ci] ? a.cells[ci].getAttribute('data-v') || a.cells[ci].innerText : '';
          var bv = b.cells[ci] ? b.cells[ci].getAttribute('data-v') || b.cells[ci].innerText : '';
          var an = parseFloat(av), bn = parseFloat(bv);
          if (!isNaN(an) && !isNaN(bn)) return asc ? an - bn : bn - an;
          return asc ? av.localeCompare(bv) : bv.localeCompare(av);
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  });
})();
"""

_HEADERS = [
    ("Sport", "sport"),
    ("Game", None),
    ("Date", "date"),
    ("Model Prob", "model_prob"),
    ("Market Fair", "market_fair_prob"),
    ("Diff (diagnostic)", "edge_vs_market"),
    ("Best Book", "best_book"),
    ("Best Line", "best_line"),
    ("Calibration", "calibration_tag"),
]


def _fmt_prob(val: Any) -> tuple[str, str]:
    """Return (display_text, data_v) for a probability value."""
    if val is None:
        return '<span class="none-val">—</span>', ""
    try:
        pct = float(val) * 100
        return f'<span class="prob">{pct:.1f}%</span>', f"{pct:.4f}"
    except (TypeError, ValueError):
        return html.escape(str(val)), str(val)


def _fmt_diff(val: Any) -> tuple[str, str]:
    if val is None:
        return '<span class="none-val">—</span>', ""
    try:
        v = float(val)
        pct = v * 100
        cls = "diff-pos" if v > 0.005 else ("diff-neg" if v < -0.005 else "diff-zero")
        sign = "+" if v > 0 else ""
        return f'<span class="{cls}">{sign}{pct:.1f}pp</span>', f"{pct:.4f}"
    except (TypeError, ValueError):
        return html.escape(str(val)), str(val)


def _fmt_cell(val: Any) -> tuple[str, str]:
    if val is None:
        return '<span class="none-val">—</span>', ""
    return html.escape(str(val)), str(val)


def _render_row(row: dict) -> str:
    home = row.get("home") or ""
    away = row.get("away") or ""
    game = html.escape(f"{away} @ {home}") if home or away else "—"

    cells_html = []

    sport_txt, sport_dv = _fmt_cell(row.get("sport"))
    cells_html.append(f'<td data-v="{html.escape(sport_dv)}">{sport_txt}</td>')

    cells_html.append(f'<td data-v="{html.escape(game)}">{game}</td>')

    date_txt, date_dv = _fmt_cell(row.get("date"))
    cells_html.append(f'<td data-v="{html.escape(date_dv)}">{date_txt}</td>')

    mp_html, mp_dv = _fmt_prob(row.get("model_prob"))
    cells_html.append(f'<td data-v="{mp_dv}">{mp_html}</td>')

    mfp_html, mfp_dv = _fmt_prob(row.get("market_fair_prob"))
    cells_html.append(f'<td data-v="{mfp_dv}">{mfp_html}</td>')

    diff_html, diff_dv = _fmt_diff(row.get("edge_vs_market"))
    cells_html.append(f'<td data-v="{diff_dv}">{diff_html}</td>')

    book_txt, book_dv = _fmt_cell(row.get("best_book"))
    cells_html.append(f'<td data-v="{html.escape(book_dv)}">{book_txt}</td>')

    line_txt, line_dv = _fmt_cell(row.get("best_line"))
    cells_html.append(f'<td data-v="{html.escape(line_dv)}">{line_txt}</td>')

    tag_raw = row.get("calibration_tag")
    if tag_raw is None:
        tag_html = '<span class="none-val">—</span>'
        tag_dv = ""
    else:
        tag_html = f'<span class="tag">{html.escape(str(tag_raw))}</span>'
        tag_dv = str(tag_raw)
    cells_html.append(f'<td data-v="{html.escape(tag_dv)}">{tag_html}</td>')

    return "<tr>" + "".join(cells_html) + "</tr>"


def _render_thead() -> str:
    ths = "".join(f"<th>{h}</th>" for h, _ in _HEADERS)
    return f"<thead><tr>{ths}</tr></thead>"


def _render_table(rows: list[dict]) -> str:
    tbody_rows = "".join(_render_row(r) for r in rows)
    return f"<table>{_render_thead()}<tbody>{tbody_rows}</tbody></table>"


def render_board_html(
    board: dict,
    honest_note: str = _DEFAULT_HONEST_NOTE,
) -> str:
    """Render board data as a self-contained static HTML string."""
    banner = (
        f'<div class="banner"><strong>Research tool only.</strong> '
        f"{html.escape(honest_note)}</div>"
    )

    sections: list[str] = []
    for sport, rows in sorted(board.items()):
        if not rows:
            continue
        tbl = _render_table(rows)
        sec = (
            f'<div class="sport-section">'
            f'<div class="sport-label">{html.escape(sport)}</div>'
            f"{tbl}"
            f"</div>"
        )
        sections.append(sec)

    body_content = "".join(sections) if sections else "<p>No games today.</p>"

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        "<title>Platform Board</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        '<h1>Platform Board</h1>\n'
        '<p class="subtitle">Sortable — click any column header · '
        '<a href="/api/intel">per-sport intelligence panels</a> '
        '(brain: archetypes / schemes / trends — understanding only, no edge)</p>\n'
        f"{banner}\n"
        f"{body_content}\n"
        f"<script>{_SORT_JS}</script>\n"
        "</body>\n"
        "</html>"
    )


def write_html(board: dict, out_path: str | os.PathLike, honest_note: str = _DEFAULT_HONEST_NOTE) -> None:
    """Render and write HTML to out_path; creates parent dirs as needed."""
    html_str = render_board_html(board, honest_note=honest_note)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_str, encoding="utf-8")
