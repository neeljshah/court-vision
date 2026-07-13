"""scripts.platformkit.omni.k_sweep_health -- K health dimension sweep v1 (S15.K1).

Mines injury_frequency, status_transition (recovery-curve proxy),
minutes_response (post-clear), load_management (b2b minutes reduction), on
k_sweep_nba.py's pooling/retention/coverage pattern. injury_frequency and
load_management are Wilson-CI proportions (player binomial-test vs league
baseline); status_transition is Mann-Whitney player-vs-league. Only tested
cells enter BH; the rest are screened-only coverage (no A/B split at v1).

Premise-checked 2026-07-13: nba_injuries_*.parquet has only QUESTIONABLE/OUT
(no DOUBTFUL -> "first QUESTIONABLE/DOUBTFUL" collapses to QUESTIONABLE-only,
~7% null player_id dropped). The box-rate snapshot ends 2026-04-12, BEFORE
the injury window starts -- zero calendar overlap, so minutes_response's
join is expected near 0; proven on the real slice below, not assumed.

INVARIANTS: pandas + scipy + stdlib only. <=300 LOC. ASCII stdout. No $/edge.
"""
from __future__ import annotations

import glob
import pathlib

import pandas as pd
from scipy import stats as sps

from domains.basketball_nba import memory_atlas_archetypes as archetypes
from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_coverage as kc
from scripts.platformkit.omni.k_sweep_nba import bh_adjust

_INJURY_GLOB = "data/cache/nba_injuries_*.parquet"
_BOX_SOURCE = pathlib.Path("data/cache/intel_claims/nba_player_box_rate__career_to_date_snapshot.parquet")
_PREDS_DIR = pathlib.Path("data/omni/preds/k_sweep_health_v1")
_LANE = "k_sweep_health_v1"
_DIMENSION = "health"

MIN_SIDE_N = 10             # proportion-cell floor (injury_frequency, load_management)
MIN_EPISODES_N = 3          # status_transition player-level floor (per spec)
EPISODE_GAP_DAYS = 3        # bridges scrape-cadence gaps (max observed real gap = 4d)
MINUTES_JOIN_FLOOR = 0.5    # below this join rate, minutes_response is INSUFFICIENT_DATA
LOAD_BASELINE_MIN = 30.0    # "30+ min/game players"
REDUCED_MIN_FRAC = 0.7      # b2b minutes-reduction flag threshold vs own baseline
BH_ALPHA, MIN_PRACTICAL_EFFECT_DAYS = 0.05, 2.0

_STATUS_PRIORITY = {"ESCALATED": 3, "MINED": 2, "INSUFFICIENT_DATA": 1}

def _load_injury_frame(paths=None) -> pd.DataFrame:
    """*paths* lets tests inject a DataFrame or file list; default = glob real snapshots."""
    if isinstance(paths, pd.DataFrame):
        df = paths.copy()
    else:
        files = paths if paths is not None else sorted(glob.glob(_INJURY_GLOB))
        df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = df.dropna(subset=["player_id"]).copy()
    df["player_id"] = df["player_id"].astype("int64")
    df["report_date"] = pd.to_datetime(df["report_date"])
    df = df.drop_duplicates(subset=["player_id", "report_date"])
    return df.sort_values(["player_id", "report_date"]).reset_index(drop=True)

def _load_box_frame(source=None) -> pd.DataFrame:
    cols = ["player_id", "date", "is_home", "pf", "pts", "min"]
    if isinstance(source, pd.DataFrame):
        return source[cols].copy()
    return pd.read_parquet(source if source is not None else _BOX_SOURCE, columns=cols)

def _archetype_map() -> dict:
    stats_df = archetypes._build_stats(archetypes.DEFAULT_DATA_DIR)
    stats_df = stats_df.assign(archetype=stats_df.apply(archetypes._classify, axis=1))
    return dict(zip(stats_df["player_id"], stats_df["archetype"]))

def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return 0.0, 0.0, 0.0
    phat = k / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = (z * ((phat * (1 - phat) + z * z / (4 * n)) / n) ** 0.5) / denom
    return phat, max(0.0, center - half), min(1.0, center + half)

def _build_episodes(inj_df: pd.DataFrame) -> dict:
    """Per player: contiguous listing runs (gap <= EPISODE_GAP_DAYS = one episode)."""
    global_max = inj_df["report_date"].max()
    episodes: dict = {}
    for pid, g in inj_df.groupby("player_id"):
        rows = list(g.sort_values("report_date")[["report_date", "status"]].itertuples(index=False, name=None))
        eps, start_date, start_status, prev_date, prev_status = [], rows[0][0], rows[0][1], rows[0][0], rows[0][1]
        for date, status in rows[1:]:
            if (date - prev_date).days > EPISODE_GAP_DAYS:
                eps.append(_episode_dict(start_date, start_status, prev_date, prev_status, global_max))
                start_date, start_status = date, status
            prev_date, prev_status = date, status
        eps.append(_episode_dict(start_date, start_status, prev_date, prev_status, global_max))
        episodes[pid] = eps
    return episodes

def _episode_dict(first_date, first_status, last_date, last_status, global_max) -> dict:
    return {"first_date": first_date, "first_status": first_status, "last_date": last_date, "last_status": last_status,
            "transition_days": int((last_date - first_date).days), "censored": bool(last_date == global_max),
            "outcome": "to_out" if last_status == "OUT" else "cleared"}

def _insufficient(mechanism, level, key, n) -> dict:
    return {"mechanism": mechanism, "level": level, "key": key, "insufficient": True, "n": n}

def _prop_record(mechanism, level, key, k, n) -> dict:
    if n < MIN_SIDE_N:
        return _insufficient(mechanism, level, key, n)
    effect, lo, hi = _wilson_ci(k, n)
    return {"mechanism": mechanism, "level": level, "key": key, "effect": effect, "ci_low": lo, "ci_high": hi, "n": n}

def _prop_cells(mechanism: str, per_pid: dict, arche_map: dict, test_vs_baseline: bool = False) -> list[dict]:
    """per_pid: {player_id: (k, n)} -> league/archetype/player Wilson-CI cells (player level tests vs league baseline if test_vs_baseline)."""
    league_k, league_n = sum(k for k, _ in per_pid.values()), sum(n for _, n in per_pid.values())
    records = [_prop_record(mechanism, "league", None, league_k, league_n)]
    arch_kn: dict = {}
    for pid, (k, n) in per_pid.items():
        arch = arche_map.get(pid)
        if arch is not None:
            ak, an = arch_kn.get(arch, (0, 0))
            arch_kn[arch] = (ak + k, an + n)
    for arch, (k, n) in arch_kn.items():
        records.append(_prop_record(mechanism, "archetype", arch, k, n))
    league_effect = league_k / league_n if league_n else 0.0
    for pid, (k, n) in per_pid.items():
        rec = _prop_record(mechanism, "player", pid, k, n)
        if test_vs_baseline and not rec.get("insufficient"):
            res = sps.binomtest(k, n, p=max(min(league_effect, 0.999), 0.001), alternative="two-sided")
            rec["p"], rec["baseline"] = float(res.pvalue), league_effect
        records.append(rec)
    return records

def _mine_injury_frequency(inj_df: pd.DataFrame, arche_map: dict, base_dir) -> list[dict]:
    n_days = inj_df["report_date"].nunique()
    per_player = inj_df.groupby("player_id")["report_date"].nunique()
    _retain(inj_df[["player_id", "player_name", "report_date", "status"]], "injury_frequency", base_dir)
    per_pid = {int(pid): (int(k), n_days) for pid, k in per_player.items()}
    return _prop_cells("injury_frequency", per_pid, arche_map)

def _group_days(resolved: list, keyfn) -> dict:
    out: dict = {}
    for r in resolved:
        k = keyfn(r)
        if k is not None:
            out.setdefault(k, []).append(r["transition_days"])
    return out

def _mine_status_transition(episodes: dict, arche_map: dict, base_dir) -> list[dict]:
    rows = [{"player_id": pid, **ep} for pid, eps in episodes.items() for ep in eps if ep["first_status"] == "QUESTIONABLE"]
    _retain(pd.DataFrame(rows), "status_transition", base_dir)
    resolved = [r for r in rows if not r["censored"]]
    records = []
    if resolved:
        league_days = [r["transition_days"] for r in resolved]
        records.append(_median_record("status_transition", "league", None, league_days, censored_of=rows))
    for arch, days in _group_days(resolved, lambda r: arche_map.get(r["player_id"])).items():
        records.append(_median_record("status_transition", "archetype", arch, days))
    for pid, days in _group_days(resolved, lambda r: r["player_id"]).items():
        if len(days) < MIN_EPISODES_N:
            records.append(_insufficient("status_transition", "player", pid, len(days)))
            continue
        others = [r["transition_days"] for r in resolved if r["player_id"] != pid]
        rec = _median_record("status_transition", "player", pid, days)
        if others:
            _, p = sps.mannwhitneyu(days, others, alternative="two-sided")
            rec["p"], rec["baseline"] = float(p), float(pd.Series(others).median())
        records.append(rec)
    return records

def _median_record(mechanism, level, key, days, censored_of=None) -> dict:
    s = pd.Series(days)
    rec = {"mechanism": mechanism, "level": level, "key": key, "effect": float(s.median()),
           "ci_low": float(s.quantile(0.25)), "ci_high": float(s.quantile(0.75)), "n": len(s)}
    if censored_of is not None:
        rec["censored_share"] = round(sum(r["censored"] for r in censored_of) / len(censored_of), 4)
    return rec

def _mine_minutes_response(episodes: dict, box_df: pd.DataFrame, base_dir) -> list[dict]:
    clears = [(pid, ep["last_date"]) for pid, eps in episodes.items() for ep in eps
              if ep["first_status"] == "QUESTIONABLE" and ep["outcome"] == "cleared" and not ep["censored"]]
    box_by_player = {pid: g.sort_values("date") for pid, g in box_df.groupby("player_id")}
    attempt_rows = []
    for pid, last_date in clears:
        g = box_by_player.get(pid)
        matched_date = matched_min = baseline_min = None
        if g is not None:
            after = g[g["date"] > last_date]
            if not after.empty:
                matched_date, matched_min = after["date"].iloc[0], float(after["min"].iloc[0])
            prior = g[g["date"] <= last_date]
            if not prior.empty:
                baseline_min = float(prior["min"].mean())
        attempt_rows.append({"player_id": pid, "last_listed_date": last_date, "matched": matched_date is not None,
                              "matched_game_date": matched_date, "matched_min": matched_min, "baseline_min": baseline_min})
    attempt_df = pd.DataFrame(attempt_rows)
    _retain(attempt_df, "minutes_response", base_dir)
    n_attempted = len(attempt_df)
    n_matched = int(attempt_df["matched"].sum()) if n_attempted else 0
    join_rate = round(n_matched / n_attempted, 4) if n_attempted else 0.0
    if n_attempted < MIN_SIDE_N or join_rate < MINUTES_JOIN_FLOOR:
        box_max, inj_min = (box_df["date"].max() if not box_df.empty else None), min((d for _, d in clears), default=None)
        rec = _insufficient("minutes_response", "league", None, n_attempted)
        rec.update(join_rate=join_rate, n_matched=n_matched, box_max_date=str(box_max), injury_clear_min_date=str(inj_min))
        return [rec]
    matched_rows = attempt_df[attempt_df["matched"]].dropna(subset=["baseline_min"])
    delta = matched_rows["matched_min"] - matched_rows["baseline_min"]
    return [{"mechanism": "minutes_response", "level": "league", "key": None, "effect": float(delta.mean()),
             "ci_low": float(delta.quantile(0.25)), "ci_high": float(delta.quantile(0.75)),
             "n": len(delta), "join_rate": join_rate}]

def _mine_load_management(box_df: pd.DataFrame, arche_map: dict, base_dir) -> list[dict]:
    df = box_df[box_df["min"] > 0].sort_values(["player_id", "date"]).copy()
    df["rest_days"] = df.groupby("player_id")["date"].diff().dt.days - 1
    baseline = df.groupby("player_id")["min"].mean()
    eligible = set(baseline[baseline >= LOAD_BASELINE_MIN].index)
    df = df[df["player_id"].isin(eligible)].copy()
    df["baseline_min"] = df["player_id"].map(baseline)
    b2b = df[df["rest_days"] <= 0].copy()
    b2b["reduced"] = b2b["min"] < REDUCED_MIN_FRAC * b2b["baseline_min"]
    _retain(b2b[["player_id", "date", "min", "baseline_min", "rest_days", "reduced"]], "load_management", base_dir)
    per_pid = {int(pid): (int(g["reduced"].sum()), len(g)) for pid, g in b2b.groupby("player_id")}
    return _prop_cells("load_management", per_pid, arche_map, test_vs_baseline=True)

def _retain(df: pd.DataFrame, name: str, base_dir) -> None:
    preds_path = _PREDS_DIR if base_dir is None else pathlib.Path(base_dir) / _PREDS_DIR.name
    preds_path.mkdir(parents=True, exist_ok=True)
    df.to_parquet(preds_path / f"{name}.parquet", index=False)

def _claim_for_cell(cell: dict, data_asof: str | None) -> tuple[dict, bool]:
    mechanism, level, key = cell["mechanism"], cell["level"], cell["key"]
    entity_ids = [] if level == "league" else [str(key)] if level == "archetype" else [int(key)]
    label = "league-wide" if level == "league" else f"{level} {key}"
    scope = {"sport": "nba", "entity_type": level, "entity_ids": entity_ids, "context": mechanism}
    statement = f"NBA {label} {mechanism} health signal"
    if cell.get("insufficient"):
        effect = {"verdict": "INSUFFICIENT_DATA"}
        evidence = {k: v for k, v in cell.items() if k not in ("mechanism", "level", "key", "insufficient")}
        escalate, lifecycle = False, "screened"
    else:
        escalate = False
        evidence = {"source": "nba_injuries + box_rate snapshots"}
        evidence.update({k: cell[k] for k in ("join_rate", "censored_share") if k in cell})
        if "p" in cell:
            escalate = cell["p_adj"] < BH_ALPHA and abs(cell["effect"] - cell.get("baseline", 0.0)) >= MIN_PRACTICAL_EFFECT_DAYS
            evidence.update({"p_value": cell["p"], "p_adj_bh": cell["p_adj"], "baseline": cell.get("baseline")})
        effect = {"verdict": "TESTED", "effect": cell["effect"], "ci_low": cell["ci_low"], "ci_high": cell["ci_high"], "n": cell["n"]}
        lifecycle = "proposed" if escalate else "screened"
    claim = {"statement": statement, "type": "conditional", "scope": scope, "topic": f"health.{mechanism}",
             "lifecycle": lifecycle, "effect": effect, "evidence": evidence,
             "provenance": {"created_by_lane": _LANE, "data_asof": data_asof}, "links": {"escalate_to_funnel": escalate}}
    return claim, escalate

def run_sweep(base_dir=None, injury_source=None, box_source=None) -> dict:
    inj_df = _load_injury_frame(injury_source)
    box_df = _load_box_frame(box_source)
    arche_map = _archetype_map()
    episodes = _build_episodes(inj_df)
    data_asof = inj_df["report_date"].max()
    data_asof = data_asof.strftime("%Y-%m-%d") if pd.notna(data_asof) else None
    all_cells: list[dict] = []
    all_cells += _mine_injury_frequency(inj_df, arche_map, base_dir)
    all_cells += _mine_status_transition(episodes, arche_map, base_dir)
    all_cells += _mine_minutes_response(episodes, box_df, base_dir)
    all_cells += _mine_load_management(box_df, arche_map, base_dir)
    tested = [c for c in all_cells if "p" in c]
    for c, a in zip(tested, bh_adjust([c["p"] for c in tested])):
        c["p_adj"] = a
    batch_overfit_est = round(BH_ALPHA * len(tested), 4)
    existing_ids = set(cl.query(sport="nba", base_dir=base_dir)["claim_id"])
    claims_added, escalations, player_status = 0, 0, {}
    for cell in all_cells:
        claim, escalate = _claim_for_cell(cell, data_asof)
        claim_id = cl.make_claim_id(claim["statement"], claim["scope"])
        if claim_id not in existing_ids:
            cl.add_claim(claim, base_dir=base_dir)
            existing_ids.add(claim_id)
            claims_added += 1
        if escalate:
            escalations += 1
        if cell["level"] == "player":
            status = "ESCALATED" if escalate else ("INSUFFICIENT_DATA" if cell.get("insufficient") else "MINED")
            player_status.setdefault(cell["key"], []).append(status)
    for pid, statuses in player_status.items():
        best = max(statuses, key=lambda s: _STATUS_PRIORITY[s])
        try:
            kc.update_cell(pid, _DIMENSION, best, len(statuses), base_dir=base_dir)
        except KeyError:
            pass  # ponytail: player not on the active-roster coverage matrix (two-way/summer-league) -- skip, not a failure
    metrics = kc.k5_metrics(base_dir=base_dir)
    insufficient_n = sum(1 for c in all_cells if c.get("insufficient"))
    return {
        "players_covered": len(player_status), "cells_mined": len(all_cells), "claims_added": claims_added,
        "insufficient_data_share": round(insufficient_n / len(all_cells), 4) if all_cells else 0.0,
        "escalations": escalations, "batch_overfit_est": batch_overfit_est, "k5_metrics": metrics,
    }

if __name__ == "__main__":
    result = run_sweep()
    for k, v in result.items():
        if k != "k5_metrics":
            print(f"[k_sweep_health_v1] {k}: {v}")
    print(f"[k_sweep_health_v1] k5_metrics: {result['k5_metrics']}")
