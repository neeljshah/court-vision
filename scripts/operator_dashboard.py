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
# Section 6b: Feature Drift (R27_T3)                                          #
# --------------------------------------------------------------------------- #
DEFAULT_DRIFT_CACHE = PROJECT_DIR / "data" / "cache" / "feature_drift_latest.json"


def fetch_feature_drift(
    *,
    cache_path: Path = DEFAULT_DRIFT_CACHE,
    feature_set: str = "m2",
    current_days: int = 14,
    live_run: bool = False,
    run_fn: Optional[Any] = None,
) -> Dict[str, Any]:
    """Read the latest feature_drift_detector.py report.

    Reads the JSON cache at ``cache_path`` (written by the drift detector
    CLI / daily_workflow). When ``live_run=True`` AND the cache is missing,
    invokes the detector in-process via ``run_fn`` (defaults to
    ``feature_drift_detector.run``). Always returns a dict — never raises —
    so a broken detector path can't take the whole dashboard down.
    """
    out: Dict[str, Any] = {
        "ok": False, "feature_set": feature_set,
        "n_features_analyzed": 0, "n_stable": 0,
        "n_drift_minor": 0, "n_drift_major": 0,
        "top_drifted": [], "reason": "",
        "ts": "", "status": "missing",
    }
    payload = _safe_load_json(Path(cache_path))
    if payload is None and live_run:
        try:
            if run_fn is None:
                from scripts.feature_drift_detector import run as run_fn  # noqa: PLC0415,E501
            payload = run_fn(
                feature_set=feature_set,
                current_days=int(current_days),
            )
        except Exception as exc:  # noqa: BLE001
            out["reason"] = f"live drift run failed: {exc}"
            return out
    if not isinstance(payload, dict):
        out["reason"] = "no drift cache and live_run=False"
        return out
    out["ok"] = True
    out["ts"] = str(payload.get("ts", ""))
    out["feature_set"] = str(payload.get("feature_set", feature_set))
    out["status"] = str(payload.get("status", "OK"))
    out["reason"] = str(payload.get("blocked_reason", "") or "")
    out["n_features_analyzed"] = int(payload.get("n_features_analyzed", 0) or 0)
    out["n_stable"]      = int(payload.get("n_stable", 0) or 0)
    out["n_drift_minor"] = int(payload.get("n_drift_minor", 0) or 0)
    out["n_drift_major"] = int(payload.get("n_drift_major", 0) or 0)
    feats = payload.get("features") or []
    # The detector pre-sorts majors first; just take the head as "top drifted".
    top: List[Dict[str, Any]] = []
    for r in feats[:5]:
        top.append({
            "feature":  str(r.get("feature", "")),
            "class":    str(r.get("class", "")),
            "ks_stat":  r.get("ks_stat"),
            "p_value":  r.get("p_value"),
            "mean_z":   r.get("mean_z"),
        })
    out["top_drifted"] = top
    return out


def _section_feature_drift(d: Dict[str, Any]) -> str:
    if not d.get("ok"):
        return ('<h2>Feature Drift</h2>'
                f'<p class="muted">(no drift report cached: '
                f'{_html_escape(d.get("reason",""))})</p>')
    n_major = int(d.get("n_drift_major", 0))
    n_minor = int(d.get("n_drift_minor", 0))
    n_stable = int(d.get("n_stable", 0))
    n_total = int(d.get("n_features_analyzed", 0))
    if d.get("status") != "OK":
        color = _STATUS_COLOR["yellow"]
    elif n_major > 15:
        color = _STATUS_COLOR["red"]
    elif n_major > 5:
        color = _STATUS_COLOR["yellow"]
    else:
        color = _STATUS_COLOR["green"]
    rows = []
    for r in (d.get("top_drifted") or []):
        try:
            ks = float(r.get("ks_stat") or 0.0)
            pv = float(r.get("p_value") or 0.0)
            mz = float(r.get("mean_z") or 0.0)
        except (TypeError, ValueError):
            ks = pv = mz = 0.0
        rows.append(
            f'<tr><td>{_html_escape(r.get("feature",""))}</td>'
            f'<td>{_html_escape(r.get("class",""))}</td>'
            f'<td>{ks:.3f}</td><td>{pv:.2e}</td>'
            f'<td>{mz:+.2f}</td></tr>'
        )
    table = (
        '<table><thead><tr><th>feature</th><th>class</th>'
        '<th>ks</th><th>p</th><th>mean_z</th></tr></thead><tbody>'
        + "".join(rows) +
        '</tbody></table>'
    ) if rows else '<p class="muted">no per-feature rows</p>'
    return (
        '<h2>Feature Drift</h2>'
        f'<p><span class="dot" style="background:{color}"></span>'
        f'set={_html_escape(d.get("feature_set",""))} · '
        f'analyzed={n_total} · '
        f'stable={n_stable} · minor={n_minor} · <b>MAJOR={n_major}</b></p>'
        + table
    )


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


# --------------------------------------------------------------------------- #
# Section 7: Settlement Health (R24_Q8)                                       #
# --------------------------------------------------------------------------- #
DEFAULT_QB_DIR_PATH = PROJECT_DIR / "data" / "cache" / "quarter_box"


def fetch_settlement_health(
    *,
    ledger_path: Path = DEFAULT_LEDGER_PATH,
    qb_dir: Path = DEFAULT_QB_DIR_PATH,
    days: int = 7,
) -> Dict[str, Any]:
    """Run the R24_Q8 settlement reconciliation over the last `days` and
    return a small summary suitable for the operator dashboard.

    Always returns a dict — never raises — so a broken reconcile path can't
    take the whole dashboard down.
    """
    out: Dict[str, Any] = {
        "ok": False, "days": int(days),
        "n_real_settled": 0, "n_verified": 0,
        "n_matched": 0, "n_mismatched": 0,
        "match_rate": None, "categories": {},
        "all_synthetic": False, "reason": "",
    }
    try:
        from scripts.reconcile_settlements import reconcile  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"reconcile import failed: {exc}"
        return out
    try:
        rep = reconcile(days=int(days), ledger_path=Path(ledger_path),
                         qb_dir=Path(qb_dir), include_synthetic=False)
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"reconcile raised: {exc}"
        return out
    out["ok"] = True
    out["n_real_settled"] = int(rep.get("n_real_settled", 0) or 0)
    out["n_verified"]     = int(rep.get("n_verified", 0) or 0)
    out["n_matched"]      = int(rep.get("n_matched", 0) or 0)
    out["n_mismatched"]   = int(rep.get("n_mismatched", 0) or 0)
    out["categories"]     = rep.get("mismatch_categories", {}) or {}
    out["all_synthetic"]  = bool(rep.get("all_synthetic", False))
    if out["n_verified"] > 0:
        out["match_rate"] = out["n_matched"] / out["n_verified"]
    if out["n_real_settled"] == 0:
        out["reason"] = ("no real settled bets in window"
                         if not out["all_synthetic"]
                         else "all settled bets in window are synthetic")
    return out


def _section_settlement_health(d: Dict[str, Any]) -> str:
    if not d.get("ok"):
        return ('<h2>Settlement Health</h2>'
                f'<p class="muted">(reconcile unavailable: '
                f'{_html_escape(d.get("reason",""))})</p>')
    days = d.get("days", 7)
    if d.get("n_real_settled", 0) == 0:
        return ('<h2>Settlement Health</h2>'
                f'<p class="muted">no real settled bets in last {days}d'
                + (' (all synthetic)' if d.get("all_synthetic") else '')
                + '</p>')
    mr = d.get("match_rate")
    if mr is None:
        rate_str = "—"
        color = _STATUS_COLOR.get("yellow", "#8b949e")
    else:
        rate_str = f"{mr * 100:.1f}%"
        if mr >= 0.99:
            color = _STATUS_COLOR.get("green", "#3fb950")
        elif mr >= 0.95:
            color = _STATUS_COLOR.get("yellow", "#d29922")
        else:
            color = _STATUS_COLOR.get("red", "#f85149")
    cats_html = ""
    cats = d.get("categories", {}) or {}
    interesting = {k: v for k, v in cats.items() if k != "ok"}
    if interesting:
        rows = "".join(
            f'<tr><td>{_html_escape(k)}</td><td>{int(v)}</td></tr>'
            for k, v in sorted(interesting.items(), key=lambda x: -x[1])
        )
        cats_html = (
            '<p class="muted">Mismatch categories:</p>'
            '<table><thead><tr><th>category</th><th>n</th></tr></thead>'
            f'<tbody>{rows}</tbody></table>'
        )
    return (
        '<h2>Settlement Health</h2>'
        f'<p><span class="dot" style="background:{color}"></span>'
        f'Match rate (last {days}d): <strong>{rate_str}</strong></p>'
        '<table><tbody>'
        f'<tr><th>Real settled (in window)</th><td>{d["n_real_settled"]}</td></tr>'
        f'<tr><th>Verified vs boxscore</th><td>{d["n_verified"]}</td></tr>'
        f'<tr><th>Matched</th><td>{d["n_matched"]}</td></tr>'
        f'<tr><th>Mismatched</th><td>{d["n_mismatched"]}</td></tr>'
        '</tbody></table>'
        + cats_html
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
# R24_Q4 — optional section, only rendered when collect_and_render is called
# with `include_rec_perf=True` (default). Degrades gracefully when the
# rec_settled.parquet file does not exist yet (first-7-days warm-up).
REC_PERF_SECTION_TITLE = "Recent Rec Performance"
# R24_Q8 — optional section, rendered when collect_and_render is called with
# `include_settlement_health=True` (the default).
SETTLEMENT_HEALTH_SECTION_TITLE = "Settlement Health"
# R30_W4 — optional section, rendered when collect_and_render is called with
# `include_data_freshness=True` (default). Surfaces age of every operator-
# critical data source so a stale feed is caught at a glance.
DATA_FRESHNESS_SECTION_TITLE = "Data Freshness"


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


# --------------------------------------------------------------------------- #
# Section 8: "Recent Rec Performance" (R24_Q4)                                 #
# --------------------------------------------------------------------------- #
DEFAULT_REC_SETTLED_PATH = (
    PROJECT_DIR / "data" / "cache" / "rec_tracker" / "rec_settled.parquet"
)
# R25_R5 — historical backtest of the live recommendation engine.
DEFAULT_REC_BACKTEST_PATH = (
    PROJECT_DIR / "data" / "cache" / "probe_R25_R5_results.json"
)


def fetch_rec_performance(
    *,
    settled_path: Path = DEFAULT_REC_SETTLED_PATH,
    days: int = 7,
    backtest_path: Path = DEFAULT_REC_BACKTEST_PATH,
) -> Dict[str, Any]:
    """Aggregate the R24_Q4 rec_settled.parquet over the last `days` days.

    Always returns a dict — degrades gracefully when the parquet does not
    exist yet (first ~7 days after the tracker is wired live).

    R25_R5: when `backtest_path` exists, also surfaces the historical
    backtest ROI alongside the live ROI so the operator can compare.
    """
    out: Dict[str, Any] = {"ok": False, "days": int(days),
                            "reason": "", "by_stat": {}}
    if not settled_path.exists():
        out["reason"] = "no settled data yet (warm-up window)"
        # Even with no live data, surface the backtest if available so
        # the operator gets *something*.
        bt = _load_backtest_summary(backtest_path)
        if bt is not None:
            out["backtest"] = bt
        return out
    try:
        from scripts.live_rec_tracker import report  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"tracker import failed: {exc}"
        return out
    try:
        rpt = report(settled_path=str(settled_path), days=int(days))
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"report raised: {exc}"
        return out
    if not rpt.get("ok"):
        out["reason"] = rpt.get("reason", "report not ok")
        return out
    out.update(rpt)
    out["ok"] = True
    # R25_R5: attach backtest alongside live ROI for the operator.
    bt = _load_backtest_summary(backtest_path)
    if bt is not None:
        out["backtest"] = bt
    return out


def _load_backtest_summary(path: Path) -> Optional[Dict[str, Any]]:
    """Load the R25_R5 backtest summary if it exists. Never raises.

    Returns a small dict with the headline numbers + caveat string.
    """
    try:
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None
    return {
        "n_dates":          int(data.get("n_dates", 0)),
        "n_recs":           int(data.get("n_recs", 0)),
        "win_rate":         float(data.get("win_rate", 0.0)),
        "roi_pct":          float(data.get("roi_pct", 0.0)),
        "best_config":      data.get("best_config"),
        "n_viable_configs": int(data.get("n_viable_configs", 0)),
        "diagnostic":       str(data.get("diagnostic", "")),
        "generated_at":     str(data.get("generated_at", "")),
    }


def _backtest_row(bt: Optional[Dict[str, Any]]) -> str:
    """R25_R5 — render a one-line backtest summary inline with the live ROI."""
    if not bt:
        return ""
    best = bt.get("best_config") or {}
    best_str = (
        f"min_edge={best.get('min_edge')} top={best.get('top')}"
        if best else "—"
    )
    return (
        '<p class="muted">'
        f'Backtest (R25_R5): {bt.get("n_dates",0)} dates, '
        f'{bt.get("n_recs",0)} recs · '
        f'win-rate <b>{bt.get("win_rate",0)*100:.2f}%</b> · '
        f'<b>backtest_roi {bt.get("roi_pct",0):+.2f}%</b> · '
        f'best config <b>{_html_escape(best_str)}</b> · '
        f'{bt.get("n_viable_configs",0)} viable configs'
        '</p>'
        '<p class="muted" style="font-size:0.85em;">'
        f'<i>{_html_escape(bt.get("diagnostic",""))}</i>'
        '</p>'
    )


def _section_rec_perf(d: Dict[str, Any]) -> str:
    bt = d.get("backtest") if isinstance(d, dict) else None
    if not d.get("ok"):
        return (
            f'<h2>{REC_PERF_SECTION_TITLE}</h2>'
            f'<p class="muted">({_html_escape(d.get("reason","(no data)"))})</p>'
            + _backtest_row(bt)
        )
    if d.get("n", 0) == 0:
        return (
            f'<h2>{REC_PERF_SECTION_TITLE}</h2>'
            f'<p class="muted">(no recs settled in window)</p>'
            + _backtest_row(bt)
        )
    head = (
        f'<p>Last {int(d.get("days",7))}d: '
        f'<b>{d.get("wins",0)}W-{d.get("losses",0)}L-{d.get("pushes",0)}P</b> '
        f'· Win-rate <b>{float(d.get("win_rate",0))*100:.1f}%</b> '
        f'· ROI <b>{float(d.get("roi",0))*100:+.2f}%</b> '
        f'· Profit <b>{float(d.get("total_profit",0)):+.2f}u</b> '
        f'· Stake {float(d.get("total_stake",0)):.2f}u</p>'
    )
    edge_line = ""
    if d.get("mean_edge_win") is not None or d.get("mean_edge_loss") is not None:
        edge_line = (
            f'<p class="muted">Mean edge — winners: '
            f'{d.get("mean_edge_win")}  ·  losers: {d.get("mean_edge_loss")}</p>'
        )
    by_stat = d.get("by_stat") or {}
    if not by_stat:
        return (
            f'<h2>{REC_PERF_SECTION_TITLE}</h2>'
            + head + edge_line + _backtest_row(bt)
        )
    rows = []
    for stat, s in sorted(by_stat.items()):
        rows.append(
            f'<tr><td>{_html_escape(str(stat).upper())}</td>'
            f'<td>{s.get("n",0)}</td>'
            f'<td>{s.get("wins",0)}</td>'
            f'<td>{s.get("losses",0)}</td>'
            f'<td>{s.get("pushes",0)}</td>'
            f'<td>{float(s.get("win_rate",0))*100:.1f}%</td>'
            f'<td>{float(s.get("roi",0))*100:+.2f}%</td>'
            f'<td>{float(s.get("profit",0)):+.2f}u</td></tr>'
        )
    return (
        f'<h2>{REC_PERF_SECTION_TITLE}</h2>'
        + head + edge_line +
        '<table><thead><tr><th>Stat</th><th>N</th><th>W</th><th>L</th>'
        '<th>P</th><th>Win%</th><th>ROI%</th><th>Profit</th>'
        '</tr></thead><tbody>'
        + "".join(rows) +
        '</tbody></table>'
        + _backtest_row(bt)
    )


# --------------------------------------------------------------------------- #
# Section 9: Data Freshness (R30_W4)                                          #
# --------------------------------------------------------------------------- #
DEFAULT_DATA_DIR     = PROJECT_DIR / "data"
DEFAULT_CACHE_DIR    = PROJECT_DIR / "data" / "cache"
DEFAULT_LINEUPS_DIR  = PROJECT_DIR / "data" / "lineups"
DEFAULT_LINES_DIR    = PROJECT_DIR / "data" / "lines"
DEFAULT_BACKUPS_DIR  = PROJECT_DIR / "data" / "backups"
DEFAULT_VAULT_DIR    = PROJECT_DIR / "vault"


def _build_freshness_sources(
    *,
    cache_dir: Path,
    lineups_dir: Path,
    lines_dir: Path,
    backups_dir: Path,
    vault_dir: Path,
    today: str,
) -> List[Dict[str, Any]]:
    """Build the (name, path, threshold_sec, kind) tuples for the 13 sources."""
    HOUR = 3600
    MINUTE = 60
    DAY = 86400
    sources: List[Dict[str, Any]] = [
        {"name": "predictions_cache", "kind": "file",
         "path": cache_dir / f"predictions_cache_{today}.parquet",
         "threshold_sec": 12 * HOUR},
        {"name": "nba_injuries", "kind": "file",
         "path": cache_dir / f"nba_injuries_{today}.parquet",
         "threshold_sec": 1 * HOUR},
        {"name": "lineups", "kind": "file",
         "path": lineups_dir / f"{today}.json",
         "threshold_sec": 30 * MINUTE},
        {"name": "lines_fd", "kind": "file",
         "path": lines_dir / f"{today}_fd.csv",
         "threshold_sec": 60},
        {"name": "lines_bov", "kind": "file",
         "path": lines_dir / f"{today}_bov.csv",
         "threshold_sec": 60},
        {"name": "lines_pin", "kind": "file",
         "path": lines_dir / f"{today}_pin.csv",
         "threshold_sec": 60},
        {"name": "bankroll_state", "kind": "file",
         "path": cache_dir / "bankroll_state.json",
         "threshold_sec": 5 * MINUTE},
        {"name": "middles_live", "kind": "file",
         "path": cache_dir / "middles_live.json",
         "threshold_sec": 60},
        {"name": "m2_family_cache", "kind": "glob",
         "path": cache_dir, "glob": "m2_family_predictions_*.json",
         "threshold_sec": 12 * HOUR},
        {"name": "feature_drift", "kind": "file",
         "path": cache_dir / "feature_drift_latest.json",
         "threshold_sec": 24 * HOUR},
        {"name": "pnl_ledger_backup", "kind": "glob",
         "path": backups_dir, "glob": "pnl_ledger.csv.*.gz",
         "threshold_sec": 24 * HOUR},
        {"name": "morning_md", "kind": "file",
         "path": vault_dir / "MORNING.md",
         "threshold_sec": 24 * HOUR},
        {"name": "e2e_smoke", "kind": "glob",
         "path": cache_dir, "glob": "e2e_smoke_*.json",
         "threshold_sec": 24 * HOUR},
    ]
    return sources


def _resolve_freshness_source(
    src: Dict[str, Any], now_ts: float
) -> Dict[str, Any]:
    """For a single source spec, return {name, path, age_sec, status, exists, threshold_sec}."""
    name = src["name"]
    threshold = float(src["threshold_sec"])
    kind = src.get("kind", "file")
    path: Optional[Path] = None
    age_sec: Optional[float] = None
    exists = False

    try:
        if kind == "file":
            path = Path(src["path"])
            if path.exists() and path.is_file():
                exists = True
                age_sec = now_ts - path.stat().st_mtime
        elif kind == "glob":
            base = Path(src["path"])
            pattern = src.get("glob", "*")
            if base.exists() and base.is_dir():
                matches = list(base.glob(pattern))
                if matches:
                    # newest match wins
                    newest = max(matches, key=lambda p: p.stat().st_mtime)
                    path = newest
                    exists = True
                    age_sec = now_ts - newest.stat().st_mtime
                else:
                    path = base / pattern
            else:
                path = base / pattern
    except OSError:
        pass

    # Status classification — missing file is red. Fresh = green. Stale within
    # 2x threshold = yellow. Beyond 2x = red.
    if not exists or age_sec is None:
        status = "red"
    elif age_sec <= threshold:
        status = "green"
    elif age_sec <= threshold * 2.0:
        status = "yellow"
    else:
        status = "red"

    return {
        "name": name,
        "path": str(path) if path is not None else "",
        "age_sec": age_sec,
        "threshold_sec": threshold,
        "status": status,
        "exists": exists,
    }


def fetch_data_freshness(
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    lineups_dir: Path = DEFAULT_LINEUPS_DIR,
    lines_dir: Path = DEFAULT_LINES_DIR,
    backups_dir: Path = DEFAULT_BACKUPS_DIR,
    vault_dir: Path = DEFAULT_VAULT_DIR,
    today: Optional[str] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Inventory operator-critical data sources + classify freshness.

    Result schema:
        {
          "ok": bool,
          "n_total": int,
          "n_green": int,
          "n_yellow": int,
          "n_red": int,
          "sources": [
            {"name": str, "path": str, "age_sec": float|None,
             "threshold_sec": float, "status": "green"|"yellow"|"red",
             "exists": bool},
            ...
          ]
        }

    Always returns a dict — never raises — so a missing data dir cannot
    take the dashboard down.
    """
    out: Dict[str, Any] = {
        "ok": False, "n_total": 0, "n_green": 0, "n_yellow": 0,
        "n_red": 0, "sources": [],
    }
    today = today or _today_iso()
    now_ts = now if now is not None else time.time()

    try:
        specs = _build_freshness_sources(
            cache_dir=Path(cache_dir),
            lineups_dir=Path(lineups_dir),
            lines_dir=Path(lines_dir),
            backups_dir=Path(backups_dir),
            vault_dir=Path(vault_dir),
            today=today,
        )
    except Exception:  # noqa: BLE001
        return out

    for spec in specs:
        try:
            row = _resolve_freshness_source(spec, now_ts)
        except Exception:  # noqa: BLE001
            row = {
                "name": spec.get("name", "?"),
                "path": "",
                "age_sec": None,
                "threshold_sec": float(spec.get("threshold_sec", 0)),
                "status": "red",
                "exists": False,
            }
        out["sources"].append(row)
        out[f"n_{row['status']}"] += 1

    out["n_total"] = len(out["sources"])
    out["ok"] = out["n_total"] > 0
    return out


def _fmt_threshold(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def _section_data_freshness(d: Dict[str, Any]) -> str:
    if not d.get("ok"):
        return (f'<h2>{DATA_FRESHNESS_SECTION_TITLE}</h2>'
                '<p class="muted">(no data sources resolved)</p>')
    rows_html = []
    for r in d.get("sources", []):
        color = _STATUS_COLOR.get(r["status"], "#8b949e")
        age = _fmt_age(r["age_sec"])
        threshold = _fmt_threshold(r["threshold_sec"])
        exists = "yes" if r.get("exists") else "no"
        rows_html.append(
            f'<tr>'
            f'<td><span class="dot" style="background:{color}"></span>'
            f'{_html_escape(r["name"])}</td>'
            f'<td>{_html_escape(age)}</td>'
            f'<td>{_html_escape(threshold)}</td>'
            f'<td>{exists}</td>'
            f'<td>{_html_escape(r["status"].upper())}</td>'
            f'</tr>'
        )
    summary = (
        f'<span style="color:{_STATUS_COLOR["green"]}">{d["n_green"]} green</span> · '
        f'<span style="color:{_STATUS_COLOR["yellow"]}">{d["n_yellow"]} yellow</span> · '
        f'<span style="color:{_STATUS_COLOR["red"]}">{d["n_red"]} red</span> '
        f'<span class="muted">of {d["n_total"]} sources</span>'
    )
    return (
        f'<h2>{DATA_FRESHNESS_SECTION_TITLE}</h2>'
        f'<p>{summary}</p>'
        '<table><thead><tr><th>Source</th><th>Age</th><th>Threshold</th>'
        '<th>Exists</th><th>Status</th></tr></thead><tbody>'
        + "".join(rows_html) +
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


# --------------------------------------------------------------------------- #
# Section 11: "Multi5 vs MLP Mode Compare" (R32_Y6)                            #
# --------------------------------------------------------------------------- #
ENGINE_MODE_COMPARE_TITLE = "Multi5 vs MLP Mode Compare"


def fetch_engine_mode_compare(
    *,
    bankroll: float = 1000.0,
    top: int = 5,
    today: Optional[str] = None,
    min_edge: float = 0.05,
    top_overlap_k: Tuple[int, ...] = (5, 10, 20),
) -> Dict[str, Any]:
    """Call the R32_Y6 mode-compare helper for today's recs.

    Always returns a dict — defensive even when the engine, predictions
    cache, or comparison helper raises, so a broken downstream never takes
    the dashboard down.
    """
    out: Dict[str, Any] = {
        "ok":            False,
        "date":          today or _today_iso(),
        "reason":        "",
        "top_multi5":    [],
        "top_mlp":       [],
        "overlap":       {},
        "n_recs_multi5": 0,
        "n_recs_mlp":    0,
        "operator_would_change_bets": False,
    }
    try:
        # Local import — keeps the dashboard cold-start light when the
        # compare helper is unavailable (e.g. fresh clone w/o scripts).
        from scripts.compare_engine_modes import compare_modes  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"compare import failed: {exc}"
        return out
    try:
        payload = compare_modes(
            bankroll=float(bankroll),
            top=int(top),
            date=out["date"],
            min_edge=float(min_edge),
            top_overlap_k=tuple(int(k) for k in top_overlap_k),
        )
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"compare raised: {exc}"
        return out
    out["ok"] = True
    out["top_multi5"] = payload.get("top_multi5", []) or []
    out["top_mlp"]    = payload.get("top_mlp", []) or []
    out["overlap"]    = payload.get("overlap", {}) or {}
    out["shared_bets"] = payload.get("shared_bets", {}) or {}
    out["only_in_multi5"] = payload.get("only_in_multi5", []) or []
    out["only_in_mlp"]    = payload.get("only_in_mlp", []) or []
    out["n_recs_multi5"] = (payload.get("multi5", {}) or {}).get("n_recs", 0) or 0
    out["n_recs_mlp"]    = (payload.get("mlp", {}) or {}).get("n_recs", 0) or 0
    out["operator_would_change_bets"] = bool(
        payload.get("operator_would_change_bets", False)
    )
    return out


def _section_engine_mode_compare(d: Dict[str, Any]) -> str:
    if not d.get("ok"):
        return (
            f'<h2>{ENGINE_MODE_COMPARE_TITLE}</h2>'
            f'<p class="muted">(compare unavailable: '
            f'{_html_escape(d.get("reason",""))})</p>'
        )
    recs_a = d.get("top_multi5", []) or []
    recs_b = d.get("top_mlp", []) or []
    overlap = d.get("overlap", {}) or {}

    # Build the side-by-side top-5 table. Render up to 5 rows even if one
    # side is shorter — empty cells where no rec exists.
    n_rows = max(len(recs_a[:5]), len(recs_b[:5]), 1)
    side_rows = []
    for i in range(n_rows):
        a = recs_a[i] if i < len(recs_a) else None
        b = recs_b[i] if i < len(recs_b) else None
        def _cell(rec):
            if rec is None:
                return '<td colspan="4" class="muted">—</td>'
            return (
                f'<td>{_html_escape(rec.get("player",""))}</td>'
                f'<td>{_html_escape(str(rec.get("stat","")).upper())}</td>'
                f'<td>{_html_escape(rec.get("side",""))}</td>'
                f'<td>{float(rec.get("edge_pct",0)):+.2f}%</td>'
            )
        side_rows.append(f'<tr><td>{i+1}</td>{_cell(a)}{_cell(b)}</tr>')

    # Jaccard ribbon
    ribbon_parts = []
    for k_label, bucket in overlap.items():
        ribbon_parts.append(
            f'{_html_escape(k_label)}: J={float(bucket.get("jaccard",0)):.2f} '
            f'({int(bucket.get("overlap",0))} shared)'
        )
    ribbon = " · ".join(ribbon_parts) if ribbon_parts else "(no overlap data)"

    changed_flag = (
        "YES" if d.get("operator_would_change_bets") else "no"
    )
    n_added = len(d.get("only_in_mlp", []) or [])
    n_dropped = len(d.get("only_in_multi5", []) or [])
    shared = d.get("shared_bets", {}) or {}
    return (
        f'<h2>{ENGINE_MODE_COMPARE_TITLE}</h2>'
        f'<p>multi5 n_recs={int(d.get("n_recs_multi5",0))} · '
        f'MLP n_recs={int(d.get("n_recs_mlp",0))} · '
        f'operator would change bets: <strong>{changed_flag}</strong> '
        f'(added={n_added} · dropped={n_dropped} · shared={int(shared.get("n_shared",0))})</p>'
        f'<p class="muted">{ribbon}</p>'
        '<table><thead><tr><th>#</th>'
        '<th colspan="4">multi5 (M2_FAMILY_USE_MLP=0)</th>'
        '<th colspan="4">MLP (M2_FAMILY_USE_MLP=1)</th></tr>'
        '<tr><th></th>'
        '<th>Player</th><th>Stat</th><th>Side</th><th>Edge</th>'
        '<th>Player</th><th>Stat</th><th>Side</th><th>Edge</th></tr></thead>'
        '<tbody>' + "".join(side_rows) + '</tbody></table>'
    )


def render_operator_html(
    health: Dict[str, Any],
    bankroll: Dict[str, Any],
    alerts: Dict[str, Any],
    bets: Dict[str, Any],
    slate: Dict[str, Any],
    tracker: Dict[str, Any],
    live_recs: Optional[Dict[str, Any]] = None,    # R23_P8
    rec_perf: Optional[Dict[str, Any]] = None,     # R24_Q4
    settlement: Optional[Dict[str, Any]] = None,   # R24_Q8
    drift: Optional[Dict[str, Any]] = None,        # R27_T3
    data_freshness: Optional[Dict[str, Any]] = None,  # R30_W4
    engine_mode_compare: Optional[Dict[str, Any]] = None,  # R32_Y6
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
    if data_freshness is not None:
        body += _section_data_freshness(data_freshness)
    if drift is not None:
        body += _section_feature_drift(drift)
    if settlement is not None:
        body += _section_settlement_health(settlement)
    if live_recs is not None:
        body += _section_live_recs(live_recs)
    if rec_perf is not None:
        body += _section_rec_perf(rec_perf)
    if engine_mode_compare is not None:
        body += _section_engine_mode_compare(engine_mode_compare)
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
    include_rec_perf: bool = True,            # R24_Q4
    rec_perf_settled_path: Optional[Path] = None,
    rec_perf_days: int = 7,
    include_settlement_health: bool = True,   # R24_Q8
    settlement_window_days: int = 7,
    qb_dir: Path = DEFAULT_QB_DIR_PATH,
    include_feature_drift: bool = True,       # R27_T3
    drift_cache_path: Path = DEFAULT_DRIFT_CACHE,
    include_data_freshness: bool = True,      # R30_W4
    freshness_cache_dir: Optional[Path] = None,
    freshness_lineups_dir: Optional[Path] = None,
    freshness_lines_dir: Optional[Path] = None,
    freshness_backups_dir: Optional[Path] = None,
    freshness_vault_dir: Optional[Path] = None,
    include_engine_mode_compare: bool = True,  # R32_Y6
    engine_mode_compare_bankroll: float = 1000.0,
    engine_mode_compare_top: int = 5,
    engine_mode_compare_min_edge: float = 0.05,
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

    rec_perf = None
    if include_rec_perf:
        rec_perf = _safe(
            fetch_rec_performance,
            settled_path=rec_perf_settled_path or DEFAULT_REC_SETTLED_PATH,
            days=int(rec_perf_days),
        )
        rec_perf.setdefault("ok", False)

    settlement = None
    if include_settlement_health:
        settlement = _safe(
            fetch_settlement_health,
            ledger_path=ledger_path, qb_dir=qb_dir,
            days=settlement_window_days,
        )
        settlement.setdefault("ok", False)

    drift = None
    if include_feature_drift:
        drift = _safe(fetch_feature_drift, cache_path=drift_cache_path)
        drift.setdefault("ok", False)

    data_freshness = None
    if include_data_freshness:
        data_freshness = _safe(
            fetch_data_freshness,
            cache_dir=freshness_cache_dir or DEFAULT_CACHE_DIR,
            lineups_dir=freshness_lineups_dir or DEFAULT_LINEUPS_DIR,
            lines_dir=freshness_lines_dir or DEFAULT_LINES_DIR,
            backups_dir=freshness_backups_dir or DEFAULT_BACKUPS_DIR,
            vault_dir=freshness_vault_dir or DEFAULT_VAULT_DIR,
            today=today,
        )
        data_freshness.setdefault("ok", False)

    engine_mode_compare = None
    if include_engine_mode_compare:
        engine_mode_compare = _safe(
            fetch_engine_mode_compare,
            bankroll=engine_mode_compare_bankroll,
            top=int(engine_mode_compare_top),
            today=today,
            min_edge=float(engine_mode_compare_min_edge),
        )
        engine_mode_compare.setdefault("ok", False)

    # Defensive defaults so render never KeyErrors on a partial-result.
    for d in (health, bankroll, alerts, bets, slate, tracker):
        d.setdefault("ok", False)

    return render_operator_html(
        health, bankroll, alerts, bets, slate, tracker,
        live_recs, rec_perf, settlement, drift, data_freshness,
        engine_mode_compare,
        auto_refresh_sec=auto_refresh_sec,
    )
