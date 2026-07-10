"""Entry-timing study CLI (lane B1).

Measures, per sport x market, WHEN in the pregame timeline prices are softest
relative to information we already hold. Yardstick: CLV vs the same-feed close
(prob points). Calibration/CLV language only -- no ROI or profit claims.

  cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.execution.entry_timing.cli --sport mlb --market moneyline

Outputs: docs/research/entry_timing_2026-07-11.md (report) and
data/frontend/ops/timing_policy.json (machine-readable, composer-consumed).
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from scripts.platformkit.execution.entry_timing.assemble import (
    GAME_MARKETS, HORIZONS, ROOT, assemble_line_history, assemble_nba_parquet,
)
from scripts.platformkit.execution.entry_timing.study import (
    drift_decomposition, entry_clv, ingame_phase, leadlag_reuse,
)

SPORTS = ("nba", "mlb", "tennis", "soccer", "soccer_intl", "wnba", "npb", "kbo")
REPORT = ROOT / "docs" / "research" / "entry_timing_2026-07-11.md"
POLICY = ROOT / "data" / "frontend" / "ops" / "timing_policy.json"


def nearest_horizon(lead_h: float) -> str:
    return min(HORIZONS, key=lambda h: abs(h[1] / 3600.0 - lead_h))[0]


def derive_policy(drift_rows: list[dict], clv: dict | None,
                  leadlag_sport: dict | None) -> dict:
    """Best-evidence entry horizon + confidence tier from the three studies."""
    n_drift = max((r["n"] for r in drift_rows), default=0)
    ll_ok = bool(leadlag_sport) and any(
        (h.get("n") or 0) >= 30 for h in leadlag_sport.get("horizons", []))
    clv_ok = bool(clv) and clv.get("n", 0) >= 30
    ev = (n_drift >= 100) + ll_ok + clv_ok
    beats = (leadlag_sport or {}).get("horizons_model_beats_market") or []
    if beats:
        entry = beats[0]
        why = ("frozen model beats the CONTEMPORANEOUS price at this horizon "
               "(reused freshness_model_placement artifact)")
    elif clv_ok and (clv.get("clv_ci95_pp") or [0])[0] and clv["clv_ci95_pp"][0] > 0:
        entry = nearest_horizon(clv["median_entry_lead_h"])
        why = "observed paper entries beat the same-feed close at this median lead"
    else:
        entry = "last_pregame_tick"
        why = ("no horizon shows an information advantage over the "
               "contemporaneous price; late entry minimizes residual drift")
    conf = "HIGH" if ev >= 2 else ("MED" if ev == 1 else "LOW")
    return {"entry_horizon": entry, "confidence": conf, "rationale": why,
            "n_drift_events": n_drift, "n_paper_entries": (clv or {}).get("n", 0),
            "leadlag_available": bool(leadlag_sport), "provisional": ev < 2}


def md_drift(rows: list[dict]) -> list[str]:
    out = ["| horizon | n | mean abs move to close (pp) | signed continuation (pp) | 95% CI | label |",
           "|---|---|---|---|---|---|"]
    for r in rows:
        ci = r.get("signed_ci95")
        out.append("| {h} | {n} | {a} | {s} | {ci} | {lb} |".format(
            h=r["horizon"], n=r["n"], a=r.get("mean_abs_move_pp", "-"),
            s=r.get("signed_continuation_pp", "-"),
            ci=f"[{ci[0]}, {ci[1]}]" if ci else "-", lb=r.get("label", "")))
    return out


def run(sports: list[str], markets: list[str], max_days: int | None,
        report_path, policy_path) -> dict:
    leadlag = leadlag_reuse()
    policies: dict = {}
    lines = [
        "# Entry-timing study -- when are prices softest? (2026-07-11)",
        "",
        "Yardstick: CLV vs the SAME-FEED close, in probability points (pp).",
        "No ROI / profit claims; cross-venue CLV is basis, not edge. Honest",
        "UNDERPOWERED labels where n < 30. CIs are game-clustered bootstrap.",
        "Corpora: line_history consensus paths (multi-book, devigged, 5-min",
        "bins, stale-repeat filtered), NBA kalshi/PM tick parquet (tip times",
        "joined exactly from checkpoints), clv_ledger paper entries, and the",
        "REUSED freshness_model_placement artifact for model-vs-price lead/lag.",
        ""]
    for sport in sports:
        print(f"[entry_timing] {sport}: assembling paths...")
        stats: dict = {}
        paths = assemble_line_history(sport, markets=tuple(markets),
                                      max_days=max_days, stats=stats)
        lines.append(f"## {sport}")
        lines.append("")
        ll_sport = (leadlag.get("sports") or {}).get(sport)
        if not paths:
            reason = max((k for k in stats if k != "rows"),
                         key=lambda k: stats[k], default="no_rows")
            policies[sport] = {"status": "NO_COVERAGE",
                               "dominant_drop_reason": reason, "feed_stats": stats}
            lines += [f"NO_COVERAGE -- feed rows scanned: {stats.get('rows', 0)}; "
                      f"dominant drop reason: `{reason}` "
                      f"(no_devig={stats.get('no_devig')}, "
                      f"no_commence={stats.get('no_commence')}, "
                      f"out_of_window={stats.get('out_of_window')})", ""]
            continue
        for market in markets:
            mpaths = {k: v for k, v in paths.items() if k[1] == market}
            corpus_note = f"line_history consensus, {len(mpaths)} event-paths"
            if sport == "nba" and market == "moneyline":
                pq = assemble_nba_parquet()
                if len(pq) > len(mpaths):
                    mpaths, corpus_note = pq, (
                        f"NBA tick parquet (kalshi/PM, exact tips), {len(pq)} events; "
                        f"line_history had {len(paths)} paths (stale-filtered)")
            if not mpaths:
                continue
            drift = drift_decomposition(mpaths)
            clv = entry_clv({k: v for k, v in paths.items() if k[1] == market}, sport,
                            markets=(market,))
            pol = derive_policy(drift, clv, ll_sport)
            policies.setdefault(sport, {})[market] = pol
            lines += [f"### {market}  ({corpus_note})", "",
                      "**(a) price-drift decomposition**", ""]
            lines += md_drift(drift)
            lines += ["", "**(c) realized CLV of actual paper entries (within-feed)**", "",
                      "```json", json.dumps(clv, indent=1), "```", "",
                      f"**policy:** enter at `{pol['entry_horizon']}` "
                      f"(confidence {pol['confidence']}) -- {pol['rationale']}", ""]
        if ll_sport:
            lines += ["**(b) frozen-model vs contemporaneous price (REUSED artifact)**", "",
                      "```json", json.dumps(ll_sport, indent=1), "```", ""]
        if sport == "nba":
            ig = ingame_phase()
            if ig:
                lines += ["**in-game phase uncertainty (market Brier vs outcome)**", "",
                          "| phase | n games | market Brier |", "|---|---|---|"]
                lines += [f"| {r['phase']} | {r['n_games']} | {r['market_brier']} |"
                          for r in ig]
                lines.append("")
    policy_doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "study": "entry_timing_lane_B1",
        "yardstick": "CLV vs same-feed close (prob points); no ROI claims",
        "edge_claimed": False,
        "leadlag_source": leadlag.get("source"),
        "policies": policies,
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[entry_timing] report -> {report_path}")
    if policy_path:
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(json.dumps(policy_doc, indent=1), encoding="utf-8")
        print(f"[entry_timing] policy -> {policy_path}")
    return policy_doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Entry-timing study (CLV vs close)")
    ap.add_argument("--sport", default="all", help="sport or 'all'")
    ap.add_argument("--market", default="all", help="market or 'all'")
    ap.add_argument("--max-days", type=int, default=None)
    ap.add_argument("--report", default=str(REPORT))
    ap.add_argument("--policy", default=str(POLICY))
    ap.add_argument("--dry-run", action="store_true", help="compute, write nothing")
    a = ap.parse_args(argv)
    sports = list(SPORTS) if a.sport == "all" else [a.sport]
    markets = list(GAME_MARKETS) if a.market == "all" else [a.market]
    from pathlib import Path
    run(sports, markets, a.max_days,
        None if a.dry_run else Path(a.report),
        None if a.dry_run else Path(a.policy))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
