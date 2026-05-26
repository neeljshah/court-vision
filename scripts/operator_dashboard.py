"""operator_dashboard.py — R22_O5 single-pane operator dashboard.

Daily-operator HTML page that summarizes the betting system's state in one
scannable view. Combines:

  - R19_L3 daemon registry + heartbeats   -> System Health
  - R19_L8 bankroll filter                -> Bankroll snapshot
  - R21_N3 alerts vault + critical stack  -> Recent Alerts
  - data/pnl_ledger.csv (real bets)       -> Active Bets
  - data/cache/predictions_cache_<date>   -> Today's Slate
  - R20_M7 + R21_N5 m2_family cache       -> Tracker Status

Designed so that each section's data-fetch helper is independent: a missing
file or a broken daemon never causes the page to 500 — the section just
renders ``(no data)``.

This module is consumed by ``scripts/mobile_html_server.py``'s ``/operator``
route. Tests exercise each helper independently (see
``tests/test_operator_dashboard.py``).
"""
from __future__ import annotations

import csv
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = Path(__file__).resolve().parent.parent

# Default sources -------------------------------------------------------------
DEFAULT_REGISTRY_PATH    = PROJECT_DIR / "scripts" / "daemon_registry.json"
DEFAULT_HEARTBEAT_DIR    = PROJECT_DIR / "data" / "cache" / "daemon_heartbeats"
DEFAULT_BANKROLL_PATH    = PROJECT_DIR / "data" / "cache" / "bankroll_state.json"
DEFAULT_ALERTS_VAULT     = PROJECT_DIR / "vault" / "Improvements" / "alerts.md"
DEFAULT_ALERTS_DIR       = PROJECT_DIR / "data" / "cache" / "alerts"
DEFAULT_LEDGER_PATH      = PROJECT_DIR / "data" / "pnl_ledger.csv"
DEFAULT_PREDICTIONS_DIR  = PROJECT_DIR / "data" / "cache"
DEFAULT_M2_FAMILY_GLOB   = "m2_family_predictions_*.json"

STALE_MULTIPLIER = 3.0  # mirrors daemon_watchdog.STALE_MULTIPLIER


# --------------------------------------------------------------------------- #
# Tiny safe-load helpers — every section degrades gracefully on missing data. #
# --------------------------------------------------------------------------- #
def _safe_load_json(path: Path) -> Optional[Any]:
    try:
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def _safe_read_text(path: Path) -> Optional[str]:
    try:
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception:  # noqa: BLE001
        return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_iso(tz: timezone = timezone.utc) -> str:
    return datetime.now(tz).strftime("%Y-%m-%d")


def _fmt_age(seconds: Optional[float]) -> str:
    if seconds is None:
        return "missing"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    h = s // 3600
    m = (s % 3600) // 60
    return f"{h}h {m}m"


# --------------------------------------------------------------------------- #
# Section 1: System Health (R19_L3)                                           #
# --------------------------------------------------------------------------- #
def fetch_system_health(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    heartbeat_dir: Path = DEFAULT_HEARTBEAT_DIR,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Return system-health rows from daemon registry + heartbeat files.

    Result schema:
        {
          "ok": bool,
          "n_total": int,
          "n_green": int,
          "n_yellow": int,
          "n_red": int,
          "rows": [
            {"name": str, "age_sec": float|None, "expected_sec": float,
             "status": "green"|"yellow"|"red", "reason": str},
            ...
          ]
        }
    """
    out: Dict[str, Any] = {
        "ok": False, "n_total": 0, "n_green": 0, "n_yellow": 0,
        "n_red": 0, "rows": [],
    }
    blob = _safe_load_json(Path(registry_path))
    if not blob or "daemons" not in blob:
        return out
    daemons = blob.get("daemons") or []
    if not isinstance(daemons, list):
        return out
    now_ts = now if now is not None else time.time()

    for d in daemons:
        if not isinstance(d, dict):
            continue
        name = d.get("name") or "(unnamed)"
        expected = float(d.get("expected_interval_sec", 60) or 60)
        hb_rel = d.get("heartbeat_file") or ""
        hb_optional = bool(d.get("heartbeat_optional", False))
        # Resolve heartbeat file location.
        hb_path: Optional[Path] = None
        if hb_rel:
            candidate = Path(hb_rel)
            if not candidate.is_absolute():
                candidate = PROJECT_DIR / hb_rel
            hb_path = candidate
        else:
            hb_path = Path(heartbeat_dir) / f"{name}.txt"

        age: Optional[float] = None
        if hb_path and hb_path.exists():
            try:
                age = now_ts - hb_path.stat().st_mtime
            except OSError:
                age = None

        if age is None:
            status = "yellow" if hb_optional else "red"
            reason = "heartbeat_optional_missing" if hb_optional else "heartbeat_missing"
        elif age <= expected * 1.5:
            status = "green"
            reason = "ok"
        elif age <= expected * STALE_MULTIPLIER:
            status = "yellow"
            reason = f"warm ({_fmt_age(age)} >{int(expected*1.5)}s)"
        else:
            status = "red"
            reason = f"stale ({_fmt_age(age)} >{int(expected*STALE_MULTIPLIER)}s)"

        out["rows"].append({
            "name": name,
            "age_sec": age,
            "expected_sec": expected,
            "status": status,
            "reason": reason,
        })
        out[f"n_{status}"] += 1

    out["n_total"] = len(out["rows"])
    out["ok"] = out["n_total"] > 0
    return out


# --------------------------------------------------------------------------- #
# Section 2: Bankroll (R19_L8 filter applied)                                 #
# --------------------------------------------------------------------------- #
def fetch_bankroll(
    *,
    bankroll_path: Path = DEFAULT_BANKROLL_PATH,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    today: Optional[str] = None,
) -> Dict[str, Any]:
    """Bankroll snapshot. Pulls from R19_L8 filtered bankroll_state.json,
    augments with today's bet counts from the real ledger."""
    today = today or _today_iso()
    state = _safe_load_json(Path(bankroll_path)) or {}

    n_open = 0
    n_settled_today = 0
    if Path(ledger_path).exists():
        try:
            with open(ledger_path, "r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    strat = (row.get("strategy") or "").strip().lower()
                    # Filter to real bets (R19_L8 — exclude synthetic).
                    if "synthetic" in strat or "synth" in strat:
                        continue
                    status = (row.get("status") or "").strip().lower()
                    if status == "open":
                        n_open += 1
                    settled_at = row.get("settled_at") or ""
                    if status in ("won", "lost", "push", "voided") \
                            and settled_at.startswith(today):
                        n_settled_today += 1
        except Exception:  # noqa: BLE001
            pass

    fi = state.get("filter_info") or {}
    return {
        "ok": bool(state),
        "start_bankroll": state.get("start_bankroll"),
        "current_bankroll": state.get("current_bankroll"),
        "available_bankroll": state.get("available_bankroll"),
        "today_pnl": state.get("daily_pnl"),
        "today_roi_pct": (state.get("roi") or {}).get("roi_pct"),
        "n_real_bets_open": n_open,
        "n_real_bets_settled_today": n_settled_today,
        "filter_n_kept": fi.get("n_kept"),
        "filter_n_total": fi.get("n_total"),
        "filter_start_date": fi.get("start_date"),
        "as_of": state.get("as_of"),
    }


# --------------------------------------------------------------------------- #
# Section 3: Recent Alerts (R21_N3 layered)                                   #
# --------------------------------------------------------------------------- #
_VAULT_LINE_RE = re.compile(
    r"^-?\s*\*?\*?(?P<ts>\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}Z?)\*?\*?\s*"
    r"\[(?P<level>CRITICAL|WARN|INFO|critical|warn|info)\]\s*"
    r"(?:\[(?P<tag>[^\]]+)\])?\s*(?P<msg>.+)$",
    re.IGNORECASE,
)


def _parse_vault_alerts_text(text: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _VAULT_LINE_RE.match(line)
        if not m:
            continue
        rows.append({
            "timestamp": m.group("ts"),
            "level": (m.group("level") or "info").lower(),
            "tag": m.group("tag") or "",
            "message": m.group("msg").strip(),
        })
    return rows


def fetch_recent_alerts(
    *,
    vault_path: Path = DEFAULT_ALERTS_VAULT,
    alerts_dir: Path = DEFAULT_ALERTS_DIR,
    window_hours: int = 24,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return recent alerts merged from vault markdown + critical-stack JSON."""
    out: Dict[str, Any] = {
        "ok": False, "window_hours": window_hours,
        "counts": {"critical": 0, "warn": 0, "info": 0},
        "latest": [],
    }
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)
    rows: List[Dict[str, Any]] = []

    # 1. Vault markdown
    vault_text = _safe_read_text(Path(vault_path))
    if vault_text:
        rows.extend(_parse_vault_alerts_text(vault_text))

    # 2. Critical-stack JSON files (any date file in alerts_dir).
    if Path(alerts_dir).exists() and Path(alerts_dir).is_dir():
        for f in sorted(Path(alerts_dir).glob("critical_*.json")):
            blob = _safe_load_json(f)
            if not isinstance(blob, list):
                continue
            for r in blob:
                if not isinstance(r, dict):
                    continue
                rows.append({
                    "timestamp": r.get("timestamp") or r.get("ts") or "",
                    "level": str(r.get("level") or "critical").lower(),
                    "tag": r.get("tag") or r.get("source") or "",
                    "message": r.get("message") or r.get("msg") or "",
                })

    if not rows:
        return out

    # Filter to window, then sort newest-first.
    def _parse_ts(s: str) -> Optional[datetime]:
        if not s:
            return None
        s = s.replace(" ", "T")
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None

    filtered = []
    for r in rows:
        dt = _parse_ts(r["timestamp"])
        if dt is None:
            # Keep row but treat as un-windowed (sort to the bottom).
            r["_dt"] = datetime.min.replace(tzinfo=timezone.utc)
            filtered.append(r)
            continue
        if dt >= cutoff:
            r["_dt"] = dt
            filtered.append(r)

    filtered.sort(key=lambda r: r["_dt"], reverse=True)

    counts = {"critical": 0, "warn": 0, "info": 0}
    for r in filtered:
        lvl = r["level"]
        if lvl not in counts:
            lvl = "info"
        counts[lvl] += 1

    latest = []
    for r in filtered[:5]:
        first_line = (r["message"] or "").splitlines()[0] if r["message"] else ""
        latest.append({
            "timestamp": r["timestamp"],
            "level": r["level"],
            "tag": r["tag"],
            "message": first_line,
        })

    out["ok"] = True
    out["counts"] = counts
    out["latest"] = latest
    return out


# --------------------------------------------------------------------------- #
# Section 4: Active Bets (real ledger, status=open)                           #
# --------------------------------------------------------------------------- #
def _line_age(placed_at: str, now: Optional[datetime] = None) -> Optional[float]:
    if not placed_at:
        return None
    s = placed_at.replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    now = now or datetime.now(timezone.utc)
    return (now - dt).total_seconds()


def fetch_active_bets(
    *,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    limit: int = 25,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return open real bets from data/pnl_ledger.csv (R19_L8 filter applied)."""
    out: Dict[str, Any] = {"ok": False, "n_open": 0, "bets": []}
    if not Path(ledger_path).exists():
        return out
    try:
        with open(ledger_path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
    except Exception:  # noqa: BLE001
        return out

    bets: List[Dict[str, Any]] = []
    for r in rows:
        strat = (r.get("strategy") or "").strip().lower()
        if "synth" in strat:
            continue
        if (r.get("status") or "").strip().lower() != "open":
            continue
        try:
            line = float(r.get("line") or 0.0)
        except (TypeError, ValueError):
            line = 0.0
        try:
            edge = float(r.get("model_edge")) if r.get("model_edge") else None
        except (TypeError, ValueError):
            edge = None
        try:
            kelly = float(r.get("kelly_pct")) if r.get("kelly_pct") else None
        except (TypeError, ValueError):
            kelly = None
        age = _line_age(r.get("placed_at") or "", now=now)
        bets.append({
            "player": r.get("player") or "",
            "stat": (r.get("stat") or "").upper(),
            "line": line,
            "side": (r.get("side") or "").upper(),
            "book": r.get("book") or "",
            "edge": edge,
            "kelly_pct": kelly,
            "line_age_sec": age,
        })

    bets.sort(key=lambda b: (b["edge"] if b["edge"] is not None else -1e9), reverse=True)
    out["ok"] = True
    out["n_open"] = len(bets)
    out["bets"] = bets[:limit]
    return out


# --------------------------------------------------------------------------- #
# Section 5: Today's Slate (predictions cache)                                #
# --------------------------------------------------------------------------- #
def fetch_today_slate(
    *,
    predictions_dir: Path = DEFAULT_PREDICTIONS_DIR,
    today: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Return top-N predictions for today's slate ranked by an EV proxy
    (q90 - q50). Uses parquet via pandas when available."""
    today = today or _today_iso()
    out: Dict[str, Any] = {"ok": False, "date": today, "n_rows": 0, "top": []}
    parquet = Path(predictions_dir) / f"predictions_cache_{today}.parquet"
    if not parquet.exists():
        return out
    try:
        import pandas as pd  # local import — pandas is heavy
        df = pd.read_parquet(parquet)
    except Exception:  # noqa: BLE001
        return out
    if df is None or df.empty:
        return out
    # EV proxy: width of the q90 tail relative to q50.
    cols = set(df.columns)
    needed = {"player_name", "stat", "q10", "q50", "q90"}
    if not needed.issubset(cols):
        return out
    try:
        df = df.copy()
        df["ev_proxy"] = (df["q90"] - df["q50"]).clip(lower=0)
        df = df.sort_values("ev_proxy", ascending=False).head(limit)
        top = []
        for _, row in df.iterrows():
            top.append({
                "player": str(row.get("player_name") or ""),
                "team": str(row.get("team") or ""),
                "stat": str(row.get("stat") or "").upper(),
                "q10": float(row.get("q10") or 0.0),
                "q50": float(row.get("q50") or 0.0),
                "q90": float(row.get("q90") or 0.0),
                "ev_proxy": float(row.get("ev_proxy") or 0.0),
            })
    except Exception:  # noqa: BLE001
        return out
    out["ok"] = True
    out["n_rows"] = int(len(df))
    out["top"] = top
    return out


# --------------------------------------------------------------------------- #
# Section 6: Tracker Status (m2_family cache freshness)                       #
# --------------------------------------------------------------------------- #
def fetch_tracker_status(
    *,
    predictions_dir: Path = DEFAULT_PREDICTIONS_DIR,
    today: Optional[str] = None,
    max_age_hours: float = 24.0,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Tracker / M2 multi5 status — is the prediction cache fresh for today?"""
    today = today or _today_iso()
    now_ts = now if now is not None else time.time()
    out: Dict[str, Any] = {
        "ok": False, "date": today, "predictions_cache_present": False,
        "predictions_cache_age_hours": None, "m2_family_files": 0,
        "m2_family_newest_age_hours": None, "status": "red",
        "summary": "no data",
    }
    parquet = Path(predictions_dir) / f"predictions_cache_{today}.parquet"
    if parquet.exists():
        out["predictions_cache_present"] = True
        try:
            age_h = (now_ts - parquet.stat().st_mtime) / 3600.0
            out["predictions_cache_age_hours"] = round(age_h, 2)
        except OSError:
            pass

    m2_files = sorted(Path(predictions_dir).glob(DEFAULT_M2_FAMILY_GLOB))
    out["m2_family_files"] = len(m2_files)
    if m2_files:
        try:
            newest = max(m2_files, key=lambda p: p.stat().st_mtime)
            out["m2_family_newest_age_hours"] = round(
                (now_ts - newest.stat().st_mtime) / 3600.0, 2
            )
        except OSError:
            pass

    out["ok"] = out["predictions_cache_present"] or bool(m2_files)

    age = out["predictions_cache_age_hours"]
    if out["predictions_cache_present"] and age is not None and age <= max_age_hours:
        out["status"] = "green"
        out["summary"] = (
            f"predictions cache fresh ({age:.1f}h old); "
            f"m2_family files={out['m2_family_files']}"
        )
    elif out["predictions_cache_present"]:
        out["status"] = "yellow"
        out["summary"] = (
            f"predictions cache present but stale ({age}h old)"
            if age is not None else "predictions cache present, age unknown"
        )
    else:
        out["status"] = "red"
        out["summary"] = "no predictions cache for today"

    return out


# --------------------------------------------------------------------------- #
# HTML rendering                                                              #
# --------------------------------------------------------------------------- #
_STATUS_COLOR = {
    "green":  "#2ea043",
    "yellow": "#d29922",
    "red":    "#f85149",
}


def _html_escape(s: Any) -> str:
    s = "" if s is None else str(s)
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def _fmt_money(v: Any) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return _html_escape(v)
    return f"${f:,.2f}"


def _fmt_pct(v: Any) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return _html_escape(v)
    return f"{f:+.2f}%"


def _section_system_health(d: Dict[str, Any]) -> str:
    if not d.get("ok"):
        return ('<h2>System Health</h2>'
                '<p class="muted">(no daemon registry found)</p>')
    rows_html = []
    for r in d.get("rows", []):
        color = _STATUS_COLOR.get(r["status"], "#8b949e")
        age = _fmt_age(r["age_sec"])
        expected = int(r["expected_sec"])
        rows_html.append(
            f'<tr>'
            f'<td><span class="dot" style="background:{color}"></span>'
            f'{_html_escape(r["name"])}</td>'
            f'<td>{_html_escape(age)}</td>'
            f'<td>{expected}s</td>'
            f'<td>{_html_escape(r["reason"])}</td>'
            f'</tr>'
        )
    summary = (
        f'<span style="color:{_STATUS_COLOR["green"]}">{d["n_green"]} green</span> · '
        f'<span style="color:{_STATUS_COLOR["yellow"]}">{d["n_yellow"]} yellow</span> · '
        f'<span style="color:{_STATUS_COLOR["red"]}">{d["n_red"]} red</span> '
        f'<span class="muted">of {d["n_total"]} daemons</span>'
    )
    return (
        '<h2>System Health</h2>'
        f'<p>{summary}</p>'
        '<table><thead><tr><th>Daemon</th><th>Heartbeat age</th>'
        '<th>Expected</th><th>Reason</th></tr></thead><tbody>'
        + "".join(rows_html) +
        '</tbody></table>'
    )


def _section_bankroll(d: Dict[str, Any]) -> str:
    if not d.get("ok"):
        return ('<h2>Bankroll</h2>'
                '<p class="muted">(no bankroll_state.json found)</p>')
    today_pnl = d["today_pnl"]
    pnl_color = _STATUS_COLOR["green"] if (today_pnl or 0) >= 0 else _STATUS_COLOR["red"]
    filter_line = ""
    if d.get("filter_n_kept") is not None and d.get("filter_n_total"):
        filter_line = (
            f'<p class="muted">R19_L8 filter: showing {d["filter_n_kept"]:,} of '
            f'{d["filter_n_total"]:,} bets'
            + (f' since {_html_escape(d["filter_start_date"])}'
               if d.get("filter_start_date") else "")
            + '</p>'
        )
    return (
        '<h2>Bankroll</h2>'
        '<table><tbody>'
        f'<tr><th>Start</th><td>{_fmt_money(d["start_bankroll"])}</td></tr>'
        f'<tr><th>Current</th><td>{_fmt_money(d["current_bankroll"])}</td></tr>'
        f'<tr><th>Available</th><td>{_fmt_money(d["available_bankroll"])}</td></tr>'
        f'<tr><th>Today P&amp;L</th>'
        f'<td style="color:{pnl_color}">{_fmt_money(today_pnl)}</td></tr>'
        f'<tr><th>Today ROI</th><td>{_fmt_pct(d["today_roi_pct"])}</td></tr>'
        f'<tr><th>Open real bets</th><td>{d["n_real_bets_open"]}</td></tr>'
        f'<tr><th>Settled today</th><td>{d["n_real_bets_settled_today"]}</td></tr>'
        '</tbody></table>'
        + filter_line
    )


def _section_alerts(d: Dict[str, Any]) -> str:
    if not d.get("ok"):
        return ('<h2>Recent Alerts</h2>'
                '<p class="muted">(no alerts found)</p>')
    c = d.get("counts", {})
    line = (
        f'<span style="color:{_STATUS_COLOR["red"]}">{c.get("critical",0)} critical</span> · '
        f'<span style="color:{_STATUS_COLOR["yellow"]}">{c.get("warn",0)} warn</span> · '
        f'<span style="color:{_STATUS_COLOR["green"]}">{c.get("info",0)} info</span> '
        f'<span class="muted">(last {d["window_hours"]}h)</span>'
    )
    if not d.get("latest"):
        return f'<h2>Recent Alerts</h2><p>{line}</p>'
    rows = []
    for r in d["latest"]:
        lvl = r["level"]
        color = (_STATUS_COLOR["red"] if lvl == "critical"
                 else _STATUS_COLOR["yellow"] if lvl == "warn"
                 else _STATUS_COLOR["green"])
        rows.append(
            f'<tr><td>{_html_escape(r["timestamp"])}</td>'
            f'<td style="color:{color}">{_html_escape(lvl.upper())}</td>'
            f'<td>{_html_escape(r["tag"])}</td>'
            f'<td>{_html_escape(r["message"])}</td></tr>'
        )
    return (
        '<h2>Recent Alerts</h2>'
        f'<p>{line}</p>'
        '<table><thead><tr><th>Time</th><th>Level</th><th>Tag</th>'
        '<th>Message</th></tr></thead><tbody>'
        + "".join(rows) +
        '</tbody></table>'
    )


def _section_active_bets(d: Dict[str, Any]) -> str:
    if not d.get("ok"):
        return ('<h2>Active Bets</h2>'
                '<p class="muted">(no pnl_ledger.csv found)</p>')
    if not d.get("bets"):
        return f'<h2>Active Bets</h2><p>{d["n_open"]} open</p>'
    rows = []
    for b in d["bets"]:
        edge = "—" if b["edge"] is None else f'{b["edge"]:+.2f}'
        kelly = "—" if b["kelly_pct"] is None else f'{b["kelly_pct"]*100:.2f}%'
        age = _fmt_age(b["line_age_sec"])
        rows.append(
            f'<tr><td>{_html_escape(b["player"])}</td>'
            f'<td>{_html_escape(b["stat"])}</td>'
            f'<td>{b["line"]:.1f}</td>'
            f'<td>{_html_escape(b["side"])}</td>'
            f'<td>{_html_escape(b["book"])}</td>'
            f'<td>{edge}</td>'
            f'<td>{kelly}</td>'
            f'<td>{age}</td></tr>'
        )
    return (
        '<h2>Active Bets</h2>'
        f'<p>{d["n_open"]} open</p>'
        '<table><thead><tr><th>Player</th><th>Stat</th><th>Line</th>'
        '<th>Side</th><th>Book</th><th>Edge</th><th>Kelly%</th>'
        '<th>Age</th></tr></thead><tbody>'
        + "".join(rows) +
        '</tbody></table>'
    )


def _section_today_slate(d: Dict[str, Any]) -> str:
    if not d.get("ok"):
        return (f'<h2>Today\'s Slate ({_html_escape(d.get("date",""))})</h2>'
                '<p class="muted">(no predictions cache for today)</p>')
    if not d.get("top"):
        return (f'<h2>Today\'s Slate ({_html_escape(d.get("date",""))})</h2>'
                '<p>0 ranked recs</p>')
    rows = []
    for r in d["top"]:
        rows.append(
            f'<tr><td>{_html_escape(r["player"])}</td>'
            f'<td>{_html_escape(r["team"])}</td>'
            f'<td>{_html_escape(r["stat"])}</td>'
            f'<td>{r["q10"]:.2f}</td>'
            f'<td>{r["q50"]:.2f}</td>'
            f'<td>{r["q90"]:.2f}</td>'
            f'<td>{r["ev_proxy"]:.2f}</td></tr>'
        )
    return (
        f'<h2>Today\'s Slate ({_html_escape(d["date"])})</h2>'
        f'<p>{d["n_rows"]} rows · top {len(d["top"])} by EV proxy (q90-q50)</p>'
        '<table><thead><tr><th>Player</th><th>Team</th><th>Stat</th>'
        '<th>q10</th><th>q50</th><th>q90</th><th>EV proxy</th>'
        '</tr></thead><tbody>'
        + "".join(rows) +
        '</tbody></table>'
    )


def _section_tracker_status(d: Dict[str, Any]) -> str:
    color = _STATUS_COLOR.get(d.get("status", "red"), "#8b949e")
    age = d.get("predictions_cache_age_hours")
    m2_age = d.get("m2_family_newest_age_hours")
    return (
        '<h2>Tracker Status</h2>'
        f'<p><span class="dot" style="background:{color}"></span>'
        f'{_html_escape(d.get("summary",""))}</p>'
        '<table><tbody>'
        f'<tr><th>Date</th><td>{_html_escape(d.get("date",""))}</td></tr>'
        f'<tr><th>Predictions cache present</th>'
        f'<td>{"yes" if d.get("predictions_cache_present") else "no"}</td></tr>'
        f'<tr><th>Cache age</th>'
        f'<td>{"—" if age is None else f"{age:.2f}h"}</td></tr>'
        f'<tr><th>m2_family files</th><td>{d.get("m2_family_files",0)}</td></tr>'
        f'<tr><th>m2_family newest age</th>'
        f'<td>{"—" if m2_age is None else f"{m2_age:.2f}h"}</td></tr>'
        '</tbody></table>'
    )


# Section IDs/titles — also used by tests / probe to assert presence.
SECTION_TITLES = (
    "System Health",
    "Bankroll",
    "Recent Alerts",
    "Active Bets",
    "Today's Slate",
    "Tracker Status",
)
# R23_P8 — optional section, only rendered when collect_and_render is called
# with `include_live_recs=True` (the default).
LIVE_RECS_SECTION_TITLE = "What to bet right now"


# --------------------------------------------------------------------------- #
# Section 7: "What to bet right now" (R23_P8)                                 #
# --------------------------------------------------------------------------- #
def fetch_live_recommendations(
    *,
    bankroll: float = 1000.0,
    top: int = 5,
    today: Optional[str] = None,
    min_edge: float = 0.05,
) -> Dict[str, Any]:
    """Call the R23_P8 live recommendation engine for today.

    Always returns a dict — defensive even if the engine import fails so
    a broken downstream never takes the operator page down.
    """
    out: Dict[str, Any] = {
        "ok": False, "date": today or _today_iso(),
        "recommendations": [], "reason": "",
        "bankroll": bankroll, "n_recs": 0,
        "n_filtered_out": 0, "n_filtered_kelly_cap": 0,
    }
    try:
        # Local import — keep dashboard cold-start light.
        from scripts.live_recommendation_engine import run_engine  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"engine import failed: {exc}"
        return out
    try:
        payload = run_engine(
            bankroll=float(bankroll),
            top=int(top),
            date=out["date"],
            min_edge=float(min_edge),
        )
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"engine raised: {exc}"
        return out
    out["ok"] = True
    out["recommendations"] = payload.get("recommendations", []) or []
    out["reason"] = payload.get("reason", "")
    out["n_recs"] = payload.get("n_recs", 0) or 0
    out["n_filtered_out"] = payload.get("n_filtered_out", 0) or 0
    out["n_filtered_kelly_cap"] = payload.get("n_filtered_kelly_cap", 0) or 0
    out["total_stake_post_cap"] = payload.get("total_stake_post_cap", 0.0) or 0.0
    out["slate_cap_dollars"] = payload.get("slate_cap_dollars", 0.0) or 0.0
    return out


def _section_live_recs(d: Dict[str, Any]) -> str:
    if not d.get("ok"):
        return ('<h2>What to bet right now</h2>'
                f'<p class="muted">(engine unavailable: '
                f'{_html_escape(d.get("reason",""))})</p>')
    if not d.get("recommendations"):
        return (
            '<h2>What to bet right now</h2>'
            f'<p>{_html_escape(d.get("reason","")) or "no recommendations"}</p>'
            f'<p class="muted">filtered OUT={d.get("n_filtered_out",0)} '
            f'kelly-cap-scaled={d.get("n_filtered_kelly_cap",0)}</p>'
        )
    rows = []
    for i, b in enumerate(d["recommendations"], 1):
        rows.append(
            f'<tr><td>{i}</td>'
            f'<td>{_html_escape(b.get("player",""))}</td>'
            f'<td>{_html_escape(str(b.get("stat","")).upper())}</td>'
            f'<td>{_html_escape(b.get("side",""))}</td>'
            f'<td>{_html_escape(b.get("book",""))}</td>'
            f'<td>{float(b.get("line",0)):.1f}</td>'
            f'<td>{int(b.get("odds",0)):+d}</td>'
            f'<td>{float(b.get("edge_pct",0)):+.2f}%</td>'
            f'<td>{float(b.get("kelly_pct",0))*100:.2f}%</td>'
            f'<td>${float(b.get("stake_dollars",0)):.2f}</td></tr>'
        )
    summary = (
        f'<p>{len(d["recommendations"])} recs · '
        f'exposure ${d.get("total_stake_post_cap",0):.2f} '
        f'of ${d.get("slate_cap_dollars",0):.2f} cap · '
        f'filtered OUT={d.get("n_filtered_out",0)} · '
        f'kelly-cap-scaled={d.get("n_filtered_kelly_cap",0)}</p>'
    )
    return (
        '<h2>What to bet right now</h2>'
        + summary +
        '<table><thead><tr><th>#</th><th>Player</th><th>Stat</th>'
        '<th>Side</th><th>Book</th><th>Line</th><th>Odds</th>'
        '<th>Edge</th><th>Kelly%</th><th>Stake$</th></tr></thead><tbody>'
        + "".join(rows) +
        '</tbody></table>'
    )


_OPERATOR_CSS = """
* { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0;
  background: #0d1117; color: #c9d1d9;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 17px; line-height: 1.5;
  -webkit-text-size-adjust: 100%;
}
.wrap { max-width: 960px; margin: 0 auto; padding: 12px 14px 64px; }
h1 {
  font-size: 1.5em; margin: 0.4em 0 0.3em; color: #f0f6fc;
  border-bottom: 2px solid #30363d; padding-bottom: 0.25em;
}
h2 {
  font-size: 1.18em; margin: 1.1em 0 0.4em;
  padding: 0.5em 0.7em; border-radius: 6px;
  background: #161b22; border-left: 4px solid #58a6ff;
}
p { margin: 0.4em 0 0.8em; }
.muted { color: #8b949e; font-style: italic; }
.dot {
  display: inline-block; width: 10px; height: 10px; border-radius: 50%;
  margin-right: 8px; vertical-align: middle;
}
table {
  border-collapse: collapse; width: 100%;
  margin: 0.4em 0 1em; font-size: 0.92em;
  display: block; overflow-x: auto; white-space: nowrap;
}
th, td { padding: 6px 9px; border: 1px solid #30363d; text-align: left; }
th { background: #161b22; color: #f0f6fc; }
tr:nth-child(even) td { background: #0d1117; }
tr:nth-child(odd) td { background: #11161d; }
.refresh-badge {
  position: fixed; bottom: 10px; right: 10px;
  background: #21262d; color: #8b949e;
  padding: 6px 10px; border-radius: 16px;
  font-size: 0.75em; border: 1px solid #30363d;
}
@media (max-width: 480px) {
  body { font-size: 16px; } h1 { font-size: 1.3em; }
  h2 { font-size: 1.05em; padding: 0.45em 0.6em; }
  table { font-size: 0.85em; } th, td { padding: 5px 6px; }
  .wrap { padding: 8px 10px 64px; }
}
"""


def render_operator_html(
    health: Dict[str, Any],
    bankroll: Dict[str, Any],
    alerts: Dict[str, Any],
    bets: Dict[str, Any],
    slate: Dict[str, Any],
    tracker: Dict[str, Any],
    live_recs: Optional[Dict[str, Any]] = None,  # R23_P8
    *,
    auto_refresh_sec: int = 60,
    title: str = "Operator — Morning Coffee",
) -> str:
    """Render the full operator dashboard HTML."""
    body = (
        _section_system_health(health)
        + _section_bankroll(bankroll)
        + _section_alerts(alerts)
        + _section_active_bets(bets)
        + _section_today_slate(slate)
        + _section_tracker_status(tracker)
    )
    if live_recs is not None:
        body += _section_live_recs(live_recs)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta http-equiv="refresh" content="{int(auto_refresh_sec)}">'
        f'<title>{_html_escape(title)}</title>'
        f"<style>{_OPERATOR_CSS}</style>"
        '</head><body>'
        f'<div class="wrap">'
        f'<h1>{_html_escape(title)}</h1>'
        f'<p class="muted">Rendered {_iso_now()}</p>'
        f'{body}'
        '</div>'
        f'<div class="refresh-badge">auto-refresh {int(auto_refresh_sec)}s</div>'
        '</body></html>'
    )


def collect_and_render(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    heartbeat_dir: Path = DEFAULT_HEARTBEAT_DIR,
    bankroll_path: Path = DEFAULT_BANKROLL_PATH,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    alerts_vault: Path = DEFAULT_ALERTS_VAULT,
    alerts_dir: Path = DEFAULT_ALERTS_DIR,
    predictions_dir: Path = DEFAULT_PREDICTIONS_DIR,
    today: Optional[str] = None,
    auto_refresh_sec: int = 60,
    include_live_recs: bool = True,    # R23_P8
    live_recs_bankroll: float = 1000.0,
    live_recs_top: int = 5,
    live_recs_min_edge: float = 0.05,
) -> str:
    """Top-level entry: collect every section's data + render HTML.

    Each helper is independent — a single broken section degrades gracefully.
    """
    today = today or _today_iso()
    # Each fetch is independent and exception-isolated.
    def _safe(fn, **kw):
        try:
            return fn(**kw)
        except Exception:  # noqa: BLE001
            return {"ok": False}

    health   = _safe(fetch_system_health,
                     registry_path=registry_path, heartbeat_dir=heartbeat_dir)
    bankroll = _safe(fetch_bankroll,
                     bankroll_path=bankroll_path, ledger_path=ledger_path,
                     today=today)
    alerts   = _safe(fetch_recent_alerts,
                     vault_path=alerts_vault, alerts_dir=alerts_dir)
    bets     = _safe(fetch_active_bets, ledger_path=ledger_path)
    slate    = _safe(fetch_today_slate,
                     predictions_dir=predictions_dir, today=today)
    tracker  = _safe(fetch_tracker_status,
                     predictions_dir=predictions_dir, today=today)
    live_recs = None
    if include_live_recs:
        live_recs = _safe(
            fetch_live_recommendations,
            bankroll=live_recs_bankroll, top=live_recs_top,
            today=today, min_edge=live_recs_min_edge,
        )
        live_recs.setdefault("ok", False)

    # Defensive defaults so render never KeyErrors on a partial-result.
    for d in (health, bankroll, alerts, bets, slate, tracker):
        d.setdefault("ok", False)

    return render_operator_html(
        health, bankroll, alerts, bets, slate, tracker, live_recs,
        auto_refresh_sec=auto_refresh_sec,
    )
