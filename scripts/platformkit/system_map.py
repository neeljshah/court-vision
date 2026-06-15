"""scripts.platformkit.system_map — ONE organized view of the whole prediction system.

Get to an organized place: a single per-sport map of where the system stands — PREGAME
(engine/predictor + calibration vs the close), IN-GAME (repricer + measured sharpness),
DATA (corpus + freshness), INTELLIGENCE (brain concepts wired into the reads). Live-checks
the repricers and pulls the beat-the-close numbers. Writes vault/_Edge_Maps/_System_Map.md
(survives the brain rebuild rmtree, unlike _Organized).

HONEST: prediction-QUALITY map, not a $-edge claim. INVARIANTS: never edit src/ or kernel/;
read-only on the system; <=300 LOC.
Run: python -m scripts.platformkit.system_map
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_SPORTS = ("nba", "mlb", "soccer", "tennis")


def _repricer_status() -> Dict[str, str]:
    from scripts.platformkit.live_repricer import get_repricer
    out: Dict[str, str] = {}
    for s in _SPORTS:
        try:
            r = get_repricer(s)
            out[s] = type(r).__name__ if "Stub" not in type(r).__name__ else "not_wired"
        except Exception as exc:  # noqa: BLE001
            out[s] = f"error: {exc}"
    return out


def _beat_close() -> List[Dict]:
    try:
        from scripts.platformkit.beat_the_close_scoreboard import build
        return build()
    except Exception:  # noqa: BLE001
        return []


# Sane per-sport mid-event demo states (mirror live_read CLI's _SANE/demo_params):
# (elapsed_minutes, home_score, away_score, pregame_params, extra).
_DEMO_STATE = {
    "nba":    (24.0, 58, 50, {"mu_home": 114, "mu_away": 112}, {}),
    "mlb":    (5.0, 3, 2, {"lam_home": 4.6, "lam_away": 4.3}, {"innings_played": 5.0}),
    "soccer": (60.0, 1, 1, {"lam_home": 1.6, "lam_away": 1.2}, {}),
    "tennis": (1.0, 1, 0, {"best_of": 3, "p_set": 0.55}, {"sets_1": 1, "sets_2": 0}),
}


def _ingame_reads() -> Dict[str, Dict]:
    """Exercise live_read (the in-game concept-fusion layer) per sport on a sane demo
    state. This is what wires the orphaned in-game read into the real rebuild. The
    repricer-direct predictor path (predict_live) is unchanged — this is the brain
    concept-fusion view, not the validated predictor."""
    from scripts.platformkit.live_repricer import GameState
    from scripts.platformkit.live_read import build_live_read
    out: Dict[str, Dict] = {}
    for s in _SPORTS:
        try:
            elapsed, home, away, pp, extra = _DEMO_STATE[s]
            state = GameState(sport=s, elapsed_minutes=elapsed, home_score=home,
                              away_score=away, pregame_params=pp, extra=extra)
            out[s] = build_live_read(s, state)
        except Exception as exc:  # noqa: BLE001
            out[s] = {"sport": s, "surface": {"status": f"error: {exc}"},
                      "ingame_concepts": []}
    return out


# Curated per-sport state (kept honest + in sync with the edge maps / commits).
_PREGAME = {
    "nba": "MOV-Elo win-prob MATCHES the close (Brier +0.006); possessions/eff totals trail "
           "~1 RMSE (freshness). Usable: domains/basketball_nba/predictor.py (+to_jd).",
    "mlb": "Elo + validated NegBinom over-dispersed run engine (wired into JointDistribution); "
           "O/U Brier -0.014..-0.021 vs Poisson. Pitcher-blind -> ~0.010 behind the close.",
    "soccer": "Poisson goals + DC-rho + finishing-regression prior; pooled Platt recal is the "
              "big win (O/U ECE 0.107->0.012). Per-division mean-shift absorbed (null).",
    "tennis": "Elo + Platt (ATP ECE 0.048->0.019); WTA over-confident (T=1.39), temperature is "
              "the recalibrator of choice (honest data-limited FAIL on the strict bar).",
}
_INGAME = {
    "nba": "NBARepricer (Gaussian score-anchor). BACKTESTED on 1,313 games (per-quarter "
           "linescores): COMBINED pregame-rating-prior + realized-score = Brier 0.159, beats "
           "pregame-Elo 0.209 AND score-only 0.172. Usable: predictor.predict_live(). "
           "Per-quarter curve = null (quarters uniform). THE in-game advantage, measured.",
    "mlb": "MLBRepricer + empirical per-inning run curve (final-total bias -35% vs flat). "
           "Backtested: conditional Brier 0.13 vs static 0.25 (repricer_calibration.py).",
    "soccer": "SoccerRepricer (bivariate-Poisson + DC-rho, remaining-minutes scaling). No "
              "leak-free per-minute timeline on disk yet -> not backtested.",
    "tennis": "TennisRepricer (race-to-N-sets, set-score conditional). Score string is "
              "winner-ordered -> no leak-free replay corpus yet.",
}
_DATA = {
    "nba": "ESPN box 2024-26 (1,977 games; FGA/FTA/TOV/OREB parsed) + odds 2025-26 + per-quarter "
           "linescores. Freshness (injuries) in ESPN summary - not yet ingested as as-of.",
    "mlb": "SBR odds 2010-2021 (27,983 games) + per-inning linescores + SP corpus. Richest odds.",
    "soccer": "football-data 2015-2025 (25,834 games, 6 divisions) + SoT as-of + odds.",
    "tennis": "Sackmann ATP 30,616 + WTA 8,001 + serve stats; odds closing-only (CLV blocked).",
}


def build() -> Dict:
    reps = _repricer_status()
    btc = {f"{r.get('sport','?')}:{r.get('market','?')}".lower(): r for r in _beat_close()}
    live = _ingame_reads()
    rows = []
    for s in _SPORTS:
        rows.append({
            "sport": s.upper(),
            "pregame": _PREGAME[s],
            "ingame_repricer": reps.get(s, "?"),
            "ingame": _INGAME[s],
            "data": _DATA[s],
        })
    return {"rows": rows, "repricers": reps, "beat_the_close": btc, "live_reads": live}


def _summarize_live(read: Dict) -> str:
    """One-line summary of a live_read: top win/match prob + concept count."""
    surf = read.get("surface", {}) or {}
    if surf.get("status"):
        prob = f"_({surf['status']})_"
    else:
        prob = "—"
        for kh, ka, lbl in (("win_home", "win_away", "win"),
                            ("ml_home", "ml_away", "ML"),
                            ("match_win_p1", "match_win_p2", "match"),
                            ("1X2_home", "1X2_away", "1X2")):
            if kh in surf:
                prob = f"{lbl} home/p1={surf[kh]:.3f} away/p2={surf[ka]:.3f}"
                break
    n_concepts = len(read.get("ingame_concepts", []))
    return f"re-priced surface [{prob}] + {n_concepts} in-game brain concepts"


def render_markdown(m: Dict) -> str:
    L = ["# System Map — pregame + in-game, per sport (organized)", "",
         "> ONE honest view: how the system predicts each sport pregame AND in-game, the data "
         "behind it, and where it stands vs the market. In-game = the real edge (conditioning "
         "on realized state beats the static line). Prediction-quality, NOT a $ edge.", "",
         "## Beat-the-close (measured)", ""]
    btc = m["beat_the_close"]
    if btc:
        L += ["| Sport:Market | Our model | Close | Verdict |", "|---|---|---|---|"]
        for k, r in btc.items():
            if r.get("status"):
                L.append(f"| {k} | — | — | {r['status']} |")
            else:
                L.append(f"| {k} | {r['model']} | {r['close']} | {r['verdict']} |")
    L += ["", "## Per-sport pregame + in-game", ""]
    for r in m["rows"]:
        L += [f"### {r['sport']}",
              f"- **Pregame:** {r['pregame']}",
              f"- **In-game** (`{r['ingame_repricer']}`): {r['ingame']}",
              f"- **Data:** {r['data']}", ""]
    # In-game concept-fusion layer (live_read), exercised on a sane per-sport demo.
    live = m.get("live_reads", {})
    if live:
        L += ["## In-game read (live_read concept-fusion, demo state)",
              "",
              "> The in-game counterpart of the cohesive read: each sport's repricer "
              "re-prices the remaining markets (gate-owned engine) and the brain's "
              "relevant IN-GAME concepts are fused in (descriptive only). Demo mid-event "
              "state; not the validated `predict_live` predictor path (that stays "
              "repricer-direct). No edge claimed.", ""]
        for s in _SPORTS:
            rd = live.get(s)
            if not rd:
                continue
            ds = _DEMO_STATE.get(s)
            state_str = (f"score=({ds[1]},{ds[2]}) elapsed={ds[0]}" if ds else "?")
            L.append(f"- **{s.upper()}** _(demo {state_str})_: {_summarize_live(rd)}")
        L += [""]
    L += ["## In-game scoreboard (measured, conditional vs static)", "",
          "> The in-game counterpart of beat-the-close: where a leak-free per-period corpus "
          "exists, the conditional-on-realized-state forecaster vs the static/pregame line "
          "(lower Brier = sharper). Full table + numbers in `_Ingame_Scoreboard.md` "
          "(`scripts.platformkit.ingame_scoreboard`).",
          "- **NBA** (per-quarter): Brier 0.209 -> **0.159** (combined rating prior + score) = WIN",
          "- **MLB** (per-inning): vs a REAL pregame-Elo prior 0.241 -> combined **0.126** "
          "(pregame prior + realized runs; > score-only 0.128) = WIN",
          "- **Soccer** (half-time): 1X2 Brier 0.626 -> **0.502**, O/U-2.5 0.264 -> **0.176** = WIN",
          "- **Tennis (ATP)** (after set 1): Brier 0.219 -> **0.151** (combined: Elo prior + "
          "1-0 set lead; > score-only 0.162) = WIN -- UNBLOCKED W155 via the set-1-leader "
          "framing (scoreboard now 4/4)", ""]
    L += ["## The honest bottom line",
          "- We MATCH the market on team-strength markets (NBA moneyline); we trail on "
          "totals only by the FRESHNESS edge (injuries/lineups).",
          "- IN-GAME is the real advantage: conditioning on realized state beats the static "
          "line (MLB measured; NBA now backtestable via per-quarter linescores).",
          "- The path to fully beat the close: the market's freshness DATA (an injury/lineup "
          "feed forward) + deeper in-game conditioning + every brain concept as a structural "
          "prior. More/own data -> better predictions, re-measured against the close."]
    return "\n".join(L)


def write_report(root: Path = None) -> Path:
    out = (root or _REPO) / "vault" / "_Edge_Maps" / "_System_Map.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(build()), encoding="utf-8")
    return out


def _main() -> int:
    print(render_markdown(build()))
    try:
        print(f"\n(written -> {write_report()})")
    except Exception as exc:  # noqa: BLE001
        print(f"\n(not written: {exc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
