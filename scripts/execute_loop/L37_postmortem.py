"""L37_postmortem.py — Automated Postmortem Agent (execute_loop layer 37).

Detects betting incidents (large loss, losing streak, model drift), categorises
each losing bet to a root cause, writes a Markdown postmortem to
data/ledger/postmortems/, and surfaces a root-cause hypothesis + remediation.

Public API
----------
    PostmortemReport            dataclass
    detect_incidents(window_days) -> list[dict]
    run_postmortem(losing_bets)   -> PostmortemReport
    categorize_losses(bets)       -> dict[str, int]

CLI
---
    python L37_postmortem.py detect [--window 1]
    python L37_postmortem.py run --losing-bets path.json
    python L37_postmortem.py list

Event Publication (L46 EventBus)
---------------------------------
L37 publishes two event types via the L46 default bus (soft-import; bus absence
is non-fatal — detection and postmortem behaviour are unchanged).

``incident.opened``
    Emitted once per new incident returned by detect_incidents().
    Payload fields:
        incident_id  : str   — UUID4 fragment (8 chars) generated for the incident
        loss_pattern : str   — trigger_type value ("large_loss", "losing_streak", …)
        bet_count    : int   — number of bets in the incident
        total_loss   : float — sum of pnl for the incident's bets (negative)
        avg_clv      : float | None — average CLV if present in the incident dict
        detected_at  : str  — ISO 8601 UTC timestamp of detection
        incident_class : str | None — IncidentClass.name from classify_incident()
        severity       : str | None — "P0" | "P1" | "P2" | None

``incident.classified``
    Emitted by run_postmortem() after structured classification is complete.
    Payload fields:
        incident_id    : str
        incident_class : str | None
        severity       : str | None
        remediation    : str | None — Remediation.suggestion
        trigger_type   : str
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parents[1]
sys.path.insert(0, str(_PROJECT_DIR))

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Soft-import L46 EventBus — absence is non-fatal
# ---------------------------------------------------------------------------
try:
    from scripts.execute_loop import L46_event_bus as _L46  # type: ignore[import]
except Exception:  # noqa: BLE001
    _L46 = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_LEDGER_DIR = _PROJECT_DIR / "data" / "ledger"
_BETS_PARQUET = _LEDGER_DIR / "bets.parquet"
_BETS_CSV = _LEDGER_DIR / "bets.csv"
_POSTMORTEM_DIR = _LEDGER_DIR / "postmortems"
_BANKROLL_STATE = _LEDGER_DIR / "bankroll_state.json"
_INJURY_SEEN = _PROJECT_DIR / "data" / "ledger" / "injury_seen.json"
_LINEUP_DIR = _PROJECT_DIR / "data" / "lineup_announcements"

_DEFAULT_BANKROLL = 100_000.0
_LARGE_LOSS_THRESHOLD = 0.05   # 5% of bankroll
_STREAK_LENGTH = 5             # consecutive losses to trigger

# ---------------------------------------------------------------------------
# Cause categories (evaluated in priority order)
# ---------------------------------------------------------------------------
CAUSE_ORDER = [
    "missing_injury_news",
    "late_scratch",
    "line_movement_against",
    "stat_drift",
    "model_overconfidence",
    "variance",
    "unknown",
]

_INVESTIGATION_MAP: dict[str, str] = {
    "missing_injury_news": (
        "Increase L20 scrape frequency to 5 min during pregame window"
    ),
    "late_scratch": (
        "Add L21 confirmation check 25 min before tip-off"
    ),
    "line_movement_against": (
        "Tighten L19 CLV alert threshold; consider line-snapping closer to close"
    ),
    "stat_drift": (
        "Trigger L24 nightly retrain for affected stat"
    ),
    "model_overconfidence": (
        "Recalibrate σ multipliers for affected stats; run validation backtest"
    ),
    "variance": (
        "No action needed; track over more games"
    ),
}

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class IncidentClass:
    name: str          # e.g. "model_drift", "stale_line", ...
    severity: str      # "P0" | "P1" | "P2"
    description: str


@dataclass(frozen=True)
class Remediation:
    class_name: str
    suggestion: str
    runbook_link: Optional[str] = None


_BUILTIN_CLASSES: tuple[IncidentClass, ...] = (
    IncidentClass("model_drift",            "P1", "predictions consistently off-target"),
    IncidentClass("stale_line",             "P2", "line moved before bet placed"),
    IncidentClass("injury_unaccounted",     "P1", "key player injury announced post-bet"),
    IncidentClass("ev_calc_bug",            "P0", "EV calculation produced negative-EV bet"),
    IncidentClass("slippage_underestimate", "P2", "fill price worse than expected"),
    IncidentClass("kelly_oversized",        "P1", "bet sized above max Kelly cap"),
)

_BUILTIN_REMEDIATIONS: dict[str, Remediation] = {
    "model_drift": Remediation(
        class_name="model_drift",
        suggestion="Trigger L24 nightly retrain for drifting stats; run walk-forward validation",
        runbook_link=None,
    ),
    "stale_line": Remediation(
        class_name="stale_line",
        suggestion="Tighten L19 CLV alert threshold; snap lines closer to close",
        runbook_link=None,
    ),
    "injury_unaccounted": Remediation(
        class_name="injury_unaccounted",
        suggestion="Increase L20 scrape frequency to 5 min during pregame window",
        runbook_link=None,
    ),
    "ev_calc_bug": Remediation(
        class_name="ev_calc_bug",
        suggestion="HALT betting immediately; audit EV calculation formula and unit tests",
        runbook_link=None,
    ),
    "slippage_underestimate": Remediation(
        class_name="slippage_underestimate",
        suggestion="Recalibrate L18 slippage model with recent fill-price vs requested-price data",
        runbook_link=None,
    ),
    "kelly_oversized": Remediation(
        class_name="kelly_oversized",
        suggestion="Reduce Kelly fraction cap; check L18 stake sizing logic for max_stake guard",
        runbook_link=None,
    ),
}

# Registry for custom classifiers and remediations (extended at runtime)
_custom_classes: dict[str, IncidentClass] = {}
_custom_classifiers: dict[str, Callable[[dict], bool]] = {}
_custom_remediations: dict[str, Remediation] = {}


def classify_incident(incident: dict) -> Optional[IncidentClass]:
    """Heuristic classification of an incident dict.

    Uses avg_clv, model_p, total stake vs bankroll, and model_p_side fields.
    Returns None if no class can be confidently assigned.
    """
    # --- custom classifiers take priority (registered first = highest priority) ---
    for class_name, fn in _custom_classifiers.items():
        try:
            if fn(incident):
                # Return from custom registry, then fallback to builtin classes
                cls = _custom_classes.get(class_name)
                if cls is None:
                    cls = next((c for c in _BUILTIN_CLASSES if c.name == class_name), None)
                if cls is not None:
                    return cls
        except Exception:
            log.warning("[L37] Custom classifier %r raised an exception", class_name)

    bets: list[dict] = incident.get("bets", [])

    # --- ev_calc_bug (P0): any bet has model_p_side < 0.5 with an EV in the bet record ---
    for b in bets:
        mp = float(b.get("model_p_side", 1.0) or 1.0)
        ev = b.get("ev", b.get("expected_value", None))
        if mp < 0.5 and ev is not None and float(ev) > 0:
            return next(c for c in _BUILTIN_CLASSES if c.name == "ev_calc_bug")

    # --- stale_line: avg_clv < -0.05 ---
    avg_clv = incident.get("avg_clv", None)
    if avg_clv is not None and float(avg_clv) < -0.05:
        return next(c for c in _BUILTIN_CLASSES if c.name == "stale_line")

    # --- model_drift: model_p_side < market_p for all losses ---
    if bets:
        all_model_below_market = all(
            float(b.get("model_p_side", 0.5) or 0.5) < float(b.get("market_p", 0.5) or 0.5)
            for b in bets
            if b.get("market_p") is not None
        ) and any(b.get("market_p") is not None for b in bets)
        if all_model_below_market:
            return next(c for c in _BUILTIN_CLASSES if c.name == "model_drift")

    # --- kelly_oversized: sum(stake) > bankroll * 0.1 ---
    bankroll = float(incident.get("bankroll", _get_bankroll()))
    total_stake = sum(float(b.get("stake", 0.0) or 0.0) for b in bets)
    if total_stake > bankroll * 0.1:
        return next(c for c in _BUILTIN_CLASSES if c.name == "kelly_oversized")

    return None


def suggest_remediation(incident_class: IncidentClass) -> Optional[Remediation]:
    """Return the remediation suggestion for a given IncidentClass.

    Checks custom remediations first, then builtin table.
    """
    custom = _custom_remediations.get(incident_class.name)
    if custom is not None:
        return custom
    return _BUILTIN_REMEDIATIONS.get(incident_class.name)


def register_classifier(
    class_def: IncidentClass,
    classifier_fn: Callable[[dict], bool],
) -> None:
    """Register a custom incident class and its classifier function.

    The classifier_fn receives an incident dict and returns True if the
    incident matches this class.  Custom classifiers run before builtins.
    """
    _custom_classes[class_def.name] = class_def
    _custom_classifiers[class_def.name] = classifier_fn
    log.info("[L37] Registered custom classifier: %s (%s)", class_def.name, class_def.severity)


def register_remediation(remediation: Remediation) -> None:
    """Register or override a remediation for a given class_name."""
    _custom_remediations[remediation.class_name] = remediation
    log.info("[L37] Registered custom remediation for: %s", remediation.class_name)


@dataclass
class PostmortemReport:
    incident_id: str
    date: str
    trigger_type: str          # "large_loss"|"losing_streak"|"model_drift"
    losing_bets: list[dict]
    categorized_causes: dict[str, int]
    root_cause_hypothesis: str
    recommended_investigation: str
    written_to: str
    # v2 classification fields (additive — None when classification is uncertain)
    incident_class: Optional[str] = None        # IncidentClass.name
    severity: Optional[str] = None              # "P0" | "P1" | "P2"
    remediation: Optional[str] = None           # Remediation.suggestion


# ---------------------------------------------------------------------------
# Parquet / CSV helpers
# ---------------------------------------------------------------------------
try:
    import pyarrow  # noqa: F401
    _HAS_PARQUET = True
except ImportError:
    _HAS_PARQUET = False


def _read_bets() -> pd.DataFrame:
    """Load bets ledger, returning empty DataFrame on failure."""
    paths = [_BETS_PARQUET, _BETS_CSV]
    for p in paths:
        if p.exists():
            try:
                return pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
            except Exception as exc:
                log.warning("[L37] Could not read %s: %s", p.name, exc)
    log.info("[L37] No bets ledger found — returning empty DataFrame")
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Bankroll helpers
# ---------------------------------------------------------------------------
def _get_bankroll() -> float:
    """Read current_bankroll from L18 state file; fallback to default."""
    if _BANKROLL_STATE.exists():
        try:
            state = json.loads(_BANKROLL_STATE.read_text(encoding="utf-8"))
            return float(state.get("current_bankroll", _DEFAULT_BANKROLL))
        except Exception as exc:
            log.warning("[L37] Could not parse bankroll state: %s", exc)
    return _DEFAULT_BANKROLL


# ---------------------------------------------------------------------------
# Cross-reference file loaders (all soft — log INFO if missing)
# ---------------------------------------------------------------------------
def _load_injury_seen() -> list[dict]:
    """Load L20 _seen.json: list of {player, status, ts, ...}."""
    path = _INJURY_SEEN
    if not path.exists():
        log.info("[L37] L20 injury_seen.json not found at %s", path)
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        # Support both dict-of-hashes (real format) and plain list (test mock)
        if isinstance(raw, dict):
            return list(raw.values())
        return raw
    except Exception as exc:
        log.warning("[L37] Could not parse injury_seen.json: %s", exc)
        return []


def _load_lineup_announcements(date_str: str) -> list[dict]:
    """Load L21 lineup JSON for a given date YYYY-MM-DD."""
    path = _LINEUP_DIR / f"{date_str}.json"
    if not path.exists():
        log.info("[L37] L21 lineup file not found: %s", path)
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("[L37] Could not parse lineup file %s: %s", path.name, exc)
        return []


def _load_clv_report(date_str: str) -> dict:
    """Load L19 CLV report for a given date; returns {} if missing."""
    path = _LEDGER_DIR / f"clv_report_{date_str}.json"
    if not path.exists():
        log.info("[L37] L19 CLV report not found: %s", path)
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("[L37] Could not parse CLV report %s: %s", path.name, exc)
        return {}


def _load_drift_report(date_str: str) -> dict:
    """Load L8 drift report for a given date; returns {} if missing."""
    path = _LEDGER_DIR / f"drift_report_{date_str}.json"
    if not path.exists():
        log.info("[L37] L8 drift report not found: %s", path)
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("[L37] Could not parse drift report %s: %s", path.name, exc)
        return {}


# ---------------------------------------------------------------------------
# Incident detection
# ---------------------------------------------------------------------------
def detect_incidents(window_days: int = 1) -> list[dict]:
    """Return list of incident dicts detected in the last *window_days* days."""
    df = _read_bets()
    if df.empty:
        log.info("[L37] No bets to analyse — no incidents.")
        return []

    # Normalise date column
    ts_col = next(
        (c for c in ("settled_at_iso", "settled_at", "placed_at_iso", "placed_at")
         if c in df.columns),
        None,
    )
    if ts_col is None:
        log.warning("[L37] Bets DataFrame has no recognised timestamp column.")
        return []

    df["_ts"] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    window_df = df[df["_ts"] >= cutoff].copy()

    incidents: list[dict] = []
    bankroll = _get_bankroll()

    # --- 1. large_loss ---------------------------------------------------
    settled = window_df[window_df.get("status", pd.Series(dtype=str)).isin(["WON", "LOST", "PUSH"])] \
        if "status" in window_df.columns else window_df
    if "pnl" in settled.columns and not settled.empty:
        daily_pnl = settled["pnl"].sum()
        if daily_pnl < -(_LARGE_LOSS_THRESHOLD * bankroll):
            incidents.append({
                "trigger_type": "large_loss",
                "pnl": float(daily_pnl),
                "bankroll": bankroll,
                "pct_bankroll": float(daily_pnl / bankroll),
                "bets": _rows_to_dicts(settled),
            })
            log.info("[L37] large_loss incident: PnL=%.2f (%.1f%% bankroll)",
                     daily_pnl, daily_pnl / bankroll * 100)

    # --- 2. losing_streak ------------------------------------------------
    if "status" in df.columns and "_ts" in df.columns:
        chronological = df.sort_values("_ts")
        statuses = chronological["status"].tolist()
        streak_bets = []
        for i, row in chronological.iterrows():
            if row["status"] == "LOST":
                streak_bets.append(row.to_dict())
                if len(streak_bets) >= _STREAK_LENGTH:
                    incidents.append({
                        "trigger_type": "losing_streak",
                        "streak_length": len(streak_bets),
                        "bets": streak_bets[-_STREAK_LENGTH:],
                    })
                    log.info("[L37] losing_streak: %d consecutive losses", len(streak_bets))
                    break
            else:
                streak_bets = []

    # --- 3. model_drift --------------------------------------------------
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    drift_report = _load_drift_report(today_str)
    if drift_report:
        drifting = [
            m for m in drift_report.get("metrics", [])
            if m.get("status") == "DRIFT"
        ]
        if drifting:
            incidents.append({
                "trigger_type": "model_drift",
                "drifting_stats": [m.get("stat") for m in drifting],
                "bets": _rows_to_dicts(window_df),
            })
            log.info("[L37] model_drift: stats=%s", [m.get("stat") for m in drifting])

    # --- Publish incident.opened events via L46 ---
    detected_at = datetime.now(timezone.utc).isoformat()
    for incident in incidents:
        # Assign a stable incident_id for event correlation
        if "incident_id" not in incident:
            incident["incident_id"] = str(uuid.uuid4())[:8]
        if _L46 is not None:
            try:
                inc_class = classify_incident(incident)
                _L46.publish(
                    "incident.opened",
                    source="L37",
                    payload={
                        "incident_id": incident["incident_id"],
                        "loss_pattern": incident.get("trigger_type"),
                        "bet_count": len(incident.get("bets", [])),
                        "total_loss": float(
                            sum(float(b.get("pnl", 0.0) or 0.0) for b in incident.get("bets", []))
                        ),
                        "avg_clv": incident.get("avg_clv"),
                        "detected_at": incident.get("detected_at", detected_at),
                        "incident_class": inc_class.name if inc_class else None,
                        "severity": inc_class.severity if inc_class else None,
                    },
                )
            except Exception:
                log.debug("L46 publish failed (non-fatal)", exc_info=True)

    return incidents


def _rows_to_dicts(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame rows to list[dict], dropping NaT/NaN safely."""
    records = []
    for _, row in df.iterrows():
        d = {}
        for k, v in row.items():
            if k.startswith("_"):
                continue
            try:
                d[k] = None if pd.isna(v) else v  # type: ignore[arg-type]
            except (TypeError, ValueError):
                d[k] = v
        records.append(d)
    return records


# ---------------------------------------------------------------------------
# Cause categorisation
# ---------------------------------------------------------------------------
def categorize_losses(bets: list[dict]) -> dict[str, int]:
    """Assign the first matching cause to each bet; return cause tallies."""
    if not bets:
        return {}

    # Pre-load cross-reference files once
    injury_entries = _load_injury_seen()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    drift_report = _load_drift_report(today_str)
    drift_stats = {
        m.get("stat", "").lower()
        for m in drift_report.get("metrics", [])
        if m.get("status") == "DRIFT"
    }

    clv_exists = (_LEDGER_DIR / f"clv_report_{today_str}.json").exists()
    lineup_files_exist = _LINEUP_DIR.is_dir() and bool(list(_LINEUP_DIR.glob("*.json")))
    all_missing = (
        not injury_entries
        and not lineup_files_exist
        and not clv_exists
        and not drift_report
    )

    tallies: dict[str, int] = {}

    for bet in bets:
        cause = _classify_bet(bet, injury_entries, drift_stats, all_missing, today_str)
        tallies[cause] = tallies.get(cause, 0) + 1

    return tallies


def _classify_bet(
    bet: dict,
    injury_entries: list[dict],
    drift_stats: set[str],
    all_missing: bool,
    date_str: str,
) -> str:
    """Return the first matching cause string for a single bet."""
    if all_missing:
        return "unknown"

    player_raw = str(bet.get("player", "")).lower().strip()
    bet_ts_str = bet.get("placed_at_iso") or bet.get("settled_at_iso") or ""
    stat = str(bet.get("stat", "")).lower().strip()
    model_p = float(bet.get("model_p_side", 0.0) or 0.0)

    # 1. missing_injury_news — player appears as OUT in L20 history after bet placed
    if injury_entries and bet_ts_str:
        try:
            bet_ts = datetime.fromisoformat(bet_ts_str.replace("Z", "+00:00"))
        except ValueError:
            bet_ts = None
        if bet_ts:
            for entry in injury_entries:
                ep = str(entry.get("player", "")).lower().strip()
                es = str(entry.get("status", "")).upper()
                ets_str = entry.get("ts") or entry.get("timestamp") or entry.get("last_seen_iso", "")
                if ep and player_raw and ep in player_raw or (player_raw and player_raw in ep):
                    if es == "OUT":
                        try:
                            entry_ts = datetime.fromisoformat(ets_str.replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            continue
                        if entry_ts > bet_ts:
                            return "missing_injury_news"

    # 2. late_scratch — player benched (status not OUT) in L21 after bet placed
    lineup_entries = _load_lineup_announcements(date_str)
    if lineup_entries and bet_ts_str:
        try:
            bet_ts = datetime.fromisoformat(bet_ts_str.replace("Z", "+00:00"))
        except ValueError:
            bet_ts = None
        if bet_ts:
            for entry in lineup_entries:
                ep = str(entry.get("player", "")).lower().strip()
                role = str(entry.get("role", entry.get("status", ""))).lower()
                ets_str = entry.get("ts") or entry.get("timestamp", "")
                if ep and player_raw and (ep in player_raw or player_raw in ep):
                    if "bench" in role or role == "dnp":
                        try:
                            entry_ts = datetime.fromisoformat(ets_str.replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            continue
                        if entry_ts > bet_ts:
                            return "late_scratch"

    # 3. line_movement_against — CLV moved > 0.5 units against bet side
    clv_report = _load_clv_report(date_str)
    if clv_report:
        bet_id = str(bet.get("bet_id", ""))
        bets_clv = clv_report.get("bets", clv_report)
        if isinstance(bets_clv, list):
            for entry in bets_clv:
                if str(entry.get("bet_id", "")) == bet_id:
                    if float(entry.get("clv_units", 0.0) or 0.0) < -0.5:
                        return "line_movement_against"
        elif isinstance(bets_clv, dict) and bet_id in bets_clv:
            if float(bets_clv[bet_id].get("clv_units", 0.0) or 0.0) < -0.5:
                return "line_movement_against"

    # 4. stat_drift — stat in DRIFT status per L8 report
    if stat in drift_stats:
        return "stat_drift"

    # 5. model_overconfidence — model_p_side >= 0.7 and bet LOST
    if model_p >= 0.7:
        return "model_overconfidence"

    # 6. variance — fallback
    return "variance"


# ---------------------------------------------------------------------------
# Root cause logic
# ---------------------------------------------------------------------------
def _derive_root_cause(tallies: dict[str, int]) -> tuple[str, str]:
    """Return (root_cause_hypothesis, recommended_investigation)."""
    if not tallies:
        return "insufficient_signal", "No bets to analyse"

    total = sum(tallies.values())
    if total == 0:
        return "insufficient_signal", "No bets to analyse"

    # All unknown
    unknown_count = tallies.get("unknown", 0)
    if unknown_count == total:
        return "insufficient_signal", "No action needed; gather more history data"

    # Ignore unknown for dominance check
    signal_tallies = {k: v for k, v in tallies.items() if k != "unknown"}
    signal_total = sum(signal_tallies.values())
    if signal_total == 0:
        return "insufficient_signal", "No action needed; gather more history data"

    pcts = {k: v / signal_total for k, v in signal_tallies.items()}

    # All variance
    variance_only = set(signal_tallies.keys()) <= {"variance"}
    if variance_only:
        return (
            "expected variance, no signal",
            _INVESTIGATION_MAP["variance"],
        )

    # Check for dominant cause > 50%
    dominant = max(pcts, key=lambda k: pcts[k])
    if pcts[dominant] > 0.5:
        return (
            f"Dominant cause: {dominant}",
            _INVESTIGATION_MAP.get(dominant, "Review manually"),
        )

    # Tied causes — multiple causes ≥ 40% (excluding variance)
    non_variance = {k: v for k, v in pcts.items() if k != "variance"}
    tied = [k for k, v in non_variance.items() if v >= 0.4]
    if len(tied) >= 2:
        return (
            "multi-factor: " + ", ".join(sorted(tied)),
            "; ".join(_INVESTIGATION_MAP.get(k, "Review manually") for k in sorted(tied)),
        )

    # Default to dominant
    return (
        f"Dominant cause: {dominant}",
        _INVESTIGATION_MAP.get(dominant, "Review manually"),
    )


# ---------------------------------------------------------------------------
# Postmortem document writer
# ---------------------------------------------------------------------------
def run_postmortem(
    losing_bets: list[dict],
    trigger_type: str = "large_loss",
    pnl: Optional[float] = None,
    bankroll: Optional[float] = None,
    incident: Optional[dict] = None,
) -> PostmortemReport:
    """Categorise *losing_bets*, build the report, write Markdown, return dataclass.

    v2: also classifies the incident into a known IncidentClass and attaches
    a remediation suggestion.  Existing callers are unaffected (additive only).
    """
    _POSTMORTEM_DIR.mkdir(parents=True, exist_ok=True)

    incident_id = str(uuid.uuid4())[:8]
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    categorized = categorize_losses(losing_bets)
    root_cause, investigation = _derive_root_cause(categorized)

    # --- v2: structured classification ---
    _incident_ctx = incident or {
        "bets": losing_bets,
        "bankroll": bankroll or _get_bankroll(),
        "trigger_type": trigger_type,
        "pnl": pnl,
    }
    inc_class = classify_incident(_incident_ctx)
    remediation_obj = suggest_remediation(inc_class) if inc_class else None

    # Publish incident.classified via L46
    if _L46 is not None:
        try:
            _L46.publish(
                "incident.classified",
                source="L37",
                payload={
                    "incident_id": incident_id,
                    "incident_class": inc_class.name if inc_class else None,
                    "severity": inc_class.severity if inc_class else None,
                    "remediation": remediation_obj.suggestion if remediation_obj else None,
                    "trigger_type": trigger_type,
                },
            )
        except Exception:
            log.debug("L46 publish failed (non-fatal)", exc_info=True)

    # Build magnitude line
    if pnl is not None and bankroll:
        pct = abs(pnl / bankroll * 100)
        magnitude_line = f"$**{abs(pnl):,.2f}** ({pct:.1f}% bankroll)"
    elif pnl is not None:
        magnitude_line = f"$**{abs(pnl):,.2f}**"
    else:
        magnitude_line = "N/A"

    total_loss = sum(float(b.get("pnl", 0.0) or 0.0) for b in losing_bets)
    n = len(losing_bets)

    # Cause breakdown lines
    cause_lines = ""
    if categorized:
        total_cats = sum(categorized.values())
        for cause, count in sorted(categorized.items(), key=lambda x: -x[1]):
            pct_str = f"{count / total_cats * 100:.0f}%" if total_cats else "N/A"
            cause_lines += f"- {cause}: {count} ({pct_str})\n"

    md = f"""# Postmortem {incident_id} - {date_str}

## Trigger
{trigger_type}, magnitude: {magnitude_line}

## Losing bets analyzed
{n} bets totaling ${abs(total_loss):,.2f} loss

## Cause breakdown
{cause_lines.rstrip()}

## Root cause hypothesis
{root_cause}

## Recommended investigation
{investigation}
"""

    out_path = _POSTMORTEM_DIR / f"{date_str}_{incident_id}.md"
    out_path.write_text(md, encoding="utf-8")
    log.info("[L37] Postmortem written to %s", out_path)

    return PostmortemReport(
        incident_id=incident_id,
        date=date_str,
        trigger_type=trigger_type,
        losing_bets=losing_bets,
        categorized_causes=categorized,
        root_cause_hypothesis=root_cause,
        recommended_investigation=investigation,
        written_to=str(out_path),
        incident_class=inc_class.name if inc_class else None,
        severity=inc_class.severity if inc_class else None,
        remediation=remediation_obj.suggestion if remediation_obj else None,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cmd_detect(args: argparse.Namespace) -> None:
    incidents = detect_incidents(window_days=args.window)
    if not incidents:
        print("No incidents detected.")
        return
    for inc in incidents:
        print(json.dumps(inc, indent=2, default=str))


def _cmd_run(args: argparse.Namespace) -> None:
    path = Path(args.losing_bets)
    bets = json.loads(path.read_text(encoding="utf-8"))
    report = run_postmortem(bets)
    print(json.dumps(asdict(report), indent=2, default=str))


def _cmd_list(_args: argparse.Namespace) -> None:
    _POSTMORTEM_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(_POSTMORTEM_DIR.glob("*.md"))
    if not files:
        print("No postmortems found.")
        return
    for f in files:
        print(f.name)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="L37 Postmortem Agent")
    sub = parser.add_subparsers(dest="cmd")

    p_detect = sub.add_parser("detect", help="Detect incidents in recent bets")
    p_detect.add_argument("--window", type=int, default=1, help="Look-back days")
    p_detect.set_defaults(func=_cmd_detect)

    p_run = sub.add_parser("run", help="Run postmortem on a JSON list of losing bets")
    p_run.add_argument("--losing-bets", required=True, help="Path to JSON file")
    p_run.set_defaults(func=_cmd_run)

    p_list = sub.add_parser("list", help="List written postmortems")
    p_list.set_defaults(func=_cmd_list)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
