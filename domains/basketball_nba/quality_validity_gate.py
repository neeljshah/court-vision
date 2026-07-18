"""3a PREDICTIVE-VALIDITY GATE (core) -- shooter_quality_v1 vs naive composite.

Implements EXACTLY basketball_truth_spec.json "validation.predictive_validity_gate".
Pre-registered, walk-forward, leak-free. Binding honest-null clause: if naive
wins OR the delta CI includes 0, NAIVE STAYS CANONICAL and the richer index is
REJECT-logged with the exact numbers -- that is a SUCCESS, not a failure.
Claims emission lives in quality_validity_gate_claims.py (kept separate to
stay under the 300-LOC/file cap); quality_claim_builders.write_verdict()
persists VERDICT_PATH for that lane's gate claim to cite as provenance.

Design (spec 3a):
  - 4 monthly cutoffs T in 2024-25: 2024-12-01, 2025-01-01, 2025-02-01, 2025-03-01.
  - At each T, build BOTH rankings using ONLY data dated < T:
      * naive rank: 0.55*TS% + 0.30*eFG% + 0.15*FT%, recomputed from pre-T
        boxscore rows only (leak-free).
      * shooter_quality_v1 rank: EFFICIENCY/VOLUME pillars recomputed from
        pre-T boxscore rows; DIFFICULTY/GRAVITY pillars use the season-level
        atlas STYLE fields (style descriptors, far more stable than
        efficiency within a season) -- this is the spec's declared caveat,
        not a leak of the target (TS%).
  - Target: realized TS% over [T, T+30d], restricted to players with >=8
    shooting games in that forward window, on the 329-qualifier pool.
  - Comparison: Spearman rho(pre-T rank, realized future TS%) per cutoff,
    averaged across cutoffs. Paired bootstrap (cluster by player) on
    rho(shooter_quality_v1) - rho(naive); richer index wins ONLY if that
    delta's CI excludes 0 in its favor.
  - 2nd corpus: 2025-26 partial, cutoff 2025-12-01 -> forward 30d, out-of-
    season replication (sign must hold).
  - Floors: >=8 forward shooting games/player; >=20 games & >=200 FGA in the
    pre-T pool; a cutoff used only if >=100 qualifying players clear both.

CLI:
    python -m domains.basketball_nba.quality_validity_gate
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from domains.basketball_nba.quality_indices import (
    NAIVE_WEIGHTS,
    PILLAR_FACTORS,
    QUALIFY_MIN_FGA,
    QUALIFY_MIN_GAMES,
    SHOOTER_WEIGHTS,
    _parse_struct,
    load_atlas,
    load_boxscores,
)
from domains.basketball_nba.quality_indices_score import _pillar_score, percentile_rank
from domains.basketball_nba.quality_validity_stats import (
    paired_bootstrap_delta,
    spearman as _spearman,
    top_decile_diagnostic,
)

CUTOFFS_2024_25 = ["2024-12-01", "2025-01-01", "2025-02-01", "2025-03-01"]
REPLICATION_CUTOFF = "2025-12-01"
FORWARD_DAYS = 30
MIN_FORWARD_GAMES = 8
MIN_PLAYERS_PER_CUTOFF = 100


def _agg_pre_t(rows: pd.DataFrame) -> pd.DataFrame:
    """Sum pre-T box counts per player_id ONLY (never player_id+player_name --
    see quality_indices.aggregate_season docstring for why: the same
    player_id carries inconsistent name spellings across dates in
    player_boxscores.parquet, and grouping on both columns splits one
    player's games into two rows -- the source of the duplicate player_id
    that later crashes percentile_rank's .loc assignment once re-indexed."""
    g = rows.sort_values("date").groupby("player_id", as_index=False).agg(
        player_name=("player_name", "last"),
        games=("game_id", "nunique"),
        fgm=("fgm", "sum"), fga=("fga", "sum"),
        fg3m=("fg3m", "sum"), fg3a=("fg3a", "sum"),
        ftm=("ftm", "sum"), fta=("fta", "sum"),
        pts=("pts", "sum"),
    )
    g["fga_pg"] = g["fga"] / g["games"]
    g["fg3a_pg"] = g["fg3a"] / g["games"]
    g["efg_pct"] = (g["fgm"] + 0.5 * g["fg3m"]) / g["fga"].replace(0, pd.NA)
    g["ts_pct"] = g["pts"] / (2 * (g["fga"] + 0.44 * g["fta"])).replace(0, pd.NA)
    g["ft_pct"] = g["ftm"] / g["fta"].replace(0, pd.NA)
    g["naive_comp"] = (
        NAIVE_WEIGHTS["ts_pct"] * g["ts_pct"]
        + NAIVE_WEIGHTS["efg_pct"] * g["efg_pct"]
        + NAIVE_WEIGHTS["ft_pct"] * g["ft_pct"]
    )
    return g


def _forward_ts(rows: pd.DataFrame) -> pd.DataFrame:
    g = rows.groupby("player_id", as_index=False).agg(
        fwd_games=("game_id", "nunique"),
        fga=("fga", "sum"), fta=("fta", "sum"), pts=("pts", "sum"),
    )
    g["realized_ts_pct"] = g["pts"] / (2 * (g["fga"] + 0.44 * g["fta"])).replace(0, pd.NA)
    return g


def _style_pillars_asof(pool_pids: pd.Series) -> pd.DataFrame:
    """DIFFICULTY / GRAVITY style-share pillars from the season-level atlas
    (spec caveat: atlas is a season aggregate; style shares -- playtype mix,
    gravity_score -- are far more stable within-season than efficiency, so
    using the same-season atlas structure fields for a mid-season cutoff is
    the declared leak-free-adjacent approximation; efficiency/volume are
    recomputed exactly pre-T from boxscores, never taken from atlas)."""
    csp = load_atlas("catch_shoot_vs_pullup").set_index("player_id")
    sg = load_atlas("spacing_gravity").set_index("player_id")
    sc = load_atlas("scoring_creation").set_index("player_id")

    def col(df, pid, c, default=None):
        if pid not in df.index or c not in df.columns:
            return default
        return df.loc[pid, c]

    rows = []
    for pid in pool_pids:
        pull_up = _parse_struct(col(csp, pid, "pull_up", {}))
        time_to_shot = _parse_struct(col(csp, pid, "time_to_shot", {}))
        off_dribble_3 = _parse_struct(col(csp, pid, "off_dribble_3", {}))
        cs_grav = _parse_struct(col(sg, pid, "cs_gravity", {}))
        pg = _parse_struct(col(sg, pid, "playtypes_gravity", {}))
        rows.append({
            "player_id": pid,
            "pullup_combined_freq": pull_up.get("pullup_combined_freq_pct"),
            "pullup_pnr_ppp": pull_up.get("pullup_pnr_handler_ppp"),
            "late_clock_shots_pg": time_to_shot.get("late_clock_shots_pg"),
            "unassisted_share_3pm": col(sc, pid, "unassisted_share_3pm"),
            "off_dribble_3_proxy": off_dribble_3.get("off_screen_freq_pct"),
            "gravity_score": col(sg, pid, "gravity_score"),
            "cs_gravity_efg": cs_grav.get("catch_shoot_efg_pct"),
            "spotup_ppp": pg.get("spotup_ppp"),
        })
    out = pd.DataFrame(rows).set_index("player_id")
    for c in out.columns:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def rank_at_cutoff(box: pd.DataFrame, cutoff: str) -> dict[str, Any] | None:
    """Build both pre-T rankings + forward realized TS%, leak-free.

    Returns None if the cutoff fails the >=100-qualifying-players floor.
    """
    t0 = pd.Timestamp(cutoff)
    t1 = t0 + pd.Timedelta(days=FORWARD_DAYS)

    pre = box[box["date"] < t0]
    pool_pre = _agg_pre_t(pre)
    qual = pool_pre[(pool_pre["games"] >= QUALIFY_MIN_GAMES) & (pool_pre["fga"] >= QUALIFY_MIN_FGA)].copy()
    if len(qual) < MIN_PLAYERS_PER_CUTOFF:
        return None

    fwd_rows = box[(box["date"] >= t0) & (box["date"] < t1)]
    fwd = _forward_ts(fwd_rows)
    fwd = fwd[fwd["fwd_games"] >= MIN_FORWARD_GAMES]

    merged = qual.merge(fwd[["player_id", "fwd_games", "realized_ts_pct"]], on="player_id", how="inner")
    if len(merged) < MIN_PLAYERS_PER_CUTOFF:
        return None

    style = _style_pillars_asof(merged["player_id"])
    merged = merged.set_index("player_id")
    for c in style.columns:
        merged[c] = style[c]
    merged["fga_per_game"] = merged["fga"] / merged["games"]
    merged["fg3a_per_game"] = merged["fg3a"] / merged["games"]

    # naive pre-T rank (exact, leak-free: pre-T boxscore only)
    merged["naive_pctile"] = percentile_rank(merged["naive_comp"])

    # shooter_quality_v1 pre-T rank: EFFICIENCY/VOLUME from pre-T boxscore;
    # DIFFICULTY/GRAVITY from same-season atlas style shares (declared caveat)
    pct = pd.DataFrame(index=merged.index)
    pct["ts_pct"] = percentile_rank(merged["ts_pct"])
    pct["efg_pct"] = percentile_rank(merged["efg_pct"])
    pct["shot_quality_ts"] = pct["ts_pct"]  # no pre-T atlas efficiency substitute; use boxscore TS%
    for f in ("pullup_combined_freq", "pullup_pnr_ppp", "late_clock_shots_pg",
              "unassisted_share_3pm", "off_dribble_3_proxy", "gravity_score",
              "cs_gravity_efg", "spotup_ppp"):
        pct[f] = percentile_rank(merged[f])
    pct["fg3a_per_game"] = percentile_rank(merged["fg3a_per_game"])
    pct["fga_per_game"] = percentile_rank(merged["fga_per_game"])

    shooter_scores = []
    for idx in merged.index:
        avail_w, wsum = 0.0, 0.0
        for pillar, w in SHOOTER_WEIGHTS.items():
            pv = _pillar_score(pct, PILLAR_FACTORS["shooter"][pillar], idx)
            if pd.notna(pv):
                wsum += w * pv
                avail_w += w
        shooter_scores.append(wsum / avail_w if avail_w > 0 else float("nan"))
    merged["shooter_v1_score"] = shooter_scores
    merged["shooter_pctile"] = percentile_rank(merged["shooter_v1_score"])

    valid = merged.dropna(subset=["naive_pctile", "shooter_pctile", "realized_ts_pct"])
    return {
        "cutoff": cutoff,
        "n_players": int(len(valid)),
        "table": valid.reset_index(),
    }


@dataclass
class GateResult:
    per_cutoff: list[dict] = field(default_factory=list)
    mean_rho_shooter: float = float("nan")
    mean_rho_naive: float = float("nan")
    bootstrap: dict = field(default_factory=dict)
    sign_holds_folds: int = 0
    n_folds: int = 0
    replication: dict | None = None
    verdict: str = "PENDING"


def run_gate() -> GateResult:
    box = load_boxscores()
    fold_results = []
    tables = []
    for cutoff in CUTOFFS_2024_25:
        r = rank_at_cutoff(box, cutoff)
        if r is None:
            fold_results.append({"cutoff": cutoff, "status": "SKIPPED_BELOW_FLOOR"})
            continue
        table = r["table"]
        rho_s = _spearman(table["shooter_pctile"], table["realized_ts_pct"])
        rho_n = _spearman(table["naive_pctile"], table["realized_ts_pct"])
        diag_s = top_decile_diagnostic(table, "shooter_pctile")
        diag_n = top_decile_diagnostic(table, "naive_pctile")
        fold_results.append({
            "cutoff": cutoff, "status": "OK", "n_players": r["n_players"],
            "rho_shooter": rho_s, "rho_naive": rho_n, "delta": rho_s - rho_n,
            "top_decile_diagnostic_shooter": diag_s,
            "top_decile_diagnostic_naive": diag_n,
        })
        tables.append(table)

    ok_folds = [f for f in fold_results if f["status"] == "OK"]
    mean_rho_s = float(np.mean([f["rho_shooter"] for f in ok_folds])) if ok_folds else float("nan")
    mean_rho_n = float(np.mean([f["rho_naive"] for f in ok_folds])) if ok_folds else float("nan")
    sign_holds = sum(1 for f in ok_folds if f["delta"] > 0)

    bootstrap = paired_bootstrap_delta(tables) if len(tables) >= 2 else {}

    # 2nd corpus: 2025-26 partial replication
    rep = rank_at_cutoff(box, REPLICATION_CUTOFF)
    if rep is not None:
        rt = rep["table"]
        rho_s = _spearman(rt["shooter_pctile"], rt["realized_ts_pct"])
        rho_n = _spearman(rt["naive_pctile"], rt["realized_ts_pct"])
        replication = {
            "cutoff": REPLICATION_CUTOFF, "n_players": rep["n_players"],
            "rho_shooter": rho_s, "rho_naive": rho_n, "delta": rho_s - rho_n,
            "sign_matches_2024_25": (bool((rho_s - rho_n) > 0) == bool(mean_rho_s > mean_rho_n)) if ok_folds else None,
        }
    else:
        replication = {"cutoff": REPLICATION_CUTOFF, "status": "SKIPPED_BELOW_FLOOR"}

    ci_excludes_0_in_favor = bool(bootstrap) and bootstrap["ci_lo"] > 0
    sign_ok = len(ok_folds) > 0 and sign_holds >= 3
    replicates = bool(replication.get("delta", -1) > 0) if replication and "delta" in replication else False

    verdict = "SHIP_RICHER_INDEX" if (ci_excludes_0_in_favor and sign_ok and replicates) else "REJECT_NAIVE_STAYS_CANONICAL"

    return GateResult(
        per_cutoff=fold_results,
        mean_rho_shooter=mean_rho_s,
        mean_rho_naive=mean_rho_n,
        bootstrap=bootstrap,
        sign_holds_folds=sign_holds,
        n_folds=len(ok_folds),
        replication=replication,
        verdict=verdict,
    )


VERDICT_PATH = "data/domains/basketball_nba/quality_validity_gate_verdict.json"
# write_verdict() lives in quality_claim_builders.py (kept out of this file
# purely to stay under the 300-LOC/file cap) -- see its docstring for the
# verdict-artifact convention + why it carries no planted_null_passed.


if __name__ == "__main__":
    from domains.basketball_nba.quality_claim_builders import write_verdict  # deferred: avoids import cycle

    gate = run_gate()
    print(f"VERDICT: {gate.verdict}")
    print(f"mean_rho_shooter={gate.mean_rho_shooter:.4f} mean_rho_naive={gate.mean_rho_naive:.4f}")
    if gate.bootstrap:
        print(f"bootstrap delta CI=[{gate.bootstrap['ci_lo']:.4f}, {gate.bootstrap['ci_hi']:.4f}]")
    print(f"sign_holds={gate.sign_holds_folds}/{gate.n_folds}")
    print(f"replication={gate.replication}")
    write_verdict(gate)
    print(f"wrote verdict -> {VERDICT_PATH}")
