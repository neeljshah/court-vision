"""vault_dashboard_daemon.py — R17_J7 Single-Pane-of-Glass Vault Dashboard.

Aggregates every live betting signal into ONE human-readable Markdown file
(``vault/TONIGHT.md``) on a fixed cadence so the user can open a single file
on their phone and see:

    - Top bets (R16_E2 live ranker)
    - Current bankroll + daily P&L (R17_J4)
    - Urgent alerts (R17_J3, ``vault/URGENT_BETS.md``)
    - Active middles (R16_E5)
    - Recent line moves (R16_E4)
    - CLV running totals (R16_E8)
    - Lineup confirmations (R17_J1)
    - System health (orchestrator + daemons)

Design notes
------------
* Every source file is OPTIONAL.  If a producer hasn't shipped yet, the
  corresponding section degrades to ``(awaiting R17_J1)`` etc. — never errors.
* Render is ATOMIC: write to ``TONIGHT.md.tmp`` then ``os.replace`` so a phone
  refresh never lands mid-write.
* Health is queried from the orchestrator's local HTTP endpoint (default
  ``http://localhost:8765/health``) and falls back to ``ps``-grep if missing.

CLI
---
    python scripts/vault_dashboard_daemon.py --once
    python scripts/vault_dashboard_daemon.py --interval-sec 30
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

# R19_L3 heartbeat import (sys.path bootstrap so daemons launched via
# 'python -u scripts/<name>.py' can still find src.monitor at the project root).
try:
    import os as _r19_os, sys as _r19_sys
    _r19_root = _r19_os.path.dirname(_r19_os.path.dirname(_r19_os.path.abspath(__file__)))
    if _r19_root not in _r19_sys.path:
        _r19_sys.path.insert(0, _r19_root)
    from src.monitor.daemon_heartbeat import write_heartbeat as _r19_hb
except Exception:
    def _r19_hb(_name):
        return False


PROJECT_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Default source paths.  Every reader is defensive: missing file -> None.
# ---------------------------------------------------------------------------
DEFAULTS = {
    "live_bets_dir":   PROJECT_DIR / "data" / "cache" / "live_bets",
    "middles_path":    PROJECT_DIR / "data" / "cache" / "middles_live.json",
    "clv_path":        PROJECT_DIR / "data" / "cache" / "clv_running_total.json",
    "bankroll_path":   PROJECT_DIR / "data" / "cache" / "bankroll_state.json",
    "lineups_dir":     PROJECT_DIR / "data" / "lineups",
    "urgent_path":     PROJECT_DIR / "vault" / "URGENT_BETS.md",
    "out_path":        PROJECT_DIR / "vault" / "TONIGHT.md",
    "health_url":      "http://localhost:8765/health",
}

UTC = _dt.timezone.utc

# ---------------------------------------------------------------------------
# Safe IO helpers.
# ---------------------------------------------------------------------------


def _safe_load_json(path: Path) -> Optional[dict]:
    """Return parsed JSON or None on any error."""
    try:
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001 — daemon never crashes on bad input
        return None


def _safe_read_text(path: Path) -> Optional[str]:
    try:
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception:  # noqa: BLE001
        return None


def _newest_file(dir_path: Path, suffix: str = ".json") -> Optional[Path]:
    if not dir_path.exists() or not dir_path.is_dir():
        return None
    files = [p for p in dir_path.iterdir() if p.is_file() and p.name.endswith(suffix)]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _iso_now() -> str:
    return _dt.datetime.now(UTC).replace(microsecond=0).isoformat()


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically via tmp+rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Section renderers.  Each returns a Markdown block (or graceful placeholder).
# ---------------------------------------------------------------------------


def _format_money(v: Any) -> str:
    if v is None:
        return "?"
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "?"


def _format_signed_money(v: Any) -> str:
    if v is None:
        return "$0.00"
    try:
        f = float(v)
        sign = "+" if f >= 0 else "-"
        return f"{sign}${abs(f):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def render_header(label: str, isodate: str, bankroll: Optional[dict]) -> str:
    """Top-of-file banner with bankroll + daily P&L."""
    lines = [
        f"# Tonight — {isodate} — {label}",
        "",
        f"**Last updated:** {_iso_now()}",
    ]
    if bankroll is None:
        lines.append("**Bankroll:** _(awaiting R17_J4)_")
        lines.append("**Daily P&L:** _(awaiting R17_J4)_")
    else:
        # R17_J4 schema uses ``current_bankroll`` / ``available_bankroll`` /
        # ``pending_exposure``; legacy schemas use ``total`` / ``available``
        # / ``pending``.  Accept either.
        total = (bankroll.get("current_bankroll")
                 or bankroll.get("total")
                 or bankroll.get("bankroll"))
        pending = (bankroll.get("pending_exposure")
                   or bankroll.get("pending")
                   or bankroll.get("pending_stakes")
                   or 0.0)
        available = (bankroll.get("available_bankroll")
                     or bankroll.get("available"))
        if available is None and total is not None:
            try:
                available = float(total) - float(pending)
            except (TypeError, ValueError):
                available = None
        daily = (bankroll.get("daily_pnl")
                 or bankroll.get("pnl_today")
                 or 0.0)
        lines.append(
            f"**Bankroll:** {_format_money(total)} "
            f"(pending {_format_money(pending)}, available {_format_money(available)})"
        )
        lines.append(f"**Daily P&L:** {_format_signed_money(daily)}")
        # Optional: open positions + drawdown if present.
        n_open = bankroll.get("n_open_positions")
        max_dd_pct = bankroll.get("max_drawdown_pct")
        if n_open is not None or max_dd_pct is not None:
            bits = []
            if n_open is not None:
                bits.append(f"{n_open} open positions")
            if isinstance(max_dd_pct, (int, float)):
                bits.append(f"max DD {max_dd_pct * 100:.2f}%")
            lines.append("_" + " • ".join(bits) + "_")
    return "\n".join(lines) + "\n"


def render_urgent(urgent_text: Optional[str], limit: int = 5) -> str:
    """Latest N entries from URGENT_BETS.md, or graceful placeholder."""
    out = ["## ⚠️ URGENT", ""]
    if not urgent_text or not urgent_text.strip():
        out.append("_(awaiting R17_J3 — no urgent alerts yet)_")
        return "\n".join(out) + "\n"
    # The urgent file is markdown — extract recent block(s).  Heuristic:
    # split on H2/H3 headings and keep the latest ``limit`` blocks.  Fall back
    # to last ``limit*8`` lines if no headings found.
    raw = urgent_text.strip()
    blocks: List[str] = []
    cur: List[str] = []
    for line in raw.splitlines():
        if line.startswith("## ") or line.startswith("### "):
            if cur:
                blocks.append("\n".join(cur).rstrip())
                cur = []
        cur.append(line)
    if cur:
        blocks.append("\n".join(cur).rstrip())
    if blocks and len(blocks) > 1:
        # Newest entries usually appended at end; take the last ``limit``.
        keep = blocks[-limit:]
        out.append("\n\n".join(keep))
    else:
        tail = raw.splitlines()[-(limit * 8):]
        out.append("\n".join(tail))
    return "\n".join(out) + "\n"


def render_top_bets(live_bets: Optional[dict], limit: int = 5) -> str:
    out = ["## 🎯 Top 5 Bets (live)", ""]
    if not live_bets:
        out.append("_(awaiting R16_E2 — no ranker output yet)_")
        return "\n".join(out) + "\n"
    bets = live_bets.get("ranked_bets") or []
    if not bets:
        out.append("_(ranker ran but produced 0 positive-EV bets)_")
        return "\n".join(out) + "\n"
    captured = live_bets.get("captured_at", "?")
    slate = live_bets.get("label") or live_bets.get("slate_id") or ""
    stale = ", ".join(live_bets.get("stale_books") or [])
    meta_bits = [f"_tick {live_bets.get('tick_idx', '?')}_", f"_captured {captured}_"]
    if stale:
        meta_bits.append(f"_stale books: {stale}_")
    out.append(" • ".join(meta_bits))
    out.append("")
    out.append("| # | Player | Stat | Side | Book | Line | Odds | Edge% | Kelly | Stake |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for i, b in enumerate(bets[:limit], 1):
        odds = b.get("odds", "?")
        odds_str = f"+{odds}" if isinstance(odds, (int, float)) and odds > 0 else str(odds)
        move = b.get("line_move", "")
        side = b.get("side", "?")
        if move:
            side = f"{side} {move}"
        out.append(
            f"| {i} "
            f"| {b.get('player', '?')} "
            f"| {str(b.get('stat', '?')).upper()} "
            f"| {side} "
            f"| {b.get('book', '?')} "
            f"| {b.get('line', '?')} "
            f"| {odds_str} "
            f"| {b.get('edge_pct', 0):.1f}% "
            f"| {b.get('kelly_pct_used', 0):.1f}% "
            f"| {_format_money(b.get('kelly_stake_$'))} |"
        )
    if slate:
        out.append("")
        out.append(f"_Slate:_ {slate}")
    return "\n".join(out) + "\n"


def render_lineups(lineups: Optional[dict]) -> str:
    out = ["## 🏟️ Lineup Status", ""]
    if not lineups:
        out.append("_(awaiting R17_J1)_")
        return "\n".join(out) + "\n"

    # Status summary: either ``status`` (legacy) or derived from per-starter
    # ``status`` field on the flat list (R17_J1 rotowire schema).
    updated = lineups.get("updated_at") or lineups.get("captured_at") or "?"
    source = lineups.get("source", "")
    n_starters = lineups.get("n_starters")

    # Build a normalized [{team, starters: [{name,status,injury,...}], scratches: []}, ...]
    teams_map: Dict[str, dict] = {}
    if "teams" in lineups or "games" in lineups:
        # Legacy nested schema.
        raw_teams = lineups.get("teams") or lineups.get("games") or []
        if isinstance(raw_teams, dict):
            raw_teams = [
                {"team": k, **(v if isinstance(v, dict) else {"starters": v})}
                for k, v in raw_teams.items()
            ]
        for t in raw_teams:
            name = t.get("name") or t.get("team") or "?"
            teams_map[name] = {
                "starters": t.get("starters") or t.get("lineup") or [],
                "scratches": t.get("scratches") or t.get("out") or t.get("inactive") or [],
            }
    else:
        # R17_J1 flat list: lineups["starters"] = [{team, player_name, status, ...}]
        for st in lineups.get("starters") or []:
            tm = st.get("team") or "?"
            teams_map.setdefault(tm, {"starters": [], "scratches": []})
            teams_map[tm]["starters"].append(st)
        for sx in lineups.get("scratches") or lineups.get("inactive") or []:
            tm = sx.get("team") or "?"
            teams_map.setdefault(tm, {"starters": [], "scratches": []})
            teams_map[tm]["scratches"].append(sx)

    # Aggregate status: confirmed if every starter is CONFIRMED, else projected.
    statuses = []
    for v in teams_map.values():
        for s in v["starters"]:
            if isinstance(s, dict):
                statuses.append(str(s.get("status", "")).upper())
    if statuses and all(s == "CONFIRMED" for s in statuses):
        agg = "CONFIRMED"
    elif any(s == "QUESTIONABLE" for s in statuses):
        agg = "PROJECTED (questionable starter present)"
    else:
        agg = lineups.get("status") or lineups.get("confirmation_status") or "PROJECTED"
    header_bits = [f"**Confirmation:** {agg}"]
    if source:
        header_bits.append(f"_source: {source}_")
    if n_starters is not None:
        header_bits.append(f"_{n_starters} starters_")
    header_bits.append(f"_updated {updated}_")
    out.append(" • ".join(header_bits))
    out.append("")

    if not teams_map:
        out.append("_(no team lineups in payload)_")
        return "\n".join(out) + "\n"

    def _name(x):
        if isinstance(x, str):
            return x
        return x.get("player_name") or x.get("name") or "?"

    for team_name in sorted(teams_map.keys()):
        v = teams_map[team_name]
        starters = v["starters"]
        scratches = v["scratches"]
        if starters:
            parts = []
            for s in starters:
                nm = _name(s)
                if isinstance(s, dict):
                    status = str(s.get("status", "")).upper()
                    injury = s.get("injury")
                    tag = ""
                    if status and status not in ("CONFIRMED", "PROJECTED", ""):
                        tag = f" ({status})"
                    elif injury:
                        tag = f" ({injury})"
                    parts.append(f"{nm}{tag}")
                else:
                    parts.append(nm)
            out.append(f"- **{team_name}** ({len(starters)}): {', '.join(parts)}")
        else:
            out.append(f"- **{team_name}** _(no starters listed)_")
        if scratches:
            sx_names = [_name(s) for s in scratches]
            out.append(f"  - scratches: {', '.join(sx_names)}")
    return "\n".join(out) + "\n"


def render_clv(clv: Optional[dict]) -> str:
    out = ["## 📊 CLV Running Total", ""]
    if not clv:
        out.append("_(awaiting R16_E8 — no CLV tracker output yet)_")
        return "\n".join(out) + "\n"
    n = clv.get("n_bets_tracked", 0)
    mean_pct = clv.get("mean_clv_pct", 0.0) or 0.0
    pct_pos = clv.get("pct_positive_clv", 0.0) or 0.0
    updated = clv.get("updated_at", "?")
    out.append(f"- **Bets tracked:** {n}")
    out.append(f"- **Mean CLV%:** {mean_pct:+.2f}%")
    out.append(f"- **% positive:** {pct_pos:.1f}%")
    out.append(f"- **Updated:** {updated}")
    by_book = clv.get("by_book") or {}
    if by_book:
        out.append("")
        out.append("| Book | N | Mean CLV% | % Positive |")
        out.append("|---|---|---|---|")
        for book, stats in sorted(by_book.items()):
            out.append(
                f"| {book} "
                f"| {stats.get('n', 0)} "
                f"| {(stats.get('mean_clv_pct') or 0):+.2f}% "
                f"| {(stats.get('pct_positive') or 0):.1f}% |"
            )
    return "\n".join(out) + "\n"


def render_middles(middles: Optional[dict], limit: int = 10) -> str:
    out = ["## 💸 Active Middles", ""]
    if not middles:
        out.append("_(awaiting R16_E5)_")
        return "\n".join(out) + "\n"
    items = middles.get("middles") or []
    n = middles.get("n_middles", len(items))
    n_arb = middles.get("n_free_arbs", 0)
    n_conf = middles.get("n_model_confirmed", 0)
    out.append(
        f"_{n} middles • {n_arb} free arbs • {n_conf} model-confirmed_ "
        f"(generated {middles.get('generated_at', '?')})"
    )
    if not items:
        out.append("")
        out.append("_(no middles available right now)_")
        return "\n".join(out) + "\n"
    out.append("")
    out.append("| Player | Stat | Over | Under | Width | Worst Juice | Model Band | Confirmed |")
    out.append("|---|---|---|---|---|---|---|---|")
    # Sort: free arbs first, then model-confirmed, then by width desc.
    sortable = sorted(
        items,
        key=lambda m: (
            not bool(m.get("free_arb")),
            not bool(m.get("model_confirmed")),
            -(m.get("middle_width") or 0),
        ),
    )
    for m in sortable[:limit]:
        op = m.get("over_price")
        up = m.get("under_price")
        op_s = f"+{op}" if isinstance(op, (int, float)) and op > 0 else str(op)
        up_s = f"+{up}" if isinstance(up, (int, float)) and up > 0 else str(up)
        band = m.get("model_band_prob")
        band_s = f"{band:.1%}" if isinstance(band, (int, float)) else "—"
        marks = []
        if m.get("free_arb"):
            marks.append("ARB")
        if m.get("model_confirmed"):
            marks.append("✓")
        out.append(
            f"| {m.get('player', '?')} "
            f"| {str(m.get('stat', '?')).upper()} "
            f"| {m.get('over_book')} {m.get('over_line')} {op_s} "
            f"| {m.get('under_book')} {m.get('under_line')} {up_s} "
            f"| {m.get('middle_width', '?')} "
            f"| {m.get('worst_price', '?')} "
            f"| {band_s} "
            f"| {' '.join(marks) or '—'} |"
        )
    return "\n".join(out) + "\n"


def render_line_moves(moves_path: Path, limit: int = 5, window_min: int = 60) -> str:
    """Read the append-only line-moves cache (one JSON event per line)."""
    out = ["## 📈 Line Moves (Last Hour)", ""]
    if not moves_path.exists():
        out.append("_(awaiting R16_E4 — no line-moves cache yet)_")
        return "\n".join(out) + "\n"
    cutoff = _dt.datetime.now(UTC) - _dt.timedelta(minutes=window_min)
    events: List[dict] = []
    try:
        with open(moves_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = ev.get("detected_at") or ev.get("ts") or ev.get("timestamp")
                if ts:
                    try:
                        when = _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                        if when.tzinfo is None:
                            when = when.replace(tzinfo=UTC)
                        if when < cutoff:
                            continue
                    except ValueError:
                        pass
                events.append(ev)
    except Exception:  # noqa: BLE001
        out.append("_(error reading line-moves cache)_")
        return "\n".join(out) + "\n"
    if not events:
        out.append("_(no line moves in the last hour)_")
        return "\n".join(out) + "\n"

    def _magnitude(ev: dict) -> float:
        for k in ("line_delta_abs", "line_delta", "odds_delta_pct", "delta"):
            v = ev.get(k)
            if isinstance(v, (int, float)):
                return abs(v)
        return 0.0

    events.sort(key=_magnitude, reverse=True)
    out.append("| Player | Stat | Book | Old → New | Delta | Detected |")
    out.append("|---|---|---|---|---|---|")
    for ev in events[:limit]:
        delta_parts = []
        if "line_old" in ev and "line_new" in ev:
            delta_parts.append(f"line {ev['line_old']} → {ev['line_new']}")
        if "odds_old" in ev and "odds_new" in ev:
            delta_parts.append(f"odds {ev['odds_old']} → {ev['odds_new']}")
        change = ev.get("change") or "; ".join(delta_parts) or "?"
        out.append(
            f"| {ev.get('player', '?')} "
            f"| {str(ev.get('stat', '?')).upper()} "
            f"| {ev.get('book', '?')} "
            f"| {change} "
            f"| {_magnitude(ev):.2f} "
            f"| {ev.get('detected_at', ev.get('ts', '?'))} |"
        )
    return "\n".join(out) + "\n"


def fetch_health(url: str, timeout: float = 2.0) -> Optional[dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def count_alive_daemons() -> int:
    """Heuristic: count python processes whose cmdline mentions one of our daemons."""
    needles = (
        "scraper_orchestrator",
        "clv_tracker_daemon",
        "middle_finder_daemon",
        "line_move_detector",
        "live_inplay_daemon",
        "live_ranker_daemon",
        "vault_dashboard_daemon",
    )
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid,cmd"], text=True, stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, OSError):
        return 0
    n = 0
    for line in out.splitlines()[1:]:
        if "grep" in line:
            continue
        if any(needle in line for needle in needles):
            n += 1
    return n


def render_system_health(health: Optional[dict], daemons_alive: int) -> str:
    out = ["## ⚙️ System Health", ""]
    if not health:
        out.append("- Scraper orchestrator: _(health endpoint unreachable)_")
    else:
        now = health.get("now", "?")
        out.append(f"- Scraper orchestrator: OK • now={now}")
        for book, info in (health.get("books") or {}).items():
            last_ago = info.get("last_tick_ago_sec", "?")
            alive = "alive" if info.get("alive") else "DEAD"
            errs = info.get("total_errors", 0)
            ticks = info.get("total_ticks", 0)
            out.append(
                f"  - **{book}**: {alive} • last_tick {last_ago}s ago • "
                f"ticks={ticks} errors={errs}"
            )
    out.append(f"- Daemon count: {daemons_alive} alive")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Top-level render.
# ---------------------------------------------------------------------------


def render_dashboard(
    isodate: str,
    label: str,
    sources: Dict[str, Path],
    health_url: str,
) -> Dict[str, Any]:
    """Read every source, render the full TONIGHT.md text.

    Returns ``{"text": <md>, "available": [...], "missing": [...]}`` so the
    daemon can log + emit a probe-results JSON.
    """
    # Load all sources defensively.
    live_bets_dir = sources["live_bets_dir"]
    # Pick today's slate file if available, else newest.
    live_bets_path = None
    if live_bets_dir.exists():
        candidates = sorted(
            [p for p in live_bets_dir.iterdir()
             if p.is_file() and p.name.startswith(isodate) and p.suffix == ".json"],
            key=lambda p: p.stat().st_mtime,
        )
        if candidates:
            live_bets_path = candidates[-1]
        else:
            live_bets_path = _newest_file(live_bets_dir, ".json")

    live_bets = _safe_load_json(live_bets_path) if live_bets_path else None
    middles   = _safe_load_json(sources["middles_path"])
    clv       = _safe_load_json(sources["clv_path"])
    bankroll  = _safe_load_json(sources["bankroll_path"])
    urgent    = _safe_read_text(sources["urgent_path"])

    # Lineups: prefer today's file, else newest in dir.
    lineups_dir = sources["lineups_dir"]
    lineups_path = lineups_dir / f"{isodate}.json"
    if not lineups_path.exists():
        lineups_path = _newest_file(lineups_dir, ".json") if lineups_dir.exists() else None
    lineups = _safe_load_json(lineups_path) if lineups_path else None

    health = fetch_health(health_url)
    daemons_alive = count_alive_daemons()

    line_moves_path = PROJECT_DIR / "data" / "cache" / f"line_moves_{isodate}.json"

    # If live_bets has a label, override the caller's.
    if live_bets and live_bets.get("label"):
        label = live_bets["label"]

    sections = [
        render_header(label, isodate, bankroll),
        render_urgent(urgent),
        render_top_bets(live_bets),
        render_lineups(lineups),
        render_clv(clv),
        render_middles(middles),
        render_line_moves(line_moves_path),
        render_system_health(health, daemons_alive),
    ]
    text = "\n".join(sections).rstrip() + "\n"

    available = []
    missing = []
    for name, present in (
        ("live_bets",  live_bets is not None),
        ("middles",    middles is not None),
        ("clv",        clv is not None),
        ("bankroll",   bankroll is not None),
        ("lineups",    lineups is not None),
        ("urgent",     urgent is not None),
        ("line_moves", line_moves_path.exists()),
        ("health",     health is not None),
    ):
        (available if present else missing).append(name)

    return {
        "text": text,
        "available": available,
        "missing": missing,
        "n_sections": 8,
        "rendered_at": _iso_now(),
    }


# ---------------------------------------------------------------------------
# Daemon loop.
# ---------------------------------------------------------------------------

_RUNNING = True


def _handle_signal(signum, frame):  # noqa: ARG001
    global _RUNNING
    _RUNNING = False
    print(f"[vault_dashboard] caught signal {signum}, exiting on next tick", flush=True)


def run_once(
    isodate: str,
    label: str,
    out_path: Path,
    health_url: str,
) -> Dict[str, Any]:
    sources = {
        "live_bets_dir": DEFAULTS["live_bets_dir"],
        "middles_path":  DEFAULTS["middles_path"],
        "clv_path":      DEFAULTS["clv_path"],
        "bankroll_path": DEFAULTS["bankroll_path"],
        "lineups_dir":   DEFAULTS["lineups_dir"],
        "urgent_path":   DEFAULTS["urgent_path"],
    }
    result = render_dashboard(isodate, label, sources, health_url)
    atomic_write_text(out_path, result["text"])
    return result


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--interval-sec", type=int, default=30,
                    help="Loop cadence (default 30s). Ignored when --once.")
    ap.add_argument("--once", action="store_true",
                    help="Render one snapshot and exit.")
    ap.add_argument("--date", type=str, default=None,
                    help="Override ISO date for slate selection (defaults to today UTC).")
    ap.add_argument("--label", type=str, default="Tonight's slate",
                    help="Fallback header label if live_bets has no label.")
    ap.add_argument("--out", type=str, default=str(DEFAULTS["out_path"]),
                    help="Output Markdown path (default vault/TONIGHT.md).")
    ap.add_argument("--health-url", type=str, default=DEFAULTS["health_url"],
                    help="Scraper orchestrator health endpoint URL.")
    args = ap.parse_args(argv)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    isodate = args.date or _dt.datetime.now(UTC).strftime("%Y-%m-%d")
    out_path = Path(args.out)

    if args.once:
        res = run_once(isodate, args.label, out_path, args.health_url)
        print(
            f"[{_iso_now()}] vault_dashboard once: wrote {out_path} "
            f"({len(res['text'])} bytes, available={res['available']}, "
            f"missing={res['missing']})",
            flush=True,
        )
        return 0

    print(
        f"[{_iso_now()}] vault_dashboard daemon started, "
        f"interval={args.interval_sec}s, out={out_path}",
        flush=True,
    )
    tick = 0
    while _RUNNING:
        t0 = time.time()
        # R19_L3 heartbeat
        _r19_hb('vault_dashboard_daemon')
        try:
            isodate = args.date or _dt.datetime.now(UTC).strftime("%Y-%m-%d")
            res = run_once(isodate, args.label, out_path, args.health_url)
            tick += 1
            print(
                f"[{_iso_now()}] tick={tick} wrote {out_path.name} "
                f"available={len(res['available'])}/8 "
                f"latency_ms={int((time.time()-t0)*1000)}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[{_iso_now()}] tick error: {exc!r}", flush=True)
        # Sleep until next tick, honouring signals.
        sleep_remaining = max(0.0, args.interval_sec - (time.time() - t0))
        end = time.time() + sleep_remaining
        while _RUNNING and time.time() < end:
            time.sleep(min(0.5, end - time.time()))
    print(f"[{_iso_now()}] vault_dashboard daemon exited cleanly", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
