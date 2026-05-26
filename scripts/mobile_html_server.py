"""mobile_html_server.py — R18_K4 mobile-friendly HTML dashboard.

Tiny aiohttp HTTP server that renders ``vault/TONIGHT.md`` to a mobile-first
HTML page so the user can pull up tonight's bets on a phone via SSH tunnel.

Endpoints
---------
``GET /``           render markdown -> HTML with mobile CSS + 30s auto-refresh
``GET /api/state``  JSON dump of bankroll_state + live_bets + lineups
``GET /healthz``    plain ``OK`` for liveness probes

Auth
----
Optional bearer token via ``DASHBOARD_TOKEN`` env var.  If set, every
request must carry ``Authorization: Bearer <token>`` (or ``?token=<token>``
query for phones without auth headers).  If unset, the server is open
(intended for use over a private SSH tunnel).

CLI
---
    python scripts/mobile_html_server.py --port 8766
    DASHBOARD_TOKEN=secret python scripts/mobile_html_server.py
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from aiohttp import web

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MD_PATH = PROJECT_DIR / "vault" / "TONIGHT.md"
DEFAULT_LIVE_BETS_DIR = PROJECT_DIR / "data" / "cache" / "live_bets"
DEFAULT_BANKROLL_PATH = PROJECT_DIR / "data" / "cache" / "bankroll_state.json"
DEFAULT_LINEUPS_DIR = PROJECT_DIR / "data" / "lineups"

ENV_TOKEN = "DASHBOARD_TOKEN"

logger = logging.getLogger("mobile_html_server")


# --------------------------------------------------------------------------- #
# Markdown -> HTML rendering                                                  #
# --------------------------------------------------------------------------- #
def _get_md_renderer():
    """Return a callable(text) -> html.  Uses markdown-it-py with tables."""
    try:
        from markdown_it import MarkdownIt
    except ImportError:  # pragma: no cover — declared dependency
        raise RuntimeError(
            "markdown-it-py is required. `pip install markdown-it-py`."
        )
    md = MarkdownIt("commonmark", {"breaks": True, "html": False}).enable("table")
    return md.render


# Mobile-first CSS — single column, large fonts, color-coded sections.
MOBILE_CSS = """
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: #0d1117;
  color: #c9d1d9;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 18px;
  line-height: 1.5;
  -webkit-text-size-adjust: 100%;
}
.wrap {
  max-width: 760px;
  margin: 0 auto;
  padding: 12px 14px 64px 14px;
}
h1 {
  font-size: 1.55em;
  margin: 0.4em 0 0.3em;
  color: #f0f6fc;
  border-bottom: 2px solid #30363d;
  padding-bottom: 0.25em;
}
h2 {
  font-size: 1.25em;
  margin: 1.1em 0 0.4em;
  padding: 0.5em 0.7em;
  border-radius: 6px;
  background: #161b22;
  border-left: 4px solid #58a6ff;
}
h2:has(+ * .urgent), h1 + h2 {
  border-left-color: #f85149;
}
/* color code sections by emoji prefix */
h2 { border-left-color: #58a6ff; }
h2:nth-of-type(1) { border-left-color: #f85149; }  /* URGENT */
ul, ol { padding-left: 1.4em; }
li { margin: 0.2em 0; }
strong { color: #f0f6fc; }
code {
  background: #161b22;
  padding: 0.1em 0.4em;
  border-radius: 4px;
  font-size: 0.88em;
}
hr {
  border: 0;
  border-top: 1px solid #30363d;
  margin: 1em 0;
}
table {
  border-collapse: collapse;
  width: 100%;
  margin: 0.6em 0 1em;
  font-size: 0.92em;
  display: block;
  overflow-x: auto;
  white-space: nowrap;
}
th, td {
  padding: 6px 9px;
  border: 1px solid #30363d;
  text-align: left;
}
th {
  background: #161b22;
  color: #f0f6fc;
  position: sticky;
  top: 0;
}
tr:nth-child(even) td { background: #0d1117; }
tr:nth-child(odd)  td { background: #11161d; }
.refresh-badge {
  position: fixed;
  bottom: 10px;
  right: 10px;
  background: #21262d;
  color: #8b949e;
  padding: 6px 10px;
  border-radius: 16px;
  font-size: 0.75em;
  border: 1px solid #30363d;
}
@media (max-width: 480px) {
  body { font-size: 17px; }
  h1 { font-size: 1.35em; }
  h2 { font-size: 1.1em; padding: 0.45em 0.6em; }
  table { font-size: 0.85em; }
  th, td { padding: 5px 6px; }
  .wrap { padding: 8px 10px 64px 10px; }
}
"""


def render_html(md_text: str, *, auto_refresh_sec: int = 30, title: str = "Tonight") -> str:
    """Return a complete HTML document for ``md_text``.

    The HTML is fully self-contained: inlined CSS, no external assets, no JS
    (apart from the meta-refresh).  Safe to serve over a private SSH tunnel.
    """
    body_html = _get_md_renderer()(md_text)
    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"en\"><head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<meta http-equiv=\"refresh\" content=\"{int(auto_refresh_sec)}\">"
        f"<title>{title}</title>"
        f"<style>{MOBILE_CSS}</style>"
        "</head><body>"
        f"<div class=\"wrap\">{body_html}</div>"
        f"<div class=\"refresh-badge\">auto-refresh {int(auto_refresh_sec)}s</div>"
        "</body></html>"
    )


# --------------------------------------------------------------------------- #
# State aggregation for /api/state                                            #
# --------------------------------------------------------------------------- #
def _safe_load_json(path: Path) -> Optional[dict]:
    try:
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def collect_state(
    *,
    bankroll_path: Path,
    live_bets_dir: Path,
    lineups_dir: Path,
) -> dict:
    """Aggregate underlying JSON sources into a single dict for /api/state."""
    state: dict = {
        "bankroll_state": _safe_load_json(bankroll_path),
        "live_bets": {},
        "lineups": {},
    }

    if live_bets_dir.exists() and live_bets_dir.is_dir():
        for child in sorted(live_bets_dir.glob("*.json")):
            blob = _safe_load_json(child)
            if blob is not None:
                state["live_bets"][child.stem] = blob

    if lineups_dir.exists() and lineups_dir.is_dir():
        for child in sorted(lineups_dir.glob("*.json")):
            blob = _safe_load_json(child)
            if blob is not None:
                state["lineups"][child.stem] = blob

    return state


# --------------------------------------------------------------------------- #
# Auth middleware                                                             #
# --------------------------------------------------------------------------- #
def _extract_token(request: web.Request) -> Optional[str]:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(None, 1)[1].strip()
    # Convenience for phones: ?token=...
    query_token = request.query.get("token")
    if query_token:
        return query_token.strip()
    return None


@web.middleware
async def auth_middleware(request: web.Request, handler):
    expected = request.app.get("token")
    if not expected:
        return await handler(request)
    if request.path == "/healthz":
        return await handler(request)
    if _extract_token(request) == expected:
        return await handler(request)
    return web.Response(
        status=401,
        text="unauthorized",
        headers={"WWW-Authenticate": "Bearer"},
    )


# --------------------------------------------------------------------------- #
# Handlers                                                                    #
# --------------------------------------------------------------------------- #
def render_filter_banner(bankroll_state: Optional[dict]) -> str:
    """R19_L8 — render \"filtered out N synthetic rows\" banner."""
    if not bankroll_state:
        return ""
    fi = bankroll_state.get("filter_info") or {}
    if not fi:
        return ""
    n_synth = int(fi.get("n_synth_excluded") or 0)
    n_date = int(fi.get("n_date_excluded") or 0)
    n_kept = int(fi.get("n_kept") or 0)
    n_total = int(fi.get("n_total") or 0)
    excl = bool(fi.get("exclude_synthetic"))
    start_date = fi.get("start_date") or ""
    if not excl and n_date == 0:
        return ""
    bits = []
    if excl:
        bits.append(f"filtered out {n_synth:,} synthetic rows")
    if start_date:
        bits.append(f"dropped {n_date:,} rows before {start_date}")
    bits.append(f"showing {n_kept:,} of {n_total:,} bets")
    msg = " • ".join(bits)
    return (
        '<div style="background:#161b22;border-left:4px solid #2ea043;'
        'padding:8px 12px;margin:8px 0;border-radius:6px;'
        'color:#c9d1d9;font-size:0.9em;">'
        f'<strong>Bankroll filter (R19_L8):</strong> {msg}'
        '</div>'
    )


async def handle_index(request: web.Request) -> web.Response:
    md_path: Path = request.app["md_path"]
    if not md_path.exists():
        return web.Response(status=404, text=f"vault markdown missing: {md_path}")
    try:
        md_text = md_path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover — defensive
        logger.warning("read failed: %s", exc)
        return web.Response(status=500, text=f"read error: {exc}")

    refresh = request.app.get("refresh_sec", 30)
    html = render_html(md_text, auto_refresh_sec=refresh, title="NBA Tonight")
    # R19_L8 — inject filter banner into the rendered HTML if present.
    bankroll_state = _safe_load_json(request.app["bankroll_path"])
    banner = render_filter_banner(bankroll_state)
    if banner:
        html = html.replace(
            '<div class="wrap">', f'<div class="wrap">{banner}', 1
        )
    return web.Response(text=html, content_type="text/html", charset="utf-8")


async def handle_api_state(request: web.Request) -> web.Response:
    state = collect_state(
        bankroll_path=request.app["bankroll_path"],
        live_bets_dir=request.app["live_bets_dir"],
        lineups_dir=request.app["lineups_dir"],
    )
    return web.json_response(state)


async def handle_healthz(request: web.Request) -> web.Response:
    return web.Response(text="OK")


# --------------------------------------------------------------------------- #
# R22_O5 — /operator and /morning single-pane daily dashboard                 #
# --------------------------------------------------------------------------- #
async def handle_operator(request: web.Request) -> web.Response:
    """Render the R22_O5 operator dashboard.

    Imports the dashboard module lazily so import failures do not break the
    other (already working) routes.
    """
    try:
        # Late import — keeps original routes working even if the dashboard
        # module has a bug.
        from scripts import operator_dashboard as od  # type: ignore
    except Exception:  # noqa: BLE001
        # Fall back to a single-file import path (tests/probe import directly).
        try:
            import operator_dashboard as od  # type: ignore
        except Exception as exc:  # noqa: BLE001
            return web.Response(
                status=500,
                text=f"operator_dashboard import failed: {exc!r}",
            )

    refresh = request.app.get("operator_refresh_sec", 60)
    overrides = request.app.get("operator_overrides") or {}
    try:
        html = od.collect_and_render(
            auto_refresh_sec=refresh,
            **overrides,
        )
    except Exception as exc:  # noqa: BLE001 — never let the page 500
        return web.Response(
            status=500,
            text=f"operator dashboard render error: {exc!r}",
        )
    return web.Response(text=html, content_type="text/html", charset="utf-8")


# --------------------------------------------------------------------------- #
# App factory                                                                 #
# --------------------------------------------------------------------------- #
def create_app(
    *,
    md_path: Path = DEFAULT_MD_PATH,
    bankroll_path: Path = DEFAULT_BANKROLL_PATH,
    live_bets_dir: Path = DEFAULT_LIVE_BETS_DIR,
    lineups_dir: Path = DEFAULT_LINEUPS_DIR,
    refresh_sec: int = 30,
    token: Optional[str] = None,
    operator_refresh_sec: int = 60,
    operator_overrides: Optional[dict] = None,
) -> web.Application:
    """Build (but don't run) the aiohttp Application — used by tests + CLI."""
    app = web.Application(middlewares=[auth_middleware])
    app["md_path"] = Path(md_path)
    app["bankroll_path"] = Path(bankroll_path)
    app["live_bets_dir"] = Path(live_bets_dir)
    app["lineups_dir"] = Path(lineups_dir)
    app["refresh_sec"] = int(refresh_sec)
    app["token"] = token or os.environ.get(ENV_TOKEN) or None
    # R22_O5 — operator dashboard config (per-source overrides for tests).
    app["operator_refresh_sec"] = int(operator_refresh_sec)
    app["operator_overrides"] = operator_overrides or {}

    app.router.add_get("/", handle_index)
    app.router.add_get("/api/state", handle_api_state)
    app.router.add_get("/healthz", handle_healthz)
    # R22_O5 — single-pane operator dashboard with /morning alias.
    app.router.add_get("/operator", handle_operator)
    app.router.add_get("/morning", handle_operator)
    return app


# --------------------------------------------------------------------------- #
# CLI entry                                                                   #
# --------------------------------------------------------------------------- #
def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Mobile HTML dashboard server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--md-path", default=str(DEFAULT_MD_PATH))
    parser.add_argument("--refresh-sec", type=int, default=30)
    parser.add_argument(
        "--token",
        default=None,
        help=f"override ${ENV_TOKEN}; if empty, server is open",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = create_app(
        md_path=Path(args.md_path),
        refresh_sec=args.refresh_sec,
        token=args.token,
    )
    has_token = bool(app["token"])
    logger.info(
        "starting mobile HTML server host=%s port=%d auth=%s md=%s",
        args.host, args.port, "bearer" if has_token else "open", args.md_path,
    )
    web.run_app(app, host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
