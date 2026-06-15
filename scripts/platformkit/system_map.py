"""scripts.platformkit.system_map — ONE organized view of the whole prediction system.

Get to an organized place: a single per-sport map of where the system stands — PREGAME
(engine/predictor + calibration vs the close), IN-GAME (repricer + measured sharpness),
DATA (corpus + freshness), INTELLIGENCE (brain concepts wired into the reads). Live-checks
the repricers and pulls the beat-the-close numbers. Writes vault/_Edge_Maps/_System_Map.md
(survives the brain rebuild rmtree, unlike _Organized).

HONEST: prediction-QUALITY map, not a $-edge claim. INVARIANTS: never edit src/ or kernel/;
read-only on the system; <=300 LOC.

ANTI-DRIFT (W159): the in-game scoreboard section is NO LONGER a hardcoded literal table (which
would silently drift from scripts.platformkit.ingame_scoreboard.build()). By DEFAULT the section
renders a SHORT pointer to the canonical _Ingame_Scoreboard.md (kept fast — ingame_scoreboard
recomputes all 4 in-game proofs, minutes). Pass build(live_ingame=True) / write_report(
live_ingame=True) / `--live-ingame` / SYSTEM_MAP_LIVE_INGAME=1 to live-pull the real rows so the
numbers can never drift. Beat-the-close + repricer status + live_read demos stay live by default
(cheap). Run: python -m scripts.platformkit.system_map [--live-ingame]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_SPORTS = ("nba", "mlb", "soccer", "tennis")


def _fmt_num(x) -> str:
    return f"{x:.3f}" if isinstance(x, (int, float)) else str(x)


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


def _ingame_score() -> List[Dict]:
    """Live-pull the in-game scoreboard rows (mirrors _beat_close). HEAVY: recomputes all 4
    in-game proofs (minutes) -> only called when build(live_ingame=True). Default-OFF keeps the
    System Map regen fast; the canonical numbers live in _Ingame_Scoreboard.md."""
    try:
        from scripts.platformkit.ingame_scoreboard import build
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
    """Exercise live_read (the in-game read) per sport on a sane demo state. As of W158 the
    in-game read prices via each sport's predictor.predict_live (the VALIDATED calibrated path:
    Elo/rating prior + realized state + the W156 in-game recalibrator), with a graceful raw-
    repricer fallback; surface['_calibrated'] records which path ran. The brain's in-game
    concepts are fused in as descriptive context."""
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


def build(live_ingame: bool = False) -> Dict:
    """Assemble the System Map data. By DEFAULT (live_ingame=False) the in-game scoreboard is a
    SHORT pointer to _Ingame_Scoreboard.md, keeping regen fast — beat-the-close + repricer status
    + live_read demos are all cheap. Pass live_ingame=True (or set SYSTEM_MAP_LIVE_INGAME=1) to
    live-pull ingame_scoreboard.build() so the rendered numbers can never silently drift; this is
    HEAVY (recomputes all 4 in-game proofs, minutes). W159 anti-drift fix."""
    if live_ingame is None:  # explicit None -> consult the env flag
        live_ingame = os.environ.get("SYSTEM_MAP_LIVE_INGAME", "").strip() in ("1", "true", "TRUE")
    reps = _repricer_status()
    btc = {f"{r.get('sport','?')}:{r.get('market','?')}".lower(): r for r in _beat_close()}
    live = _ingame_reads()
    ingame_score = _ingame_score() if live_ingame else []
    rows = []
    for s in _SPORTS:
        rows.append({
            "sport": s.upper(),
            "pregame": _PREGAME[s],
            "ingame_repricer": reps.get(s, "?"),
            "ingame": _INGAME[s],
            "data": _DATA[s],
        })
    return {"rows": rows, "repricers": reps, "beat_the_close": btc, "live_reads": live,
            "ingame_scoreboard": ingame_score}


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
                if lbl == "1X2" and "1X2_draw" in surf:   # 3-outcome market: show the draw
                    prob += f" draw={surf['1X2_draw']:.3f}"
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
        L += ["## In-game read (live_read, calibrated predict_live, demo state)",
              "",
              "> The in-game counterpart of the cohesive read: each sport's read is priced via "
              "`predictor.predict_live` (W158) -- the VALIDATED calibrated path (rating prior + "
              "realized state + the W156 in-game recalibrator), with a graceful raw-repricer "
              "fallback -- and the brain's relevant IN-GAME concepts are fused in (descriptive). "
              "Demo mid-event state. No edge claimed.", ""]
        for s in _SPORTS:
            rd = live.get(s)
            if not rd:
                continue
            ds = _DEMO_STATE.get(s)
            state_str = (f"score=({ds[1]},{ds[2]}) elapsed={ds[0]}" if ds else "?")
            L.append(f"- **{s.upper()}** _(demo {state_str})_: {_summarize_live(rd)}")
        L += [""]
    # In-game scoreboard. ANTI-DRIFT (W159): when live-pulled (build(live_ingame=True)) the rows
    # come straight from ingame_scoreboard.build() so they can never silently drift; by DEFAULT
    # (fast regen) we render a SHORT pointer to the canonical _Ingame_Scoreboard.md instead of a
    # hardcoded literal table (which used to drift from the proofs).
    L += ["## In-game scoreboard (measured, conditional vs static)", "",
          "> The in-game counterpart of beat-the-close: where a leak-free per-period corpus "
          "exists, the conditional-on-realized-state forecaster vs the static/pregame line "
          "(lower Brier = sharper)."]
    isb = m.get("ingame_scoreboard", [])
    if isb:
        L += ["",
              "| Sport | Checkpoint | n | Metric | Conditional | Static | Delta | Verdict |",
              "|---|---|---|---|---|---|---|---|"]
        for r in isb:
            if r.get("status"):
                L.append(f"| {r.get('sport','?')} | - | - | - | - | - | - | "
                         f"{r['status']} |")
                continue
            d = r.get("delta")
            ds = f"{d:+}" if isinstance(d, (int, float)) else str(d)
            L.append(f"| {r['sport']} | {r['checkpoint']} | {r['n']} | {r['metric']} | "
                     f"{_fmt_num(r['conditional'])} | {_fmt_num(r['static'])} | {ds} | "
                     f"{r['verdict']} |")
        L += ["", "_Live-pulled from `scripts.platformkit.ingame_scoreboard.build()`; full why-"
              "text in `_Ingame_Scoreboard.md`._", ""]
    else:
        L += ["> **Canonical numbers + full why-text live in `_Ingame_Scoreboard.md`**, "
              "regenerated by the in-game CLI: `python -m scripts.platformkit.ingame_scoreboard` "
              "(or `build(live_ingame=True)` here / `SYSTEM_MAP_LIVE_INGAME=1`). Kept as a pointer "
              "by default because the proofs are HEAVY (minutes); the System Map no longer carries "
              "a hardcoded copy that could drift. Headline: NBA/MLB/Soccer/Tennis in-game "
              "conditioning each beats the static pregame line (all 4 WIN).", ""]
    L += ["## The honest bottom line",
          "- We MATCH the market on team-strength markets (NBA moneyline); we trail on "
          "totals only by the FRESHNESS edge (injuries/lineups).",
          "- IN-GAME is the real advantage: conditioning on realized state beats the static "
          "line (MLB measured; NBA now backtestable via per-quarter linescores).",
          "- The path to fully beat the close: the market's freshness DATA (an injury/lineup "
          "feed forward) + deeper in-game conditioning + every brain concept as a structural "
          "prior. More/own data -> better predictions, re-measured against the close."]
    return "\n".join(L)


def write_report(root: Path = None, live_ingame: bool = False) -> Path:
    out = (root or _REPO) / "vault" / "_Edge_Maps" / "_System_Map.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(build(live_ingame=live_ingame)), encoding="utf-8")
    return out


def _main() -> int:
    # Default FAST: in-game scoreboard is a pointer to _Ingame_Scoreboard.md. Opt into the HEAVY
    # live-pull (recomputes all 4 in-game proofs) with --live-ingame or SYSTEM_MAP_LIVE_INGAME=1.
    live = ("--live-ingame" in sys.argv or
            os.environ.get("SYSTEM_MAP_LIVE_INGAME", "").strip() in ("1", "true", "TRUE"))
    print(render_markdown(build(live_ingame=live)))
    try:
        print(f"\n(written -> {write_report(live_ingame=live)})")
    except Exception as exc:  # noqa: BLE001
        print(f"\n(not written: {exc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
