"""tests.fixtures.proof.tennis._gen -- deterministic tiny ATP fixture for the tennis proofs.

Generates a SMALL synthetic-but-realistic corpus matching the real
data/domains/tennis/{matches,odds}.parquet schema + filenames, so the
beat-the-close ML proof and the in-game accuracy proof both return status=='ok'
on the committed fixture (no real, gitignored data needed in CI).

Design (so the leak-free walk-forward Elo learns a calibrated, finite-gap signal):
  * A fixed pool of players each with a latent skill; match winners are sampled
    from a logistic on the skill gap, so Elo recovers a real signal and the
    devigged Pinnacle close (built from the SAME latent prob + a small vig +
    noise) is slightly sharper -> a finite Brier gap, honest verdict computable.
  * Scores are WINNER-ordered best-of-3 (the winner takes 2 sets) with a
    realistic per-set margin, so _parse_sets yields >=2 sets and the in-game
    after-set-1 / after-set-2@1-1 checkpoints have rows.
  * Chronological across 2015..2025 so train (<=2022) and held-out (>2022)
    splits both have ample volume (>=60 rows in the held-out window).

Deterministic: fixed numpy seed, no wall-clock. Re-running overwrites identically.
Run: python -m tests.fixtures.proof.tennis._gen
PRIVATE fixture generator -- stdlib + numpy/pandas only. No edge claimed.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

_SEED = 20260615
_OUT = Path(__file__).resolve().parent
_SURFACES = ["Hard", "Clay", "Grass"]
_N_PLAYERS = 48
_MATCHES_PER_YEAR = 90          # ~990 matches total over 11 years
_YEARS = list(range(2015, 2026))  # 2015..2025 inclusive
_SCALE = 400.0


def _logistic(x: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-x / _SCALE))


def _winner_ordered_score(rng: np.random.Generator, close: bool) -> str:
    """Best-of-3 score string, winner first (winner takes 2 sets)."""
    sets: List[str] = []
    # winner wins exactly 2 sets; loser may steal one (a 3-set match)
    loser_steals = rng.random() < (0.45 if close else 0.25)
    set_results: List[bool] = [True, True]  # True = winner won the set
    if loser_steals:
        # insert a stolen set at a random position among the first two slots
        set_results = [True, False, True] if rng.random() < 0.5 else [False, True, True]
    for won in set_results:
        if won:
            wg = 6
            lg = int(rng.integers(0, 5))            # winner 6-x, x in 0..4
        else:
            lg = 6
            wg = int(rng.integers(0, 5))            # loser took it 6-x
        sets.append(f"{wg}-{lg}")
    return " ".join(sets)


def generate() -> None:
    rng = np.random.default_rng(_SEED)
    # latent player skills (Elo-like spread ~ +/- 250)
    skills = rng.normal(0.0, 250.0, size=_N_PLAYERS)
    pids = [100000 + i for i in range(_N_PLAYERS)]

    m_rows = []
    o_rows = []
    for year in _YEARS:
        for k in range(_MATCHES_PER_YEAR):
            a, b = rng.choice(_N_PLAYERS, size=2, replace=False)
            ia, ib = int(a), int(b)
            # symmetric id-order: p1 is the LOWER id (outcome-independent)
            if pids[ia] > pids[ib]:
                ia, ib = ib, ia
            p1_id, p2_id = pids[ia], pids[ib]
            gap = skills[ia] - skills[ib]
            p1_true = _logistic(gap)
            p1_wins = rng.random() < p1_true
            winner = 1 if p1_wins else 2

            close = abs(p1_true - 0.5) < 0.12
            score = _winner_ordered_score(rng, close)

            surface = _SURFACES[int(rng.integers(0, len(_SURFACES)))]
            # spread matches across the year (day-of-year), keep chronological
            doy = int(1 + (k * 360) // _MATCHES_PER_YEAR)
            date = dt.date(year, 1, 1) + dt.timedelta(days=doy - 1)
            event_id = f"{date:%Y%m%d}-atp-{year}-{k:03d}-{p1_id}-{p2_id}-{k}"

            m_rows.append({
                "event_id": event_id,
                "date": date,
                "tour": "atp",
                "tourney_id": f"{year}-{k % 12:03d}",
                "tourney_name": f"Event{k % 12}",
                "tourney_level": "A",
                "surface": surface,
                "best_of": np.int8(3),
                "round": "R32",
                "match_num": np.int32(k),
                "p1_id": p1_id,
                "p2_id": p2_id,
                "p1_name": f"Player {p1_id}",
                "p2_name": f"Player {p2_id}",
                "p1_rank": np.float32(1 + (ia % 100)),
                "p2_rank": np.float32(1 + (ib % 100)),
                "winner": np.int8(winner),
                "score": score,
                "retirement": False,
                "minutes": np.float32(60 + 30 * len(score.split())),
            })

            # --- devigged-close-able odds: build Pinnacle decimals from the SAME
            #     latent prob + small noise + ~3% vig, mapped to id-order p1/p2. ---
            noisy = float(np.clip(p1_true + rng.normal(0.0, 0.03), 0.02, 0.98))
            vig = 1.03
            imp1 = noisy * vig
            imp2 = (1.0 - noisy) * vig
            ps_p1 = float(np.clip(1.0 / imp1, 1.01, 50.0))
            ps_p2 = float(np.clip(1.0 / imp2, 1.01, 50.0))
            o_rows.append({
                "event_id": event_id,
                "date_td": date,
                "tour": "atp",
                "tournament_td": f"Event{k % 12} International",
                "round_td": "1st Round",
                "comment": "Completed",
                "b365w": np.float32(ps_p1 if winner == 1 else ps_p2),
                "b365l": np.float32(ps_p2 if winner == 1 else ps_p1),
                "psw": np.float32(ps_p1 if winner == 1 else ps_p2),
                "psl": np.float32(ps_p2 if winner == 1 else ps_p1),
                "maxw": np.float32(ps_p1 if winner == 1 else ps_p2),
                "maxl": np.float32(ps_p2 if winner == 1 else ps_p1),
                "avgw": np.float32(ps_p1 if winner == 1 else ps_p2),
                "avgl": np.float32(ps_p2 if winner == 1 else ps_p1),
                "b365_p1": np.float32(ps_p1),
                "b365_p2": np.float32(ps_p2),
                "ps_p1": np.float32(ps_p1),
                "ps_p2": np.float32(ps_p2),
            })

    matches = pd.DataFrame(m_rows)
    odds = pd.DataFrame(o_rows)
    # enforce the schema dtypes the proofs/helpers expect
    matches["best_of"] = matches["best_of"].astype("int8")
    matches["winner"] = matches["winner"].astype("int8")
    matches["match_num"] = matches["match_num"].astype("int32")
    matches["p1_id"] = matches["p1_id"].astype("Int64")
    matches["p2_id"] = matches["p2_id"].astype("Int64")
    matches["retirement"] = matches["retirement"].astype(bool)

    _OUT.mkdir(parents=True, exist_ok=True)
    matches.to_parquet(_OUT / "matches.parquet", index=False)
    odds.to_parquet(_OUT / "odds.parquet", index=False)
    print(f"wrote {len(matches)} matches, {len(odds)} odds rows to {_OUT}")
    yrs = pd.to_datetime(matches["date"]).dt.year
    print(f"  held-out (year>2022) matches: {int((yrs > 2022).sum())}")


if __name__ == "__main__":
    generate()
