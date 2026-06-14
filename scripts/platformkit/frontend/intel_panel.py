"""scripts.platformkit.frontend.intel_panel — Per-sport intelligence panel.

Surfaces the organized brain + per-sport intelligence read into the honest board
(:8099, separate from api/main.py); understanding + provenance only, NEVER an
un-gated number; markets efficient, calibration not edge.

Public API:
    normalize_sport(s: str) -> str
    build_intel_panel(sport, root=None, top_k=6) -> dict
    render_intel_html(panel) -> str
    attach_intel_routes(app) -> None
CLI:
    python -m scripts.platformkit.frontend.intel_panel --sport nba [--json|--html]
"""
from __future__ import annotations

import argparse, html, json, re, sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── sport normalisation ──────────────────────────────────────────────────────
_SPORT_KEY_MAP: Dict[str, str] = {
    "basketball_nba": "nba", "nba": "nba", "basketball": "nba",
    "mlb_sbro": "mlb", "mlb": "mlb", "baseball": "mlb",
    "soccer": "soccer", "football": "soccer",
    "tennis": "tennis",
}
_SPORT_PREFIX: List[tuple] = [
    ("basketball", "nba"), ("nba", "nba"),
    ("mlb", "mlb"), ("baseball", "mlb"),
    ("soccer", "soccer"), ("football", "soccer"),
    ("tennis", "tennis"),
]


def normalize_sport(s: str) -> str:
    """Normalize any sport id/friendly name to one of nba/mlb/soccer/tennis."""
    low = s.lower().strip()
    if low in _SPORT_KEY_MAP:
        return _SPORT_KEY_MAP[low]
    for prefix, key in _SPORT_PREFIX:
        if low.startswith(prefix) or prefix in low:
            return key
    return low


# ── constants ────────────────────────────────────────────────────────────────
_HONEST_BANNER = (
    "HONEST BOARD: Markets are efficient — NO model edge claimed. "
    "Value = line-shopping / devig / CLV. "
    "This panel shows understanding + provenance only; "
    "no un-gated betting number or pick is surfaced here."
)
_ORG_DIR_MAP: Dict[str, str] = {
    "nba": "NBA", "mlb": "MLB", "soccer": "Soccer", "tennis": "Tennis",
}
_CSS = ("*{box-sizing:border-box;margin:0;padding:0}"
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "background:#0f1117;color:#e2e8f0;padding:24px 16px;min-height:100vh}"
        ".banner{background:#1e293b;border:1px solid #334155;"
        "border-left:4px solid #f59e0b;border-radius:6px;"
        "padding:14px 18px;margin-bottom:24px;font-size:.85rem;"
        "color:#94a3b8;line-height:1.5}"
        ".banner strong{color:#fbbf24}"
        "h1{font-size:1.4rem;font-weight:700;color:#f1f5f9;margin-bottom:6px}"
        "h2{font-size:1.05rem;font-weight:600;color:#cbd5e1;"
        "border-bottom:1px solid #1e293b;padding-bottom:4px;margin:18px 0 10px}"
        ".depth{font-size:.8rem;color:#64748b;margin-bottom:18px}"
        ".section{margin-bottom:20px}"
        "ul{list-style:none;padding:0}"
        "li{font-size:.88rem;padding:5px 8px;border-left:2px solid #334155;"
        "margin-bottom:4px;color:#cbd5e1}"
        "li .prov{font-size:.72rem;color:#475569;margin-left:8px;font-style:italic}"
        ".verdict{background:#0f2d1a;border:1px solid #166534;"
        "border-radius:5px;padding:12px 16px;margin-bottom:20px}"
        ".verdict .label{font-size:.75rem;color:#86efac;text-transform:uppercase}"
        ".verdict .val{font-size:.9rem;color:#d1fae5;margin-top:2px}"
        ".narrative{font-size:.88rem;color:#94a3b8;line-height:1.6;"
        "background:#1a2234;border-radius:4px;padding:12px 14px}"
        ".prov-list{font-size:.75rem;color:#475569;margin-top:16px}"
        ".prov-list code{background:#1e293b;padding:1px 4px;"
        "border-radius:3px;color:#64748b}")

# ── helpers ──────────────────────────────────────────────────────────────────
def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_organized(root: Optional[Path]) -> Optional[Path]:
    if root is None:
        c = _repo_root() / "vault" / "_Organized"
        return c if c.is_dir() else None
    rp = Path(root)
    if not rp.is_dir():
        return None
    for d in _ORG_DIR_MAP.values():
        if (rp / d).is_dir():
            return rp
    sub = rp / "_Organized"
    return sub if sub.is_dir() else rp


def _parse_digest_counts(digest_path: Path) -> Dict[str, Any]:
    """Parse counts from a _Digest.md; return {} on failure."""
    try:
        text = digest_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    pats = [
        ("teams", r"Teams\s*/\s*entities\s*tracked[^:]*:\*+\s*(\d+)"),
        ("archetypes", r"Archetypes[^:]*:\*+\s*(\d+)"),
        ("schemes", r"Schemes\s*/[^:]*:\*+\s*(\d+)"),
        ("trends", r"Trend\s+notes[^:]*:\*+\s*(\d+)"),
    ]
    return {k: int(m.group(1)) for k, p in pats if (m := re.search(p, text, re.I))}


# ── public builder ────────────────────────────────────────────────────────────
def build_intel_panel(sport: str, root: Optional[Path] = None,
                      top_k: int = 6) -> Dict[str, Any]:
    """Build the intelligence panel dict for *sport*.

    Returns: sport, banner, read, digest, provenance, edge_claimed (always False).
    No un-gated betting number or pick key is present.
    """
    sport_key = normalize_sport(sport)
    org_root = _resolve_organized(root)
    try:
        from scripts.platformkit.sport_read import build_sport_read  # noqa: PLC0415
        read_dict = build_sport_read(sport=sport_key, jd=None, root=org_root,
                                     use_llm=False, top_k=top_k)
    except Exception:  # noqa: BLE001
        read_dict = {
            "sport": sport_key, "banner": _HONEST_BANNER,
            "scout": {"archetypes": [], "schemes": [], "trends": []},
            "priors": {"edge_claimed": False, "market_efficiency": "efficient",
                       "tested_signals": "REJECT", "note": "markets efficient; calibration not edge"},
            "surface": None,
            "narrative": "Brain read unavailable — no vault data found for this sport.",
            "critique": {"passes": True, "edge_claim_detected": False,
                         "citation_coverage": 0.0, "reasons": []},
            "edge_claimed": False,
            "provenance": ["scripts.platformkit.sport_read (unavailable)"],
        }
    digest: Dict[str, Any] = {}
    if org_root is not None:
        dp = org_root / _ORG_DIR_MAP.get(sport_key, sport_key.upper()) / "_Digest.md"
        digest = _parse_digest_counts(dp)
    prov: List[str] = list(read_dict.get("provenance", []))
    if "brain_digest" not in " ".join(prov):
        prov.append("scripts.platformkit.brain_digest._parse_digest_counts")
    return {"sport": sport_key, "banner": _HONEST_BANNER, "read": read_dict,
            "digest": digest, "provenance": prov, "edge_claimed": False}


# ── HTML renderer ─────────────────────────────────────────────────────────────
def render_intel_html(panel: Dict[str, Any]) -> str:
    """Render a self-contained HTML page; NEVER includes odds/ROI/edge/probability."""
    sk = html.escape(str(panel.get("sport", "unknown")).upper())
    bn = html.escape(str(panel.get("banner", _HONEST_BANNER)))
    read = panel.get("read") or {}
    scout = read.get("scout") or {}
    priors = read.get("priors") or {}
    narr = html.escape(str(read.get("narrative", "")))
    digest = panel.get("digest") or {}
    prov = panel.get("provenance") or []

    if digest:
        dp = " &bull; ".join(f"{digest[k]} {k}" for k in ("teams","archetypes","schemes","trends") if k in digest)
        depth = dp or "depth data unavailable"
    else:
        depth = "digest not yet generated for this sport"

    def _ul(items: List[Dict[str, Any]], empty: str) -> str:
        if not items:
            return f"<li><em>{html.escape(empty)}</em></li>"
        return "\n".join(
            f'<li>{html.escape(str(i.get("title","—")))}'
            f'<span class="prov">{html.escape(str(i.get("provenance","")))}</span></li>'
            for i in items
        )

    eff = html.escape(str(priors.get("market_efficiency", "efficient")))
    sigs = html.escape(str(priors.get("tested_signals", "REJECT")))
    ec = html.escape(str(panel.get("edge_claimed", False)))
    pi = "".join(f"<li><code>{html.escape(str(p))}</code></li>" for p in prov)

    return (
        "<!DOCTYPE html>\n"
        f'<html lang="en"><head><meta charset="UTF-8">'
        f"<title>Intelligence Panel — {sk}</title>"
        f"<style>{_CSS}</style></head><body>\n"
        f'<div class="banner"><strong>NO model edge</strong> &mdash; {bn}</div>\n'
        f"<h1>Intelligence Panel &mdash; {sk}</h1>\n"
        f'<div class="depth">Knowledge Depth: {depth}</div>\n'
        f'<div class="section"><h2>Archetypes</h2><ul>'
        f'{_ul(scout.get("archetypes",[]),"no archetype notes found in vault for this sport")}'
        f'</ul></div>\n'
        f'<div class="section"><h2>Schemes</h2><ul>'
        f'{_ul(scout.get("schemes",[]),"no scheme notes found")}</ul></div>\n'
        f'<div class="section"><h2>Trends</h2><ul>'
        f'{_ul(scout.get("trends",[]),"no trend notes found")}</ul></div>\n'
        f'<div class="verdict"><div class="label">Honest Market Verdict (Empirical)</div>'
        f'<div class="val">Market efficiency: <strong>{eff}</strong> &bull; '
        f'Tested signals: <strong>{sigs}</strong> &bull; '
        f'edge_claimed: <strong>{ec}</strong></div></div>\n'
        f'<div class="narrative">{narr}</div>\n'
        f'<div class="prov-list"><strong>Provenance:</strong><ul>{pi}</ul></div>\n'
        "</body></html>"
    )


# ── route attachment ──────────────────────────────────────────────────────────
def attach_intel_routes(app: Any) -> None:  # noqa: ANN401
    """Register 3 routes on *app* (any FastAPI instance).

    Paths: GET /api/intel  |  GET /api/intel/{sport}  |  GET /intel/{sport}.html
    HTMLResponse is imported lazily so this module is safe without fastapi installed.
    """
    from fastapi.responses import HTMLResponse  # noqa: PLC0415

    @app.get("/api/intel")
    def api_intel_index() -> Dict[str, Any]:
        sports = list(_ORG_DIR_MAP.keys())
        return {"sports": sports,
                "links": {sp: f"/api/intel/{sp}" for sp in sports},
                "html_links": {sp: f"/intel/{sp}.html" for sp in sports},
                "banner": _HONEST_BANNER, "edge_claimed": False}

    @app.get("/api/intel/{sport}")
    def api_intel_sport(sport: str) -> Dict[str, Any]:
        return build_intel_panel(sport)

    @app.get("/intel/{sport}.html", response_class=HTMLResponse)
    def intel_sport_html(sport: str) -> str:
        return render_intel_html(build_intel_panel(sport))


# ── CLI ───────────────────────────────────────────────────────────────────────
def _cli(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="intel_panel: per-sport intelligence panel; no edge.")
    ap.add_argument("--sport", default="nba")
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--html", action="store_true", dest="as_html")
    a = ap.parse_args(argv)
    panel = build_intel_panel(sport=a.sport, top_k=a.top_k)
    if a.as_json:
        def _def(o: Any) -> Any:
            try:
                import numpy as _np  # noqa: PLC0415
                if isinstance(o, _np.floating): return float(o)
                if isinstance(o, _np.integer): return int(o)
            except ImportError:
                pass
            raise TypeError(type(o))
        print(json.dumps(panel, indent=2, default=_def)); return 0
    if a.as_html:
        print(render_intel_html(panel)); return 0
    read = panel.get("read", {}); scout = read.get("scout", {}); priors = read.get("priors", {})
    digest = panel.get("digest", {})
    print(f"=== Intelligence Panel: {panel['sport'].upper()} ===")
    print(f"Banner     : {panel['banner'][:80]}...")
    print(f"edge_claimed: {panel['edge_claimed']}")
    if digest:
        print(f"Depth: teams={digest.get('teams','?')} archetypes={digest.get('archetypes','?')} "
              f"schemes={digest.get('schemes','?')} trends={digest.get('trends','?')}")
    print(f"Scout: {len(scout.get('archetypes',[]))} archetypes, "
          f"{len(scout.get('schemes',[]))} schemes, {len(scout.get('trends',[]))} trends")
    print(f"Market: {priors.get('market_efficiency','efficient')} / "
          f"signals={priors.get('tested_signals','REJECT')}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
