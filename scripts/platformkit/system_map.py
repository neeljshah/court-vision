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
    rows = []
    for s in _SPORTS:
        rows.append({
            "sport": s.upper(),
            "pregame": _PREGAME[s],
            "ingame_repricer": reps.get(s, "?"),
            "ingame": _INGAME[s],
            "data": _DATA[s],
        })
    return {"rows": rows, "repricers": reps, "beat_the_close": btc}


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
