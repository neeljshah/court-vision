"""generate_morning_brief.py — R28_U5 one-page operator morning brief.

Auto-generates ``vault/MORNING.md`` — a single markdown page the operator
opens with morning coffee to see the entire betting-system state in 60
seconds. The brief is composed of 8 short sections, each backed by an
already-existing data source (most produced by earlier R-series probes):

  1. Header             — date, master commit SHA (first 8), uptime
  2. Bankroll           — start / current / today P&L / ROI (R19_L8)
  3. Yesterday's recs   — n_settled, win_rate, ROI, top winner/loser
  4. Today's recs       — top 5 from live_recommendation_engine (R23_P8)
  5. System health      — daemon green/yellow/red counts (R19_L3)
  6. Recent alerts      — last 5 critical/warn (R21_N3)
  7. Drift status       — n_major + top 3 most-drifted features (R27_T3)
  8. Backup + smoke     — last backup age + sha8 + last e2e smoke result

Hard rules
----------
* Pure-read aside from the single atomic write to the output path.
* Every section degrades gracefully: a missing data source renders
  the literal string ``(no data)`` and the brief keeps going.
* Atomic write: stage to ``<out>.tmp`` then ``os.replace``. The previous
  brief (if any) is rotated to ``<out>.bak`` before the new file
  replaces it.
* Idempotent: same data on disk -> byte-identical output (no clock-
  derived strings inside the rendered body — the timestamp in the
  header comes from ``--now`` for tests; production uses datetime.now).

CLI
---
    python scripts/generate_morning_brief.py
    python scripts/generate_morning_brief.py --date 2026-05-27
    python scripts/generate_morning_brief.py --out vault/MORNING.md
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import date as _date_cls
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

# ---- Default paths (every one overridable from the renderer signature). ----
DEFAULT_OUT_PATH = PROJECT_DIR / "vault" / "MORNING.md"

DEFAULT_BANKROLL_PATH    = PROJECT_DIR / "data" / "cache" / "bankroll_state.json"
DEFAULT_REC_TRACKER_DIR  = PROJECT_DIR / "data" / "cache" / "rec_tracker"
DEFAULT_SETTLED_PATH     = DEFAULT_REC_TRACKER_DIR / "rec_settled.parquet"
DEFAULT_REGISTRY_PATH    = PROJECT_DIR / "scripts" / "daemon_registry.json"
DEFAULT_HEARTBEAT_DIR    = PROJECT_DIR / "data" / "cache" / "daemon_heartbeats"
DEFAULT_ALERTS_VAULT     = PROJECT_DIR / "vault" / "Improvements" / "alerts.md"
DEFAULT_ALERTS_DIR       = PROJECT_DIR / "data" / "cache" / "alerts"
DEFAULT_DRIFT_CACHE      = PROJECT_DIR / "data" / "cache" / "feature_drift_latest.json"
DEFAULT_BACKUP_DIR       = PROJECT_DIR / "data" / "backups"
DEFAULT_SMOKE_DIR        = PROJECT_DIR / "data" / "cache"

SECTION_NAMES: Tuple[str, ...] = (
    "Header", "Bankroll", "Yesterday", "Today",
    "Health", "Alerts", "Drift", "Backup",
)
N_SECTIONS = len(SECTION_NAMES)  # 8


# ============================================================================ #
# Safe loaders                                                                  #
# ============================================================================ #
def _safe_load_json(path: Path) -> Optional[Any]:
    try:
        if not Path(path).exists():
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def _safe_read_text(path: Path) -> Optional[str]:
    try:
        if not Path(path).exists():
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception:  # noqa: BLE001
        return None


def _today_iso() -> str:
    return _date_cls.today().isoformat()


def _yesterday_iso(today: Optional[str] = None) -> str:
    if today:
        try:
            d = datetime.fromisoformat(today).date()
        except ValueError:
            d = _date_cls.today()
    else:
        d = _date_cls.today()
    return (d - timedelta(days=1)).isoformat()


def _fmt_age_seconds(sec: Optional[float]) -> str:
    if sec is None:
        return "n/a"
    s = int(sec)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        h = s // 3600
        m = (s % 3600) // 60
        return f"{h}h{m}m"
    d = s // 86400
    h = (s % 86400) // 3600
    return f"{d}d{h}h"


# ============================================================================ #
# Section 1 — Header                                                           #
# ============================================================================ #
def fetch_header(
    *,
    project_dir: Path = PROJECT_DIR,
    today: Optional[str] = None,
) -> Dict[str, Any]:
    """Date + master SHA (first 8) + uptime fields."""
    today = today or _today_iso()
    sha: Optional[str] = None
    try:
        sha_out = subprocess.run(
            ["git", "-C", str(project_dir), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=4,
        )
        if sha_out.returncode == 0:
            sha = (sha_out.stdout or "").strip()[:8] or None
    except Exception:  # noqa: BLE001
        sha = None
    return {"ok": True, "date": today, "commit_sha8": sha}


# ============================================================================ #
# Section 2 — Bankroll                                                         #
# ============================================================================ #
def fetch_bankroll(
    *,
    bankroll_path: Path = DEFAULT_BANKROLL_PATH,
) -> Dict[str, Any]:
    state = _safe_load_json(Path(bankroll_path))
    if not state:
        return {"ok": False}
    roi = state.get("roi") or {}
    return {
        "ok":                True,
        "start_bankroll":    state.get("start_bankroll"),
        "current_bankroll":  state.get("current_bankroll"),
        "available_bankroll": state.get("available_bankroll"),
        "today_pnl":         state.get("daily_pnl"),
        "roi_pct":           roi.get("roi_pct"),
        "n_bets":            roi.get("n_bets"),
        "as_of":             state.get("as_of"),
    }


# ============================================================================ #
# Section 3 — Yesterday's recs                                                  #
# ============================================================================ #
def fetch_yesterday_recs(
    *,
    settled_path: Path = DEFAULT_SETTLED_PATH,
    yesterday: Optional[str] = None,
) -> Dict[str, Any]:
    """Yesterday's settled rec roll-up: n / win_rate / ROI / top winner+loser."""
    yesterday = yesterday or _yesterday_iso()
    settled_path = Path(settled_path)
    if not settled_path.exists():
        return {"ok": False, "date": yesterday}
    try:
        import pandas as pd  # noqa: PLC0415 — heavy, only when present
    except Exception:  # noqa: BLE001
        return {"ok": False, "date": yesterday, "reason": "pandas missing"}
    try:
        df = pd.read_parquet(settled_path)
    except Exception:  # noqa: BLE001
        return {"ok": False, "date": yesterday, "reason": "read failed"}
    if df is None or df.empty or "date" not in df.columns:
        return {"ok": True, "date": yesterday, "n_settled": 0}
    df = df[df["date"].astype(str) == str(yesterday)]
    if df.empty:
        return {"ok": True, "date": yesterday, "n_settled": 0}
    graded = df[df.get("result", "").isin(["WIN", "LOSS", "PUSH"])]
    non_push = graded[graded["result"].isin(["WIN", "LOSS"])]
    wins = int((graded["result"] == "WIN").sum())
    losses = int((graded["result"] == "LOSS").sum())
    pushes = int((graded["result"] == "PUSH").sum())
    win_rate = (wins / len(non_push)) if len(non_push) > 0 else 0.0
    total_stake = float(non_push["stake_unit"].sum()) if "stake_unit" in non_push.columns and not non_push.empty else 0.0
    total_profit = float(graded["profit"].sum()) if "profit" in graded.columns and not graded.empty else 0.0
    roi = (total_profit / total_stake) if total_stake > 0 else 0.0
    # Top winner / loser by profit.
    top_winner: Optional[Dict[str, Any]] = None
    top_loser: Optional[Dict[str, Any]] = None
    if "profit" in graded.columns and not graded.empty:
        try:
            ix_w = graded["profit"].idxmax()
            ix_l = graded["profit"].idxmin()
            for ix, slot in ((ix_w, "win"), (ix_l, "loss")):
                row = graded.loc[ix]
                d = {
                    "player": str(row.get("player", "")),
                    "stat":   str(row.get("stat", "")).upper(),
                    "line":   float(row.get("line", 0.0) or 0.0),
                    "side":   str(row.get("side", "")).upper(),
                    "profit": float(row.get("profit", 0.0) or 0.0),
                    "result": str(row.get("result", "")),
                }
                if slot == "win":
                    top_winner = d
                else:
                    top_loser = d
        except Exception:  # noqa: BLE001
            pass
    return {
        "ok":           True,
        "date":         yesterday,
        "n_settled":    int(len(graded)),
        "wins":         wins,
        "losses":       losses,
        "pushes":       pushes,
        "win_rate":     round(win_rate, 4),
        "roi":          round(roi, 4),
        "total_stake":  round(total_stake, 2),
        "total_profit": round(total_profit, 2),
        "top_winner":   top_winner,
        "top_loser":    top_loser,
    }


# ============================================================================ #
# Section 4 — Today's recs                                                      #
# ============================================================================ #
def fetch_today_recs(
    *,
    today: Optional[str] = None,
    top: int = 5,
    engine_fn: Optional[Any] = None,
    bankroll: float = 1000.0,
) -> Dict[str, Any]:
    """Top live recs from R23_P8 live_recommendation_engine.

    A test seam (``engine_fn``) lets tests skip the import + heavy parquet
    load. Returns ok=False if either the engine import fails or the engine
    payload reports no recommendations.
    """
    today = today or _today_iso()
    fn = engine_fn
    if fn is None:
        try:
            from scripts.live_recommendation_engine import run_engine as fn  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            return {"ok": False, "date": today, "reason": "import failed"}
    try:
        payload = fn(
            bankroll=float(bankroll),
            top=int(top),
            date=today,
            min_edge=0.05,
        ) or {}
    except Exception:  # noqa: BLE001
        return {"ok": False, "date": today, "reason": "engine raised"}
    recs = (payload.get("recommendations") or [])[:top]
    return {
        "ok":          True,
        "date":        today,
        "n_recs":      int(payload.get("n_recs", len(recs)) or len(recs)),
        "n_evaluated": int(payload.get("n_evaluated", 0) or 0),
        "reason":      payload.get("reason", ""),
        "top":         recs,
    }


# ============================================================================ #
# Section 5 — System health                                                    #
# ============================================================================ #
def fetch_system_health(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    heartbeat_dir: Path = DEFAULT_HEARTBEAT_DIR,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Reuses the operator_dashboard helper when present; otherwise inlines
    the same green/yellow/red ladder so the brief is self-contained."""
    out: Dict[str, Any] = {
        "ok": False, "n_total": 0, "n_green": 0, "n_yellow": 0, "n_red": 0,
        "yellow_names": [], "red_names": [],
    }
    blob = _safe_load_json(Path(registry_path))
    if not blob or "daemons" not in blob:
        return out
    daemons = blob.get("daemons") or []
    if not isinstance(daemons, list):
        return out
    now_ts = now if now is not None else time.time()
    rows: List[Dict[str, Any]] = []
    for d in daemons:
        if not isinstance(d, dict):
            continue
        name = d.get("name") or "(unnamed)"
        expected = float(d.get("expected_interval_sec", 60) or 60)
        hb_rel = d.get("heartbeat_file") or ""
        hb_optional = bool(d.get("heartbeat_optional", False))
        if hb_rel:
            candidate = Path(hb_rel)
            if not candidate.is_absolute():
                candidate = PROJECT_DIR / hb_rel
            hb_path = candidate
        else:
            hb_path = Path(heartbeat_dir) / f"{name}.txt"
        age: Optional[float] = None
        if hb_path.exists():
            try:
                age = now_ts - hb_path.stat().st_mtime
            except OSError:
                age = None
        if age is None:
            status = "yellow" if hb_optional else "red"
        elif age <= expected * 1.5:
            status = "green"
        elif age <= expected * 3.0:
            status = "yellow"
        else:
            status = "red"
        rows.append({"name": name, "status": status, "age_sec": age})
    out["n_total"] = len(rows)
    out["n_green"] = sum(1 for r in rows if r["status"] == "green")
    out["n_yellow"] = sum(1 for r in rows if r["status"] == "yellow")
    out["n_red"] = sum(1 for r in rows if r["status"] == "red")
    out["yellow_names"] = [r["name"] for r in rows if r["status"] == "yellow"]
    out["red_names"] = [r["name"] for r in rows if r["status"] == "red"]
    out["ok"] = out["n_total"] > 0
    return out


# ============================================================================ #
# Section 6 — Recent alerts                                                    #
# ============================================================================ #
_VAULT_LINE_RE = re.compile(
    r"^-?\s*\*?\*?(?P<ts>\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}Z?)\*?\*?\s*"
    r"\[(?P<level>CRITICAL|WARN|INFO|critical|warn|info)\]\s*"
    r"(?:\[(?P<tag>[^\]]+)\])?\s*(?P<msg>.+)$",
    re.IGNORECASE,
)


def _parse_vault_alerts(text: str) -> List[Dict[str, Any]]:
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
            "level":     (m.group("level") or "info").lower(),
            "tag":       m.group("tag") or "",
            "message":   m.group("msg").strip(),
        })
    return rows


def fetch_recent_alerts(
    *,
    vault_path: Path = DEFAULT_ALERTS_VAULT,
    alerts_dir: Path = DEFAULT_ALERTS_DIR,
    window_hours: int = 24,
    now: Optional[datetime] = None,
    limit: int = 5,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "ok": False, "window_hours": window_hours,
        "counts": {"critical": 0, "warn": 0, "info": 0},
        "latest": [],
    }
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)
    rows: List[Dict[str, Any]] = []

    txt = _safe_read_text(Path(vault_path))
    if txt:
        rows.extend(_parse_vault_alerts(txt))

    adir = Path(alerts_dir)
    if adir.exists() and adir.is_dir():
        for f in sorted(adir.glob("critical_*.json")):
            blob = _safe_load_json(f)
            if not isinstance(blob, list):
                continue
            for r in blob:
                if not isinstance(r, dict):
                    continue
                rows.append({
                    "timestamp": r.get("timestamp") or r.get("ts") or "",
                    "level":     str(r.get("level") or "critical").lower(),
                    "tag":       r.get("tag") or r.get("source") or "",
                    "message":   r.get("message") or r.get("msg") or "",
                })

    if not rows:
        return out

    def _parse_ts(s: str) -> Optional[datetime]:
        if not s:
            return None
        s2 = s.replace(" ", "T")
        if s2.endswith("Z"):
            s2 = s2[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s2)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None

    keepable: List[Tuple[datetime, Dict[str, Any]]] = []
    for r in rows:
        dt = _parse_ts(r.get("timestamp", ""))
        # Keep rows even with un-parsable timestamps so a fresh clone
        # with only synthetic alert files isn't completely empty.
        eff_dt = dt if dt is not None else datetime.min.replace(tzinfo=timezone.utc)
        if dt is None or dt >= cutoff:
            keepable.append((eff_dt, r))
    keepable.sort(key=lambda t: t[0], reverse=True)
    counts = {"critical": 0, "warn": 0, "info": 0}
    for _, r in keepable:
        lvl = r["level"] if r["level"] in counts else "info"
        counts[lvl] += 1
    latest = []
    for _, r in keepable[:limit]:
        msg = (r["message"] or "").splitlines()[0] if r["message"] else ""
        latest.append({
            "timestamp": r["timestamp"],
            "level":     r["level"],
            "tag":       r["tag"],
            "message":   msg,
        })
    out["ok"] = True
    out["counts"] = counts
    out["latest"] = latest
    return out


# ============================================================================ #
# Section 7 — Drift status                                                     #
# ============================================================================ #
def fetch_drift(
    *,
    cache_path: Path = DEFAULT_DRIFT_CACHE,
    top_k: int = 3,
) -> Dict[str, Any]:
    blob = _safe_load_json(Path(cache_path))
    if not blob:
        return {"ok": False}
    feats = list(blob.get("features") or [])
    # The cache already sorts most-drifted first when produced by
    # scripts/feature_drift_detector — but resort defensively by |mean_z|.
    def _key(r: Dict[str, Any]) -> float:
        try:
            v = r.get("mean_z")
            if v is None or v != v:  # NaN guard
                return 0.0
            return abs(float(v))
        except Exception:  # noqa: BLE001
            return 0.0
    feats_sorted = sorted(
        [f for f in feats if isinstance(f, dict) and f.get("class") == "drift_major"],
        key=_key, reverse=True,
    )
    top = [
        {
            "feature":  str(f.get("feature", "")),
            "mean_z":   (None if (f.get("mean_z") is None or f.get("mean_z") != f.get("mean_z"))
                         else round(float(f.get("mean_z")), 3)),
            "ks_stat":  round(float(f.get("ks_stat", 0.0) or 0.0), 3),
        }
        for f in feats_sorted[:top_k]
    ]
    return {
        "ok":            True,
        "feature_set":   blob.get("feature_set", ""),
        "status":        blob.get("status", ""),
        "n_major":       int(blob.get("n_drift_major", 0) or 0),
        "n_minor":       int(blob.get("n_drift_minor", 0) or 0),
        "n_stable":      int(blob.get("n_stable", 0) or 0),
        "n_analyzed":    int(blob.get("n_features_analyzed", 0) or 0),
        "ts":            blob.get("ts", ""),
        "top_drifted":   top,
    }


# ============================================================================ #
# Section 8 — Backup status + smoke status                                     #
# ============================================================================ #
def fetch_backup(
    *,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    bdir = Path(backup_dir)
    if not bdir.exists() or not bdir.is_dir():
        return {"ok": False}
    entries: List[Tuple[float, Path]] = []
    for p in bdir.glob("*.gz"):
        try:
            entries.append((p.stat().st_mtime, p))
        except OSError:
            continue
    if not entries:
        return {"ok": False}
    entries.sort(key=lambda t: t[0], reverse=True)
    mtime, newest = entries[0]
    sidecar = newest.with_suffix(newest.suffix + ".sha256")
    sha8 = None
    if sidecar.exists():
        try:
            with open(sidecar, "r", encoding="utf-8") as fh:
                txt = (fh.read() or "").strip().split()
                if txt:
                    sha8 = txt[0][:8]
        except Exception:  # noqa: BLE001
            sha8 = None
    if sha8 is None:
        # Compute lazily from the gz payload if the sidecar is missing.
        try:
            h = hashlib.sha256()
            with open(newest, "rb") as fh:
                for chunk in iter(lambda: fh.read(8192), b""):
                    h.update(chunk)
            sha8 = h.hexdigest()[:8]
        except Exception:  # noqa: BLE001
            sha8 = None
    now_ts = now if now is not None else time.time()
    age = now_ts - mtime
    return {
        "ok":          True,
        "name":        newest.name,
        "size_bytes":  int(newest.stat().st_size),
        "age_seconds": float(age),
        "age_human":   _fmt_age_seconds(age),
        "sha256_8":    sha8,
        "n_total":     len(entries),
    }


def fetch_smoke(
    *,
    smoke_dir: Path = DEFAULT_SMOKE_DIR,
    today: Optional[str] = None,
) -> Dict[str, Any]:
    sdir = Path(smoke_dir)
    if not sdir.exists():
        return {"ok": False}
    # Prefer today's file if present, else newest e2e_smoke_*.json by mtime.
    today = today or _today_iso()
    target: Optional[Path] = None
    todays = sdir / f"e2e_smoke_{today}.json"
    if todays.exists():
        target = todays
    else:
        cands = []
        for p in sdir.glob("e2e_smoke_*.json"):
            try:
                cands.append((p.stat().st_mtime, p))
            except OSError:
                continue
        if cands:
            cands.sort(key=lambda t: t[0], reverse=True)
            target = cands[0][1]
    if target is None:
        return {"ok": False}
    blob = _safe_load_json(target)
    if not isinstance(blob, dict):
        return {"ok": False}
    return {
        "ok":             True,
        "path":           str(target),
        "status":         str(blob.get("status", "")),
        "n_stages":       int(blob.get("n_stages", 0) or 0),
        "n_passed":       int(blob.get("n_passed", 0) or 0),
        "n_failed":       int(blob.get("n_failed", 0) or 0),
        "failed_stages":  list(blob.get("failed_stage_names", []) or []),
        "runtime_sec":    float(blob.get("runtime_sec", 0.0) or 0.0),
        "ts":             str(blob.get("ts", "")),
    }


# ============================================================================ #
# Rendering                                                                    #
# ============================================================================ #
def _fmt_money(v: Optional[float]) -> str:
    if v is None:
        return "(no data)"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "(no data)"
    sign = "-" if f < 0 else ""
    return f"{sign}${abs(f):,.2f}"


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "(no data)"
    try:
        return f"{float(v)*100:+.2f}%"
    except (TypeError, ValueError):
        return "(no data)"


def _render_header(d: Dict[str, Any]) -> str:
    sha = d.get("commit_sha8") or "(no data)"
    return (
        "# Morning Brief\n\n"
        f"- Date: **{d.get('date','')}**\n"
        f"- Master SHA: `{sha}`\n"
    )


def _render_bankroll(d: Dict[str, Any]) -> str:
    if not d.get("ok"):
        return "## Bankroll\n\n(no data)\n"
    lines = [
        "## Bankroll",
        "",
        f"- Start: {_fmt_money(d.get('start_bankroll'))}",
        f"- Current: **{_fmt_money(d.get('current_bankroll'))}**",
        f"- Available: {_fmt_money(d.get('available_bankroll'))}",
        f"- Today PnL: {_fmt_money(d.get('today_pnl'))}",
        f"- ROI: {_fmt_pct(d.get('roi_pct') if d.get('roi_pct') is None else float(d.get('roi_pct'))/100.0)}  (n_bets={d.get('n_bets') if d.get('n_bets') is not None else 'n/a'})",
        "",
    ]
    return "\n".join(lines)


def _render_yesterday(d: Dict[str, Any]) -> str:
    head = "## Yesterday's Recs"
    if not d.get("ok"):
        return f"{head}\n\n(no data)\n"
    if int(d.get("n_settled", 0) or 0) == 0:
        return f"{head}\n\n- Date: {d.get('date','')}\n- (no settled recs)\n"
    lines = [
        head, "",
        f"- Date: {d.get('date','')}",
        f"- Settled: {d.get('n_settled')}  (W={d.get('wins')} L={d.get('losses')} P={d.get('pushes')})",
        f"- Win rate: {float(d.get('win_rate',0.0))*100:.1f}%",
        f"- ROI: {float(d.get('roi',0.0))*100:+.2f}%  (stake={_fmt_money(d.get('total_stake'))} profit={_fmt_money(d.get('total_profit'))})",
    ]
    tw = d.get("top_winner")
    tl = d.get("top_loser")
    if tw:
        lines.append(
            f"- Top winner: {tw.get('player','?')} {tw.get('stat','')} "
            f"{tw.get('side','')} {tw.get('line','?')} -> {_fmt_money(tw.get('profit'))}"
        )
    if tl:
        lines.append(
            f"- Top loser: {tl.get('player','?')} {tl.get('stat','')} "
            f"{tl.get('side','')} {tl.get('line','?')} -> {_fmt_money(tl.get('profit'))}"
        )
    lines.append("")
    return "\n".join(lines)


def _render_today(d: Dict[str, Any]) -> str:
    head = "## Today's Top Recs"
    if not d.get("ok"):
        return f"{head}\n\n(no data)\n"
    recs = d.get("top") or []
    if not recs:
        return f"{head}\n\n- Date: {d.get('date','')}\n- (no positive-edge recs)\n- Reason: {d.get('reason','')}\n"
    lines = [head, "", f"- Date: {d.get('date','')}  (evaluated={d.get('n_evaluated',0)} kept={d.get('n_recs',0)})", ""]
    lines.append("| # | Player | Stat | Side | Line | Book | Edge | Stake |")
    lines.append("|---|--------|------|------|------|------|------|-------|")
    for i, r in enumerate(recs, 1):
        edge = r.get("edge")
        edge_str = f"{float(edge)*100:+.2f}%" if isinstance(edge, (int, float)) else "?"
        stake = r.get("stake_dollars")
        stake_str = _fmt_money(stake) if stake is not None else "?"
        lines.append(
            f"| {i} | {r.get('player','?')} | {str(r.get('stat','')).upper()} "
            f"| {str(r.get('side','')).upper()} | {r.get('line','?')} "
            f"| {r.get('book','?')} | {edge_str} | {stake_str} |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_health(d: Dict[str, Any]) -> str:
    head = "## System Health"
    if not d.get("ok"):
        return f"{head}\n\n(no data)\n"
    lines = [
        head, "",
        f"- Daemons: {d.get('n_total',0)} total  green={d.get('n_green',0)} yellow={d.get('n_yellow',0)} red={d.get('n_red',0)}",
    ]
    if d.get("yellow_names"):
        lines.append(f"- Yellow: {', '.join(d['yellow_names'])}")
    if d.get("red_names"):
        lines.append(f"- Red: {', '.join(d['red_names'])}")
    lines.append("")
    return "\n".join(lines)


def _render_alerts(d: Dict[str, Any]) -> str:
    head = "## Recent Alerts (24h)"
    if not d.get("ok"):
        return f"{head}\n\n(no data)\n"
    counts = d.get("counts") or {}
    lines = [
        head, "",
        f"- Counts: critical={counts.get('critical',0)} warn={counts.get('warn',0)} info={counts.get('info',0)}",
    ]
    for a in d.get("latest", []):
        lvl = (a.get("level") or "info").upper()
        ts = a.get("timestamp") or ""
        tag = a.get("tag") or ""
        msg = (a.get("message") or "").strip()
        if len(msg) > 100:
            msg = msg[:97] + "..."
        lines.append(f"- [{lvl}] {ts} [{tag}] {msg}")
    lines.append("")
    return "\n".join(lines)


def _render_drift(d: Dict[str, Any]) -> str:
    head = "## Feature Drift"
    if not d.get("ok"):
        return f"{head}\n\n(no data)\n"
    lines = [
        head, "",
        f"- Feature set: {d.get('feature_set','?')}  status={d.get('status','?')}",
        f"- Analyzed: {d.get('n_analyzed',0)}  major={d.get('n_major',0)} minor={d.get('n_minor',0)} stable={d.get('n_stable',0)}",
    ]
    top = d.get("top_drifted") or []
    if top:
        lines.append("- Top drifted:")
        for r in top:
            mz = r.get("mean_z")
            mz_str = f"{mz:+.3f}" if isinstance(mz, (int, float)) else "n/a"
            lines.append(f"  - {r.get('feature','?')}  mean_z={mz_str}  ks={r.get('ks_stat','?')}")
    lines.append("")
    return "\n".join(lines)


def _render_backup(backup: Dict[str, Any], smoke: Dict[str, Any]) -> str:
    head = "## Backup + Smoke"
    parts: List[str] = [head, ""]
    if backup.get("ok"):
        parts.append(
            f"- Latest backup: {backup.get('name','?')}  age={backup.get('age_human','?')}  "
            f"sha8=`{backup.get('sha256_8','?')}`  ({backup.get('n_total',0)} kept)"
        )
    else:
        parts.append("- Backup: (no data)")
    if smoke.get("ok"):
        parts.append(
            f"- Smoke: {smoke.get('status','?')}  "
            f"passed={smoke.get('n_passed',0)}/{smoke.get('n_stages',0)}  "
            f"failed={smoke.get('n_failed',0)}  "
            f"runtime={smoke.get('runtime_sec',0.0):.2f}s"
        )
        if smoke.get("failed_stages"):
            parts.append(f"  - Failed stages: {', '.join(smoke['failed_stages'])}")
    else:
        parts.append("- Smoke: (no data)")
    parts.append("")
    return "\n".join(parts)


def render_brief(sections: Dict[str, Dict[str, Any]]) -> str:
    """Compose the 8 rendered sections into one markdown blob."""
    parts: List[str] = []
    parts.append(_render_header(sections.get("Header", {})))
    parts.append(_render_bankroll(sections.get("Bankroll", {})))
    parts.append(_render_yesterday(sections.get("Yesterday", {})))
    parts.append(_render_today(sections.get("Today", {})))
    parts.append(_render_health(sections.get("Health", {})))
    parts.append(_render_alerts(sections.get("Alerts", {})))
    parts.append(_render_drift(sections.get("Drift", {})))
    parts.append(_render_backup(
        sections.get("Backup", {}).get("backup", {}),
        sections.get("Backup", {}).get("smoke", {}),
    ))
    parts.append("---\n")
    parts.append("_Generated by `scripts/generate_morning_brief.py` (R28_U5)._\n")
    return "\n".join(parts)


# ============================================================================ #
# Top-level orchestrator                                                       #
# ============================================================================ #
def collect_sections(
    *,
    today: Optional[str] = None,
    yesterday: Optional[str] = None,
    bankroll_path: Path = DEFAULT_BANKROLL_PATH,
    settled_path: Path = DEFAULT_SETTLED_PATH,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    heartbeat_dir: Path = DEFAULT_HEARTBEAT_DIR,
    alerts_vault: Path = DEFAULT_ALERTS_VAULT,
    alerts_dir: Path = DEFAULT_ALERTS_DIR,
    drift_cache: Path = DEFAULT_DRIFT_CACHE,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    smoke_dir: Path = DEFAULT_SMOKE_DIR,
    engine_fn: Optional[Any] = None,
    bankroll_for_engine: float = 1000.0,
    now: Optional[float] = None,
    now_dt: Optional[datetime] = None,
) -> Dict[str, Dict[str, Any]]:
    today = today or _today_iso()
    yesterday = yesterday or _yesterday_iso(today=today)
    sections: Dict[str, Dict[str, Any]] = {}
    sections["Header"]    = fetch_header(today=today)
    sections["Bankroll"]  = fetch_bankroll(bankroll_path=bankroll_path)
    sections["Yesterday"] = fetch_yesterday_recs(
        settled_path=settled_path, yesterday=yesterday,
    )
    sections["Today"]     = fetch_today_recs(
        today=today, top=5, engine_fn=engine_fn,
        bankroll=bankroll_for_engine,
    )
    sections["Health"]    = fetch_system_health(
        registry_path=registry_path,
        heartbeat_dir=heartbeat_dir,
        now=now,
    )
    sections["Alerts"]    = fetch_recent_alerts(
        vault_path=alerts_vault,
        alerts_dir=alerts_dir,
        now=now_dt,
    )
    sections["Drift"]     = fetch_drift(cache_path=drift_cache)
    sections["Backup"]    = {
        "backup": fetch_backup(backup_dir=backup_dir, now=now),
        "smoke":  fetch_smoke(smoke_dir=smoke_dir, today=today),
    }
    return sections


def write_brief_atomic(out_path: Path, content: str) -> Dict[str, Any]:
    """Write atomically (tmp + os.replace). Rotate previous to <out>.bak."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bak_path = out_path.with_suffix(out_path.suffix + ".bak")
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    # 1. Rotate previous brief (if any).
    rotated = False
    if out_path.exists():
        try:
            os.replace(out_path, bak_path)
            rotated = True
        except OSError:
            rotated = False
    # 2. Stage to tmp.
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    # 3. Atomic rename into place.
    os.replace(tmp_path, out_path)
    return {
        "out_path": str(out_path),
        "bak_path": str(bak_path) if rotated else None,
        "rotated":  rotated,
        "size":     out_path.stat().st_size,
    }


def generate(
    *,
    out_path: Path = DEFAULT_OUT_PATH,
    today: Optional[str] = None,
    yesterday: Optional[str] = None,
    bankroll_path: Path = DEFAULT_BANKROLL_PATH,
    settled_path: Path = DEFAULT_SETTLED_PATH,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    heartbeat_dir: Path = DEFAULT_HEARTBEAT_DIR,
    alerts_vault: Path = DEFAULT_ALERTS_VAULT,
    alerts_dir: Path = DEFAULT_ALERTS_DIR,
    drift_cache: Path = DEFAULT_DRIFT_CACHE,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    smoke_dir: Path = DEFAULT_SMOKE_DIR,
    engine_fn: Optional[Any] = None,
    bankroll_for_engine: float = 1000.0,
    now: Optional[float] = None,
    now_dt: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Full end-to-end: collect 8 sections, render markdown, atomic-write."""
    sections = collect_sections(
        today=today, yesterday=yesterday,
        bankroll_path=bankroll_path, settled_path=settled_path,
        registry_path=registry_path, heartbeat_dir=heartbeat_dir,
        alerts_vault=alerts_vault, alerts_dir=alerts_dir,
        drift_cache=drift_cache, backup_dir=backup_dir,
        smoke_dir=smoke_dir, engine_fn=engine_fn,
        bankroll_for_engine=bankroll_for_engine,
        now=now, now_dt=now_dt,
    )
    content = render_brief(sections)
    write_info = write_brief_atomic(Path(out_path), content)
    n_sections_ok = sum(
        1 for k, v in sections.items()
        if (isinstance(v, dict) and v.get("ok"))
        or (k == "Backup" and isinstance(v, dict)
            and ((v.get("backup") or {}).get("ok") or (v.get("smoke") or {}).get("ok")))
    )
    return {
        "ok":               True,
        "out_path":         write_info["out_path"],
        "bak_path":         write_info["bak_path"],
        "size_bytes":       write_info["size"],
        "n_sections":       N_SECTIONS,
        "n_sections_with_data": int(n_sections_ok),
        "sections":         sections,
    }


# ============================================================================ #
# CLI                                                                          #
# ============================================================================ #
def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="R28_U5 — generate vault/MORNING.md one-page operator brief.",
    )
    ap.add_argument("--date", type=str, default=None,
                    help="Override today's date (YYYY-MM-DD).")
    ap.add_argument("--out", type=str, default=str(DEFAULT_OUT_PATH),
                    help="Output markdown path (default vault/MORNING.md).")
    ap.add_argument("--bankroll", type=float, default=1000.0,
                    help="Bankroll passed to live_recommendation_engine.")
    ap.add_argument("--json", action="store_true",
                    help="Emit a JSON status report on stdout.")
    return ap.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    res = generate(
        out_path=Path(args.out),
        today=args.date,
        bankroll_for_engine=float(args.bankroll),
    )
    if args.json:
        # Trim sections — they are big; keep ship-relevant fields only.
        slim = {
            "ok":                   res["ok"],
            "out_path":             res["out_path"],
            "bak_path":             res["bak_path"],
            "size_bytes":           res["size_bytes"],
            "n_sections":           res["n_sections"],
            "n_sections_with_data": res["n_sections_with_data"],
        }
        print(json.dumps(slim, indent=2, default=str))
    else:
        print(
            f"wrote {res['out_path']}  size={res['size_bytes']}B  "
            f"sections_with_data={res['n_sections_with_data']}/{res['n_sections']}"
        )
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
