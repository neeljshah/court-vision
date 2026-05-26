"""L36_edge_erosion.py — Edge-Erosion Watcher (execute_loop layer 36).

Monitors betting angles for EV degradation over rolling windows.
Automatically quarantines angles that show statistically-significant
negative edge, with manual unquarantine requiring a user token.

Storage:
    data/ledger/quarantined_angles.json  — quarantine state (atomic write)
    data/ledger/edge_erosion_report_<date>.json — daily snapshot

CLI:
    python L36_edge_erosion.py report
    python L36_edge_erosion.py quarantine --angle-key X --reason "manual"
    python L36_edge_erosion.py unquarantine --angle-key X --token UNQUARANTINE_OK
    python L36_edge_erosion.py list-quarantined

Event Publication
-----------------
When a per-stat erosion crosses the detection threshold, L36 publishes to
the shared L46 EventBus (if one has been injected via ``set_event_bus``):

    Event name : "edge_erosion.detected"
    Payload fields:
        stat          – stat name derived from angle_key (str)
        current_edge  – observed_ev_pct for this angle (float)
        baseline_edge – expected_ev_pct for this angle (float)
        erosion_pct   – absolute gap (baseline - current, float)
        threshold     – the erosion gap threshold used (float, default 5.0)
        severity      – "QUARANTINED" | "WARN" (str)
        window_days   – window_n used when computing metrics (int)
        detected_at   – ISO 8601 UTC timestamp (str)

Publisher failures are silently swallowed so reports are never interrupted.

Environment Variables
---------------------
None required.  All configuration is provided programmatically:
    • L36 reads ledger paths from module-level constants (_BETS_PARQUET,
      _BETS_CSV, _QUARANTINE_FILE) which tests monkeypatch via module attrs.
    • The L46 EventBus instance is injected via set_event_bus(); L36 does
      NOT read any env vars at import time.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# L46 EventBus integration (optional; injected at runtime)
# ---------------------------------------------------------------------------
_L46 = None  # type: ignore[assignment]  # set by set_event_bus()

_EROSION_EVENT_THRESHOLD = 5.0  # pp gap (baseline - current) that triggers event


def set_event_bus(bus) -> None:  # type: ignore[type-arg]
    """Inject an L46 EventBus instance for edge_erosion.detected events."""
    global _L46  # noqa: PLW0603
    _L46 = bus


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_DIR = Path(__file__).resolve().parents[2]
_LEDGER_DIR = _PROJECT_DIR / "data" / "ledger"
_BETS_PARQUET = _LEDGER_DIR / "bets.parquet"
_BETS_CSV = _LEDGER_DIR / "bets.csv"
_QUARANTINE_FILE = _LEDGER_DIR / "quarantined_angles.json"

_AUTO_REVIEW_DAYS = 14
_UNQUARANTINE_TOKEN = "UNQUARANTINE_OK"

# ---------------------------------------------------------------------------
# Parquet / CSV detection
# ---------------------------------------------------------------------------
try:
    import pyarrow  # noqa: F401
    _HAS_PARQUET = True
except ImportError:
    _HAS_PARQUET = False

# ---------------------------------------------------------------------------
# scipy.stats.binomtest with normal-approximation fallback
# ---------------------------------------------------------------------------
try:
    from scipy.stats import binomtest as _scipy_binomtest

    def _binomtest_pvalue(n_wins: int, n_total: int, p0: float = 0.5) -> float:
        """Return one-sided (less) p-value: P(X <= k | p=p0)."""
        if n_total == 0:
            return 1.0
        result = _scipy_binomtest(n_wins, n_total, p0, alternative="less")
        return float(result.pvalue)

except ImportError:
    import math

    def _binomtest_pvalue(n_wins: int, n_total: int, p0: float = 0.5) -> float:  # type: ignore[misc]
        """Normal approximation of P(X <= k | p=p0), one-sided (less)."""
        if n_total == 0:
            return 1.0
        observed_rate = n_wins / n_total
        variance = p0 * (1.0 - p0) / n_total
        if variance <= 0:
            return 1.0
        z = (observed_rate - p0) / math.sqrt(variance)
        # CDF of standard normal via erfc approximation
        return 0.5 * math.erfc(-z / math.sqrt(2))


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------
@dataclass
class AngleMetric:
    angle_key: str
    n_bets_in_window: int
    observed_ev_pct: float
    expected_ev_pct: float
    p_value: float
    status: str  # "OK" | "WARN" | "QUARANTINED" | "INSUFFICIENT"


# ---------------------------------------------------------------------------
# Ledger loading (monkeypatching target for tests)
# ---------------------------------------------------------------------------
def _load_bets() -> Optional[pd.DataFrame]:
    """Load bets ledger; return None if absent."""
    if _HAS_PARQUET and _BETS_PARQUET.exists():
        return pd.read_parquet(_BETS_PARQUET)
    if _BETS_CSV.exists():
        return pd.read_csv(_BETS_CSV, dtype=str)
    return None


# ---------------------------------------------------------------------------
# Atomic write helper (shared by quarantine + report writers)
# ---------------------------------------------------------------------------
def _atomic_write_json(path: Path, data: dict, *, indent: int = 2) -> None:
    """Write *data* as JSON to *path* via a .tmp sibling + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.json")
    try:
        tmp.write_text(json.dumps(data, indent=indent), encoding="utf-8")
        os.replace(str(tmp), str(path))
    except OSError as exc:
        log.error("L36: atomic write failed for %s: %s", path, exc)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Quarantine state helpers
# ---------------------------------------------------------------------------
def _load_quarantine() -> dict:
    """Load quarantine JSON; return empty state if absent/corrupt."""
    if not _QUARANTINE_FILE.exists():
        return {"angles": [], "auto_review_after_days": _AUTO_REVIEW_DAYS}
    try:
        return json.loads(_QUARANTINE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("L36: failed to load quarantine file: %s", exc)
        return {"angles": [], "auto_review_after_days": _AUTO_REVIEW_DAYS}


def _save_quarantine(state: dict) -> None:
    """Atomic write via _atomic_write_json helper."""
    try:
        _atomic_write_json(_QUARANTINE_FILE, state)
    except OSError:
        pass  # already logged inside helper


# ---------------------------------------------------------------------------
# Angle key derivation
# ---------------------------------------------------------------------------
def _angle_key_from_row(row: pd.Series) -> str:
    """Derive angle_key from a BetRow-compatible Series."""
    book = str(row.get("book", "") or "").lower()
    stat = str(row.get("stat", "") or "").lower()
    side = str(row.get("side", "") or "").lower()
    line = row.get("line", "")
    try:
        line_str = f"{float(line):.1f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        line_str = str(line)
    side_pattern = f"{side}_{line_str}"
    return f"{book}_{stat}_{side_pattern}"


# ---------------------------------------------------------------------------
# Auto-review helper (logs eligibility, never auto-unquarantines in v1)
# ---------------------------------------------------------------------------
def _auto_review_quarantines(
    state: dict,
    current_metrics: dict[str, AngleMetric],
    df_settled: Optional[pd.DataFrame],
) -> None:
    """Log INFO if a quarantined angle is eligible for manual review."""
    review_after = int(state.get("auto_review_after_days", _AUTO_REVIEW_DAYS))
    now = datetime.now(timezone.utc)

    for entry in state.get("angles", []):
        key = entry.get("angle_key", "")
        q_at_str = entry.get("quarantined_at", "")
        n_at = int(entry.get("n_bets_at_quarantine", 0))

        if not q_at_str:
            continue
        try:
            q_at = datetime.fromisoformat(q_at_str)
        except ValueError:
            continue

        days_elapsed = (now - q_at).days
        if days_elapsed < review_after:
            continue

        # Count bets since quarantine
        n_since = 0
        if df_settled is not None and not df_settled.empty:
            try:
                df_settled["_angle_key"] = df_settled.apply(_angle_key_from_row, axis=1)
                after_mask = df_settled["settled_at_iso"].astype(str) >= q_at_str[:10]
                n_since = int((df_settled["_angle_key"] == key)[after_mask].sum())
            except Exception:
                pass

        metric = current_metrics.get(key)
        ev_ok = metric is not None and metric.observed_ev_pct > 5.0
        n_ok = n_since >= 30

        if ev_ok and n_ok:
            log.info(
                "L36 auto_review: angle %r eligible for manual unquarantine "
                "(days=%d, n_since=%d, observed_ev=%.1f%%). "
                "Call unquarantine_angle(key, 'UNQUARANTINE_OK') to restore.",
                key, days_elapsed, n_since, metric.observed_ev_pct,
            )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_angle_metrics(
    window_n: int = 50,
    min_n: int = 30,
) -> list[AngleMetric]:
    """Compute AngleMetric for each angle_key in the settled ledger.

    Args:
        window_n: last N bets per angle (sorted by settled_at_iso DESC).
        min_n: minimum bets required before scoring.

    Returns:
        List of AngleMetric, one per distinct angle_key.
    """
    df = _load_bets()
    if df is None or df.empty:
        log.info("L36: no ledger data found — returning empty metrics")
        return []

    # Coerce numeric columns
    for col in ("stake", "pnl", "model_edge_pp"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        else:
            df[col] = 0.0

    # Filter to settled statuses
    settled_statuses = {"WON", "LOST", "PUSH"}
    if "status" not in df.columns:
        log.warning("L36: ledger missing 'status' column")
        return []
    df = df[df["status"].str.upper().isin(settled_statuses)].copy()

    if df.empty:
        return []

    # Derive angle keys
    df["_angle_key"] = df.apply(_angle_key_from_row, axis=1)

    state = _load_quarantine()
    results: list[AngleMetric] = []
    angle_metrics_map: dict[str, AngleMetric] = {}

    for angle_key, group in df.groupby("_angle_key"):
        # Sort by settled_at_iso DESC, take last window_n
        if "settled_at_iso" in group.columns:
            group = group.sort_values("settled_at_iso", ascending=False)
        window = group.head(window_n)
        n = len(window)

        # EV metrics
        total_stake = float(window["stake"].sum())
        total_pnl = float(window["pnl"].sum())
        observed_ev_pct = (total_pnl / total_stake * 100.0) if total_stake > 0 else 0.0

        edge_col = window["model_edge_pp"] if "model_edge_pp" in window.columns else None
        if edge_col is not None and edge_col.notna().any():
            expected_ev_pct = float(edge_col.mean())
        else:
            expected_ev_pct = 0.0

        # Win-rate binomial test (p0=0.5 baseline)
        n_wins = int((window["status"].str.upper() == "WON").sum())
        p_value = _binomtest_pvalue(n_wins, n, p0=0.5)

        # Status logic
        if n < min_n:
            status = "INSUFFICIENT"
        elif observed_ev_pct < 2.0 and p_value < 0.10:
            status = "QUARANTINED"
        elif observed_ev_pct < expected_ev_pct - 5.0:
            status = "WARN"
        else:
            status = "OK"

        metric = AngleMetric(
            angle_key=str(angle_key),
            n_bets_in_window=n,
            observed_ev_pct=round(observed_ev_pct, 4),
            expected_ev_pct=round(expected_ev_pct, 4),
            p_value=round(p_value, 6),
            status=status,
        )
        results.append(metric)
        angle_metrics_map[str(angle_key)] = metric

        # Auto-quarantine
        if status == "QUARANTINED":
            quarantine_angle(
                str(angle_key),
                reason=f"auto: ev={observed_ev_pct:.1f}% p={p_value:.4f}",
                n_bets=n,
                observed_ev=observed_ev_pct,
            )

        # L46 event publication for erosion events (WARN or QUARANTINED)
        if status in ("WARN", "QUARANTINED") and _L46 is not None:
            erosion_pct = expected_ev_pct - observed_ev_pct
            # Derive stat name from angle_key (format: book_stat_side_line)
            parts = str(angle_key).split("_")
            stat_name = parts[1] if len(parts) > 1 else str(angle_key)
            try:
                _L46.publish(
                    "edge_erosion.detected",
                    source="L36",
                    payload={
                        "stat": stat_name,
                        "current_edge": round(observed_ev_pct, 4),
                        "baseline_edge": round(expected_ev_pct, 4),
                        "erosion_pct": round(erosion_pct, 4),
                        "threshold": _EROSION_EVENT_THRESHOLD,
                        "severity": status,
                        "window_days": window_n,
                        "detected_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception:  # noqa: BLE001
                pass

    # Auto-review check (logs only, never restores)
    _auto_review_quarantines(state, angle_metrics_map, df)

    return results


def quarantine_angle(
    angle_key: str,
    reason: str,
    n_bets: int = 0,
    observed_ev: float = 0.0,
) -> None:
    """Append angle_key to quarantine state (idempotent).

    Also fires an L22 drift-channel alert on new quarantine.
    """
    state = _load_quarantine()
    existing_keys = {e["angle_key"] for e in state.get("angles", [])}

    if angle_key in existing_keys:
        log.debug("L36: angle %r already quarantined — skipping", angle_key)
        return

    entry = {
        "angle_key": angle_key,
        "quarantined_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "n_bets_at_quarantine": n_bets,
    }
    state.setdefault("angles", []).append(entry)
    state["auto_review_after_days"] = _AUTO_REVIEW_DAYS
    _save_quarantine(state)
    log.warning("L36: QUARANTINED angle %r — %s", angle_key, reason)

    # L22 alert (soft import)
    try:
        from scripts.execute_loop.L22_alerting import send_alert  # type: ignore[import]
        send_alert(
            channel="drift",
            level="error",
            title="Angle quarantined",
            body=f"{angle_key}: ev={observed_ev:.1f}% — {reason}",
        )
    except ImportError:
        pass
    except Exception as exc:
        log.warning("L36: L22 alert failed: %s", exc)


def unquarantine_angle(angle_key: str, user_token: str) -> None:
    """Remove angle_key from quarantine state.

    Raises:
        ValueError: if user_token != UNQUARANTINE_OK
    """
    if user_token != _UNQUARANTINE_TOKEN:
        raise ValueError(
            f"Invalid token. Pass user_token='{_UNQUARANTINE_TOKEN}' to confirm."
        )
    state = _load_quarantine()
    before = len(state.get("angles", []))
    state["angles"] = [
        e for e in state.get("angles", []) if e["angle_key"] != angle_key
    ]
    after = len(state["angles"])
    _save_quarantine(state)
    if before == after:
        log.info("L36: angle %r was not quarantined — no change", angle_key)
    else:
        log.info("L36: unquarantined angle %r", angle_key)


def is_quarantined(angle_key: str) -> bool:
    """Return True if angle_key is currently in the quarantine list."""
    state = _load_quarantine()
    return any(e["angle_key"] == angle_key for e in state.get("angles", []))


def daily_edge_report() -> dict:
    """Compute all angle metrics and write a dated JSON snapshot.

    Returns the report dict (also written to data/ledger/edge_erosion_report_<date>.json).

    The report includes:
    - Aggregate summary fields (n_angles, n_quarantined, n_warn, n_ok, n_insufficient)
      for backward compatibility.
    - ``metrics`` — full list of per-angle AngleMetric dicts.
    - ``per_stat_erosion`` — per-stat breakdown: for each distinct stat name derived
      from angle_keys, reports the worst (most eroded) angle, aggregated observed_ev,
      and a count of WARN/QUARANTINED angles. This is the primary v2 addition.
    """
    metrics = compute_angle_metrics()
    quarantined = [m for m in metrics if m.status == "QUARANTINED"]
    warned = [m for m in metrics if m.status == "WARN"]
    ok = [m for m in metrics if m.status == "OK"]
    insufficient = [m for m in metrics if m.status == "INSUFFICIENT"]

    # ------------------------------------------------------------------
    # Per-stat erosion breakdown (v2 addition)
    # ------------------------------------------------------------------
    stat_groups: dict[str, list[AngleMetric]] = {}
    for m in metrics:
        # Angle key format: book_stat_side_line → stat is index 1
        parts = m.angle_key.split("_")
        stat_name = parts[1] if len(parts) > 1 else m.angle_key
        stat_groups.setdefault(stat_name, []).append(m)

    per_stat_erosion: list[dict] = []
    for stat_name, stat_metrics in sorted(stat_groups.items()):
        n_eroded = sum(1 for m in stat_metrics if m.status in ("WARN", "QUARANTINED"))
        # Worst angle = largest (expected - observed) gap
        worst = max(stat_metrics, key=lambda m: m.expected_ev_pct - m.observed_ev_pct)
        avg_observed = (
            sum(m.observed_ev_pct for m in stat_metrics) / len(stat_metrics)
        )
        per_stat_erosion.append({
            "stat": stat_name,
            "n_angles": len(stat_metrics),
            "n_eroded": n_eroded,
            "avg_observed_ev_pct": round(avg_observed, 4),
            "worst_angle_key": worst.angle_key,
            "worst_observed_ev_pct": worst.observed_ev_pct,
            "worst_expected_ev_pct": worst.expected_ev_pct,
            "worst_status": worst.status,
        })

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_n": 50,
        "n_angles": len(metrics),
        "n_quarantined": len(quarantined),
        "n_warn": len(warned),
        "n_ok": len(ok),
        "n_insufficient": len(insufficient),
        "metrics": [asdict(m) for m in metrics],
        "per_stat_erosion": per_stat_erosion,
        "quarantine_list": _load_quarantine().get("angles", []),
    }

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = _LEDGER_DIR / f"edge_erosion_report_{today}.json"
    try:
        _atomic_write_json(report_path, report)
        log.info("L36: edge report written to %s", report_path)
    except OSError:
        pass  # already logged inside helper

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cli_report(args) -> None:  # noqa: ARG001
    report = daily_edge_report()
    print(f"[L36] Edge Erosion Report — {report['generated_at'][:10]}")
    print(f"  Total angles:     {report['n_angles']}")
    print(f"  Quarantined:      {report['n_quarantined']}")
    print(f"  Warned:           {report['n_warn']}")
    print(f"  OK:               {report['n_ok']}")
    print(f"  Insufficient data:{report['n_insufficient']}")
    for m in report["metrics"]:
        print(
            f"  {m['angle_key']:<40}  {m['status']:<14}  "
            f"obs_ev={m['observed_ev_pct']:+.1f}%  "
            f"exp_ev={m['expected_ev_pct']:+.1f}%  "
            f"p={m['p_value']:.4f}  n={m['n_bets_in_window']}"
        )


def _cli_quarantine(args) -> None:
    quarantine_angle(args.angle_key, reason=args.reason)
    print(f"[L36] Quarantined: {args.angle_key}")


def _cli_unquarantine(args) -> None:
    unquarantine_angle(args.angle_key, args.token)
    print(f"[L36] Unquarantined: {args.angle_key}")


def _cli_list(args) -> None:  # noqa: ARG001
    state = _load_quarantine()
    angles = state.get("angles", [])
    if not angles:
        print("[L36] No quarantined angles.")
        return
    print(f"[L36] {len(angles)} quarantined angle(s):")
    for e in angles:
        print(
            f"  {e['angle_key']:<40}  since={e.get('quarantined_at', '')[:10]}  "
            f"n={e.get('n_bets_at_quarantine', '?')}  reason={e.get('reason', '')}"
        )


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="L36_edge_erosion")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("report", help="Run daily edge report").set_defaults(func=_cli_report)

    p_q = sub.add_parser("quarantine", help="Manually quarantine an angle")
    p_q.add_argument("--angle-key", required=True)
    p_q.add_argument("--reason", default="manual quarantine")
    p_q.set_defaults(func=_cli_quarantine)

    p_uq = sub.add_parser("unquarantine", help="Restore a quarantined angle")
    p_uq.add_argument("--angle-key", required=True)
    p_uq.add_argument("--token", required=True)
    p_uq.set_defaults(func=_cli_unquarantine)

    sub.add_parser("list-quarantined", help="List all quarantined angles").set_defaults(func=_cli_list)

    args = p.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
