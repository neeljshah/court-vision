"""market_favorite_longshot.py -- is the betting market calibrated? A
favorite-longshot bias (FLB) audit, cross-sport, pregame.

This grades THE MARKET's own calibration, not our model. We do not claim to
beat the market anywhere on this page.

Method (both sports): proportional devig of the two-way closing price ->
implied probability. The favorite is max(q, 1-q). A match/game's favorite
"won" if the eventual winner was the favorite. Bucket rows by favorite
implied probability; per bucket report n, mean implied probability, realized
favorite win-rate, gap = real - impl, and a 95% Wilson interval on the
realized rate. Each row is one independent match/game, so binomial Wilson
CIs are valid here -- unlike in-game ticks, there is no within-event
clustering to correct for.

TENNIS (data/domains/tennis/odds.parquet): Pinnacle closing psw/psl
(winner/loser odds -- the winner is known inline by column construction).
q = (1/psw)/((1/psw)+(1/psl)). Keep psw>1 & psl>1.

MLB (data/domains/mlb/odds.parquet joined to games.parquet on event_id):
closing decimal moneyline dec_close_home/dec_close_away, target_home_win
from games.parquet. qh = (1/dec_close_home)/((1/dec_close_home)+(1/dec_close_away)).
If qh>=0.5 the favorite is home (fav_won=target_home_win), else the favorite
is away (fav_won=1-target_home_win). Keep dec_close_home>1 & dec_close_away>1,
drop rows with a null target_home_win.

THE STORY (verified against the real parquets in this session): tennis shows
a mild, MONOTONE favorite-longshot bias -- favorites win slightly more than
their devigged price implies, and the gap grows with favorite strength (from
~0 to +1.76 points). MLB moneyline is essentially efficient: gaps are small
and NOT monotone, i.e. within Wilson noise -- no systematic bias at the
closing line.

Descriptive only. No edge/ROI/profit/bankroll claim (edge_claimed:false).

Output: out/market_favorite_longshot.json (this committed JSON IS the
recorded artifact -- --check reloads it and does not require data/ locally,
i.e. is clone-safe).

Usage:
  python -m scripts.platformkit.analytics_showcase.market_favorite_longshot
  python -m scripts.platformkit.analytics_showcase.market_favorite_longshot --check
"""
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "market_favorite_longshot.json"
TENNIS_ODDS = REPO / "data" / "domains" / "tennis" / "odds.parquet"
MLB_ODDS = REPO / "data" / "domains" / "mlb" / "odds.parquet"
MLB_GAMES = REPO / "data" / "domains" / "mlb" / "games.parquet"

METHOD = (
    "Proportional devig of the two-way closing price -> implied probability; "
    "favorite = max(q, 1-q); bucketed by favorite implied probability, each "
    "bucket reports n, mean implied, realized favorite win-rate, the gap, "
    "and a 95% Wilson interval -- each row is one independent match/game."
)
CONFOUNDS = [
    "proportional devig shifts absolute probability levels vs. other devig methods",
    "closing snapshot only, not a continuous feed",
    "each row is one independent match/game, so binomial Wilson CIs are valid here -- unlike in-game ticks, which are dependent within an event",
    "favorite is defined by closing price, not by any external ranking",
    "bucket boundaries are declared upfront, not tuned to the data",
    "this grades the market's own calibration, not our model -- nothing here is a claim about beating it",
]
BANNED_TERMS = ("edge", "roi", "profit", "bankroll", "forecast")

TENNIS_BUCKETS = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.001)]
MLB_BUCKETS = [(0.5, 0.55), (0.55, 0.6), (0.6, 0.65), (0.65, 0.8)]


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO)).replace("\\", "/")


def _wilson(k: int, n: int, z: float = 1.96) -> tuple:
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return center - half, center + half


def _bucket_rows(fav_impl, fav_won, buckets) -> list:
    rows = []
    for lo, hi in buckets:
        mask = (fav_impl >= lo) & (fav_impl < hi)
        n = int(mask.sum())
        impl = float(fav_impl[mask].mean())
        k = int(fav_won[mask].sum())
        real = k / n
        gap = real - impl
        wlo, whi = _wilson(k, n)
        rows.append({
            "lo": lo, "hi": hi, "n": n,
            "impl": round(impl, 4), "real": round(real, 4), "gap": round(gap, 4),
            "wilson_lo": round(wlo, 4), "wilson_hi": round(whi, 4),
        })
    return rows


def _tennis_block(df) -> dict:
    sub = df[(df["psw"] > 1) & (df["psl"] > 1)].dropna(subset=["psw", "psl"])
    n_total = int(len(sub))
    q = (1.0 / sub["psw"]) / ((1.0 / sub["psw"]) + (1.0 / sub["psl"]))
    fav_impl = q.where(q >= 0.5, 1.0 - q)  # favorite = max(q, 1-q)
    fav_won = (q >= 0.5).astype(int)  # winner side (by construction of psw/psl) IS the favorite iff q>=0.5
    buckets = _bucket_rows(fav_impl, fav_won, TENNIS_BUCKETS)
    return {
        "book": "Pinnacle (close)", "market": "match winner",
        "n_total": n_total, "buckets": buckets,
        "verdict": "mild monotone favorite-longshot bias",
    }


def _mlb_block(odds_df, games_df) -> dict:
    joined = odds_df.merge(games_df[["event_id", "target_home_win"]], on="event_id", how="inner")
    joined = joined.dropna(subset=["target_home_win"])
    sub = joined[(joined["dec_close_home"] > 1) & (joined["dec_close_away"] > 1)]
    sub = sub.dropna(subset=["dec_close_home", "dec_close_away"])
    n_total = int(len(sub))
    qh = (1.0 / sub["dec_close_home"]) / ((1.0 / sub["dec_close_home"]) + (1.0 / sub["dec_close_away"]))
    fav_impl = qh.where(qh >= 0.5, 1.0 - qh)
    home_fav = qh >= 0.5
    target = sub["target_home_win"]
    fav_won = (target.where(home_fav, 1.0 - target)).astype(int)
    buckets = _bucket_rows(fav_impl, fav_won, MLB_BUCKETS)
    return {
        "book": "closing line", "market": "moneyline",
        "n_total": n_total, "buckets": buckets,
        "verdict": "essentially efficient -- no systematic bias",
    }


def build() -> dict:
    needed = [TENNIS_ODDS, MLB_ODDS, MLB_GAMES]
    missing = [p for p in needed if not p.exists()]
    if missing:
        return {"status": "local_corpus_absent", "needed_artifacts": [_rel(p) for p in missing]}

    import pandas as pd

    tennis_df = pd.read_parquet(TENNIS_ODDS)
    tennis = _tennis_block(tennis_df)

    mlb_odds_df = pd.read_parquet(MLB_ODDS)
    mlb_games_df = pd.read_parquet(MLB_GAMES)
    mlb = _mlb_block(mlb_odds_df, mlb_games_df)

    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "edge_claimed": False,
        "headline": (
            "The betting market is well-calibrated: MLB moneyline is essentially "
            "efficient, tennis shows only a mild favorite-longshot bias."
        ),
        "method": METHOD,
        "grades": "the market, not our model",
        "sports": {"tennis": tennis, "mlb": mlb},
        "observation_window": {
            "note": "committed odds corpora (decade-plus per sport), not a rolling cache; pregame closing prices",
        },
        "confounds": CONFOUNDS,
        "receipt": {
            "source_parquets": [_rel(TENNIS_ODDS), _rel(MLB_ODDS), _rel(MLB_GAMES)],
        },
    }


def main() -> dict:
    result = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="ascii")
    return result


def _no_nan_inf(obj) -> bool:
    if isinstance(obj, float):
        return not (math.isnan(obj) or math.isinf(obj))
    if isinstance(obj, dict):
        return all(_no_nan_inf(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_no_nan_inf(v) for v in obj)
    return True


def _string_values(obj) -> list:
    """Collect string VALUES only (never dict keys) for the banned-term scan."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        out = []
        for v in obj.values():
            out.extend(_string_values(v))
        return out
    if isinstance(obj, list):
        out = []
        for v in obj:
            out.extend(_string_values(v))
        return out
    return []


def _check():
    assert OUT_JSON.exists(), f"missing {OUT_JSON} -- run the module (no --check) first"
    assert OUT_JSON.stat().st_size > 0, f"{OUT_JSON} is empty"
    result = json.loads(OUT_JSON.read_text(encoding="ascii"))
    assert result["status"] in ("ok", "local_corpus_absent"), result["status"]

    if result["status"] == "ok":
        assert result["descriptive_only"] is True
        assert result["edge_claimed"] is False

        tennis = result["sports"]["tennis"]
        assert tennis["n_total"] == 33713, tennis["n_total"]
        last = tennis["buckets"][-1]
        assert last["lo"] == 0.9 and abs(last["hi"] - 1.001) < 1e-9
        assert last["real"] == 0.9497, last["real"]
        assert last["n"] == 1850, last["n"]
        gaps = [b["gap"] for b in tennis["buckets"]]
        assert all(gaps[i] <= gaps[i + 1] for i in range(len(gaps) - 1)), f"tennis gaps not monotone: {gaps}"

        mlb = result["sports"]["mlb"]
        assert mlb["n_total"] == 27983, mlb["n_total"]
        last_mlb = mlb["buckets"][-1]
        assert last_mlb["lo"] == 0.65 and last_mlb["hi"] == 0.8
        assert last_mlb["real"] == 0.7031, last_mlb["real"]
        assert last_mlb["n"] == 2994, last_mlb["n"]
        assert all(abs(b["gap"]) < 0.02 for b in mlb["buckets"]), [b["gap"] for b in mlb["buckets"]]

        for sport in ("tennis", "mlb"):
            for b in result["sports"][sport]["buckets"]:
                assert b["wilson_lo"] <= b["real"] <= b["wilson_hi"], (sport, b)

        assert _no_nan_inf(result), "NaN/inf found in emitted numbers"

        blob = " ".join(_string_values(result)).lower()
        for term in BANNED_TERMS:
            assert not re.search(rf"\b{term}\b", blob), f"banned term '{term}' found in artifact prose"
    else:
        assert "needed_artifacts" in result
    print("OK")


if __name__ == "__main__":
    if "--check" in sys.argv:
        _check()
    else:
        res = main()
        if res["status"] == "ok":
            print(json.dumps({
                "status": "ok",
                "sports": {
                    k: {"n_total": v["n_total"], "buckets": v["buckets"]}
                    for k, v in res["sports"].items()
                },
            }, indent=2))
        else:
            print(json.dumps(res, indent=2))
        print(f"wrote {OUT_JSON}")
