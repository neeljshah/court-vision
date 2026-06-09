"""board_render.py — V9 PAPER board renderer: board dict -> self-contained board.html.

Inline CSS only (no Tailwind/CDN/JS-deps). GUARDRAIL UX is a hard requirement:
small default stakes, over-betting visibly HARDER than under-betting, prominent
honest banners. honesty_class="paper". NEVER imports api/ or golive.

"""
from __future__ import annotations

import argparse
import html
import os
import sys
from typing import Any, Dict, Optional

# sys.path bootstrap so imports resolve when run as __main__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"
))

__all__ = ["render_board", "write_board", "main"]

_CSS = """
<style>
:root {
  --cv-bg:#0b0f17; --cv-card:#151a24; --cv-border:#222b3a;
  --cv-accent:#3b82f6; --cv-danger:#ef4444; --cv-warn:#f59e0b;
  --cv-ok:#22c55e; --cv-muted:#64748b;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--cv-bg);color:#e2e8f0;font-family:'Segoe UI',system-ui,sans-serif;
     font-size:14px;line-height:1.6}
.container{max-width:980px;margin:0 auto;padding:12px}
h1{font-size:1.4rem;color:var(--cv-accent);margin-bottom:4px}
h2{font-size:1.1rem;color:#94a3b8;margin:18px 0 8px;border-bottom:1px solid var(--cv-border);
   padding-bottom:4px}
h3{font-size:.95rem;color:#7dd3fc;margin:12px 0 6px}
.banner{padding:10px 14px;border-radius:6px;font-weight:600;margin-bottom:8px}
.banner.critical{background:#7f1d1d;color:#fca5a5;border-left:4px solid var(--cv-danger)}
.banner.warn{background:#451a03;color:#fcd34d;border-left:4px solid var(--cv-warn)}
.card{background:var(--cv-card);border:1px solid var(--cv-border);border-radius:8px;
      padding:12px;margin-bottom:12px}
table{width:100%;border-collapse:collapse;margin-top:6px}
th{background:#1e2736;color:#94a3b8;padding:6px 8px;text-align:left;font-size:.82rem}
td{padding:5px 8px;border-bottom:1px solid #1a2133;font-size:.82rem}
tr:last-child td{border-bottom:none}
.prob-hi{color:var(--cv-ok)} .prob-lo{color:var(--cv-muted)}
.edge-notable{color:var(--cv-ok);font-weight:700}
.edge-small{color:#86efac} .edge-tiny{color:var(--cv-muted)}
.tag{display:inline-block;padding:1px 6px;border-radius:4px;font-size:.75rem;margin-left:4px}
.tag-paper{background:#1e3a5f;color:#7dd3fc}
.tag-pend{background:#1a2133;color:#94a3b8}
.btn{display:inline-block;padding:7px 14px;border-radius:6px;cursor:pointer;
     font-size:.85rem;font-weight:600;border:none;min-height:36px}
.btn-pass{background:#1e2736;color:#94a3b8;width:100%;text-align:center;margin-bottom:6px}
.btn-stake{background:#1a2133;color:#64748b;border:1px dashed #334155;font-size:.78rem;
           padding:5px 10px;cursor:default;opacity:.7}
.confirm-box{background:#0f172a;border:1px solid #334155;border-radius:6px;
             padding:8px 10px;margin-top:6px;color:#94a3b8;font-size:.8rem}
.confirm-warn{color:var(--cv-warn);font-weight:600}
.guardrail-note{color:var(--cv-warn);font-size:.8rem;margin-top:6px;font-style:italic}
.section-note{color:var(--cv-muted);font-size:.78rem;margin-top:4px}
.caveat-footer{color:#475569;font-size:.78rem;padding:8px 0;border-top:1px solid var(--cv-border);
               margin-top:8px}
.live-none{color:var(--cv-muted);font-style:italic;padding:8px 0}
.clv-na{color:var(--cv-muted);font-style:italic}
.meta-row{display:flex;gap:16px;flex-wrap:wrap;color:var(--cv-muted);font-size:.8rem;margin-bottom:8px}
.meta-row span{white-space:nowrap}
@media(max-width:640px){
  table{overflow-x:auto;display:block}
  .container{padding:8px}
  .meta-row{gap:8px}
}
</style>
"""


def _esc(x: Any) -> str:
    if x is None:
        return ""
    return html.escape(str(x))


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _section_banners(board: Dict) -> str:
    parts = []
    for b in board.get("banners", []):
        lvl = _esc(b.get("level", "warn"))
        parts.append(f'<div class="banner {lvl}">{_esc(b.get("text",""))}</div>')
    return "\n".join(parts)


def _section_pregame(board: Dict) -> str:
    pg = board.get("pregame", {}) or {}
    parts = ['<h2>Pregame Projections</h2>']

    # Ensemble consensus card
    ens = pg.get("ensemble") or {}
    if ens:
        parts.append('<div class="card">')
        parts.append(f'<h3>Ensemble Consensus</h3>')
        txt = _esc(ens.get("consensus_text", ""))
        if txt:
            parts.append(f'<p>{txt}</p>')
        ph = ens.get("proj_h"); pa = ens.get("proj_a")
        meta = board.get("meta", {})
        home = _esc(meta.get("home", "HOME")); away = _esc(meta.get("away", "AWAY"))
        if ph is not None and pa is not None:
            parts.append(f'<p style="margin-top:6px"><strong>{home}</strong> proj {ph:.1f} &nbsp;|&nbsp; '
                         f'<strong>{away}</strong> proj {pa:.1f} &nbsp;|&nbsp; '
                         f'Win prob {home}: <strong>{ens.get("eq_wp", 0):.1%}</strong></p>')
        parts.append('</div>')

    # Team lines table
    tl = pg.get("team_lines") or []
    if tl:
        parts.append('<h3>Team Lines <span class="tag tag-paper">PAPER</span></h3>')
        parts.append('<div style="overflow-x:auto"><table><thead><tr>'
                     '<th>Entity</th><th>Market</th><th>Line</th><th>Side</th>'
                     '<th>Model P</th><th>Fair</th></tr></thead><tbody>')
        for m in tl[:10]:
            mp = m.get("model_prob", 0)
            cls = "prob-hi" if mp >= 0.55 else "prob-lo"
            fa = m.get("fair_american")
            fa_str = f"{fa:+d}" if fa is not None else "-"
            parts.append(f'<tr><td>{_esc(m.get("entity_name",""))}</td>'
                         f'<td>{_esc(m.get("market_type",""))}</td>'
                         f'<td>{m.get("line","")}</td>'
                         f'<td>{_esc(m.get("side",""))}</td>'
                         f'<td class="{cls}">{mp:.1%}</td>'
                         f'<td>{_esc(fa_str)}</td></tr>')
        parts.append('</tbody></table></div>')

    # Top props table
    tp = pg.get("top_props") or []
    if tp:
        parts.append('<h3>Top Player Props (fair prices) <span class="tag tag-paper">PAPER</span></h3>')
        parts.append('<div style="overflow-x:auto"><table><thead><tr>'
                     '<th>Player</th><th>Stat</th><th>Line</th><th>Side</th>'
                     '<th>Model P</th><th>Fair</th></tr></thead><tbody>')
        for m in tp[:12]:
            mp = m.get("model_prob", 0)
            cls = "prob-hi" if mp >= 0.55 else "prob-lo"
            fa = m.get("fair_american")
            fa_str = f"{fa:+d}" if fa is not None else "-"
            parts.append(f'<tr><td>{_esc(m.get("entity_name",""))}</td>'
                         f'<td>{_esc(m.get("stat",""))}</td>'
                         f'<td>{m.get("line","")}</td>'
                         f'<td>{_esc(m.get("side",""))}</td>'
                         f'<td class="{cls}">{mp:.1%}</td>'
                         f'<td>{_esc(fa_str)}</td></tr>')
        parts.append('</tbody></table></div>')

    # Breakout watch
    bw = pg.get("breakout_watch") or []
    if bw:
        parts.append('<h3>Breakout Watch</h3>')
        parts.append('<div style="overflow-x:auto"><table><thead><tr>'
                     '<th>Player</th><th>Team</th><th>P(20+)</th><th>P(30+)</th>'
                     '<th>Ceiling</th><th>Threshold</th><th>Prob</th></tr></thead><tbody>')
        for b in bw:
            parts.append(f'<tr><td>{_esc(b.get("name",""))}</td>'
                         f'<td>{_esc(b.get("team",""))}</td>'
                         f'<td>{b.get("p20",0):.1%}</td>'
                         f'<td>{b.get("p30",0):.1%}</td>'
                         f'<td>{b.get("ceiling",0):.1f}</td>'
                         f'<td>{b.get("thr",0):.1f}</td>'
                         f'<td>{b.get("prob",0):.1%}</td></tr>')
        parts.append('</tbody></table></div>')

    # SGP
    sgp = pg.get("sgp") or []
    if sgp:
        parts.append('<h3>Same-Game Parlay: Joint vs Independent</h3>')
        parts.append('<div style="overflow-x:auto"><table><thead><tr>'
                     '<th>Basket</th><th>Joint</th><th>Independent</th><th>Lift</th></tr></thead><tbody>')
        for b in sgp:
            lift = b.get("lift", 1)
            cls = "edge-notable" if lift < 0.9 else ("prob-hi" if lift > 1.1 else "")
            parts.append(f'<tr><td>{_esc(b.get("label",""))}</td>'
                         f'<td>{b.get("joint",0):.1%}</td>'
                         f'<td>{b.get("independent",0):.1%}</td>'
                         f'<td class="{cls}">{lift:.2f}x</td></tr>')
        parts.append('</tbody></table></div>')

    caveat = _esc(board.get("caveat", ""))
    parts.append(f'<div class="caveat-footer">{caveat}</div>')
    return "\n".join(parts)


def _section_edges(board: Dict) -> str:
    edges = board.get("edges_plain_english") or []
    parts = ['<h2>Flagged Paper Edges (plain English)</h2>']
    if not edges:
        parts.append('<p class="clv-na">No flagged edges (no paper lines with edge &ge;0.03 and EV&gt;0).</p>')
    else:
        parts.append('<p class="section-note">Staking is intentionally harder than passing. Default action = pass.</p>')
        for e in edges:
            strength = e.get("strength", "tiny")
            ecls = {"notable": "edge-notable", "small": "edge-small", "tiny": "edge-tiny"}.get(strength, "edge-tiny")
            parts.append(f'<div class="card"><span class="{ecls}">[{_esc(strength.upper())}]</span> '
                         f'{_esc(e.get("sentence",""))}</div>')
    caveat = _esc(board.get("caveat", ""))
    parts.append(f'<div class="caveat-footer">{caveat}</div>')
    return "\n".join(parts)


def _section_portfolio(board: Dict) -> str:
    port = board.get("portfolio") or {}
    bets = port.get("bets") or []
    parts = ['<h2>Paper Portfolio <span class="tag tag-paper">PAPER</span></h2>']

    max_pct = port.get("max_stake_pct", 0.04)
    bankroll = port.get("bankroll", 100.0)
    parts.append(f'<p class="guardrail-note">Max stake: {max_pct:.0%} of bankroll '
                 f'(${bankroll:.0f}). Default stakes are tiny. Over-betting requires explicit confirmation.</p>')
    parts.append('<p class="section-note">Staking is intentionally harder than passing. Default action = pass.</p>')

    gnote = port.get("guardrail_note", "")
    if gnote:
        parts.append(f'<p class="guardrail-note">{_esc(gnote)}</p>')

    if not bets:
        parts.append('<p class="clv-na">Portfolio empty (no paper lines with edge &ge;0.03 and EV &gt;0).</p>')
    else:
        for b in bets:
            ename = _esc(b.get("entity_name", b.get("entity", "")))
            mtype = _esc(b.get("market_type", ""))
            stat = _esc(b.get("stat", ""))
            line = b.get("line", "")
            side = _esc(b.get("side", ""))
            edge = b.get("edge", 0)
            ev = b.get("ev", 0)
            stake = b.get("stake", 0)
            kpct = b.get("kelly_pct", 0)
            book_odds = b.get("book_odds", 0)
            spct = b.get("stake_pct_display", kpct)
            confirm = _esc(b.get("confirm_phrase", f"Type CONFIRM to stake ${stake:.2f}"))
            parts.append('<div class="card">')
            parts.append(f'<strong>{ename}</strong> &mdash; {mtype} {stat} {line} {side} '
                         f'<span class="tag tag-paper">PAPER</span><br>')
            parts.append(f'<span style="color:var(--cv-muted)">Edge: {edge:.1%} &nbsp;|&nbsp; '
                         f'EV: {ev:.3f} &nbsp;|&nbsp; Book: {book_odds:+d} &nbsp;|&nbsp; '
                         f'Kelly: {kpct:.2%} &nbsp;|&nbsp; Stake: ${stake:.2f} ({spct:.2%})</span><br>')
            # Pass affordance = default, prominent
            parts.append('<button class="btn btn-pass" type="button">Pass / Smaller (default)</button>')
            # Stake affordance = gated, friction
            parts.append(f'<button class="btn btn-stake" type="button" disabled>{confirm}</button>')
            parts.append('<div class="confirm-box"><span class="confirm-warn">Stake requires confirmation. '
                         'Playoffs = NO proven edge.</span> Paper only &mdash; no real money placed.</div>')
            parts.append('</div>')

    caveat = _esc(board.get("caveat", ""))
    parts.append(f'<div class="caveat-footer">{caveat}</div>')
    return "\n".join(parts)


def _section_live(board: Dict) -> str:
    live = board.get("live")
    parts = ['<h2>Live Replay <span class="tag tag-paper">PAPER</span></h2>']
    if not live:
        parts.append('<p class="live-none">No live game cached. '
                     'Pass --game-id with a cached PBP/box game to enable this section.</p>')
    else:
        gid = _esc(live.get("game_id", ""))
        parts.append(f'<p>Game: {gid} &nbsp;|&nbsp; '
                     f'Median reprice: {live.get("median_reprice_ms",0):.1f}ms</p>')
        note = live.get("note", "")
        if note:
            parts.append(f'<p class="section-note">{_esc(note)}</p>')
        chk = live.get("checkpoints") or []
        if chk:
            parts.append('<div style="overflow-x:auto"><table><thead><tr>'
                         '<th>Pct</th><th>Period</th><th>Clock</th>'
                         '<th>H Score</th><th>A Score</th>'
                         '<th>Proj H</th><th>Proj A</th><th>H Win%</th></tr></thead><tbody>')
            for c in chk:
                parts.append(f'<tr><td>{c.get("pct",0):.0%}</td>'
                              f'<td>{c.get("period","")}</td>'
                              f'<td>{c.get("clock_sec","")}</td>'
                              f'<td>{c.get("home_score","")}</td>'
                              f'<td>{c.get("away_score","")}</td>'
                              f'<td>{c.get("proj_home_final","")}</td>'
                              f'<td>{c.get("proj_away_final","")}</td>'
                              f'<td>{c.get("home_win_prob",0):.1%}</td></tr>')
            parts.append('</tbody></table></div>')
        rec = live.get("reconcile") or {}
        if rec:
            parts.append(f'<p class="section-note">Team score err: {rec.get("team_score_err","")}'
                         f' &nbsp;|&nbsp; Player MAE: {rec.get("player_mae","")}'
                         f' &nbsp;|&nbsp; {_esc(rec.get("note_ast",""))}</p>')
    caveat = _esc(board.get("caveat", ""))
    parts.append(f'<div class="caveat-footer">{caveat}</div>')
    return "\n".join(parts)


def _section_clv(board: Dict) -> str:
    clv = board.get("bankroll_clv") or {}
    parts = ['<h2>CLV &amp; Paper Bankroll Scoreboard</h2>']

    if not clv.get("clv_available", False):
        parts.append('<p class="clv-na">No CLV data yet. '
                     'Real CLV requires the live daemon to capture open&#8594;close prices. '
                     'Prop CLV is structurally un-gradable until then.</p>')
    else:
        pairs = clv.get("open_close_pairs", 0)
        real_moves = clv.get("n_real_moves", 0)
        parts.append(f'<p>Open/close pairs: {pairs} &nbsp;|&nbsp; Real line moves: {real_moves}</p>')
        rows = clv.get("rows") or []
        if rows:
            parts.append('<div style="overflow-x:auto"><table><thead><tr>'
                         '<th>Game</th><th>Market</th><th>Selection</th><th>Line</th>'
                         '<th>Book</th><th>Open</th><th>Close</th><th>CLV (cents)</th><th>Moved</th>'
                         '</tr></thead><tbody>')
            for r in rows[:25]:
                clv_cents = r.get("clv_cents", 0)
                cls = "prob-hi" if clv_cents > 0 else ("edge-tiny" if clv_cents == 0 else "edge-notable")
                parts.append(f'<tr><td>{_esc(r.get("game",""))}</td>'
                              f'<td>{_esc(r.get("market",""))}</td>'
                              f'<td>{_esc(r.get("selection",""))}</td>'
                              f'<td>{r.get("line","")}</td>'
                              f'<td>{_esc(r.get("book",""))}</td>'
                              f'<td>{r.get("open_price","")}</td>'
                              f'<td>{r.get("close_price","")}</td>'
                              f'<td class="{cls}">{clv_cents}</td>'
                              f'<td>{"Yes" if r.get("moved") else "No"}</td></tr>')
            parts.append('</tbody></table></div>')
        note = clv.get("note", "")
        if note:
            parts.append(f'<p class="section-note">{_esc(note)}</p>')

    # Paper scoreboard
    sb = clv.get("paper_scoreboard") or {}
    if sb:
        parts.append('<h3>Paper Scoreboard</h3>')
        parts.append(f'<p>Total staked: ${sb.get("total_stake",0):.2f} &nbsp;|&nbsp; '
                     f'P&amp;L: ${sb.get("total_pnl",0):.2f} &nbsp;|&nbsp; '
                     f'ROI: <em>PENDING</em></p>')
        sb_note = sb.get("note", "")
        if sb_note:
            parts.append(f'<p class="section-note">{_esc(sb_note)}</p>')
        sb_bets = sb.get("bets") or []
        if sb_bets:
            parts.append('<div style="overflow-x:auto"><table><thead><tr>'
                         '<th>Selection</th><th>Market</th><th>Line</th><th>Side</th>'
                         '<th>Stake</th><th>Result</th><th>P&amp;L</th></tr></thead><tbody>')
            for b in sb_bets:
                parts.append(f'<tr><td>{_esc(b.get("selection",""))}</td>'
                              f'<td>{_esc(b.get("market",""))}</td>'
                              f'<td>{b.get("line","")}</td>'
                              f'<td>{_esc(b.get("side",""))}</td>'
                              f'<td>${b.get("stake",0):.2f}</td>'
                              f'<td><span class="tag tag-pend">{_esc(b.get("result","PENDING"))}</span></td>'
                              f'<td>${b.get("pnl",0):.2f}</td></tr>')
            parts.append('</tbody></table></div>')

    caveat = _esc(board.get("caveat", ""))
    parts.append(f'<div class="caveat-footer">{caveat}</div>')
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_board(board: Dict[str, Any]) -> str:
    """Return a complete standalone HTML document string (doctype..</html>)."""
    meta = board.get("meta", {})
    matchup = _esc(meta.get("matchup", meta.get("home", "") + "@" + meta.get("away", "")))
    ts = _esc(meta.get("generated_utc", ""))
    nsims = meta.get("nsims", "")
    hc = _esc(board.get("honesty_class", "paper"))

    head = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PAPER Board — {matchup}</title>
{_CSS}
</head>
<body>
<div class="container">
<h1>V9 PAPER Board &mdash; {matchup}
  <span class="tag tag-paper">honesty_class={hc}</span>
</h1>
<div class="meta-row">
  <span>Generated: {ts}</span>
  <span>NSims: {nsims}</span>
  <span>Bankroll: ${meta.get("bankroll", 100):.0f}</span>
  <span>Markets: {meta.get("n_concrete", "")}</span>
  <span>Types: {meta.get("n_types", "")}</span>
  <span>Ontology: {meta.get("ontology_count", "")}</span>
</div>
"""

    banners = _section_banners(board)
    pregame = _section_pregame(board)
    edges = _section_edges(board)
    portfolio = _section_portfolio(board)
    live = _section_live(board)
    clv = _section_clv(board)

    body = f"""{banners}
{pregame}
{edges}
{portfolio}
{live}
{clv}
"""

    foot = """</div><!-- /container -->
</body>
</html>"""

    return head + body + foot


def write_board(board: Dict[str, Any], out_path: str) -> str:
    """render_board -> write UTF-8 file (atomic via .staging + os.replace). Returns out_path."""
    content = render_board(board)
    staging = out_path + ".staging"
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(staging, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(staging, out_path)
    return out_path


# ---------------------------------------------------------------------------
# __main__ — renders a STUB board dict and validates required sections
# ---------------------------------------------------------------------------

def _make_stub_board() -> Dict[str, Any]:
    """Return a minimal stub board dict for smoke-testing render_board()."""
    return {
        "meta": {
            "home": "NYK", "away": "SAS", "matchup": "SAS@NYK",
            "nsims": 10, "asof": None, "bankroll": 100.0,
            "honesty_class": "paper", "generated_utc": "2026-06-08T00:00:00Z",
            "n_concrete": 5, "n_types": 3, "ontology_count": 120,
        },
        "banners": [
            {"level": "critical", "text": "PAPER -- no real money is placed."},
            {"level": "critical", "text": "Playoffs: NO proven betting edge. The closing line beats the model in playoffs."},
            {"level": "warn",     "text": "ROI requires proven FORWARD CLV (real captured open->close prices). None claimed here."},
        ],
        "pregame": {
            "ensemble": {
                "engines": [],
                "eq_margin": 2.5, "eq_wp": 0.54, "iv_margin": 2.0, "iv_wp": 0.53,
                "eq_total": 218.0, "pooled_sd": 12.0, "engine_spread": 1.5,
                "clutch_wp": 0.55, "proj_h": 110.5, "proj_a": 108.0,
                "consensus_text": "5/7 engines lean NYK; disagreement 1.5 pts",
            },
            "team_lines": [
                {"market_type": "spread", "entity_name": "NYK", "line": -2.5,
                 "side": "over", "model_prob": 0.54, "fair_american": -115},
            ],
            "top_props": [
                {"entity_name": "Star Guard", "market_type": "pts_ou", "stat": "pts",
                 "line": 25.5, "side": "over", "model_prob": 0.58, "fair_american": -140},
            ],
            "breakout_watch": [
                {"name": "Wing Player", "team": "NYK", "p20": 0.32, "p30": 0.08,
                 "ceiling": 28.0, "thr": 20.0, "prob": 0.32},
            ],
            "sgp": [
                {"label": "SAME-PLAYER Star pts & reb", "joint": 0.24, "independent": 0.25, "lift": 0.96,
                 "legs": [(101, "pts", 25.5, True), (101, "reb", 5.5, True)]},
            ],
        },
        "edges_plain_english": [
            {
                "sentence": "Model gives Star Guard PTS over 25.5 a 58% chance vs the book's implied 50% -- a small paper edge (fair -140, book -110). Playoffs = no proven edge; paper only.",
                "entity_name": "Star Guard", "market_type": "pts_ou", "stat": "pts",
                "line": 25.5, "side": "over",
                "model_prob": 0.58, "book_prob": 0.50, "edge": 0.08,
                "book_odds": -110, "ev": 0.08, "strength": "small",
                "caveat": "Playoffs = no proven edge; paper only.",
            }
        ],
        "portfolio": {
            "bets": [
                {
                    "market_type": "pts_ou", "entity": "101", "entity_name": "Star Guard",
                    "stat": "pts", "line": 25.5, "side": "over",
                    "model_prob": 0.58, "book_odds": -110, "edge": 0.08, "ev": 0.08,
                    "corr_to_book": 0.0, "stake": 2.50, "kelly_pct": 0.025,
                    "stake_pct_display": 0.025,
                    "confirm_phrase": "Type CONFIRM to stake $2.50",
                }
            ],
            "total_stake": 2.50, "n_candidates": 1, "bankroll": 100.0,
            "max_stake_pct": 0.04,
            "honesty_class": "paper",
            "guardrail_note": "Default stakes are tiny (<=4% bankroll). Over-betting requires explicit confirmation.",
        },
        "live": None,
        "bankroll_clv": {
            "open_close_pairs": 0, "n_real_moves": 0, "rows": [],
            "clv_available": False,
            "paper_scoreboard": {
                "total_stake": 2.50, "total_pnl": 0.0, "roi": None,
                "bets": [
                    {"selection": "Star Guard pts", "market": "pts_ou", "line": 25.5,
                     "side": "over", "stake": 2.50, "result": "PENDING", "pnl": 0.0}
                ],
                "note": "All PENDING -- paper board grades nothing. Real ROI needs forward CLV.",
            },
            "note": "Prop CLV is structurally un-gradable until the live daemon captures open->close.",
        },
        "guardrails": {
            "default_bankroll": 100.0, "max_stake_pct": 0.04,
            "over_bet_requires_confirm": True, "under_bet_default": True,
            "honesty_class": "paper",
            "rules": [
                "Max stake per bet: 4% of bankroll.",
                "Default action is PASS -- staking requires explicit confirmation.",
                "Over-betting is visibly harder than under-betting.",
                "All positions are PAPER ONLY. No real money is placed.",
            ],
        },
        "caveat": "PAPER -- no real money. Playoffs have NO proven edge. ROI requires proven forward CLV.",
        "honesty_class": "paper",
    }


def main(argv=None) -> int:
    """CLI: build a stub (or real) board and write board.html."""
    ap = argparse.ArgumentParser(description="V9 PAPER board renderer")
    ap.add_argument("--home", default="NYK")
    ap.add_argument("--away", default="SAS")
    ap.add_argument("--nsims", type=int, default=3000)
    ap.add_argument("--asof", default=None)
    ap.add_argument("--bankroll", type=float, default=100.0)
    ap.add_argument("--game-id", default=None)
    ap.add_argument("--demo", action="store_true", default=True)
    ap.add_argument("--no-demo", dest="demo", action="store_false")
    ap.add_argument("--stub", action="store_true", default=False,
                    help="Use stub board dict (no GPU, for smoke-test)")
    ap.add_argument("--out", default=None,
                    help="Output path (default: vault/Intelligence/Previews/board.html)")
    args = ap.parse_args(argv)

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_out = os.path.join(root, "vault", "Intelligence", "Previews", "board.html")
    out_path = args.out or default_out

    if args.stub:
        board = _make_stub_board()
        print("[board_render] Using stub board dict (no GPU/sim).")
    else:
        # Gate check
        try:
            from board_data import build_board, is_enabled
        except ImportError:
            print("[board_render] board_data.py not found; falling back to stub.")
            board = _make_stub_board()
        else:
            enabled = is_enabled(force=args.demo)
            if not enabled:
                print("[board_render] CV_PAPER_BOARD not set and --demo not passed; use --demo or set CV_PAPER_BOARD=1")
                return 0
            board = build_board(
                home=args.home, away=args.away, nsims=args.nsims,
                asof=args.asof, bankroll=args.bankroll,
                demo=args.demo, live_game_id=args.game_id,
            )

    written = write_board(board, out_path)
    h = render_board(board)

    # Validate required content
    required = {
        "<!doctype html": "doctype",
        "PAPER -- no real money is placed.": "critical banner",
        "NO proven betting edge": "playoff banner",
        "Type CONFIRM": "confirm friction",
        "Pass / Smaller": "pass affordance",
        "PENDING": "paper scoreboard pending",
    }
    missing = [label for fragment, label in required.items()
               if fragment.lower() not in h.lower()]
    if missing:
        print(f"[board_render] WARN: missing required sections: {missing}")
    else:
        print(f"[board_render] All required sections present.")

    # Check zero external deps
    import re as _re
    ext = _re.search(r'src="https?://|cdn\.|<script src', h)
    if ext:
        print(f"[board_render] WARN: external dependency detected: {ext.group()}")
    else:
        print(f"[board_render] No external dependencies (self-contained).")

    print(f"[board_render] Written: {written}  ({len(h)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
