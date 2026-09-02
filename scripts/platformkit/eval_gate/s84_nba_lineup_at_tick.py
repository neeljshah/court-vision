"""scripts.platformkit.eval_gate.s84_nba_lineup_at_tick -- S84 NBA LINEUP-AT-TICK screen.

S84's premise -- the two NBA in-game stores are one join away -- is FALSIFIED. The priced
inplay_odds/nba_checkpoints_full.parquet (465,249 ticks, 1,593 games) is keyed by the ESPN
event id, ingame_eval_cache.parquet (2,476,544 rows, 1,987 games) by the NBA-Stats game id,
their seasons barely overlap (32 games in common), and an eval-cache row is ONE player's ONE
projected stat at one of 11 elapsed buckets -- no on-floor state. The five on the floor come
instead from the play-by-play stream team_system/pbp*/<nba_game_id>.json (3,652 games,
substitutions with personId + subType in/out), bridged to the priced corpus by the
incumbent's OWN crosswalk (nba_mechanism_ladder.build_crosswalk).
LINEUP-AT-TICK is tick-time as-of by construction: only substitutions whose game clock is
STRICTLY before the tick's elapsed time are applied, and assert_strictly_before raises
AsOfViolation on a same-tick or later read (tested).
ONE SCREEN: lineup strength = the five home players' pregame as-of ratings minus the five
away players' (asof_player_adv.pie_asof, centred per game), added as ONE logistic term to
the NBA in-game incumbent -- nba_mechanism_ladder's BASE, a logistic on standardized
[logit(p0_first_traded), signed margin, margin/sqrt(rem_frac)]. Market line = market_prob.
Screen side of a game-level partition only; game-first-date walk-forward, train games purged
(disjoint) and embargoed 1 day; standardisation fit inside each train fold.
A SCREEN is a NON-FINDING: no prereg seal, no ledger charge, no K read. SINGLE-WINDOW.
Calibration language only (Brier); no dollar, ROI or edge claim. ASCII only.
Test: python -m pytest tests/platformkit/ingame/test_s84_nba_lineup_at_tick.py -q
CLI: python -m scripts.platformkit.eval_gate.s84_nba_lineup_at_tick
"""
from __future__ import annotations

import glob
import json
import os
import re
from datetime import date as _date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import pandas as pd

from scripts.platformkit.eval_gate.catalog_rescreen import verdict_of
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.foundry.tiers import partition_corpus
from scripts.platformkit.ingame.nba_mechanism_ladder import (_BASE_COLS, _fit_predict,
                                                             build_crosswalk, load_corpus)

REPO = Path(__file__).resolve().parents[3]
PBP_GLOB = str(REPO / "data" / "cache" / "team_system" / "pbp*" / "*.json")
ADV = REPO / "data" / "domains" / "basketball_nba" / "asof_player_adv.parquet"
OUT_DIR = REPO / "data" / "cache" / "eval_gate"
STEM = "s84_nba_lineup_2026-09-03"
RATING = "pie_asof"          # as-of player impact estimate, strictly pregame for that game
FEATURE = "lineup_strength"
PARTITION_SEED = 0
MIN_TRAIN_TICKS = 500
IMPROVEMENT_BAR = 0.004      # prereg DRAFT only at or above this; never a charge
_CLOCK = re.compile(r"PT0*(\d+)M0*([\d.]+)S")
_TICK_COLS = ("ts", "game_date", "period", "elapsed", "outcome_home_win", "market_prob",
              "logit_p0", "margin_s", "z")


class AsOfViolation(ValueError):
    """A substitution at or after the tick's own game clock reached a lineup read."""


def assert_strictly_before(events: Sequence[dict], tick_elapsed: float, label: str) -> None:
    """THE tick-time guard: every event used for a lineup must predate the tick strictly."""
    bad = [e for e in events if float(e["elapsed"]) >= float(tick_elapsed)]
    if bad:
        raise AsOfViolation("%s: %d event(s) at or after tick elapsed %.1fs (first %.1fs)"
                            % (label, len(bad), float(tick_elapsed), float(bad[0]["elapsed"])))


def parse_clock(text: Any) -> float:
    """PT7M2.00S -> 422.0 seconds REMAINING in the period; -1.0 when unparseable."""
    match = _CLOCK.match(str(text))
    return float(match.group(1)) * 60.0 + float(match.group(2)) if match else -1.0


def elapsed_of(period: int, clock_remaining: float) -> float:
    """Seconds of game time elapsed at (period, clock remaining). OT periods are 300s."""
    period, clock = int(period), float(clock_remaining)
    return ((period - 1) * 720.0 + 720.0 - clock if period <= 4
            else 2880.0 + (period - 5) * 300.0 + 300.0 - clock)


def game_events(path: str) -> Tuple[List[dict], Dict[str, frozenset]]:
    """Substitutions (elapsed-sorted) + the inferred starting five per team tricode.

    A player starts if his FIRST appearance is a non-substitution action or a substitution he
    is leaving on (subType out) -- both mean he was already on the floor.
    """
    with open(path, encoding="utf-8") as handle:
        actions = json.load(handle)["game"]["actions"]
    events = []
    for order, act in enumerate(actions):
        clock = parse_clock(act.get("clock"))
        if clock < 0.0:
            continue
        events.append({"elapsed": elapsed_of(act["period"], clock), "order": order,
                       "team": act.get("teamTricode"), "player": act.get("personId"),
                       "kind": act["actionType"], "sub": act.get("subType")})
    events.sort(key=lambda e: (e["elapsed"], e["order"]))
    seen, starters = set(), {}
    for ev in events:
        if not ev["player"] or not ev["team"] or ev["player"] in seen:
            continue
        seen.add(ev["player"])
        if ev["kind"] != "substitution" or ev["sub"] == "out":
            starters.setdefault(ev["team"], []).append(int(ev["player"]))
    subs = [e for e in events if e["kind"] == "substitution" and e["sub"] in ("in", "out")
            and e["player"] and e["team"]]
    return subs, {t: frozenset(v[:5]) for t, v in starters.items()}


def lineup_at(subs: Sequence[dict], starters: Dict[str, frozenset],
              tick_elapsed: float) -> Dict[str, frozenset]:
    """The five on the floor per team at tick_elapsed, from strictly-earlier events only."""
    used = [s for s in subs if float(s["elapsed"]) < float(tick_elapsed)]
    assert_strictly_before(used, tick_elapsed, "lineup_at")
    floor = {team: set(five) for team, five in starters.items()}
    for ev in used:
        side = floor.get(ev["team"])
        if side is None:
            continue
        (side.add if ev["sub"] == "in" else side.discard)(int(ev["player"]))
    return {team: frozenset(side) for team, side in floor.items()}


def _ratings(adv: pd.DataFrame, nba_game_id: str) -> Dict[int, float]:
    """Per-game as-of rating, centred on that game's own rated players (unknown -> 0.0)."""
    block = adv[adv["game_id"] == nba_game_id]
    vals = block[RATING].astype(float)
    base = float(vals.mean()) if vals.notna().any() else 0.0
    return {int(p): float(v) - base for p, v in zip(block["player_id"], vals) if pd.notna(v)}


def build_lineups(corpus: pd.DataFrame, crosswalk: pd.DataFrame, adv: pd.DataFrame,
                  pbp: Dict[str, str]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Attach lineup-at-tick + the lineup-strength term to every live-clock priced tick."""
    rated = set(adv["game_id"].astype(str))
    cw = crosswalk[crosswalk["nba_game_id"].astype(str).isin(pbp)].copy()
    cover = {"n_games_priced": int(corpus["game_id"].nunique()),
             "n_games_bridged": int(len(crosswalk)), "n_games_bridged_with_pbp": int(len(cw)),
             "n_games_bridged_with_pbp_and_ratings":
                 int(cw["nba_game_id"].astype(str).isin(rated).sum())}
    live = corpus[corpus["game_clock_s"] > 0.0].copy()   # live clock; 0.0 = dead/post-period tick
    live["elapsed"] = [elapsed_of(p, c) for p, c in zip(live["period"], live["game_clock_s"])]
    blocks = dict(tuple(live.groupby("game_id")))
    rows, n_bad_start, n_not5 = [], 0, 0
    for rec in cw.itertuples(index=False):
        block = blocks.get(rec.game_id)
        if block is None or str(rec.nba_game_id) not in rated:
            continue
        subs, starters = game_events(pbp[str(rec.nba_game_id)])
        if sorted(starters) != sorted([rec.home, rec.away]) or any(
                len(v) != 5 for v in starters.values()):
            n_bad_start += 1
            continue
        rate = _ratings(adv, str(rec.nba_game_id))
        for tick in block.itertuples(index=False):
            floor = lineup_at(subs, starters, tick.elapsed)
            home, away = floor[rec.home], floor[rec.away]
            if len(home) != 5 or len(away) != 5:
                n_not5 += 1
                continue
            row = {c: getattr(tick, c) for c in _TICK_COLS}
            row.update(game=str(rec.game_id), nba_game_id=str(rec.nba_game_id),
                       home_five="|".join(str(p) for p in sorted(home)),
                       away_five="|".join(str(p) for p in sorted(away)))
            row[FEATURE] = (sum(rate.get(p, 0.0) for p in home)
                            - sum(rate.get(p, 0.0) for p in away))
            rows.append(row)
    frame = pd.DataFrame(rows)
    cover.update(n_games_lineup=int(frame["game"].nunique()) if len(frame) else 0,
                 n_ticks_live_clock=int(len(live)), n_ticks_lineup=int(len(frame)),
                 n_games_starters_not_5v5=int(n_bad_start), n_ticks_floor_not_5v5=int(n_not5))
    if frame.empty:
        return frame, cover
    frame["date"] = frame["game"].map(frame.groupby("game")["game_date"].min())  # game-first-date
    return frame.sort_values(["ts", "game"], kind="stable").reset_index(drop=True), cover


def screen_side(frame: pd.DataFrame, seed: int = PARTITION_SEED):
    """foundry partition on game blocks -> the SCREEN-side rows and the partition record."""
    states = [{"game_id": g, "corpus_unit": g, "state_ts": d + "T00:00:00"}
              for g, d in frame.groupby("game")["date"].min().items()]
    part = partition_corpus(states, seed=seed)
    return frame[frame["game"].isin(part.screen_ids)].reset_index(drop=True), part


def walk_forward(frame: pd.DataFrame, *, embargo_days: int) -> Tuple[pd.DataFrame, List[dict]]:
    """Game-first-date walk-forward; train games are purged (disjoint) and embargoed."""
    scored, folds = [], []
    for day in sorted(frame["date"].unique()):
        cut = str(_date.fromisoformat(day) - timedelta(days=int(embargo_days)))
        train, test = frame[frame["date"] < cut], frame[frame["date"] == day].copy()
        if len(train) < MIN_TRAIN_TICKS or train["outcome_home_win"].nunique() < 2:
            folds.append({"test_date": day, "status": "INSUFFICIENT", "n_train": len(train)})
            continue
        assert not (set(train["game"]) & set(test["game"])), "fold not game-disjoint (purge)"
        assert train["date"].max() < cut <= day, "embargo/ordering violated"
        test["p_incumbent"] = _fit_predict(train, test, list(_BASE_COLS))
        test["p_candidate"] = _fit_predict(train, test, list(_BASE_COLS) + [FEATURE])
        scored.append(test)
        folds.append({"test_date": day, "status": "OK", "embargo_cut": cut,
                      "n_train_ticks": int(len(train)), "train_date_max": str(train["date"].max()),
                      "n_train_games": int(train["game"].nunique()),
                      "n_test_ticks": int(len(test)), "n_test_games": int(test["game"].nunique()),
                      "feature_mu": float(train[FEATURE].mean()),
                      "feature_sd": float(train[FEATURE].std(ddof=0))})
    return (pd.concat(scored, ignore_index=True) if scored else frame.iloc[0:0].copy()), folds


def score(scored: pd.DataFrame, folds: List[dict], part, *, embargo_days: int,
          cover: Dict[str, Any]) -> Tuple[dict, pd.DataFrame]:
    """Tick-weighted Brier + game-clustered DM vs the incumbent and vs the market line."""
    y = scored["outcome_home_win"].to_numpy(dtype=float)
    l_inc = (scored["p_incumbent"].to_numpy() - y) ** 2
    l_cand = (scored["p_candidate"].to_numpy() - y) ** 2
    l_mkt = (scored["market_prob"].to_numpy() - y) ** 2
    diff = l_inc - l_cand                                  # d > 0 -> the candidate lost less
    games = scored["game"].astype(str).tolist()
    def _dm(series) -> dict:
        r = diebold_mariano(list(series), games)
        return {"stat": float(r.dm_stat), "p_value": float(r.p_value),
                "ci95": [float(r.ci95[0]), float(r.ci95[1])], "n_clusters": int(r.n_clusters)}
    dm = _dm(diff)
    improvement = float(l_inc.mean() - l_cand.mean())
    summary = {
        "spec_id": "scripts.platformkit.eval_gate.s84_nba_lineup_at_tick:nba_lineup_strength_asof_v1",
        "sport": "nba", "tier": "SCREEN (uncharged, no prereg seal, no K read)",
        "incumbent": "nba_mechanism_ladder BASE -- logistic on standardized "
                     "[logit_p0 (first traded), signed margin, margin/sqrt(rem_frac)]",
        "market_column": "market_prob (Polymarket in-play, same tick)",
        "embargo_days": int(embargo_days), "purge": "by game (train disjoint from test)",
        "standardisation": "fit on TRAIN inside each fold (_fit_predict), applied to TEST",
        "partition": {"basis": part.basis, "seed": part.seed, "screen_sha256": part.screen_sha256,
                      "verdict_sha256": part.verdict_sha256, "n_verdict_games":
                      len(part.verdict_ids), "n_screen_games": len(part.screen_ids)},
        "coverage": cover, "n_ticks": int(len(scored)),
        "n_games": int(scored["game"].nunique()),
        "brier": {"incumbent": float(l_inc.mean()), "candidate": float(l_cand.mean()),
                  "market": float(l_mkt.mean())},
        "improvement_vs_incumbent": improvement,
        "improvement_vs_market": float(l_mkt.mean() - l_cand.mean()),
        "dm_vs_incumbent": dm, "dm_vs_market": _dm(l_mkt - l_cand),
        "verdict": verdict_of(improvement, float(dm["p_value"])),
        "improvement_bar": IMPROVEMENT_BAR, "folds": folds, "single_window": True,
        "prereg_draft_warranted": bool(improvement >= IMPROVEMENT_BAR),
        "honest_note": "Calibration (tick-weighted Brier) only; no dollar, ROI or edge claim. "
                       "One capture window (2024-25 priced ticks) -- SINGLE-WINDOW.",
    }
    series = scored[["game", "nba_game_id", "ts", "date", "period", "elapsed",
                     "outcome_home_win", "home_five", "away_five", FEATURE,
                     "p_incumbent", "p_candidate", "market_prob"]].copy()
    for name, vals in (("loss_incumbent", l_inc), ("loss_candidate", l_cand),
                       ("loss_market", l_mkt), ("loss_differential", diff)):
        series[name] = vals
    series["cluster_id"] = series["game"]
    return summary, series


def run(*, embargo_days: int = 1, out_dir: Path = OUT_DIR, suffix: str = "") -> dict:
    corpus = load_corpus()
    crosswalk = build_crosswalk(corpus)
    adv = pd.read_parquet(ADV, columns=["player_id", "game_id", RATING])
    pbp = {os.path.basename(p)[:-5]: p for p in glob.glob(PBP_GLOB)}
    frame, cover = build_lineups(corpus, crosswalk, adv, pbp)
    if frame.empty:
        return {"verdict": "SCREEN_INFEASIBLE", "coverage": cover}
    screen, part = screen_side(frame)
    scored, folds = walk_forward(screen, embargo_days=embargo_days)
    if scored.empty:
        return {"verdict": "SCREEN_INFEASIBLE", "coverage": cover, "folds": folds}
    summary, series = score(scored, folds, part, embargo_days=embargo_days, cover=cover)
    summary["n_screen_ticks_available"] = int(len(screen))
    out_dir.mkdir(parents=True, exist_ok=True)
    csv = out_dir / ("%s%s.csv" % (STEM, suffix))
    series.to_csv(csv, index=False)
    summary["per_tick_series"] = str(csv)
    (out_dir / ("%s%s.json" % (STEM, suffix))).write_text(
        json.dumps(summary, indent=1, sort_keys=True, default=str), encoding="ascii")
    return summary


def main() -> int:
    for embargo, suffix in ((1, ""), (0, "_embargo0")):
        res = run(embargo_days=embargo, suffix=suffix)
        if res["verdict"] == "SCREEN_INFEASIBLE":
            print("embargo=%d SCREEN_INFEASIBLE %s" % (embargo, res["coverage"]))
            continue
        b, d = res["brier"], res["dm_vs_incumbent"]
        print("embargo=%d %s | n_ticks %d n_games %d | incumbent %.6f -> %.6f (impr %+.6f) | "
              "market %.6f | dm p %.4g ci95 [%.6f, %.6f] clusters %d" % (
                  embargo, res["verdict"], res["n_ticks"], res["n_games"], b["incumbent"],
                  b["candidate"], res["improvement_vs_incumbent"], b["market"], d["p_value"],
                  *d["ci95"], d["n_clusters"]))
        print("   coverage %s" % res["coverage"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
