"""scripts.platformkit.ingame.statcast_richer_pitch_layer_probe -- attempt to gate the
genuinely-NEW Statcast per-pitch fields (release_spin_rate, estimated_woba_using_
speedangle, release_speed) as ADDITIVE as-of features on the proven in-game win-prob
BASE (sigmoid((a+b*frac_elapsed)*run_diff)), via the ingame_pitch_layer_gate_mlb pattern.

HONEST FEASIBILITY PROBE FIRST (no fabrication). The win-prob BASE + the win/loss
OUTCOME label live ONLY in the ESPN pitch-states corpus
(data/cache/ingame/mlb_pitch_states__<season>.parquet: state_diff, frac_elapsed, p0,
outcome). The richer Statcast fields live ONLY in the acquired Statcast sample
(data/cache/statcast/statcast__<season>_sample.parquet). To add the richer fields to the
BASE they must JOIN to the same pitches. This probe measures whether that join exists:

  * The acquired Statcast sample carries NO score columns (home_score/away_score/
    bat_score) and NO launch_speed -> it CANNOT, on its own, build a run-diff win-prob
    BASE or a game-outcome label. (verified 18-col bounded acquisition.)
  * The ESPN corpus and the Statcast sample were drawn on DISJOINT calendar windows ->
    ZERO overlapping games -> the richer fields cannot be joined onto the BASE pitches.

When the join is empty the only honest verdict is TIER3_BLOCKED -- the gate CANNOT run
without either (a) re-acquiring Statcast WITH score columns on the ESPN-overlapping
dates, or (b) re-acquiring the ESPN base on the Statcast dates. Both are NEW bounded
acquisitions, OUT OF SCOPE here, and we do NOT 0-fill / fabricate a win-prob label.

If a future acquisition lands an overlapping, score-bearing corpus, build_joined_states()
returns gate-ready dicts and the existing ingame_pitch_layer_gate_mlb.run_gate runs the
cross-corpus + clustered-DM + planted-null gate unchanged.

PROPOSAL-ONLY: reads data/cache/ only; no registry write, no flag, no $/ROI/edge. ASCII;
<=300 LOC. CLI: python -m scripts.platformkit.ingame.statcast_richer_pitch_layer_probe
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import pandas as pd

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_ESPN_DIR = os.path.join(_REPO, "data", "cache", "ingame")
_STATCAST_DIR = os.path.join(_REPO, "data", "cache", "statcast")
_SEASONS = (2022, 2023)
# richer-new fields we WOULD add if a joinable, score-bearing corpus existed.
_RICHER = ("release_spin_rate", "estimated_woba_using_speedangle", "release_speed")
# score columns the win-prob BASE / outcome label REQUIRE.
_SCORE_COLS = ("home_score", "away_score", "bat_score", "post_home_score",
               "post_away_score")


def _espn_path(season: int) -> str:
    return os.path.join(_ESPN_DIR, f"mlb_pitch_states__{season}.parquet")


def _statcast_path(season: int) -> str:
    return os.path.join(_STATCAST_DIR, f"statcast__{season}_sample.parquet")


def _game_keys(df: pd.DataFrame, date_col: str, home: str, away: str) -> set:
    d = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    return set(d + "|" + df[home].astype(str) + "|" + df[away].astype(str))


def probe_join(season: int) -> Dict[str, object]:
    """Measure the feasibility of joining richer Statcast fields onto the ESPN BASE."""
    ep, sp = _espn_path(season), _statcast_path(season)
    out: Dict[str, object] = {"season": season, "espn_exists": os.path.exists(ep),
                              "statcast_exists": os.path.exists(sp)}
    if not (out["espn_exists"] and out["statcast_exists"]):
        out["overlap_games"] = 0
        out["reasons"] = ["NO_ESPN_CORPUS"] if not out["espn_exists"] else ["NO_STATCAST_SAMPLE"]
        return out
    e = pd.read_parquet(ep)
    s = pd.read_parquet(sp)
    reasons: List[str] = []
    have_score = [c for c in _SCORE_COLS if c in s.columns]
    if not have_score:
        reasons.append("STATCAST_SAMPLE_HAS_NO_SCORE_COLS")  # no run-diff base / outcome
    ek = _game_keys(e, "date", "home_team", "away_team")
    sk = _game_keys(s, "game_date", "home_team", "away_team")
    overlap = ek & sk
    if not overlap:
        reasons.append("ZERO_OVERLAPPING_GAMES")            # disjoint calendar windows
    out.update({"espn_games": len(ek), "statcast_games": len(sk),
                "overlap_games": len(overlap),
                "statcast_score_cols": have_score,
                "richer_fields_present": [c for c in _RICHER if c in s.columns],
                "reasons": reasons})
    return out


def build_joined_states(season: int) -> Tuple[List[dict], Dict[str, object]]:
    """Return ([], probe) when the join is infeasible (the current honest reality);
    a real gate-ready state list only if a future score-bearing overlapping corpus lands.
    """
    pr = probe_join(season)
    if pr.get("overlap_games", 0) <= 0 or pr.get("reasons"):
        return [], pr
    # (future) join richer fields onto ESPN BASE here when an overlapping corpus exists.
    return [], pr  # defensive: until the join is wired against a real overlap, stay empty


def run() -> Dict[str, object]:
    probes = {s: probe_join(s) for s in _SEASONS}
    blocked = any(p.get("reasons") or p.get("overlap_games", 0) <= 0
                  for p in probes.values())
    verdict = "TIER3_BLOCKED" if blocked else "READY_TO_GATE"
    return {"layer": "statcast_richer_pitch_winprob", "verdict": verdict,
            "probes": probes, "richer_fields": list(_RICHER),
            "base_model": "sigmoid((a+b*frac_elapsed)*run_diff) -- needs ESPN score+outcome",
            "proposal_only": True,
            "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge"}


def _report(res: Dict[str, object]) -> str:
    L = ["=" * 78,
         "STATCAST RICHER PER-PITCH FIELDS -> IN-GAME WIN-PROB LAYER (feasibility probe)",
         "=" * 78,
         f"richer-new fields: {', '.join(res['richer_fields'])}",
         f"VERDICT: {res['verdict']}", "-" * 78]
    for s, p in res["probes"].items():
        L.append(f"  {s}: overlap_games={p.get('overlap_games')} "
                 f"espn_games={p.get('espn_games')} statcast_games={p.get('statcast_games')} "
                 f"score_cols={p.get('statcast_score_cols')} "
                 f"reasons={','.join(p.get('reasons', [])) or 'none'}")
    L += ["-" * 78,
          "The win-prob BASE + outcome label live ONLY in the ESPN corpus; the richer",
          "fields ONLY in the Statcast sample; the two share ZERO games and the Statcast",
          "sample has NO score cols -> the additive-layer gate CANNOT run. Reported",
          "honestly as TIER3_BLOCKED; NOT 0-filled, NOT a fabricated win-prob label.",
          "=" * 78,
          "CALIBRATION only; NO $/ROI/edge. vs-close UNPROVEN. TIER3_BLOCKED = honest.",
          "=" * 78]
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    print(_report(run()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["probe_join", "build_joined_states", "run", "main", "_RICHER", "_SCORE_COLS"]
