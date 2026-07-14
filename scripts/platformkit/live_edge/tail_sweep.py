"""scripts.platformkit.live_edge.tail_sweep -- B2 tail/skew claim mining +
tail-bin calibration report. Ledgers one bundled tail_profile claim per
entity (NBA player, NBA team, MLB team) carrying the full quantile vector in
evidence, plus a P7-pattern pooled tail-bin realized-vs-predicted table.

Sole journal writer this cycle (per lane-spawn rails) -- do not run alongside
another claims-ledger-writing lane.

INVARIANTS: pandas/numpy + stdlib only. <=300 LOC. ASCII stdout. Never writes
data/registry/. No $/edge claims.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.live_edge import tails as tl

_REPORT_PATH = pathlib.Path("data/omni/live_edge/tails/TAIL_REPORT.md")
_LANE = "tail_sweep_v1"

BIN_EDGES = [0.0, 0.005, 0.01, 0.025, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90,
             0.95, 0.975, 0.99, 0.995, 1.0]


def _profile_claim(entity: str, entity_type: str, sport: str, stat_name: str,
                    m: dict, data_asof: str, source: str) -> dict:
    scope = {"sport": sport, "entity_type": entity_type, "entity_ids": [str(entity)],
              "context": {"stat": stat_name}}
    statement = f"{sport.upper()} {entity_type} {entity} {stat_name} tail/skew profile"
    if m.get("insufficient"):
        effect = {"verdict": "INSUFFICIENT_DATA"}
        evidence = {"n": m["n"], "floor": tl.MIN_N}
        lifecycle = "screened"
    else:
        effect = {
            "verdict": "TESTED", "breakout_prob": round(m["breakout_prob"], 4),
            "dud_prob": round(m["dud_prob"], 4), "skew": round(m["skew"], 4),
            "std": round(m["std"], 4), "median": round(m["median"], 4),
            "archetype": m["archetype"],
        }
        if "bench_tail_prob" in m:
            effect["bench_tail_prob"] = round(m["bench_tail_prob"], 4)
        evidence = {"n": m["n"], "quantiles": m["quantiles"], "source": source}
        lifecycle = "proposed"
    return {
        "statement": statement, "type": "distributional", "scope": scope,
        "topic": f"tails.{sport}.{stat_name}", "lifecycle": lifecycle,
        "effect": effect, "evidence": evidence,
        "provenance": {"created_by_lane": _LANE, "data_asof": data_asof},
        "links": {},
    }


def _tail_bin_check(fit_df: pd.DataFrame, test_df: pd.DataFrame, entity_col: str,
                     stat_col: str, fit_metrics: dict[str, dict]) -> pd.DataFrame:
    """Predicted (nominal quantile-band width) vs realized frequency, pooled
    across all entities, using each entity's FIT-half quantiles applied to
    its TEST-half rows (leak-free: fit/test never overlap, both inside
    discovery -- reserve is untouched)."""
    rows = []
    for lo, hi in zip(BIN_EDGES[:-1], BIN_EDGES[1:]):
        nominal = hi - lo
        realized_hits, total = 0, 0
        for e, g in test_df.groupby(entity_col, observed=True):
            m = fit_metrics.get(e)
            if m is None or m.get("insufficient"):
                continue
            q = m["quantiles"]
            lo_v = q.get(str(lo)) if lo > 0 else -np.inf
            hi_v = q.get(str(hi)) if hi < 1 else np.inf
            if lo_v is None or hi_v is None:
                continue
            vals = g[stat_col].to_numpy(dtype=float)
            realized_hits += int(np.sum((vals >= lo_v) & (vals < hi_v)))
            total += len(vals)
        realized = realized_hits / total if total else float("nan")
        rows.append({"bin": f"{lo*100:g}-{hi*100:g}%", "predicted": nominal,
                      "realized": realized, "n": total,
                      "ratio": (realized / nominal) if nominal and total else float("nan")})
    return pd.DataFrame(rows)


def run_sweep(base_dir=None, nba_box_source=None, mlb_source=None) -> dict:
    nba_box = tl.load_nba_player_box(nba_box_source)
    nba_disc, _ = tl.split_nba_discovery_reserve(nba_box)
    data_asof_nba = str(nba_disc["season"].max())

    mlb_team = tl.load_mlb_team_runs(mlb_source)
    mlb_disc, _ = tl.split_mlb_discovery_reserve(mlb_team)
    data_asof_mlb = str(pd.to_datetime(mlb_disc["date"]).dt.year.max())

    nba_player_metrics = tl.compute_tail_metrics(nba_disc, "player_id", "pts", min_col="min")
    nba_team_pts = nba_disc.groupby(["game_id", "team"], observed=True)["pts"].sum().reset_index()
    nba_team_metrics = tl.compute_tail_metrics(nba_team_pts, "team", "pts")
    mlb_team_metrics = tl.compute_tail_metrics(mlb_disc, "team", "runs")

    claims: list[dict] = []
    src_nba = str(tl.NBA_PLAYER_BOX_PATH)
    src_mlb = str(tl.MLB_TEAM_BOX_PATH)
    for pid, m in nba_player_metrics.items():
        claims.append(_profile_claim(pid, "player", "nba", "points", m, data_asof_nba, src_nba))
    for team, m in nba_team_metrics.items():
        claims.append(_profile_claim(team, "team", "nba", "points", m, data_asof_nba, src_nba))
    for team, m in mlb_team_metrics.items():
        claims.append(_profile_claim(team, "team", "mlb", "runs", m, data_asof_mlb, src_mlb))

    claims.append({
        "statement": "MLB player-grain tail claims are DATA-ABSENT: no per-player batting-line "
                      "store exists on disk (espn_boxscores.parquet is team-grain only).",
        "type": "structural", "scope": {"sport": "mlb"}, "topic": "tails.mlb.player_grain_absent",
    })

    # tail-bin calibration (fit/test halves inside discovery only)
    nba_fit, nba_test = tl.fit_test_halves(nba_disc)
    nba_fit_metrics = tl.compute_tail_metrics(nba_fit, "player_id", "pts")
    nba_bins = _tail_bin_check(nba_fit, nba_test, "player_id", "pts", nba_fit_metrics)

    mlb_fit, mlb_test = tl.fit_test_halves(mlb_disc)
    mlb_fit_metrics = tl.compute_tail_metrics(mlb_fit, "team", "runs")
    mlb_bins = _tail_bin_check(mlb_fit, mlb_test, "team", "runs", mlb_fit_metrics)

    claims_added, _ids = cl.add_claims_batch(claims, base_dir=base_dir)

    insufficient = sum(1 for m in {**nba_player_metrics, **nba_team_metrics, **mlb_team_metrics}.values()
                        if isinstance(m, dict) and m.get("insufficient"))
    result = {
        "nba_players_screened": len(nba_player_metrics),
        "nba_teams_screened": len(nba_team_metrics),
        "mlb_teams_screened": len(mlb_team_metrics),
        "insufficient_data": insufficient,
        "claims_built": len(claims),
        "claims_added": claims_added,
    }
    _write_report(result, nba_bins, mlb_bins, base_dir)
    return result


def _write_report(result: dict, nba_bins: pd.DataFrame, mlb_bins: pd.DataFrame, base_dir) -> None:
    path = _REPORT_PATH if base_dir is None else pathlib.Path(base_dir) / _REPORT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# B2 tail/skew report\n\n", "## Funnel arithmetic\n\n"]
    for k, v in result.items():
        lines.append(f"- {k}: {v}\n")

    lines.append("\n## Tail-bin calibration -- NBA player points (fit-half quantiles vs test-half realized)\n\n")
    lines.append("bin | predicted | realized | n | ratio (realized/predicted)\n---|---|---|---|---\n")
    for _, r in nba_bins.iterrows():
        lines.append(f"{r['bin']} | {r['predicted']:.4f} | {r['realized']:.4f} | {int(r['n'])} | {r['ratio']:.2f}\n")

    lines.append("\n## Tail-bin calibration -- MLB team runs (fit-half quantiles vs test-half realized)\n\n")
    lines.append("bin | predicted | realized | n | ratio (realized/predicted)\n---|---|---|---|---\n")
    for _, r in mlb_bins.iterrows():
        lines.append(f"{r['bin']} | {r['predicted']:.4f} | {r['realized']:.4f} | {int(r['n'])} | {r['ratio']:.2f}\n")

    combined = pd.concat([nba_bins.assign(sport="nba"), mlb_bins.assign(sport="mlb")])
    extreme = combined.dropna(subset=["ratio"]).sort_values("ratio", ascending=False).head(3)
    lines.append("\n## Top-3 under-dispersion fixes (highest realized/predicted ratio -> funnel-proposal candidates)\n\n")
    for _, r in extreme.iterrows():
        lines.append(f"- {r['sport']} bin {r['bin']}: ratio {r['ratio']:.2f} "
                       f"(realized {r['realized']:.4f} vs predicted {r['predicted']:.4f}, n={int(r['n'])})\n")

    path.write_text("".join(lines), encoding="ascii")
    print(f"[{_LANE}] wrote {path}")


def main() -> int:
    result = run_sweep()
    for k, v in result.items():
        print(f"[{_LANE}] {k}: {v}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
