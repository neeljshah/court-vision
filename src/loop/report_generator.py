"""REPORT-GENERATOR -- compose atlases + model state into readable intelligence reports.

Four report types:
  1. PREGAME  -- per-game: matchup-relevant atlas sections (shot_profile vs opp
     defensive_scheme, usage_role, pace_fit, foul environment), the joint-sim
     projection + the top EV bets vs the lines.
  2. POSTGAME -- per-game: projected vs actual, which signals/atlases were right/wrong,
     CLV captured, residuals fed back to the error-miner.
  3. LEAGUE-TREND -- cross-team pace/efficiency/scheme trends from the team atlases.
  4. MODEL-ERROR -- the residual buckets (from error_miner) rendered as readable intel:
     where the model is systematically biased + the hypotheses queued from it.

Writes markdown to ``.planning/loop/reports/``. Read-only over the substrate + models.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .error_miner import ResidualBucket
from .signal import AsOfContext, Hypothesis
from .store import PointInTimeStore, entity_key

ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT / ".planning" / "loop" / "reports"

# Atlas sections consulted for pregame intel
_PREGAME_PLAYER_SECTIONS = [
    "shot_profile",
    "scoring_usage",
    "count_distributions",
    "quarter_shape",
    "foul_propensity",
    "playtypes",
    "clutch",
    "on_off_impact",
    "prop_calibration",
]
_PREGAME_TEAM_SECTIONS = [
    "defense_scheme",
    "ratings",
    "rebounding",
]

# Stat display names
_STAT_LABELS: Dict[str, str] = {
    "pts": "Points",
    "reb": "Rebounds",
    "ast": "Assists",
    "fg3m": "3-Pointers",
    "stl": "Steals",
    "blk": "Blocks",
    "tov": "Turnovers",
    "minutes": "Minutes",
    "winprob": "Win Prob",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_reports_dir() -> None:
    """Create the reports output directory if it does not exist."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _report_path(name: str) -> Path:
    """Return the canonical path for a named report file."""
    _ensure_reports_dir()
    return REPORTS_DIR / name


def _write(path: Path, content: str, *, dry_run: bool) -> Path:
    """Write *content* to *path* unless *dry_run*; always return the path."""
    if not dry_run:
        path.write_text(content, encoding="utf-8")
    return path


def _utc_stamp() -> str:
    return _dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")


def _pct(v: Optional[float], decimals: int = 1) -> str:
    if v is None:
        return "N/A"
    return f"{v * 100:.{decimals}f}%"


def _fmt(v: Any, decimals: int = 2) -> str:
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.{decimals}f}"
    return str(v)


def _sign(v: float) -> str:
    return "+" if v >= 0 else ""


def _read_atlas_safe(store: PointInTimeStore, entity_type: str, entity_id: Any,
                     section: str, as_of: str) -> Optional[Dict[str, Any]]:
    """Leak-safe atlas read; returns None if section absent."""
    try:
        return store.read_atlas(entity_type, entity_id, section, as_of)
    except Exception:
        return None


def _section_md(section_name: str, data: Optional[Dict[str, Any]]) -> str:
    """Render one atlas section as a compact markdown block."""
    if data is None:
        return f"*{section_name}: not available*\n"
    lines: List[str] = [f"**{section_name}**"]
    cv_fields = data.pop("_cv_fields", {}) if isinstance(data, dict) else {}
    for k, v in (data.items() if isinstance(data, dict) else {}.items()):
        if k.startswith("_"):
            continue
        if isinstance(v, dict):
            inner = ", ".join(f"{ik}={_fmt(iv)}" for ik, iv in v.items()
                              if not str(ik).startswith("_"))
            lines.append(f"  - {k}: {{{inner}}}")
        elif isinstance(v, list):
            lines.append(f"  - {k}: [{', '.join(str(i) for i in v[:5])}{'…' if len(v) > 5 else ''}]")
        else:
            lines.append(f"  - {k}: {_fmt(v)}")
    # CV slots (reserved, may have values if filled)
    for slot_name, slot in (cv_fields.items() if isinstance(cv_fields, dict) else {}.items()):
        val = slot.get("value") if isinstance(slot, dict) else None
        label = f"CV:{slot_name}"
        lines.append(f"  - {label}: {_fmt(val) if val is not None else '*reserved*'}")
    if isinstance(data, dict):
        data["_cv_fields"] = cv_fields  # restore after pop
    return "\n".join(lines) + "\n"


def _lines_table(lines: List[Dict[str, Any]]) -> str:
    """Format the optional sportsbook lines list as a markdown table."""
    if not lines:
        return "*No lines provided.*\n"
    rows = ["| Stat | Line | Proj | EV | Kelly |",
            "|------|------|------|----|-------|"]
    for entry in lines:
        stat = entry.get("stat", "?")
        line = _fmt(entry.get("line"))
        proj = _fmt(entry.get("projection"))
        ev = _fmt(entry.get("ev"))
        kelly = _fmt(entry.get("kelly"))
        rows.append(f"| {stat} | {line} | {proj} | {ev} | {kelly} |")
    return "\n".join(rows) + "\n"


# ---------------------------------------------------------------------------
# 1. PREGAME REPORT
# ---------------------------------------------------------------------------

def pregame_report(
    game_ctx: AsOfContext,
    *,
    store: PointInTimeStore,
    lines: Optional[List[Dict[str, Any]]] = None,
    dry_run: bool = False,
) -> Path:
    """Compose + write the per-game pregame intelligence report; return its path.

    Reads atlas sections for each player in ``game_ctx.extra["roster"]`` (list of
    player_id ints), then the home/away team atlases, and appends a bet-surface
    section from *lines* (projection + EV + Kelly if provided). Missing sections
    are noted as N/A rather than crashing. If the simulator result is present in
    ``game_ctx.extra["simulation"]`` it is rendered inline.

    Args:
        game_ctx: the decision context; ``game_ctx.extra`` may carry
                  ``"roster"`` (List[int]), ``"simulation"`` (JointDistribution-like
                  dict) and ``"hypotheses"`` (List[Hypothesis]).
        store:    the bound :class:`PointInTimeStore`.
        lines:    optional list of ``{stat, line, projection, ev, kelly}`` dicts.
        dry_run:  if True, builds but does not write to disk.

    Returns:
        Path to the written (or would-be-written) markdown file.
    """
    as_of = game_ctx.as_of_iso()
    game_date = game_ctx.game_date or as_of
    home = game_ctx.team or "HOME"
    away = game_ctx.opp or "AWAY"
    game_id = game_ctx.game_id or "UNKNOWN"
    fname = f"pregame_{game_date}_{home}_vs_{away}.md"

    roster: List[int] = game_ctx.extra.get("roster", [])
    simulation: Optional[Dict[str, Any]] = game_ctx.extra.get("simulation")
    hypotheses: List[Any] = game_ctx.extra.get("hypotheses", [])

    parts: List[str] = []

    # --- header ---
    parts.append(f"# Pregame Intelligence Report")
    parts.append(f"**Game:** {home} vs {away}  |  **Date:** {game_date}  "
                 f"|  **ID:** {game_id}  |  **Generated:** {_utc_stamp()}\n")

    # --- team atlases ---
    parts.append("## Team Intelligence\n")
    for tri, role in [(home, "Home"), (away, "Away")]:
        parts.append(f"### {role}: {tri}\n")
        for sec in _PREGAME_TEAM_SECTIONS:
            data = _read_atlas_safe(store, "team", tri, sec, as_of)
            parts.append(_section_md(sec, data))
        parts.append("")

    # --- player atlases ---
    if roster:
        parts.append("## Player Atlas Snapshots\n")
        for pid in roster[:20]:  # cap at 20 players for readability
            parts.append(f"### Player {pid}\n")
            for sec in _PREGAME_PLAYER_SECTIONS:
                data = _read_atlas_safe(store, "player", pid, sec, as_of)
                if data is not None:
                    parts.append(_section_md(sec, data))
            parts.append("")
    else:
        parts.append("*Roster not provided — player atlas sections skipped.*\n")

    # --- simulation projection ---
    parts.append("## Joint-Sim Projection\n")
    if simulation:
        pmarginals = simulation.get("player_marginals", {})
        if pmarginals:
            rows = ["| Player | Stat | p50 | p25 | p75 |",
                    "|--------|------|-----|-----|-----|"]
            for pid_key, marginals in list(pmarginals.items())[:20]:
                for stat, dist in (marginals.items() if isinstance(marginals, dict) else {}.items()):
                    p25 = _fmt(dist.get("p25") if isinstance(dist, dict) else None)
                    p50 = _fmt(dist.get("p50") if isinstance(dist, dict) else None)
                    p75 = _fmt(dist.get("p75") if isinstance(dist, dict) else None)
                    rows.append(f"| {pid_key} | {stat} | {p50} | {p25} | {p75} |")
            parts.append("\n".join(rows) + "\n")
        team_totals = simulation.get("team_totals", {})
        if team_totals:
            parts.append(f"**Team totals:** {json.dumps(team_totals, default=str)}\n")
        final_score = simulation.get("final_score", {})
        if final_score:
            parts.append(f"**Final-score projection:** {json.dumps(final_score, default=str)}\n")
    else:
        parts.append("*Simulator result not provided (pass `game_ctx.extra[\"simulation\"]`).*\n")

    # --- bet surface ---
    parts.append("## Top EV Bets vs Lines\n")
    parts.append(_lines_table(lines or []))

    # --- active hypotheses ---
    if hypotheses:
        parts.append("## Active Hypotheses\n")
        for h in hypotheses[:10]:
            name = getattr(h, "name", str(h))
            stmt = getattr(h, "statement", "")
            pri = getattr(h, "priority", "?")
            parts.append(f"- **[{pri}] {name}**: {stmt}")
        parts.append("")

    content = "\n".join(parts)
    path = _report_path(fname)
    return _write(path, content, dry_run=dry_run)


# ---------------------------------------------------------------------------
# 2. POSTGAME REPORT
# ---------------------------------------------------------------------------

def postgame_report(
    game_id: str,
    game_date: str,
    *,
    store: PointInTimeStore,
    dry_run: bool = False,
) -> Path:
    """Compose + write the per-game postgame report (projected vs actual + CLV).

    Reads the logged predictions and actuals for *game_id* from the store (stored
    under the field ``"postgame__{game_id}"`` by the prediction tracker when
    available) and renders a signal-accuracy + CLV table. Falls back to placeholder
    text when the tracking artifacts are absent (the prediction_tracker stores its
    files as on-disk JSON that the report-generator reads via the store or directly).

    Args:
        game_id:   NBA game id (e.g. ``"0022401001"``).
        game_date: ISO date of the game.
        store:     the bound :class:`PointInTimeStore`.
        dry_run:   if True, builds but does not write to disk.

    Returns:
        Path to the written (or would-be-written) markdown file.
    """
    fname = f"postgame_{game_date}_{game_id}.md"
    as_of = game_date

    # Attempt to read logged prediction/actual data from the store
    # (written by prediction_tracker.log_prediction / score_predictions)
    pred_data = store.read("game:" + game_id, "prediction_summary", as_of)
    actual_data = store.read("game:" + game_id, "actual_summary", as_of)

    # Also attempt to read from on-disk predictions if present
    pred_dir = ROOT / "data" / "predictions"
    pred_files = sorted(pred_dir.glob(f"{game_date}_*.json")) if pred_dir.exists() else []

    parts: List[str] = []

    # --- header ---
    parts.append("# Postgame Intelligence Report")
    parts.append(f"**Game ID:** {game_id}  |  **Date:** {game_date}  "
                 f"|  **Generated:** {_utc_stamp()}\n")

    # --- projected vs actual ---
    parts.append("## Projected vs Actual\n")
    if pred_data and actual_data:
        _render_pred_vs_actual(parts, pred_data, actual_data)
    elif pred_files:
        # Parse first matching prediction file on disk
        try:
            pf_data = json.loads(pred_files[0].read_text(encoding="utf-8"))
            parts.append(f"*Source: {pred_files[0].name}*\n")
            parts.append("```json")
            parts.append(json.dumps(pf_data, indent=2, default=str)[:2000])
            parts.append("```\n")
        except Exception as exc:
            parts.append(f"*Could not parse prediction file: {exc}*\n")
    else:
        parts.append("*Prediction data not found in store or data/predictions/. "
                     "Run prediction_tracker.score_predictions() and write back to the store.*\n")

    # --- CLV section ---
    parts.append("## Closing-Line Value (CLV)\n")
    clv_data = store.read("game:" + game_id, "clv_summary", as_of)
    if clv_data and isinstance(clv_data, dict):
        rows = ["| Stat | Direction | CLV (pp) | Result |",
                "|------|-----------|----------|--------|"]
        for stat, info in clv_data.items():
            if not isinstance(info, dict):
                continue
            direction = info.get("direction", "?")
            clv_pp = _fmt(info.get("clv_pp"))
            result = info.get("result", "?")
            rows.append(f"| {stat} | {direction} | {clv_pp} | {result} |")
        parts.append("\n".join(rows) + "\n")
    else:
        parts.append("*CLV data not available — needs settlement.py + clv_predictor.py output "
                     "written to the store.*\n")

    # --- residual feed-forward ---
    parts.append("## Residuals (feed to error-miner)\n")
    resid_data = store.read("game:" + game_id, "residuals", as_of)
    if resid_data and isinstance(resid_data, dict):
        rows = ["| Player | Stat | Pred | Actual | Residual |",
                "|--------|------|------|--------|----------|"]
        for player_key, player_resids in resid_data.items():
            if not isinstance(player_resids, dict):
                continue
            for stat, r in player_resids.items():
                if not isinstance(r, dict):
                    continue
                rows.append(f"| {player_key} | {stat} | {_fmt(r.get('pred'))} | "
                             f"{_fmt(r.get('actual'))} | {_fmt(r.get('resid'))} |")
        parts.append("\n".join(rows) + "\n")
    else:
        parts.append("*Residuals not stored — write `residuals` field via the prediction "
                     "tracker after settle_day() completes.*\n")

    # --- signal/atlas accuracy ---
    parts.append("## Which Signals/Atlases Were Predictive?\n")
    signal_acc = store.read("game:" + game_id, "signal_accuracy", as_of)
    if signal_acc and isinstance(signal_acc, dict):
        rows = ["| Signal | Stat | Direction | Hit |",
                "|--------|------|-----------|-----|"]
        for sig, info in signal_acc.items():
            if not isinstance(info, dict):
                continue
            rows.append(f"| {sig} | {info.get('stat','?')} | "
                        f"{info.get('direction','?')} | {'Y' if info.get('hit') else 'N'} |")
        parts.append("\n".join(rows) + "\n")
    else:
        parts.append("*Signal accuracy data not yet available for this game.*\n")

    content = "\n".join(parts)
    path = _report_path(fname)
    return _write(path, content, dry_run=dry_run)


def _render_pred_vs_actual(
    parts: List[str],
    pred_data: Dict[str, Any],
    actual_data: Dict[str, Any],
) -> None:
    """Append a projected-vs-actual table to *parts*."""
    rows = ["| Player | Stat | Projected | Actual | Error |",
            "|--------|------|-----------|--------|-------|"]
    for player_key in sorted(set(pred_data.keys()) | set(actual_data.keys())):
        preds = pred_data.get(player_key, {})
        actuals = actual_data.get(player_key, {})
        for stat in sorted(set(preds.keys()) | set(actuals.keys())):
            proj = preds.get(stat)
            actual = actuals.get(stat)
            err = (proj - actual) if (proj is not None and actual is not None) else None
            rows.append(f"| {player_key} | {stat} | {_fmt(proj)} | "
                        f"{_fmt(actual)} | {_fmt(err)} |")
    parts.append("\n".join(rows) + "\n")


# ---------------------------------------------------------------------------
# 3. LEAGUE-TREND REPORT
# ---------------------------------------------------------------------------

def league_trend_report(
    as_of: str,
    *,
    store: PointInTimeStore,
    dry_run: bool = False,
) -> Path:
    """Compose + write the cross-team league-trend report from team atlases.

    Reads ``defense_scheme``, ``ratings``, and ``rebounding`` for all 30 teams
    (those present in the store as of *as_of*) and surfaces:
      - Pace/efficiency sorted table
      - Defensive-scheme distribution (drop / switch / blitz)
      - Rebounding leaders
      - Any team whose atlas data is stale or missing (coverage gap).

    Args:
        as_of:  ISO date (the leak boundary for all reads).
        store:  the bound :class:`PointInTimeStore`.
        dry_run: if True, builds but does not write to disk.

    Returns:
        Path to the written (or would-be-written) markdown file.
    """
    fname = f"league_trend_{as_of}.md"

    # Discover teams present in the store
    teams: List[str] = []
    with store._lock:
        for (entity, field_) in store._index.keys():
            if entity.startswith("team:") and field_ in _PREGAME_TEAM_SECTIONS:
                tri = entity[len("team:"):]
                if tri not in teams:
                    teams.append(tri)
    teams.sort()

    # Collect per-team data
    team_data: Dict[str, Dict[str, Any]] = {}
    for tri in teams:
        entry: Dict[str, Any] = {}
        for sec in _PREGAME_TEAM_SECTIONS:
            data = _read_atlas_safe(store, "team", tri, sec, as_of)
            if data is not None:
                entry[sec] = data
        if entry:
            team_data[tri] = entry

    parts: List[str] = []

    # --- header ---
    parts.append("# League-Trend Intelligence Report")
    parts.append(f"**As-of:** {as_of}  |  **Teams in store:** {len(team_data)} / 30  "
                 f"|  **Generated:** {_utc_stamp()}\n")

    # --- pace / efficiency table ---
    parts.append("## Pace + Efficiency\n")
    pace_rows: List[Dict[str, Any]] = []
    for tri, data in team_data.items():
        ratings = data.get("ratings", {})
        pace_rows.append({
            "team": tri,
            "off_rtg": ratings.get("off_rtg"),
            "def_rtg": ratings.get("def_rtg"),
            "net_rtg": ratings.get("net_rtg"),
            "pace": ratings.get("pace"),
        })
    # Sort by net_rtg descending (None last)
    pace_rows.sort(key=lambda r: (r["net_rtg"] is None, -(r["net_rtg"] or 0)))
    if pace_rows:
        tbl = ["| Rank | Team | OffRtg | DefRtg | NetRtg | Pace |",
               "|------|------|--------|--------|--------|------|"]
        for rank, row in enumerate(pace_rows, 1):
            tbl.append(f"| {rank} | {row['team']} | {_fmt(row['off_rtg'])} | "
                       f"{_fmt(row['def_rtg'])} | {_fmt(row['net_rtg'])} | "
                       f"{_fmt(row['pace'])} |")
        parts.append("\n".join(tbl) + "\n")
    else:
        parts.append("*No ratings data available in store.*\n")

    # --- defensive scheme distribution ---
    parts.append("## Defensive-Scheme Distribution\n")
    scheme_counts: Dict[str, int] = {}
    scheme_rows: List[str] = ["| Team | Primary Scheme | Drop% | Switch% | Blitz% |",
                               "|------|----------------|-------|---------|--------|"]
    for tri, data in sorted(team_data.items()):
        ds = data.get("defense_scheme", {})
        if not ds:
            continue
        primary = ds.get("primary_scheme", "unknown")
        scheme_counts[primary] = scheme_counts.get(primary, 0) + 1
        drop = _fmt(ds.get("drop_rate"), 1)
        switch = _fmt(ds.get("switch_rate"), 1)
        blitz = _fmt(ds.get("blitz_rate"), 1)
        scheme_rows.append(f"| {tri} | {primary} | {drop} | {switch} | {blitz} |")
    if len(scheme_rows) > 2:
        parts.append("\n".join(scheme_rows) + "\n")
        summary = ", ".join(f"{s}: {n}" for s, n in
                            sorted(scheme_counts.items(), key=lambda x: -x[1]))
        parts.append(f"*Scheme distribution: {summary}*\n")
    else:
        parts.append("*No defense_scheme data in store.*\n")

    # --- rebounding leaders ---
    parts.append("## Rebounding Leaders\n")
    reb_rows: List[Dict[str, Any]] = []
    for tri, data in team_data.items():
        reb = data.get("rebounding", {})
        if not reb:
            continue
        reb_rows.append({
            "team": tri,
            "off_reb_pct": reb.get("off_reb_pct"),
            "def_reb_pct": reb.get("def_reb_pct"),
            "total_reb_pg": reb.get("total_reb_pg"),
        })
    reb_rows.sort(key=lambda r: (r["total_reb_pg"] is None, -(r["total_reb_pg"] or 0)))
    if reb_rows:
        tbl = ["| Rank | Team | OReb% | DReb% | RebPG |",
               "|------|------|-------|-------|-------|"]
        for rank, row in enumerate(reb_rows, 1):
            tbl.append(f"| {rank} | {row['team']} | {_pct(row['off_reb_pct'])} | "
                       f"{_pct(row['def_reb_pct'])} | {_fmt(row['total_reb_pg'])} |")
        parts.append("\n".join(tbl) + "\n")
    else:
        parts.append("*No rebounding data in store.*\n")

    # --- coverage gaps ---
    parts.append("## Coverage Gaps\n")
    all_30 = {
        "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
        "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
        "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
    }
    missing = sorted(all_30 - set(team_data.keys()))
    stale: List[str] = []
    for tri, data in team_data.items():
        for sec, sdata in data.items():
            if isinstance(sdata, dict):
                sec_as_of = sdata.get("_prov_as_of") or sdata.get("as_of")
                if sec_as_of and sec_as_of < as_of:
                    stale.append(f"{tri}/{sec} (as_of={sec_as_of})")
    if missing:
        parts.append(f"**Missing teams ({len(missing)}):** {', '.join(missing)}\n")
    else:
        parts.append("All 30 teams present in store.\n")
    if stale:
        parts.append(f"**Stale sections ({len(stale)}):** " + ", ".join(stale[:20]) + "\n")

    content = "\n".join(parts)
    path = _report_path(fname)
    return _write(path, content, dry_run=dry_run)


# ---------------------------------------------------------------------------
# 4. MODEL-ERROR REPORT
# ---------------------------------------------------------------------------

def model_error_report(
    buckets: List[ResidualBucket],
    *,
    hypotheses: Optional[List[Hypothesis]] = None,
    dry_run: bool = False,
) -> Path:
    """Render the error-miner residual buckets as a readable model-error report.

    Surfaces:
      - Sorted bias table (largest |mean_resid| first) with stat / dimension-slice /
        sample-size / mean residual / direction / p-value.
      - Grouped by stat section so analysts can see where the model is
        systematically over or under across slices.
      - Hypotheses queued from the intel-scanner (if provided).
      - A brief diagnosis narrative per stat based on sign and magnitude.

    Args:
        buckets:     residual buckets from :func:`error_miner.bucket_residuals`.
        hypotheses:  optional list from :func:`error_miner.mine` / ``intel_scan``.
        dry_run:     if True, builds but does not write to disk.

    Returns:
        Path to the written (or would-be-written) markdown file.
    """
    stamp = _dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname = f"model_error_{stamp}.md"

    parts: List[str] = []

    # --- header ---
    parts.append("# Model-Error Intelligence Report")
    parts.append(f"**Generated:** {_utc_stamp()}  |  "
                 f"**Buckets:** {len(buckets)}  |  "
                 f"**Hypotheses queued:** {len(hypotheses or [])}\n")

    # --- sorted bias table ---
    parts.append("## Residual Bias Summary (sorted by |mean|)\n")
    if buckets:
        sorted_buckets = sorted(buckets, key=lambda b: abs(b.mean_resid), reverse=True)
        tbl = ["| Stat | Slice | n | MeanResid | StdResid | p-value | Bias Dir |",
               "|------|-------|---|-----------|----------|---------|----------|"]
        for b in sorted_buckets:
            dims_str = " / ".join(f"{k}={v}" for k, v in b.dims.items())
            direction = "OVER" if b.mean_resid > 0 else "UNDER"
            p_str = f"{b.p_value:.4f}" if b.p_value is not None else "N/A"
            tbl.append(f"| {b.stat} | {dims_str} | {b.n} | "
                       f"{_sign(b.mean_resid)}{_fmt(b.mean_resid)} | "
                       f"{_fmt(b.std_resid)} | {p_str} | **{direction}** |")
        parts.append("\n".join(tbl) + "\n")
    else:
        parts.append("*No residual buckets available — run error_miner.bucket_residuals().*\n")

    # --- per-stat grouped analysis ---
    parts.append("## Per-Stat Analysis\n")
    stats_seen: Dict[str, List[ResidualBucket]] = {}
    for b in (buckets or []):
        stats_seen.setdefault(b.stat, []).append(b)

    for stat, stat_buckets in sorted(stats_seen.items()):
        label = _STAT_LABELS.get(stat, stat.upper())
        total_n = sum(b.n for b in stat_buckets)
        weighted_bias = (sum(b.mean_resid * b.n for b in stat_buckets) / total_n
                         if total_n > 0 else 0.0)
        sig_buckets = [b for b in stat_buckets if b.p_value < 0.05]
        direction = "over-predicting" if weighted_bias > 0 else "under-predicting"
        magnitude = "severely" if abs(weighted_bias) > 1.0 else "moderately" if abs(weighted_bias) > 0.3 else "mildly"

        parts.append(f"### {label} (`{stat}`)\n")
        parts.append(f"- Weighted bias: {_sign(weighted_bias)}{_fmt(weighted_bias)} "
                     f"({magnitude} {direction})")
        parts.append(f"- Significant slices (p<0.05): {len(sig_buckets)} / {len(stat_buckets)}")
        if sig_buckets:
            worst = max(sig_buckets, key=lambda b: abs(b.mean_resid))
            worst_dims = " / ".join(f"{k}={v}" for k, v in worst.dims.items())
            parts.append(f"- Worst slice: [{worst_dims}] mean={_sign(worst.mean_resid)}"
                         f"{_fmt(worst.mean_resid)}, n={worst.n}")
        parts.append("")

    # --- hypotheses ---
    if hypotheses:
        parts.append("## Hypotheses Queued from Intel-Scanner\n")
        tbl = ["| Priority | Name | Target | Scope | Statement |",
               "|----------|------|--------|-------|-----------|"]
        for h in sorted(hypotheses, key=lambda x: getattr(x, "priority", "P2")):
            pri = getattr(h, "priority", "?")
            name = getattr(h, "name", "?")
            target = getattr(h, "target", "?")
            scope = getattr(h, "scope", "?")
            stmt = getattr(h, "statement", "")
            tbl.append(f"| {pri} | {name} | {target} | {scope} | {stmt} |")
        parts.append("\n".join(tbl) + "\n")

        # Also render rationales for top-5
        parts.append("### Rationales (top 5)\n")
        for h in sorted(hypotheses, key=lambda x: getattr(x, "priority", "P2"))[:5]:
            name = getattr(h, "name", "?")
            rationale = getattr(h, "rationale", "")
            atlas_fields = getattr(h, "atlas_fields", [])
            parts.append(f"**{name}**: {rationale}")
            if atlas_fields:
                parts.append(f"  *Reads atlas:* {', '.join(atlas_fields)}")
            parts.append("")
    else:
        parts.append("## Hypotheses Queued from Intel-Scanner\n")
        parts.append("*None provided — pass `hypotheses=error_miner.mine()` to populate.*\n")

    content = "\n".join(parts)
    path = _report_path(fname)
    return _write(path, content, dry_run=dry_run)
