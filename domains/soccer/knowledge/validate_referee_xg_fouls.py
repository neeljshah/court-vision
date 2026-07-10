"""domains.soccer.knowledge.validate_referee_xg_fouls -- 3 UNTESTED research-
seed mechanisms (M10 pool, appended commit e500a0d6) on the flat-file soccer
corpus (`data/domains/soccer/*.parquet`), a DIFFERENT and much larger corpus
than the 400-match StatsBomb slice used elsewhere in this ledger:

* referee_card_rate_persistence_at_scale (#34) -- unblocks NOT_TESTABLE #16
  with a 10,251-match referee-card corpus vs #16's <10-referee StatsBomb slice.
* xg_supremacy_persistence (#35) -- descriptive team-trait persistence, NOT
  the already-closed incremental-Brier question (`soccer_diff_xg_supremacy_asof`
  REJECT in reject_ledger.jsonl).
* fouls_suppress_opponent_sot (#36) -- fouling team's rate vs the OPPONENT's
  shots-on-target in the same match, partial-r controlling for total_shots.

Premise-check (this session): all 3 named parquets load with every column the
mechanisms.md rows cite, byte-for-byte -- no bare/prefixed column mismatch
found (`referee_card_foul_profiles.parquet` cols event_id/referee/div/year/
total_fouls/total_yellow/total_red/total_cards; `match_stats.parquet` 25,834
rows with home_/away_-prefixed fouls/sot/shots + bare `referee`/`date`;
`asof_xg_proxy.parquet` 25,834 rows with home_/away_/diff_-prefixed
xg_supremacy_asof). event_id join keys are 100% coverage against
match_stats.parquet for both smaller corpora.

DESCRIPTIVE/persistence only -- no forward replay, no market/$ edge claimed.

Run: python -m domains.soccer.knowledge.validate_referee_xg_fouls
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd
from scipy import stats

from domains.soccer.knowledge._data import LEDGER_PATH
from scripts.platformkit.io_atomic import append_jsonl_atomic

REPO = Path(__file__).resolve().parents[3]
DATA_DIR = REPO / "data" / "domains" / "soccer"
REFEREE_PATH = DATA_DIR / "referee_card_foul_profiles.parquet"
MATCH_STATS_PATH = DATA_DIR / "match_stats.parquet"
XG_PROXY_PATH = DATA_DIR / "asof_xg_proxy.parquet"


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or p != p:
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < 0.01 and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def load_referee_profiles() -> pd.DataFrame:
    return pd.read_parquet(REFEREE_PATH)


def load_match_stats() -> pd.DataFrame:
    df = pd.read_parquet(MATCH_STATS_PATH)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_xg_proxy() -> pd.DataFrame:
    return pd.read_parquet(XG_PROXY_PATH)


def referee_card_rate_persistence_at_scale(ref: pd.DataFrame, ms: pd.DataFrame) -> Dict[str, Any]:
    """#34 -- split-half persistence of per-referee card rate (total_cards/
    total_fouls) at scale; also the row that unblocks NOT_TESTABLE #16."""
    d = ref.merge(ms[["event_id", "date"]], on="event_id")
    d = d[d["total_fouls"] > 0].copy()
    d["card_rate"] = d["total_cards"] / d["total_fouls"]
    mid = d["date"].median()
    d["half"] = np.where(d["date"] < mid, "A", "B")
    cnt = d.groupby(["referee", "half"]).size().unstack("half").fillna(0)
    ok = cnt[(cnt.get("A", 0) >= 5) & (cnt.get("B", 0) >= 5)].index
    piv = d[d["referee"].isin(ok)].groupby(["referee", "half"])["card_rate"].mean().unstack("half").dropna()
    if len(piv) < 10:
        return {"hypothesis": "referee_card_rate_persistence_at_scale", "n": int(len(piv)),
                "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "fewer than 10 referees with >=5 matches per half"}
    r, p = stats.pearsonr(piv["A"], piv["B"])
    return {"hypothesis": "referee_card_rate_persistence_at_scale", "n": int(len(piv)),
            "effect": round(float(r), 4), "p": float(p), "verdict": _verdict(p, r, 0.15),
            "note": "split-half pearson r, per-referee card-rate (total_cards/total_fouls), "
                    "n=%d referees (>=5 matches/half, 10,251-match corpus)" % len(piv)}


def xg_supremacy_persistence(axg: pd.DataFrame, ms: pd.DataFrame) -> Dict[str, Any]:
    """#35 -- split-half persistence of trailing xG-supremacy as a team
    trait (descriptive, not the closed incremental-Brier question)."""
    m = axg.merge(ms[["event_id", "date", "home_team", "away_team"]], on="event_id")
    long = pd.concat([
        m[["date", "home_team", "home_xg_supremacy_asof"]].rename(
            columns={"home_team": "team", "home_xg_supremacy_asof": "sup"}),
        m[["date", "away_team", "away_xg_supremacy_asof"]].rename(
            columns={"away_team": "team", "away_xg_supremacy_asof": "sup"}),
    ]).dropna(subset=["sup"])
    mid = long["date"].median()
    long["half"] = np.where(long["date"] < mid, "A", "B")
    cnt = long.groupby(["team", "half"]).size().unstack("half").fillna(0)
    ok = cnt[(cnt.get("A", 0) >= 10) & (cnt.get("B", 0) >= 10)].index
    piv = long[long["team"].isin(ok)].groupby(["team", "half"])["sup"].mean().unstack("half").dropna()
    if len(piv) < 10:
        return {"hypothesis": "xg_supremacy_persistence", "n": int(len(piv)), "effect": None,
                "p": None, "verdict": "NOT_TESTABLE", "note": "fewer than 10 teams with >=10 games per half"}
    r, p = stats.pearsonr(piv["A"], piv["B"])
    return {"hypothesis": "xg_supremacy_persistence", "n": int(len(piv)),
            "effect": round(float(r), 4), "p": float(p), "verdict": _verdict(p, r, 0.20),
            "note": "split-half pearson r, per-team mean xg-supremacy_asof, n=%d teams "
                    "(>=10 games/half, 25,834-match corpus)" % len(piv)}


def _partial_r(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> float:
    rxy, _ = stats.pearsonr(x, y)
    rxz, _ = stats.pearsonr(x, z)
    ryz, _ = stats.pearsonr(y, z)
    denom = ((1 - rxz ** 2) * (1 - ryz ** 2)) ** 0.5
    return float(rxy - rxz * ryz) / denom if denom > 0 else float("nan")


def fouls_suppress_opponent_sot(ms: pd.DataFrame) -> Dict[str, Any]:
    """#36 -- team fouls-committed rate vs the OPPONENT's shots-on-target in
    the same match, partial-r controlling for total_shots (overall match
    shot volume confound)."""
    d = ms.dropna(subset=["home_fouls", "away_fouls", "home_sot", "away_sot", "total_shots"])
    fouls = pd.concat([d["home_fouls"], d["away_fouls"]]).to_numpy()
    opp_sot = pd.concat([d["away_sot"], d["home_sot"]]).to_numpy()
    shots = pd.concat([d["total_shots"], d["total_shots"]]).to_numpy()
    r_raw, p_raw = stats.pearsonr(fouls, opp_sot)
    pr = _partial_r(fouls, opp_sot, shots)
    n = len(fouls)
    t = pr * ((n - 3) / (1 - pr ** 2)) ** 0.5
    p_partial = float(2 * stats.t.sf(abs(t), df=n - 3))
    return {"hypothesis": "fouls_suppress_opponent_sot", "n": int(n),
            "effect": round(pr, 4), "p": p_partial, "verdict": _verdict(p_partial, pr, 0.05),
            "note": "partial pearson r (fouls vs opponent SOT, controlling total_shots)=%.4f "
                    "(raw r=%.4f, p_raw=%.3g), n=%d team-match units pooled both sides"
                    % (pr, r_raw, p_raw, n)}


def run() -> list:
    ref, ms, axg = load_referee_profiles(), load_match_stats(), load_xg_proxy()
    rows = [
        referee_card_rate_persistence_at_scale(ref, ms),
        xg_supremacy_persistence(axg, ms),
        fouls_suppress_opponent_sot(ms),
    ]
    for r in rows:
        r["sport"] = "soccer"
        r["corpus"] = "soccer_flatfile_%d_matches" % len(ms)
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        eff = r["effect"] if r["effect"] is not None else float("nan")
        p = r["p"] if r["p"] is not None else float("nan")
        print("%-46s %-16s n=%-8d effect=%+.4f p=%.4g -- %s"
              % (r["hypothesis"], r["verdict"], r["n"], eff, p, r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: verdict thresholds + partial-r formula."""
    assert _verdict(0.001, 0.5, 0.1) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.5, 0.1) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.5, 0.1) == "NOT_TESTABLE"
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y = np.array([2.0, 4.0, 6.0, 8.0, 10.0])  # y=2x -> r(x,y)=1 regardless of any non-collinear z
    z = np.array([3.0, 1.0, 4.0, 1.0, 5.0])  # not perfectly correlated w/ x -- denom stays > 0
    assert abs(_partial_r(x, y, z) - 1.0) < 1e-6
    print("self-check OK")
