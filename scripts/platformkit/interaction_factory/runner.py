"""scripts.platformkit.interaction_factory.runner -- build the as-of atomic-unit
frame, fit baseline vs baseline+interaction with a CLUSTER-ROBUST p-value, and
append honest verdict rows to the cumulative-K ledger.

DISCIPLINE (what separates the factory from p-hacking):
 * Leak-free: every as-of feature is a STRICTLY-PRIOR expanding rate (the unit's
   own outcome window is never in its own feature) -- see build_nba_offense_frame.
 * FWER-tightening: the per-test bar is eps / cum_K (scripts.platformkit.combo.
   fwer_budget.eps_eff, reused), so a wider cumulative search gets STRICTER. A
   SURVIVOR is PROVISIONAL -- belief needs an independent-corpus replication.
 * n=0 / unbuildable = NOT_TESTABLE, never FAILED. A NULL row is a recorded success.

Cluster-robust via statsmodels' own cov_type="cluster" (the interaction term's
Wald p under game/player clustering) -- no new statistics, just the robust cov
stats_common.fit_interaction deliberately leaves to the caller.

CLI: python -m scripts.platformkit.interaction_factory.runner --template nba_shot_offense_x_offense --k 20
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import statsmodels.formula.api as smf

from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, eps_eff
from scripts.platformkit.interaction_factory import generator as GEN
from scripts.platformkit.io_atomic import append_jsonl_atomic

REPO = Path(__file__).resolve().parents[3]
LEDGER_PATH = REPO / "data" / "cache" / "intel_claims" / "interaction_factory_ledger.jsonl"

SURVIVES = "SURVIVES_PREREG_PROVISIONAL"
NULL = "NULL"
NOT_TESTABLE = "NOT_TESTABLE"

# Declared BEFORE running (per statistical discipline):
MIN_PRIOR_ATT = 20     # min strictly-prior attempts for an as-of efg to be defined
MIN_GAME_FGA = 4       # min current-game FGA for a stable per-game outcome efg
MIN_N = 300            # min fit rows for a real test (else NOT_TESTABLE)
MIN_CLUSTERS = 5       # min distinct clusters for a cluster-robust cov
MAX_ROWS = 40000       # runtime cap; >MAX_ROWS rows are deterministically subsampled

# attr name -> (fgm_col, fga_col, fg3m_col or None). corner3/above_break makes are
# all 3s (fg3m == fgm); rim/paint/mid have no 3s (fg3m == 0).
_NBA_ATTR_COLS = {
    "zone_efg_rim": ("rim_fgm", "rim_fga", None),
    "zone_efg_paint": ("paint_fgm", "paint_fga", None),
    "zone_efg_mid": ("mid_fgm", "mid_fga", None),
    "zone_efg_corner3": ("corner3_fgm", "corner3_fga", "corner3_fgm"),
    "zone_efg_above_break_3": ("above_break_3_fgm", "above_break_3_fga", "above_break_3_fgm"),
    "transition_efg": ("transition_fgm", "transition_fga", "transition_fg3m"),
    "halfcourt_efg": ("halfcourt_fgm", "halfcourt_fga", "halfcourt_fg3m"),
    "late_clock_efg": ("late_clock_fgm", "late_clock_fga", "late_clock_fg3m"),
}
def nba_source_for_season(season: str) -> Path:
    """Path to the player-offense-events parquet for one season (e.g. "2024_25").
    Threads what used to be a single hardcoded 2025_26 path -- used by cross-
    season replication so a re-test never silently reads the wrong year."""
    return REPO / "data" / "cache" / "team_system" / "composition" / ("player_offense_events_%s.parquet" % season)


_NBA_DEFAULT_SEASON = "2025_26"
_NBA_SOURCE = nba_source_for_season(_NBA_DEFAULT_SEASON)
_NBA_CORPUS = "player_offense_events_%s" % _NBA_DEFAULT_SEASON


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_nba_offense_frame(df: pd.DataFrame, attrs: List[str], *,
                            min_prior_att: int = MIN_PRIOR_ATT,
                            min_game_fga: int = MIN_GAME_FGA) -> pd.DataFrame:
    """Leak-free per-(game,player) frame: outcome `y` = THIS game's eFG, and one
    `asof__<attr>` column per attr = the player's eFG over STRICTLY-PRIOR games
    (cumsum then shift(1) within player, sorted by date) -- the current game is
    excluded from its own feature by construction. Rows with <min_prior_att prior
    attempts for an attr get NaN there (dropped per-candidate at fit time)."""
    df = df.sort_values(["player_id", "date", "game_id"]).reset_index(drop=True)
    three = df.get("above_break_3_fgm", 0).fillna(0) + df.get("corner3_fgm", 0).fillna(0)
    df["y"] = (df["total_fgm"] + 0.5 * three) / df["total_fga"].where(df["total_fga"] > 0)
    grp = df.groupby("player_id", sort=False)
    for attr in attrs:
        fgm_c, fga_c, fg3_c = _NBA_ATTR_COLS[attr]
        cum_fgm = grp[fgm_c].transform(lambda s: s.fillna(0).cumsum().shift(1))
        cum_fga = grp[fga_c].transform(lambda s: s.fillna(0).cumsum().shift(1))
        cum_fg3 = cum_fgm if fg3_c is None else grp[fg3_c].transform(lambda s: s.fillna(0).cumsum().shift(1))
        if fg3_c is None:
            cum_fg3 = cum_fga * 0.0  # rim/paint/mid: no 3s
        asof = (cum_fgm + 0.5 * cum_fg3) / cum_fga.where(cum_fga >= min_prior_att)
        df["asof__" + attr] = asof
    keep = ["player_id", "game_id", "y"] + ["asof__" + a for a in attrs]
    out = df[df["total_fga"] >= min_game_fga][keep].copy()
    return out


def _nba_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _NBA_SOURCE.exists():
        return None
    frame = build_nba_offense_frame(pd.read_parquet(_NBA_SOURCE), attrs)
    return {"frame": frame, "cluster": "player_id", "corpus": _NBA_CORPUS, "kind": "ols"}


# feature_builder key -> callable. Templates whose builder is not registered here
# yield honest NOT_TESTABLE rows (the factory tests them once a builder lands).
_BUILDERS = {"nba_player_offense_asof": _nba_builder}


def _fit_candidate(build: Dict[str, Any], cand: GEN.Candidate) -> Optional[Dict[str, Any]]:
    """Fit y ~ fa + fb (baseline) vs + fa:fb (candidate); return the interaction
    term's cluster-robust effect + p, or None if not enough signal (NOT_TESTABLE)."""
    frame, cluster, kind = build["frame"], build["cluster"], build["kind"]
    ca, cb = "asof__" + cand.attr_a, "asof__" + cand.attr_b
    if ca not in frame or cb not in frame:
        return None
    sub = frame[["y", ca, cb, cluster]].rename(columns={ca: "fa", cb: "fb", cluster: "cl"}).dropna()
    if len(sub) > MAX_ROWS:
        sub = sub.sample(MAX_ROWS, random_state=0)  # declared deterministic subsample
    if len(sub) < MIN_N or sub["cl"].nunique() < MIN_CLUSTERS:
        return None
    for c in ("fa", "fb"):
        sd = sub[c].std(ddof=0)
        if sd == 0 or not (sd == sd):
            return None
        sub[c] = (sub[c] - sub[c].mean()) / sd
    model = smf.logit("y ~ fa + fb + fa:fb", sub) if kind == "logit" else smf.ols("y ~ fa + fb + fa:fb", sub)
    res = (model.fit(disp=0, cov_type="cluster", cov_kwds={"groups": sub["cl"]}) if kind == "logit"
           else model.fit(cov_type="cluster", cov_kwds={"groups": sub["cl"]}))
    term = "fa:fb"
    return {"effect": float(res.params[term]), "p": float(res.pvalues[term]), "n": int(res.nobs), "term": term}


def _row(cand: GEN.Candidate, *, verdict: str, n: int, effect, p, cum_k: int,
         k_declared: int, alpha, corpus, term=None, note="") -> Dict[str, Any]:
    return {
        "candidate_id": cand.candidate_id, "template_id": cand.template_id, "sport": cand.sport,
        "atomic_unit": cand.atomic_unit, "outcome": cand.outcome,
        "attr_a": cand.attr_a, "attr_b": cand.attr_b, "term": term,
        "k_declared": int(k_declared), "cum_K": int(cum_k), "verdict": verdict,
        "effect": effect, "p": p, "n": int(n), "alpha_fwer": alpha, "corpus": corpus,
        "note": note, "edge_claimed": False, "computed_at": _now(),
    }


def _load_ledger(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="ascii", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def run_batch(template_id: str, k: int, *, ledger_path: Path = LEDGER_PATH,
              eps: float = DEFAULT_EPS) -> List[Dict[str, Any]]:
    """Test the next <=k untested candidates for one template. Deterministic,
    idempotent (dedupes vs the ledger), never raises out. Returns the rows it
    appended. K is DECLARED as `k` before running; cum_K counts only REAL tests
    (SURVIVES|NULL) cumulatively -- NOT_TESTABLE spends no budget."""
    existing = _load_ledger(ledger_path)
    batch = GEN.next_batch(template_id, k, existing)
    if not batch:
        return []
    tpl = GEN.TEMPLATES[template_id]
    builder = _BUILDERS.get(tpl["feature_builder"])
    attrs = sorted({c.attr_a for c in batch} | {c.attr_b for c in batch})
    build = None
    if builder is not None:
        try:
            build = builder(attrs, tpl)
        except Exception as exc:  # noqa: BLE001 -- an unbuildable frame is NOT_TESTABLE, not a crash
            build = None
    corpus = build["corpus"] if build else tpl.get("feature_builder")

    running = sum(1 for r in existing
                  if r.get("template_id") == template_id and r.get("verdict") in (SURVIVES, NULL))
    out: List[Dict[str, Any]] = []
    for cand in batch:
        fit = None
        if build is not None:
            try:
                fit = _fit_candidate(build, cand)
            except Exception as exc:  # noqa: BLE001 -- one candidate's fit failure isolates
                fit = None
        if build is None:
            row = _row(cand, verdict=NOT_TESTABLE, n=0, effect=None, p=None, cum_k=running,
                       k_declared=k, alpha=None, corpus=corpus,
                       note="feature_builder %r unavailable or source missing" % tpl["feature_builder"])
        elif fit is None:
            row = _row(cand, verdict=NOT_TESTABLE, n=0, effect=None, p=None, cum_k=running,
                       k_declared=k, alpha=None, corpus=corpus,
                       note="insufficient rows / no variance for this pair")
        else:
            running += 1
            alpha = eps_eff(eps, running)
            v = SURVIVES if fit["p"] < alpha else NULL
            row = _row(cand, verdict=v, n=fit["n"], effect=round(fit["effect"], 6),
                       p=round(fit["p"], 6), cum_k=running, k_declared=k, alpha=round(alpha, 8),
                       corpus=corpus, term=fit["term"],
                       note="PROVISIONAL -- needs independent-corpus replication" if v == SURVIVES else "")
        append_jsonl_atomic(ledger_path, row)
        out.append(row)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Interaction factory -- run one candidate batch.")
    p.add_argument("--template", required=True, choices=sorted(GEN.TEMPLATES))
    p.add_argument("--k", type=int, default=20, help="declared batch size (<=20)")
    p.add_argument("--ledger", type=str, default=str(LEDGER_PATH))
    a = p.parse_args(argv)
    rows = run_batch(a.template, min(20, a.k), ledger_path=Path(a.ledger))
    if not rows:
        print("%s: EXHAUSTED (no untested candidates remain)" % a.template)
        return 0
    for r in rows:
        print("%-52s %-28s n=%-6d effect=%s p=%s cum_K=%d" % (
            r["candidate_id"][:52], r["verdict"], r["n"],
            ("%.4f" % r["effect"]) if r["effect"] is not None else "--",
            ("%.4g" % r["p"]) if r["p"] is not None else "--", r["cum_K"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_batch", "build_nba_offense_frame", "nba_source_for_season", "LEDGER_PATH",
           "SURVIVES", "NULL", "NOT_TESTABLE", "main"]
