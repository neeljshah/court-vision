"""/clv standalone HTML page.

Renders the data exposed at /api/clv/summary as a dark-theme dashboard with:
  * Headline tiles (avg CLV bps, win%, Sharpe, bet count).
  * by_book table.
  * by_stat table.
  * Daily CLV sparkline (data/clv/daily_clv.csv).

PRICE UNITS ONLY. This page is served unauthenticated, so it renders no dollar
PnL and no ROI percentage -- see .claude/rules/no-edge-claims.md. CLV in basis
points is a price-vs-close measurement, not a profit claim.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_ROOT = Path(__file__).resolve().parent.parent


def _read_daily_clv_csv(days: int) -> list[dict]:
    """Return rows from data/clv/daily_clv.csv inside the last N days."""
    import csv
    path = _ROOT / "data" / "clv" / "daily_clv.csv"
    if not path.exists():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("date", "") < cutoff:
                    continue
                rows.append(r)
    except OSError:
        return []
    rows.sort(key=lambda r: r.get("date", ""))
    return rows


def _sparkline_points(daily: list[dict], width: int = 600, height: int = 80,
                      column: str = "avg_clv_bps") -> dict:
    """Pre-compute SVG polyline points + min/max for a daily *column* series.

    Defaults to the CLV series, not ROI. A row missing the column is SKIPPED
    rather than coerced to 0.0, so an absent column yields an empty series and
    the sparkline is simply not drawn instead of plotting a fake flat line.
    """
    vals: list[float] = []
    for r in daily:
        if r.get(column) in (None, ""):
            continue
        try:
            vals.append(float(r[column]))
        except (TypeError, ValueError):
            continue
    if not vals:
        return {"points": "", "min": 0.0, "max": 0.0, "n": 0,
                "width": width, "height": height, "zero_y": height / 2}
    vmin, vmax = min(vals), max(vals)
    # Pad the range so a flat series still draws a centred line.
    if vmax == vmin:
        vmin -= 1.0
        vmax += 1.0
    span = vmax - vmin
    n = len(vals)
    dx = width / max(n - 1, 1)
    pts = []
    for i, v in enumerate(vals):
        x = i * dx if n > 1 else width / 2
        y = height - ((v - vmin) / span) * height
        pts.append(f"{x:.1f},{y:.1f}")
    # y-coordinate of the zero line, clamped to the viewbox.
    if vmin <= 0 <= vmax:
        zero_y = height - ((0 - vmin) / span) * height
    else:
        zero_y = height if vmin > 0 else 0
    return {"points": " ".join(pts), "min": round(vmin, 2), "max": round(vmax, 2),
            "n": n, "width": width, "height": height, "zero_y": round(zero_y, 1)}


@router.get("/clv", response_class=HTMLResponse, tags=["clv"])
def clv_page(request: Request,
             days: int = Query(30, ge=1, le=365)):
    """Render the CLV dashboard. Calls /api/clv/summary via in-process import."""
    try:
        # Reuse the existing summary function — no HTTP round-trip needed.
        from api.courtvision_router import api_clv_summary  # noqa: PLC0415
        summary = api_clv_summary(days=days)
        if hasattr(summary, "body"):
            import json
            summary_dict = json.loads(summary.body)
        else:
            summary_dict = dict(summary)
    except Exception as exc:  # ultra-defensive — page must render
        # A failure renders as an explicit error banner with NO numbers. The
        # previous zero-filled dict made an outage indistinguishable from a
        # genuine flat result (audit 2026-09-17, #10).
        summary_dict = {
            "error": str(exc), "window_days": days, "n_bets": 0,
            "avg_clv_bps": None, "win_pct": None, "sharpe_30d": None,
            "by_book": {}, "by_stat": {},
        }

    daily = _read_daily_clv_csv(days)

    # Sort by_book / by_stat by avg_clv_bps desc for stable rendering.
    by_book_raw = summary_dict.get("by_book", {}) or {}
    by_book_sorted = sorted(
        by_book_raw.items(),
        key=lambda kv: float((kv[1] or {}).get("avg_clv_bps") or 0),
        reverse=True,
    )
    by_stat_raw = summary_dict.get("by_stat", {}) or {}
    by_stat_sorted = sorted(
        by_stat_raw.items(),
        key=lambda kv: float((kv[1] or {}).get("avg_clv_bps") or 0),
        reverse=True,
    )

    spark = _sparkline_points(daily)

    return _TEMPLATES.TemplateResponse(
        "clv.html",
        {"request": request, "summary": summary_dict, "daily": daily,
         "days": days, "by_book_sorted": by_book_sorted,
         "by_stat_sorted": by_stat_sorted, "spark": spark})
