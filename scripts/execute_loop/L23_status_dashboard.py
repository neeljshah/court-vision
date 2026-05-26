"""L23_status_dashboard.py — Local HTTP Status Dashboard (BUILD L23).

Serves a dark-themed NBA AI status dashboard at http://127.0.0.1:8765/
Aggregates bankroll, edges, positions, CLV, freshness, health, settlements.

Public API
----------
    main(argv=None) -> int
    serve(port, host) -> None
    get_dashboard_data() -> dict          # 10 s cache
    render_dashboard_html(data) -> str
    format_pnl(x) -> str                 # colored HTML span
    format_pct(x) -> str
    svg_sparkline(values, width, height) -> str
    staleness_days(path) -> int | None
    _atomic_write_text(path, text) -> None
    _atomic_write_json(path, payload) -> None

Environment Variables
---------------------
    none — this module reads no environment variables directly.
    (Flask/http.server host/port are passed as arguments, not env vars.)
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import pathlib
import string
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = pathlib.Path(__file__).resolve()
_PROJECT = _HERE.parent.parent.parent
_LEDGER = _PROJECT / "data" / "ledger"
_MODELS = _PROJECT / "data" / "models"
_DFS = _PROJECT / "data" / "dfs_slates"
_SNAPSHOTS = _PROJECT / "scripts" / "validation" / "real_lines_check" / "snapshots"
_TEMPLATE = _HERE.parent / "templates" / "dashboard.html"

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
_CACHE: Tuple[float, dict] = (0.0, {})


# ---------------------------------------------------------------------------
# Atomic write helpers (v2 hardened pattern — used for any future file output)
# ---------------------------------------------------------------------------

def _atomic_write_text(path: pathlib.Path, text: str) -> None:
    """Write *text* to *path* atomically via a sibling temp file.

    Guarantees readers never see a partial write.  On failure the original
    file is left untouched and the temp file is cleaned up.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_write_json(path: pathlib.Path, payload: Any) -> None:
    """Serialize *payload* as indented JSON and write to *path* atomically."""
    _atomic_write_text(path, json.dumps(payload, indent=2, default=str))
_CACHE_TTL = 10.0  # seconds


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def staleness_days(path: pathlib.Path) -> Optional[int]:
    """Return file age in whole days, or None if file missing."""
    try:
        mtime = path.stat().st_mtime
        age_s = time.time() - mtime
        return max(0, int(age_s / 86400))
    except (OSError, ValueError):
        return None


def format_pnl(x: float) -> str:
    """Return HTML <span> with green/red/gray color based on sign."""
    if x > 0:
        color = "#16a34a"
        sign = "+"
    elif x < 0:
        color = "#dc2626"
        sign = ""
    else:
        color = "#6b7280"
        sign = ""
    return f'<span style="color:{color};font-weight:700">{sign}${x:,.2f}</span>'


def format_pct(x: float) -> str:
    """Return percentage string with sign and 1 decimal place."""
    if x > 0:
        color = "#16a34a"
        sign = "+"
    elif x < 0:
        color = "#dc2626"
        sign = ""
    else:
        color = "#6b7280"
        sign = ""
    return f'<span style="color:{color};font-weight:700">{sign}{x:.1f}%</span>'


def svg_sparkline(values: list, width: int = 120, height: int = 30) -> str:
    """Return inline SVG polyline of normalized values.

    Trend sign (positive slope → green, else red) controls stroke color.
    """
    if not values or len(values) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'

    lo, hi = min(values), max(values)
    rng = hi - lo or 1.0
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        px = i / (n - 1) * (width - 4) + 2
        py = height - 4 - ((v - lo) / rng) * (height - 8)
        pts.append(f"{px:.1f},{py:.1f}")
    color = "#16a34a" if values[-1] >= values[0] else "#dc2626"
    points_str = " ".join(pts)
    return (
        f'<svg width="{width}" height="{height}" '
        f'style="overflow:visible;vertical-align:middle">'
        f'<polyline points="{points_str}" fill="none" stroke="{color}" stroke-width="1.5"/>'
        f"</svg>"
    )


# ---------------------------------------------------------------------------
# Data collectors — each returns a dict; all errors are caught
# ---------------------------------------------------------------------------

def _collect_bankroll() -> dict:
    path = _LEDGER / "bankroll_state.json"
    if not path.exists():
        return {"status": "missing", "message": "L18 not initialized"}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        return {
            "current": state.get("current_bankroll", 0.0),
            "daily_pnl": state.get("daily_pnl", 0.0),
            "weekly_pnl": state.get("weekly_pnl", 0.0),
            "last_updated": state.get("last_updated", "unknown"),
            "kill_switch_active": state.get("kill_switch_active", False),
            "kill_switch_reason": state.get("kill_switch_reason", ""),
            "test_mode": state.get("test_mode", False),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _load_bets_df() -> Optional[List[dict]]:
    """Load bets from parquet or CSV fallback. Returns list of row dicts."""
    parquet_path = _LEDGER / "bets.parquet"
    csv_path = _LEDGER / "bets.csv"
    try:
        import pandas as pd  # type: ignore
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            return df.to_dict("records")
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            return df.to_dict("records")
    except Exception:
        pass
    return None


def _collect_positions() -> dict:
    rows = _load_bets_df()
    if rows is None:
        return {"status": "missing", "message": "bets.parquet not found"}
    try:
        open_rows = [r for r in rows if str(r.get("status", "")).upper() == "OPEN"]
        total_exp = sum(float(r.get("stake", 0) or 0) for r in open_rows)
        return {"count": len(open_rows), "total_exposure": total_exp}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _collect_edges() -> dict:
    # Try importing L02 snapshot path first
    snapshot_dir = _SNAPSHOTS
    today = date.today().isoformat()

    # Look for today's DK slate JSON
    slate_pattern = str(_DFS / f"dk_{today}_*.json")
    slate_files = sorted(glob.glob(slate_pattern))
    slate_source = "dk_slate"

    # Fallback: try latest snapshot
    if not slate_files:
        snap_pattern = str(snapshot_dir / "*.json")
        snap_files = sorted(glob.glob(snap_pattern), key=lambda f: pathlib.Path(f).stat().st_mtime if pathlib.Path(f).exists() else 0)
        if snap_files:
            slate_files = [snap_files[-1]]
            slate_source = "snapshot"

    if not slate_files:
        return {"status": "missing", "message": f"No edges meet threshold tonight"}

    try:
        data = json.loads(pathlib.Path(slate_files[-1]).read_text(encoding="utf-8"))
        # Normalise: edges may live under "edges" key or be a list
        edges = data if isinstance(data, list) else data.get("edges", [])
        edges = sorted(edges, key=lambda e: float(e.get("ev", e.get("edge", 0))), reverse=True)[:10]
        return {"edges": edges, "source": slate_source, "file": pathlib.Path(slate_files[-1]).name}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _collect_clv() -> dict:
    pattern = str(_LEDGER / "clv_report_*.json")
    files = sorted(glob.glob(pattern), key=lambda f: pathlib.Path(f).stat().st_mtime if pathlib.Path(f).exists() else 0)
    if not files:
        return {"status": "missing", "message": "No CLV reports found"}
    try:
        latest = json.loads(pathlib.Path(files[-1]).read_text(encoding="utf-8"))
        # Try to build 30-day history across all report files
        history: Dict[str, List[float]] = {}
        for f in files[-30:]:
            try:
                rep = json.loads(pathlib.Path(f).read_text(encoding="utf-8"))
                per_stat = rep.get("per_stat", rep.get("by_stat", {}))
                for stat, val in per_stat.items():
                    v = float(val.get("mean_clv", val) if isinstance(val, dict) else val)
                    history.setdefault(stat, []).append(v)
            except Exception:
                pass
        # Mean per stat
        means = {s: sum(vs) / len(vs) for s, vs in history.items() if vs}
        return {
            "latest_file": pathlib.Path(files[-1]).name,
            "means": means,
            "history": history,
            "raw": latest,
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _collect_freshness() -> dict:
    targets = {
        "win_prob_metrics.json": _MODELS / "win_prob_metrics.json",
        "prop_pergame_walk_forward.json": _MODELS / "prop_pergame_walk_forward.json",
    }
    result = {}
    for name, path in targets.items():
        days = staleness_days(path)
        result[name] = {"days": days, "exists": path.exists()}
    return result


def _collect_health() -> dict:
    path = _LEDGER / "system_health.json"
    if not path.exists():
        # Also check data root
        alt = _PROJECT / "data" / "system_health.json"
        if alt.exists():
            path = alt
        else:
            return {"status": "missing", "message": "system_health.json not found (L38 not run)"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"data": data, "last_modified": staleness_days(path)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _collect_settlements() -> dict:
    rows = _load_bets_df()
    if rows is None:
        return {"status": "missing", "message": "bets.parquet not found"}
    try:
        settled = [r for r in rows if str(r.get("status", "")).upper() != "OPEN"]
        # Sort by placed_at or settle_time desc, take last 20
        def _sort_key(r: dict) -> str:
            for k in ("settle_time", "settled_at", "placed_at", "date"):
                v = r.get(k)
                if v:
                    return str(v)
            return ""
        settled_sorted = sorted(settled, key=_sort_key, reverse=True)[:20]
        return {"rows": settled_sorted}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


# ---------------------------------------------------------------------------
# Master data collector with cache
# ---------------------------------------------------------------------------

def get_dashboard_data() -> dict:
    """Collect all dashboard sections. Returns cached result within 10 s TTL."""
    global _CACHE
    now = time.time()
    if now - _CACHE[0] < _CACHE_TTL and _CACHE[1]:
        return _CACHE[1]

    sections: Dict[str, Any] = {}
    collectors = {
        "bankroll": _collect_bankroll,
        "positions": _collect_positions,
        "edges": _collect_edges,
        "clv": _collect_clv,
        "freshness": _collect_freshness,
        "health": _collect_health,
        "settlements": _collect_settlements,
    }
    for key, fn in collectors.items():
        try:
            sections[key] = fn()
        except Exception as exc:
            sections[key] = {"status": "missing", "message": str(exc)}

    sections["_meta"] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "nba_date": date.today().isoformat(),
    }
    _CACHE = (now, sections)
    return sections


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

def _overall_status(data: dict) -> Tuple[str, str]:
    """Return (label, css_class) from health section."""
    h = data.get("health", {})
    if isinstance(h, dict) and "data" in h:
        raw = h["data"]
        os_ = raw.get("overall_status", raw.get("status", ""))
        if isinstance(os_, str):
            os_l = os_.lower()
            if "ok" in os_l or "green" in os_l:
                return "SYSTEM OK", "status-green"
            if "warn" in os_l or "yellow" in os_l:
                return "DEGRADED", "status-yellow"
            if "error" in os_l or "red" in os_l:
                return "ERROR", "status-red"
    return "UNKNOWN", "status-gray"


def _render_header(data: dict) -> str:
    meta = data.get("_meta", {})
    nba_date = meta.get("nba_date", date.today().isoformat())
    label, css = _overall_status(data)
    return (
        f'<div class="header grid-wide">'
        f'<div><h1>NBA AI — Status Dashboard</h1>'
        f'<div class="meta">NBA Date: {nba_date}</div></div>'
        f'<span class="status-pill {css}">{label}</span>'
        f'</div>'
    )


def _render_bankroll(data: dict) -> str:
    d = data.get("bankroll", {})
    title = '<div class="card-title">Bankroll</div>'
    if d.get("status") == "missing":
        return f'<div class="card"><div>{title}<span class="card-missing">$0 — {d.get("message","")}</span></div></div>'
    if d.get("status") == "error":
        return f'<div class="card"><div>{title}<span class="card-missing">Error: {d.get("message","")}</span></div></div>'
    cur = d.get("current", 0.0)
    dpnl = d.get("daily_pnl", 0.0)
    wpnl = d.get("weekly_pnl", 0.0)
    updated = d.get("last_updated", "—")
    ks = d.get("kill_switch_active", False)
    test = " <em style='color:#6b7280;font-size:11px'>[TEST MODE]</em>" if d.get("test_mode") else ""
    kill_html = '<div><span class="kill-active">KILL SWITCH ACTIVE</span></div>' if ks else ""
    return (
        f'<div class="card">'
        f'{title}'
        f'<div class="br-main">${cur:,.2f}{test}</div>'
        f'<div class="br-row">'
        f'<div class="br-item"><label>Daily P&amp;L</label>{format_pnl(dpnl)}</div>'
        f'<div class="br-item"><label>Weekly P&amp;L</label>{format_pnl(wpnl)}</div>'
        f'<div class="br-item"><label>Last Update</label><span style="color:#94a3b8;font-size:12px">{updated}</span></div>'
        f'</div>'
        f'{kill_html}'
        f'</div>'
    )


def _render_positions(data: dict) -> str:
    d = data.get("positions", {})
    title = '<div class="card-title">Open Positions</div>'
    if d.get("status") in ("missing", "error"):
        return f'<div class="card">{title}<span class="card-missing">{d.get("message","No data")}</span></div>'
    cnt = d.get("count", 0)
    exp = d.get("total_exposure", 0.0)
    return (
        f'<div class="card">{title}'
        f'<div class="br-row">'
        f'<div class="br-item"><label>Open Bets</label><span style="font-size:22px;font-weight:700">{cnt}</span></div>'
        f'<div class="br-item"><label>Total Exposure</label>{format_pnl(exp)}</div>'
        f'</div></div>'
    )


def _render_freshness(data: dict) -> str:
    d = data.get("freshness", {})
    title = '<div class="card-title">Model Freshness</div>'
    if not d:
        return f'<div class="card">{title}<span class="card-missing">No data</span></div>'
    rows_html = ""
    for name, info in d.items():
        days = info.get("days")
        if days is None:
            age_str = "missing"
            age_cls = "age-stale"
        elif days == 0:
            age_str = "today"
            age_cls = "age-ok"
        elif days <= 3:
            age_str = f"{days}d ago"
            age_cls = "age-ok"
        elif days <= 7:
            age_str = f"{days}d ago"
            age_cls = "age-warn"
        else:
            age_str = f"{days}d ago"
            age_cls = "age-stale"
        rows_html += (
            f'<div class="fresh-row">'
            f'<span class="fresh-name">{name}</span>'
            f'<span class="fresh-age {age_cls}">{age_str}</span>'
            f'</div>'
        )
    return f'<div class="card">{title}{rows_html}</div>'


def _render_health(data: dict) -> str:
    d = data.get("health", {})
    title = '<div class="card-title">System Health</div>'
    if d.get("status") in ("missing", "error"):
        return f'<div class="card">{title}<span class="card-missing">{d.get("message","No health data")}</span></div>'
    raw = d.get("data", {})
    checks = raw.get("checks", raw.get("results", {}))
    if not checks:
        summary = raw.get("summary", str(raw)[:120])
        return f'<div class="card">{title}<span style="color:#94a3b8;font-size:12px">{summary}</span></div>'
    items_html = ""
    for name, status in list(checks.items())[:18]:
        st = str(status).lower() if isinstance(status, str) else str(status.get("status", "")).lower()
        if "ok" in st:
            color, icon = "#16a34a", "●"
        elif "warn" in st:
            color, icon = "#ca8a04", "◐"
        else:
            color, icon = "#dc2626", "✖"
        items_html += (
            f'<div class="health-item">'
            f'<div class="h-name">{name[:20]}</div>'
            f'<div style="color:{color};font-size:12px;font-weight:700">{icon} {st[:8]}</div>'
            f'</div>'
        )
    return f'<div class="card grid-wide">{title}<div class="health-grid">{items_html}</div></div>'


def _render_edges(data: dict) -> str:
    d = data.get("edges", {})
    title = '<div class="card-title">Top Edges</div>'
    base = '<div class="card grid-wide">'
    if d.get("status") in ("missing", "error"):
        return f'{base}{title}<span class="card-missing">{d.get("message","No edges meet threshold tonight")}</span></div>'
    edges = d.get("edges", [])
    if not edges:
        return f'{base}{title}<span class="card-missing">No edges meet threshold tonight</span></div>'
    rows_html = ""
    for e in edges:
        player = e.get("player", e.get("name", "—"))
        stat = e.get("stat", e.get("market", "—"))
        line = e.get("line", e.get("ou_line", "—"))
        ev = e.get("ev", e.get("edge", 0.0))
        side = e.get("side", e.get("direction", "—"))
        ev_html = format_pct(float(ev) * 100 if abs(float(ev)) <= 1.0 else float(ev))
        rows_html += (
            f'<tr><td>{player}</td><td>{stat}</td><td>{line}</td>'
            f'<td>{side}</td><td>{ev_html}</td></tr>'
        )
    src = d.get("source", "")
    src_note = f'<div style="color:#6b7280;font-size:11px;margin-top:6px">Source: {d.get("file","")}</div>' if src else ""
    table = (
        f'<table><thead><tr>'
        f'<th>Player</th><th>Stat</th><th>Line</th><th>Side</th><th>EV</th>'
        f'</tr></thead><tbody>{rows_html}</tbody></table>'
    )
    return f'{base}{title}{table}{src_note}</div>'


def _render_clv(data: dict) -> str:
    d = data.get("clv", {})
    title = '<div class="card-title">CLV Tracker (30-Day)</div>'
    base = '<div class="card grid-wide">'
    if d.get("status") in ("missing", "error"):
        return f'{base}{title}<span class="card-missing">{d.get("message","No CLV reports")}</span></div>'
    means = d.get("means", {})
    history = d.get("history", {})
    if not means:
        return f'{base}{title}<span class="card-missing">No CLV data</span></div>'
    rows_html = ""
    for stat, mean_val in sorted(means.items()):
        spark = svg_sparkline(history.get(stat, [mean_val]), width=120, height=28)
        color = "#16a34a" if mean_val >= 0 else "#dc2626"
        rows_html += (
            f'<div class="clv-row">'
            f'<span class="clv-stat">{stat}</span>'
            f'<span class="clv-val" style="color:{color}">{mean_val:+.3f}</span>'
            f'<span class="clv-spark">{spark}</span>'
            f'</div>'
        )
    file_note = f'<div style="color:#6b7280;font-size:11px;margin-top:6px">Latest: {d.get("latest_file","")}</div>'
    return f'{base}{title}{rows_html}{file_note}</div>'


def _render_settlements(data: dict) -> str:
    d = data.get("settlements", {})
    title = '<div class="card-title">Recent Settlements</div>'
    base = '<div class="card grid-wide settle-table">'
    if d.get("status") in ("missing", "error"):
        return f'{base}{title}<span class="card-missing">{d.get("message","No settlements data")}</span></div>'
    rows = d.get("rows", [])
    if not rows:
        return f'{base}{title}<span class="card-missing">No settled bets yet</span></div>'
    # Determine columns dynamically
    header_keys = ["player", "stat", "line", "side", "stake", "pnl", "status"]
    available = [k for k in header_keys if any(k in r for r in rows)]
    th = "".join(f"<th>{k.title()}</th>" for k in available)
    rows_html = ""
    for r in rows:
        st = str(r.get("status", "")).lower()
        badge_cls = {"won": "badge-won", "lost": "badge-lost", "push": "badge-push"}.get(st, "badge-settled")
        tds = ""
        for k in available:
            v = r.get(k, "—")
            if k == "status":
                tds += f'<td><span class="badge {badge_cls}">{v}</span></td>'
            elif k == "pnl":
                try:
                    tds += f"<td>{format_pnl(float(v))}</td>"
                except (TypeError, ValueError):
                    tds += f"<td>{v}</td>"
            else:
                tds += f"<td>{v}</td>"
        rows_html += f"<tr>{tds}</tr>"
    table = f"<table><thead><tr>{th}</tr></thead><tbody>{rows_html}</tbody></table>"
    return f"{base}{title}{table}</div>"


def render_dashboard_html(data: dict) -> str:
    """Render full dashboard HTML from data dict. Never raises."""
    try:
        template_text = _TEMPLATE.read_text(encoding="utf-8")
    except OSError:
        template_text = (
            "<html><body>$header_html $bankroll_html $positions_html "
            "$freshness_html $health_html $edges_html $clv_html $settlements_html"
            "<p>$generated_at</p></body></html>"
        )
    meta = data.get("_meta", {})
    generated_at = meta.get("generated_at", "—")

    substitutions = {
        "header_html": _render_header(data),
        "bankroll_html": _render_bankroll(data),
        "positions_html": _render_positions(data),
        "freshness_html": _render_freshness(data),
        "health_html": _render_health(data),
        "edges_html": _render_edges(data),
        "clv_html": _render_clv(data),
        "settlements_html": _render_settlements(data),
        "generated_at": generated_at,
    }
    tmpl = string.Template(template_text)
    try:
        return tmpl.safe_substitute(substitutions)
    except Exception:
        return "<html><body><h1>Dashboard</h1><p>Render error</p></body></html>"


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

def _make_flask_app():
    from flask import Flask, Response  # type: ignore
    app = Flask(__name__)

    @app.route("/")
    def index():
        html = render_dashboard_html(get_dashboard_data())
        return Response(html, mimetype="text/html")

    @app.route("/api/data")
    def api_data():
        payload = json.dumps(get_dashboard_data(), default=str)
        return Response(payload, mimetype="application/json")

    return app


def _run_stdlib_server(host: str, port: int) -> None:
    """Fallback HTTP server using http.server."""
    import http.server

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # silence access log
            logger.debug(fmt, *args)

        def do_GET(self):
            if self.path in ("/", ""):
                body = render_dashboard_html(get_dashboard_data()).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/data":
                body = json.dumps(get_dashboard_data(), default=str).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

    server = http.server.HTTPServer((host, port), Handler)
    logger.info("Dashboard running at http://%s:%d/ (stdlib server)", host, port)
    print(f"Dashboard: http://{host}:{port}/  (Ctrl+C to stop)", flush=True)
    server.serve_forever()


def serve(port: int = 8765, host: str = "127.0.0.1") -> None:
    """Start the dashboard server. Blocks until interrupted."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        app = _make_flask_app()
        logger.info("Dashboard running at http://%s:%d/ (Flask)", host, port)
        print(f"Dashboard: http://{host}:{port}/  (Ctrl+C to stop)", flush=True)
        app.run(host=host, port=port, debug=False, use_reloader=False)
    except ImportError:
        _run_stdlib_server(host, port)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="L23_status_dashboard",
        description="NBA AI Status Dashboard — local HTTP server",
    )
    sub = parser.add_subparsers(dest="cmd")

    srv = sub.add_parser("serve", help="Start HTTP server")
    srv.add_argument("--port", type=int, default=8765)
    srv.add_argument("--host", type=str, default="127.0.0.1")

    sub.add_parser("dump", help="Print JSON data to stdout")

    args = parser.parse_args(argv)

    if args.cmd == "serve":
        serve(port=args.port, host=args.host)
    elif args.cmd == "dump":
        data = get_dashboard_data()
        print(json.dumps(data, indent=2, default=str))
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
