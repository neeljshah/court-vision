"""tests.fixtures.proof.soccer._gen — deterministic tiny soccer fixture corpus.

Generates synthetic-but-realistic football-data.co.uk-shaped parquets that the
soccer proofs (beat_the_close_ou, ingame_ht_accuracy) read, with the SAME
filenames + columns as the real data/domains/soccer/ corpus:

    matches.parquet      event_id,date,season,div,home_team,away_team,fthg,ftag,
                         total_goals,target_over25,ftr
    match_stats.parquet  event_id,div,date,home_team,away_team,hthg,htag,htr,
                         home_shots,away_shots,home_sot,away_sot,home_corners,...
    odds.parquet         event_id,div,date,pc_over,pc_under,ou_close_over,...

The data is small (~420 matches), DETERMINISTIC (fixed numpy seed, no clock),
and realistic enough that:
  * beat_the_close_ou returns status=ok with a FINITE Brier gap (n>=200 after the
    model<->odds inner join; ~10 teams/div build real EW histories);
  * ingame_ht_accuracy returns status=ok (hthg<=fthg, htag<=ftag enforced by
    drawing HT goals as a binomial split of FT goals).

Run:  python -m tests.fixtures.proof.soccer._gen   (regenerates the parquets in place)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent
_SEED = 20260615

# Two divisions, ~12 teams each -> deep per-team EW histories.
_DIVS = ["E0", "I1"]
_TEAMS_PER_DIV = 12
_ROUNDS = 42  # match-days per division (each round = 6 games for 12 teams)


def _team_names(div: str, n: int) -> list[str]:
    return [f"{div}_Club{j:02d}" for j in range(n)]


def _round_robin_pairs(teams: list[str], rng: np.random.Generator) -> list[tuple[str, str]]:
    """One shuffled round of home/away pairings (each team plays once)."""
    order = list(teams)
    rng.shuffle(order)
    pairs: list[tuple[str, str]] = []
    for k in range(0, len(order) - 1, 2):
        pairs.append((order[k], order[k + 1]))
    return pairs


def build() -> None:
    rng = np.random.default_rng(_SEED)

    # Per-team latent attack/defense strengths (stable across the season).
    strengths: dict[str, dict[str, float]] = {}
    for div in _DIVS:
        for t in _team_names(div, _TEAMS_PER_DIV):
            strengths[t] = {
                "atk": float(np.clip(rng.normal(1.35, 0.35), 0.6, 2.4)),
                "dfn": float(np.clip(rng.normal(1.35, 0.30), 0.7, 2.2)),
            }

    m_rows: list[dict] = []
    s_rows: list[dict] = []
    o_rows: list[dict] = []

    base_date = pd.Timestamp("2019-08-03")
    season = 2019
    for r in range(_ROUNDS):
        match_date = base_date + pd.Timedelta(days=7 * r)
        for div in _DIVS:
            teams = _team_names(div, _TEAMS_PER_DIV)
            for home, away in _round_robin_pairs(teams, rng):
                # Poisson goal means: home attack vs away defense (+ small HFA).
                lam_h = float(strengths[home]["atk"] * strengths[away]["dfn"] / 1.35 * 1.12)
                lam_a = float(strengths[away]["atk"] * strengths[home]["dfn"] / 1.35 * 0.95)
                lam_h = float(np.clip(lam_h, 0.25, 3.8))
                lam_a = float(np.clip(lam_a, 0.25, 3.8))
                fthg = int(rng.poisson(lam_h))
                ftag = int(rng.poisson(lam_a))

                # Shots-on-target consistent with K_CONV ~ 0.32 (goals/SoT) + noise.
                home_sot = int(max(fthg, rng.poisson(fthg / 0.32 + 1.5)))
                away_sot = int(max(ftag, rng.poisson(ftag / 0.32 + 1.5)))
                home_shots = int(home_sot + rng.poisson(6))
                away_shots = int(away_sot + rng.poisson(6))

                # Halftime goals = binomial split of FT goals (guarantees ht<=ft).
                hthg = int(rng.binomial(fthg, 0.45)) if fthg > 0 else 0
                htag = int(rng.binomial(ftag, 0.45)) if ftag > 0 else 0

                total = fthg + ftag
                over25 = int(total >= 3)
                ftr = "H" if fthg > ftag else ("A" if ftag > fthg else "D")
                htr = "H" if hthg > htag else ("A" if htag > hthg else "D")
                eid = f"{match_date.strftime('%Y%m%d')}-{div}-{home}-{away}"

                m_rows.append({
                    "event_id": eid, "date": match_date, "season": season, "div": div,
                    "home_team": home, "away_team": away,
                    "fthg": fthg, "ftag": ftag, "total_goals": total,
                    "target_over25": over25, "ftr": ftr,
                })
                s_rows.append({
                    "event_id": eid, "div": div, "date": match_date,
                    "home_team": home, "away_team": away,
                    "hthg": float(hthg), "htag": float(htag), "htr": htr,
                    "home_shots": float(home_shots), "away_shots": float(away_shots),
                    "home_sot": float(home_sot), "away_sot": float(away_sot),
                    "home_corners": float(rng.integers(2, 11)),
                    "away_corners": float(rng.integers(2, 11)),
                    "home_fouls": float(rng.integers(7, 18)),
                    "away_fouls": float(rng.integers(7, 18)),
                    "home_yellow": float(rng.integers(0, 5)),
                    "away_yellow": float(rng.integers(0, 5)),
                    "home_red": float(rng.binomial(1, 0.05)),
                    "away_red": float(rng.binomial(1, 0.05)),
                    "referee": f"Ref{int(rng.integers(0, 30)):02d}",
                })

                # Devigged true over-prob from the latent lambdas, then add a vig
                # margin (~5%) split across the two decimal close prices + noise.
                lt = lam_h + lam_a
                p_over_true = 1.0 - np.exp(-lt) * (1.0 + lt + lt * lt / 2.0)
                p_over_true = float(np.clip(p_over_true + rng.normal(0, 0.02), 0.05, 0.95))
                p_under_true = 1.0 - p_over_true
                margin = 1.05
                pc_over = float(round(1.0 / (p_over_true * margin), 2))
                pc_under = float(round(1.0 / (p_under_true * margin), 2))
                o_rows.append({
                    "event_id": eid, "div": div, "date": match_date,
                    "ou_open_over": pc_over + 0.03, "ou_open_under": pc_under + 0.03,
                    "ou_close_over": pc_over, "ou_close_under": pc_under,
                    "book_open": "pinnacle", "book_close": "pinnacle",
                    "p_over": pc_over + 0.03, "p_under": pc_under + 0.03,
                    "pc_over": pc_over, "pc_under": pc_under,
                    "avg_over": pc_over, "avg_under": pc_under,
                    "avgc_over": pc_over, "avgc_under": pc_under,
                    "b365_over": pc_over, "b365_under": pc_under,
                    "b365c_over": pc_over, "b365c_under": pc_under,
                    "max_over": pc_over + 0.05, "max_under": pc_under + 0.05,
                    "maxc_over": pc_over + 0.05, "maxc_under": pc_under + 0.05,
                })

    matches = pd.DataFrame(m_rows)
    matches["fthg"] = matches["fthg"].astype("Int64")
    matches["ftag"] = matches["ftag"].astype("Int64")
    matches["total_goals"] = matches["total_goals"].astype("Int64")
    matches["target_over25"] = matches["target_over25"].astype("int8")
    matches["season"] = matches["season"].astype("int32")
    stats = pd.DataFrame(s_rows)
    odds = pd.DataFrame(o_rows)
    for c in odds.columns:
        if c not in ("event_id", "div", "date", "book_open", "book_close"):
            odds[c] = odds[c].astype("float32")

    matches.to_parquet(_HERE / "matches.parquet", index=False)
    stats.to_parquet(_HERE / "match_stats.parquet", index=False)
    odds.to_parquet(_HERE / "odds.parquet", index=False)
    print(f"wrote {len(matches)} matches / {len(stats)} stats / {len(odds)} odds rows to {_HERE}")


if __name__ == "__main__":
    build()
