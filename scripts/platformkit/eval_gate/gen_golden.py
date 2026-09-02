"""Offline deterministic generator for the SYNTHETIC golden game-state fixture (blueprint N1).

SYNTHETIC reproducibility/regression ANCHOR. Not real games, not a real calibration
claim. The gate READS the committed fixture; it never regenerates at gate time. A
BSS <= 0 / MATCHES_CLOSE verdict on this anchor is an HONEST success (a near-oracle
close is, by construction, unbeatable), never a failure.

Run once by a human:
    python gen_golden.py
-> writes tests/fixtures/golden/game_states.json (README.md / SCHEMA.md are hand-written).

DETERMINISTIC: numpy default_rng(20260616) seeded once at the top of build_states; no
wall-clock time, no uuid, no hashing. Re-running yields a byte-identical fixture so the
JSON diff is stable. numpy + stdlib only. ASCII only. No retracted numbers are emitted.

Generative truth model (leak-free, learnable):
    p_true = sigmoid(beta . features), beta = (1.4, 0.5, 0.25), clipped to [0.05, 0.95].
    outcome = int(rng.random() < p_true).
    devig_close_prob = clip(p_true + N(0, 0.03), 0.02, 0.98)  -- a slightly-noised oracle,
        so the model cannot beat the close: MATCHES_CLOSE / BSS<=0 is the natural verdict.
    truth_wp = p_true (pregame truth_wp may equal devig).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta

import numpy as np

# Repo root = three levels up from this file (scripts/platformkit/eval_gate/gen_golden.py).
# Resolve absolutely so the fixture always lands at the git-tracked repo-root location
# regardless of the cwd the human runs `python gen_golden.py` from.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir, os.pardir, os.pardir))
OUT_PATH = os.path.join(_REPO_ROOT, "tests", "fixtures", "golden", "game_states.json")
SEED = 20260616
BETA = np.array([1.4, 0.5, 0.25])           # strength, rest, home_edge
SEASONS = ("2023-24", "2024-25")
TEAMS = ("ATL", "BOS", "CHI", "DAL", "DEN", "GSW",
         "LAL", "MIA", "MIL", "NYK", "PHX", "SAS")

# (regime, count) -- sums to 105, in [90,120]; every REQUIRED_REGIME present.
STRATA = (
    ("pregame", 35),
    ("q1", 12), ("q2", 12), ("q3", 12), ("q4", 12),
    ("blowout", 6), ("foul_trouble", 6),
    ("early_season", 4), ("longshot", 4),
)
# Start dates spread across a season so the expanding window has real train history
# and purge/embargo occasionally fire. early_season is forced into October.
SEASON_START = datetime(2024, 11, 1)
SEASON_END = datetime(2025, 3, 15)


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + np.exp(-z))


def _r6(x: float) -> float:
    return round(float(x), 6)


def _quarter_minutes(regime: str) -> int:
    """Minutes after tip for an in-game state so within-game states are ordered/distinct."""
    return {"q1": 8, "q2": 32, "q3": 56, "q4": 84}.get(regime, 0)


def build_states(rng) -> list:
    """Pure builder: deterministic given `rng`. Returns a list of schema-valid dicts."""
    states: list = []
    span_days = (SEASON_END - SEASON_START).days
    idx = 0  # global state index, drives unique game_ids

    # ~70 distinct game_ids: assign 1-2 states per game. In-game quarters of the SAME
    # game share a game_id (different state_ts) to exercise clustering + purge/embargo.
    for regime, count in STRATA:
        for _ in range(count):
            game_id = "g%04d" % (idx % 70)   # 70 buckets -> healthy DM n_clusters
            idx += 1

            season = SEASONS[idx % 2]
            # distinct home/away from the 12-team pool, deterministic from rng
            h, a = rng.choice(len(TEAMS), size=2, replace=False)
            home, away = TEAMS[int(h)], TEAMS[int(a)]

            # --- feature draws, regime-shaped ---
            strength = float(rng.normal(0.0, 0.6))
            rest = float(rng.normal(0.0, 1.0))
            home_edge = float(rng.normal(0.4, 0.3))
            feats = {"strength": _r6(strength), "rest": _r6(rest),
                     "home_edge": _r6(home_edge)}

            # game_date across the season; early_season forced to October.
            if regime == "early_season":
                # first 20 games window: October of the season
                gd = datetime(2024, 10, 1) + timedelta(days=int(rng.integers(0, 18)))
            else:
                gd = SEASON_START + timedelta(days=int(rng.integers(0, span_days)))
            game_date = gd.date().isoformat()

            # latent truth from the generative model
            z = float(np.dot(BETA, [strength, rest, home_edge]))

            if regime == "blowout":
                # large |strength| -> extreme latent p
                strength = float(np.sign(strength or 1.0) * (2.5 + abs(rng.normal(0, 0.4))))
                feats["strength"] = _r6(strength)
                z = float(np.dot(BETA, [strength, rest, home_edge]))
            if regime == "foul_trouble":
                # extra feature exercised; shifts the latent
                foul_diff = float(rng.normal(0.0, 1.2))
                feats["foul_diff"] = _r6(foul_diff)
                z += 0.4 * foul_diff
            if regime == "longshot":
                # force a near-0.06 or near-0.94 p_true to stress favorite-longshot bias
                hi = bool(rng.integers(0, 2))
                p_true = 0.94 if hi else 0.06
                z = float(np.log(p_true / (1.0 - p_true)))
                strength = z / BETA[0]
                feats = {"strength": _r6(strength), "rest": _r6(rest),
                         "home_edge": _r6(home_edge)}

            p_true = float(np.clip(_sigmoid(z), 0.05, 0.95))
            outcome = int(rng.random() < p_true)
            devig = float(np.clip(p_true + rng.normal(0.0, 0.03), 0.02, 0.98))
            truth_wp = p_true

            # state timestamp: pregame at tip 19:00; in-game quarters offset in minutes
            tip = datetime.fromisoformat(game_date + "T19:00:00")
            state_dt = tip + timedelta(minutes=_quarter_minutes(regime))
            state_ts = state_dt.isoformat()

            # feature_avail: day before the game at midnight -> strictly < state_ts.
            avail_dt = datetime.fromisoformat(game_date + "T00:00:00") - timedelta(days=1)
            avail_ts = avail_dt.isoformat()
            feature_avail = {f: avail_ts for f in feats}

            states.append({
                "game_id": game_id,
                "season": season,
                "sport": "nba",
                "regime": regime,
                "game_date": game_date,
                "state_ts": state_ts,
                "home": home,
                "away": away,
                "features": {k: _r6(v) for k, v in feats.items()},
                "feature_avail": feature_avail,
                "devig_close_prob": _r6(devig),
                "truth_wp": _r6(truth_wp),
                "outcome": int(outcome),
            })

    # de-dup the (game_id, state_ts) key the schema enforces: nudge collisions by +1 min
    seen = set()
    for s in states:
        key = (s["game_id"], s["state_ts"])
        while key in seen:
            dt = datetime.fromisoformat(s["state_ts"]) + timedelta(minutes=1)
            s["state_ts"] = dt.isoformat()
            key = (s["game_id"], s["state_ts"])
        seen.add(key)
    return states


def write_sidecar(out_path: str) -> str:
    """Write `<out_path>.sha256` holding the fixture's digest; return the digest."""
    digest = hashlib.sha256(open(out_path, "rb").read()).hexdigest()
    with open(out_path + ".sha256", "w", encoding="ascii") as fh:
        fh.write(digest + "\n")
    return digest


def emit_seal(out_path: str) -> str:
    """S51: write `<fixture>.sha256` and refresh golden_loader.GOLDEN_SHA256 in place.

    The gate seals the fixture's BYTES (S40b agent 1.2). Before this, regenerating meant
    hand-computing the digest and hand-editing the constant, so a legitimate regeneration
    left the gate red. The sidecar is the emitted seal; the constant stays as the fallback
    pin, and golden_loader fails closed if the two ever disagree.
    """
    digest = write_sidecar(out_path)
    loader = os.path.join(_HERE, "golden_loader.py")
    with open(loader, "r", encoding="ascii") as fh:
        src = fh.read()
    new = re.sub(r'^GOLDEN_SHA256 = "[0-9a-f]{64}"$',
                 'GOLDEN_SHA256 = "%s"' % digest, src, count=1, flags=re.M)
    if new != src:
        with open(loader, "w", encoding="ascii") as fh:
            fh.write(new)
    return digest


def main() -> None:
    rng = np.random.default_rng(SEED)
    states = build_states(rng)

    # validate before writing (schema lives beside this file in the eval_gate package)
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import schema  # noqa: E402

    schema.validate_golden(states)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    payload = {
        "schema": schema.GOLDEN_SCHEMA_VERSION,
        "_synthetic": True,  # SYNTHETIC ANCHOR -- not real games, not a calibration claim
        "n": len(states),
        "states": states,
    }
    with open(OUT_PATH, "w", encoding="ascii") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True, ensure_ascii=True)

    digest = emit_seal(OUT_PATH)

    regimes = sorted({s["regime"] for s in states})
    print("OK %d states, regimes=%s" % (len(states), regimes))
    print("GOLDEN_SHA256 = %s" % digest)


if __name__ == "__main__":
    main()
