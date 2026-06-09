"""HONEST walk-forward eval of the POSSESSION-LEVEL rest-of-game simulator
(FRONT A, per .planning/ingame/SPEC.md Sections 6-7 + the orchestrator brief).

Scores ``src.sim.rest_of_game_sim.RestOfGameSim`` on HELD-OUT games at a clock
grid for the TEAM-LEVEL targets it produces:
  * final-score MAE   (margin = home-away, and total = home+away)
  * home win-prob Brier (+ log-loss)
against the baselines named in the brief:
  (a) PRODUCTION snapshot projector's TEAM extrapolation
      = scripts.predict_in_game pace math at the team level
      (eval_second_by_second.baseline_team_projection / baseline_winprob's
       score side) -- this is the same closed-form pace the box-snapshot player
      projector uses, applied to team score.
  (b) the REJECTED sigmoid win-prob baseline
      = eval_second_by_second.baseline_winprob  (sigmoid(0.40*margin/sqrt(rem))).
  (c) the SBS head WHERE APPLICABLE. The shipped/validated SBS head is the
      PLAYER-LINE head; the SBS win-prob head was REJECTED (see
      vault/Intelligence/Second_By_Second_Engine.md). So for TEAM SCORE / WIN
      PROB there is no validated SBS head to beat; the honest learned reference
      is the per-grid-bucket LEARNED RIDGE team-score / win-prob head from
      eval_second_by_second (trained walk-forward here, identically) -- reported
      in the same table so the sim is measured against a learned model too, not
      only closed-form pace. (If/when a learned possession model is injected into
      the sim this comparison still holds.)

LEAK DISCIPLINE (HARD HONESTY RULES; identical posture to the SBS harnesses):
  * State at grid point t uses ONLY events <= t in THIS game (featurizer is
    truncation-invariant; tested). The sim reads only that state row + an
    OPTIONAL prior-form pace/ppp prior the harness builds from games strictly
    BEFORE this game's date.
  * Walk-forward: the learned ridge reference trains ONLY on games with
    game_date < min(test fold dates); the sim itself is parameter-free given the
    league constants, so it has no train set -- it is evaluated on every fold's
    held-out games exactly like the closed-form baselines.
  * Labels: team finals from PBP last event (orientation cross-checked vs
    season_games.home_win, game dropped on mismatch).

Run on a SUBSAMPLE for speed (SAID SO in the report):
    set NBA_OFFLINE=1
    python scripts/ingame/eval_possession_sim.py --max-games 300 --folds 3 --n-sims 1500
Outputs:
    .planning/ingame/eval_possession_sim.json
    .planning/ingame/eval_possession_sim.md

A NULL / NEGATIVE result is a valid, reportable outcome and is stated plainly.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("NBA_OFFLINE", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import numpy as np  # noqa: E402

from scripts.ingame.eval_second_by_second import (  # noqa: E402
    GamelogStore, load_season_games, build_game_record, _parse_iso_date,
    baseline_team_projection, baseline_winprob,
    GRID_SEC, GRID_LABELS, TEAM_FEATS, _ridge_fit, _ridge_pred,
)
from src.ingame.state_featurizer import discover_game_ids, load_pbp_events  # noqa: E402
from src.sim.rest_of_game_sim import RestOfGameSim  # noqa: E402
from src.sim.possession_model import (  # noqa: E402
    extract_possessions, PossessionOutcomeModel, STATE_FEATURES_INTEL,
)
from src.sim.intel_coupling import IntelPriorStore  # noqa: E402

PLAN_DIR = os.path.join(ROOT, ".planning", "ingame")
os.makedirs(PLAN_DIR, exist_ok=True)

_EPS = 1e-6


# --------------------------------------------------------------------------- #
# Prior-form team pace/ppp (games strictly BEFORE this game's date).
# Built from the team finals already reconstructed per game record. We keep an
# accumulating per-team list of (date, ppp, pace_per48) and, for a target game,
# average the team's prior entries. Pure as-of-before -> leak-free.
# --------------------------------------------------------------------------- #
class TeamPriorStore:
    def __init__(self):
        # team_abbrev -> list of (date, ppp, pace_per48)
        self._hist: Dict[str, List[tuple]] = defaultdict(list)

    def observe(self, rec: Dict[str, Any]) -> None:
        """Record a COMPLETED game's team ppp/pace for both teams (final row)."""
        # use the last grid's game row for possessions; finals for points.
        grids = rec.get("grids") or {}
        if not grids:
            return
        last_t = max(grids.keys())
        gr = grids[last_t]["game"]
        date = rec["game_date"]
        # estimate full-game possessions by scaling the latest-known count
        elapsed = float(gr.get("game_elapsed_sec", 0) or 0)
        total_poss = float(gr.get("total_poss_count", 0) or 0)
        if elapsed > 0 and total_poss > 0:
            full_poss = total_poss * (2880.0 / elapsed)
            one_team_poss = full_poss / 2.0
        else:
            one_team_poss = 99.0
        for side, abbr_key in (("home", "home_team"), ("away", "away_team")):
            abbr = gr.get(abbr_key)
            pts = rec["home_final"] if side == "home" else rec["away_final"]
            if not abbr or one_team_poss <= 0:
                continue
            ppp = float(pts) / one_team_poss
            self._hist[abbr].append((date, ppp, one_team_poss))

    def priors_for(self, rec: Dict[str, Any]) -> Optional[Dict[str, float]]:
        grids = rec.get("grids") or {}
        if not grids:
            return None
        gr = grids[min(grids.keys())]["game"]
        date = rec["game_date"]
        out: Dict[str, float] = {}
        for side, abbr_key in (("home", "home_team"), ("away", "away_team")):
            abbr = gr.get(abbr_key)
            prior = [(p, pc) for (d, p, pc) in self._hist.get(abbr, []) if d < date]
            if not prior:
                continue
            out[f"{side}_ppp"] = float(np.mean([p for p, _ in prior]))
            out[f"{side}_pace_per48"] = float(np.mean([pc for _, pc in prior]))
        return out or None


def _brier(p: float, y: int) -> float:
    return (p - y) ** 2


def _logloss(p: float, y: int) -> float:
    p = min(1.0 - _EPS, max(_EPS, p))
    return -(y * np.log(p) + (1 - y) * np.log(1.0 - p))


def _device_for_xgb() -> str:
    if os.environ.get("NBA_FORCE_CPU") == "1":
        return "cpu"
    try:
        import xgboost as xgb  # noqa
        d = xgb.DMatrix(np.zeros((2, 1), np.float32), label=np.array([0.0, 1.0]))
        xgb.train({"device": "cuda", "tree_method": "hist", "max_depth": 1}, d, 1)
        return "cuda"
    except Exception:
        return "cpu"


def _game_teams(rec: Dict[str, Any]) -> "tuple[Optional[str], Optional[str]]":
    """(home_tricode, away_tricode) from a built game record's grid game row."""
    grids = rec.get("grids") or {}
    if not grids:
        return None, None
    gr = grids[min(grids.keys())]["game"]
    return gr.get("home_team"), gr.get("away_team")


def run(max_games: int, folds: int, seed: int, min_train: int,
        n_sims: int, use_priors: bool, learned: bool = False,
        intel: bool = False) -> Dict[str, Any]:
    season_games = load_season_games()
    store = GamelogStore()

    all_ids = [g for g in discover_game_ids() if g in season_games]
    all_ids = [g for g in all_ids
               if _parse_iso_date(season_games[g].get("game_date") or "")]
    all_ids.sort(key=lambda g: season_games[g]["game_date"])

    n_total = len(all_ids)
    if max_games and n_total > max_games:
        idx = np.linspace(0, n_total - 1, max_games).astype(int)
        sampled = [all_ids[i] for i in sorted(set(idx.tolist()))]
    else:
        sampled = all_ids
    print(f"[psim-eval] {n_total} dated PBP games available; using {len(sampled)} "
          f"(chronological-even subsample={max_games})")

    records: List[Dict[str, Any]] = []
    n_fail = 0
    for i, gid in enumerate(sampled):
        try:
            rec = build_game_record(gid, season_games[gid], store)
        except Exception as exc:
            rec = None
            n_fail += 1
            if n_fail <= 5:
                print(f"  [warn] {gid}: {exc!r}")
        if rec is not None:
            records.append(rec)
        if (i + 1) % 50 == 0:
            print(f"  ...reconstructed {i+1}/{len(sampled)} ({len(records)} usable)")
    records.sort(key=lambda r: r["game_date"])
    print(f"[psim-eval] {len(records)} usable game records ({n_fail} failed)")
    if len(records) < min_train + 10:
        raise SystemExit(f"too few usable games ({len(records)}) for WF eval")

    # prior-form store: observe games in chronological order so priors_for(rec)
    # only ever sees strictly-earlier games (we observe AFTER computing).
    prior_store = TeamPriorStore() if use_priors else None
    rec_priors: Dict[str, Optional[Dict[str, float]]] = {}
    for rec in records:
        rec_priors[rec["game_id"]] = (prior_store.priors_for(rec)
                                      if prior_store is not None else None)
        if prior_store is not None:
            prior_store.observe(rec)

    # INTELLIGENCE-COUPLED as-of-before store: derive each matchup's offense-style
    # x defense-allowance signature from each team's OWN prior-game possessions.
    # Walk-forward READ-BEFORE-OBSERVE => a game only ever sees strictly-earlier
    # games (leak-free). Possessions are extracted ONCE per game and cached.
    poss_cache: Dict[str, list] = {}
    rec_intel: Dict[str, Optional[Dict[str, Dict[str, float]]]] = {}
    if intel:
        istore = IntelPriorStore()
        for rec in records:
            gid = rec["game_id"]
            home, away = _game_teams(rec)
            blob: Dict[str, Dict[str, float]] = {}
            ip_home = istore.intel_priors_for(home, away)   # home off vs away def
            ip_away = istore.intel_priors_for(away, home)   # away off vs home def
            if ip_home:
                blob["home"] = ip_home
            if ip_away:
                blob["away"] = ip_away
            rec_intel[gid] = blob or None
            # observe AFTER reading (uses this game's possessions for FUTURE games)
            ev = load_pbp_events(gid)
            tm = season_games.get(gid, {})
            pr = (extract_possessions(ev, gid, tm.get("home_team"),
                                      tm.get("away_team")) if ev else [])
            poss_cache[gid] = pr
            istore.observe(pr, home, away)
        n_with_intel = sum(1 for v in rec_intel.values() if v)
        print(f"[psim-eval] intel store built; {n_with_intel}/{len(records)} "
              f"games have an as-of-before matchup signature")

    dates = [r["game_date"] for r in records]
    uniq = sorted(set(dates))
    chunks = np.array_split(np.array(uniq, dtype=object), folds + 1)
    fold_test_dates = [set(chunks[k].tolist()) for k in range(1, folds + 1)]

    sim = RestOfGameSim(n_sims=n_sims, seed=seed)
    device = _device_for_xgb() if learned else "cpu"
    if learned:
        print(f"[psim-eval] learned PossessionOutcomeModel ENABLED (device={device})")

    # acc[bucket][method][metric] -> list
    acc = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    fold_summaries = []

    for fold_i, test_dates in enumerate(fold_test_dates):
        train_recs = [r for r in records if r["game_date"] < min(test_dates)]
        test_recs = [r for r in records if r["game_date"] in test_dates]
        if len(train_recs) < min_train or not test_recs:
            continue
        print(f"[fold {fold_i}] train={len(train_recs)} test={len(test_recs)} "
              f"(test {min(test_dates)}..{max(test_dates)})")

        # ---- learned possession-outcome model (trained on train fold only) ----
        learned_sim = None
        if learned:
            train_meta = {r["game_id"]: season_games[r["game_id"]] for r in train_recs}
            poss_rows = []
            for r in train_recs:
                gid = r["game_id"]
                ev = load_pbp_events(gid)
                if not ev:
                    continue
                tm = train_meta[gid]
                poss_rows.extend(extract_possessions(
                    ev, gid, tm.get("home_team"), tm.get("away_team")))
            if poss_rows:
                model = PossessionOutcomeModel(device=device, n_rounds=150).fit(poss_rows)
                learned_sim = RestOfGameSim(n_sims=n_sims, model=model, seed=seed)
                print(f"  [learned] fit on {len(poss_rows)} possessions "
                      f"from {len(train_recs)} games")

        # ---- INTELLIGENCE-COUPLED learned model (trained on train fold only) --
        intel_sim = None
        if intel and learned:
            intel_rows = []
            for r in train_recs:
                gid = r["game_id"]
                pr = poss_cache.get(gid)
                if pr is None:
                    ev = load_pbp_events(gid)
                    tm = season_games.get(gid, {})
                    pr = (extract_possessions(ev, gid, tm.get("home_team"),
                                              tm.get("away_team")) if ev else [])
                    poss_cache[gid] = pr
                if not pr:
                    continue
                ib = rec_intel.get(gid)            # as-of-before matchup signature
                # re-inject the per-side intel into this game's rows as a constant
                blob = ib or {}
                if blob:
                    for row in pr:
                        sig = blob.get(getattr(row, "off_side", ""))
                        if sig:
                            row.state.update(sig)
                intel_rows.extend(pr)
            if intel_rows:
                imodel = PossessionOutcomeModel(
                    device=device, n_rounds=150,
                    feature_names=list(STATE_FEATURES_INTEL)).fit(intel_rows)
                intel_sim = RestOfGameSim(n_sims=n_sims, model=imodel, seed=seed)
                print(f"  [intel] coupled model fit on {len(intel_rows)} "
                      f"possessions ({len(STATE_FEATURES_INTEL)} features incl intel)")

        # ---- learned ridge reference (the SBS-style learned team head) -------
        team_w: Dict[int, Dict[str, np.ndarray]] = {}
        wp_w: Dict[int, np.ndarray] = {}
        for t in GRID_SEC:
            Xt, yh, ya, yw = [], [], [], []
            for r in train_recs:
                if t not in r["grids"]:
                    continue
                gr = r["grids"][t]["game"]
                Xt.append([float(gr.get(f, 0) or 0) for f in TEAM_FEATS])
                yh.append(r["home_final"]); ya.append(r["away_final"])
                yw.append(r["home_win"])
            if len(Xt) >= 20:
                Xt = np.array(Xt, dtype=np.float64)
                team_w[t] = {"home": _ridge_fit(Xt, np.array(yh)),
                             "away": _ridge_fit(Xt, np.array(ya))}
                wp_w[t] = _ridge_fit(Xt, np.array(yw, dtype=np.float64), lam=20.0)

        # ---- evaluate on TEST (held-out) -------------------------------------
        for r in test_recs:
            priors = rec_priors.get(r["game_id"])
            true_margin = r["home_final"] - r["away_final"]
            true_total = r["home_final"] + r["away_final"]
            y = int(r["home_win"])
            for t, gd in r["grids"].items():
                gr = gd["game"]
                bucket = GRID_LABELS[t]

                # (a) snapshot/pace team projection
                bh, ba = baseline_team_projection(gr)
                acc[bucket]["snapshot_pace"]["margin"].append(abs((bh - ba) - true_margin))
                acc[bucket]["snapshot_pace"]["total"].append(abs((bh + ba) - true_total))

                # (b) rejected sigmoid win-prob
                bw = baseline_winprob(gr)
                acc[bucket]["sigmoid_wp"]["brier"].append(_brier(bw, y))
                acc[bucket]["sigmoid_wp"]["logloss"].append(_logloss(bw, y))

                # (c) learned ridge team-score + win-prob (SBS-style learned ref)
                if t in team_w:
                    fv = np.array([[float(gr.get(f, 0) or 0) for f in TEAM_FEATS]])
                    lh = float(_ridge_pred(team_w[t]["home"], fv)[0])
                    la = float(_ridge_pred(team_w[t]["away"], fv)[0])
                    acc[bucket]["learned_ridge"]["margin"].append(abs((lh - la) - true_margin))
                    acc[bucket]["learned_ridge"]["total"].append(abs((lh + la) - true_total))
                if t in wp_w:
                    fv = np.array([[float(gr.get(f, 0) or 0) for f in TEAM_FEATS]])
                    lw = float(np.clip(_ridge_pred(wp_w[t], fv)[0], 0.0, 1.0))
                    acc[bucket]["learned_ridge"]["brier"].append(_brier(lw, y))
                    acc[bucket]["learned_ridge"]["logloss"].append(_logloss(lw, y))

                # ---- the possession SIM ----
                res = sim.simulate(gr, priors=priors)
                acc[bucket]["poss_sim"]["margin"].append(abs(res.margin_mean - true_margin))
                acc[bucket]["poss_sim"]["total"].append(abs(res.total_mean - true_total))
                acc[bucket]["poss_sim"]["brier"].append(_brier(res.home_win_prob, y))
                acc[bucket]["poss_sim"]["logloss"].append(_logloss(res.home_win_prob, y))
                acc[bucket]["poss_sim"]["poss_rem"].append(res.poss_remaining_mean)

                # ---- the LEARNED possession SIM (if enabled) ----
                if learned_sim is not None:
                    lres = learned_sim.simulate(gr, priors=priors)
                    acc[bucket]["poss_sim_learned"]["margin"].append(abs(lres.margin_mean - true_margin))
                    acc[bucket]["poss_sim_learned"]["total"].append(abs(lres.total_mean - true_total))
                    acc[bucket]["poss_sim_learned"]["brier"].append(_brier(lres.home_win_prob, y))
                    acc[bucket]["poss_sim_learned"]["logloss"].append(_logloss(lres.home_win_prob, y))

                # ---- the INTELLIGENCE-COUPLED learned SIM (if enabled) ----
                if intel_sim is not None:
                    ib = rec_intel.get(r["game_id"])
                    iprior = dict(priors) if priors else {}
                    if ib:
                        iprior["intel"] = ib       # offense-POV per-side signature
                    ires = intel_sim.simulate(gr, priors=iprior or None)
                    acc[bucket]["poss_sim_intel"]["margin"].append(abs(ires.margin_mean - true_margin))
                    acc[bucket]["poss_sim_intel"]["total"].append(abs(ires.total_mean - true_total))
                    acc[bucket]["poss_sim_intel"]["brier"].append(_brier(ires.home_win_prob, y))
                    acc[bucket]["poss_sim_intel"]["logloss"].append(_logloss(ires.home_win_prob, y))

        fold_summaries.append({
            "fold": fold_i, "n_train": len(train_recs), "n_test": len(test_recs),
            "test_date_min": str(min(test_dates)), "test_date_max": str(max(test_dates)),
        })

    return _summarize(acc, fold_summaries, len(records), n_total, n_sims,
                      use_priors, intel)


def _mean(xs):
    return float(np.mean(xs)) if xs else None


def _summarize(acc, fold_summaries, n_records, n_total, n_sims, use_priors,
               intel=False):
    curve = {}
    for bucket in GRID_LABELS.values():
        if bucket not in acc:
            continue
        a = acc[bucket]
        curve[bucket] = {
            "n": len(a["poss_sim"]["margin"]),
            "poss_rem_mean": _mean(a["poss_sim"]["poss_rem"]),
            "margin_mae": {
                "snapshot_pace": _mean(a["snapshot_pace"]["margin"]),
                "learned_ridge": _mean(a["learned_ridge"]["margin"]),
                "poss_sim": _mean(a["poss_sim"]["margin"]),
                "poss_sim_learned": _mean(a["poss_sim_learned"]["margin"]),
                "poss_sim_intel": _mean(a["poss_sim_intel"]["margin"]),
            },
            "total_mae": {
                "snapshot_pace": _mean(a["snapshot_pace"]["total"]),
                "learned_ridge": _mean(a["learned_ridge"]["total"]),
                "poss_sim": _mean(a["poss_sim"]["total"]),
                "poss_sim_learned": _mean(a["poss_sim_learned"]["total"]),
                "poss_sim_intel": _mean(a["poss_sim_intel"]["total"]),
            },
            "winprob_brier": {
                "sigmoid_wp": _mean(a["sigmoid_wp"]["brier"]),
                "learned_ridge": _mean(a["learned_ridge"]["brier"]),
                "poss_sim": _mean(a["poss_sim"]["brier"]),
                "poss_sim_learned": _mean(a["poss_sim_learned"]["brier"]),
                "poss_sim_intel": _mean(a["poss_sim_intel"]["brier"]),
            },
            "winprob_logloss": {
                "sigmoid_wp": _mean(a["sigmoid_wp"]["logloss"]),
                "learned_ridge": _mean(a["learned_ridge"]["logloss"]),
                "poss_sim": _mean(a["poss_sim"]["logloss"]),
                "poss_sim_learned": _mean(a["poss_sim_learned"]["logloss"]),
                "poss_sim_intel": _mean(a["poss_sim_intel"]["logloss"]),
            },
        }
    return {
        "meta": {
            "n_total_dated_pbp_games": n_total,
            "n_usable_records": n_records,
            "n_sims_per_state": n_sims,
            "prior_form_used": use_priors,
            "intel_coupled": intel,
            "folds": fold_summaries,
            "grid_labels": GRID_LABELS,
            "sim": "src.sim.rest_of_game_sim.RestOfGameSim (EmpiricalPossessionModel: "
                   "per-team ppp+pace shrunk from four-factors-so-far to league/prior; "
                   "Monte-Carlo rest-of-game by possessions; OT resolved).",
            "baselines": {
                "snapshot_pace": "team-level pace extrapolation (production "
                                 "box-snapshot projector's score math)",
                "sigmoid_wp": "REJECTED time-and-score logistic "
                              "sigmoid(0.40*margin/sqrt(rem_min))",
                "learned_ridge": "SBS-style per-grid-bucket learned ridge "
                                 "(team-score + win-prob), trained walk-forward. "
                                 "NOTE: the validated SBS head is the PLAYER-LINE "
                                 "head; the SBS win-prob head was REJECTED, so this "
                                 "ridge is the honest learned team reference.",
            },
            "honesty": "held-out only; walk-forward (learned ref trains on dates "
                       "< test); sim is parameter-free given league constants; "
                       "labels PBP, orientation cross-checked vs home_win; "
                       "per-POSSESSION granularity (NOT per-second).",
        },
        "curve": curve,
    }


def _fmt(v, nd=3):
    return f"{v:.{nd}f}" if isinstance(v, (int, float)) else " n/a "


def write_markdown(summary: Dict[str, Any], path: str) -> None:
    m = summary["meta"]
    L = ["# Possession-Sim Eval — Honest Walk-Forward Final-Score / Win-Prob Curve\n"]
    L.append(f"- Dated PBP games: **{m['n_total_dated_pbp_games']}**; usable "
             f"records: **{m['n_usable_records']}**; sims/state: "
             f"**{m['n_sims_per_state']}**; prior-form: **{m['prior_form_used']}**")
    L.append(f"- Folds (expanding-window, chronological): {len(m['folds'])}")
    for f in m["folds"]:
        L.append(f"  - fold {f['fold']}: train={f['n_train']} test={f['n_test']} "
                 f"({f['test_date_min']}..{f['test_date_max']})")
    L.append("- " + m["honesty"])
    L.append("- **sim:** " + m["sim"])
    L.append("- bars: (a) snapshot_pace, (b) sigmoid_wp [rejected], "
             "(c) learned_ridge [SBS-style learned team ref].\n")

    L.append("## Final score MAE (lower=better) + win-prob Brier/LogLoss\n")
    L.append("| game-time | n | poss-rem | margin: snap / ridge / **SIM** | "
             "total: snap / ridge / **SIM** | Brier: sig / ridge / **SIM** | "
             "LogL: sig / ridge / **SIM** |")
    L.append("|---|---|---|---|---|---|---|")
    for b in GRID_LABELS.values():
        if b not in summary["curve"]:
            continue
        c = summary["curve"][b]
        mm = c["margin_mae"]; tm = c["total_mae"]
        wb = c["winprob_brier"]; wl = c["winprob_logloss"]
        L.append(
            f"| {b} | {c['n']} | {_fmt(c['poss_rem_mean'],1)} | "
            f"{_fmt(mm['snapshot_pace'],2)} / {_fmt(mm['learned_ridge'],2)} / "
            f"**{_fmt(mm['poss_sim'],2)}** | "
            f"{_fmt(tm['snapshot_pace'],2)} / {_fmt(tm['learned_ridge'],2)} / "
            f"**{_fmt(tm['poss_sim'],2)}** | "
            f"{_fmt(wb['sigmoid_wp'],4)} / {_fmt(wb['learned_ridge'],4)} / "
            f"**{_fmt(wb['poss_sim'],4)}** | "
            f"{_fmt(wl['sigmoid_wp'],4)} / {_fmt(wl['learned_ridge'],4)} / "
            f"**{_fmt(wl['poss_sim'],4)}** |")
    L.append("")

    # learned-variant column (only if it was run)
    has_learned = any(
        summary["curve"][b]["margin_mae"].get("poss_sim_learned") is not None
        for b in summary["curve"])
    if has_learned:
        L.append("## Learned PossessionOutcomeModel sim (trained walk-forward)\n")
        L.append("| game-time | margin: emp / **learned** | total: emp / **learned** "
                 "| Brier: emp / **learned** |")
        L.append("|---|---|---|---|")
        for b in GRID_LABELS.values():
            if b not in summary["curve"]:
                continue
            c = summary["curve"][b]
            mm, tm, wb = c["margin_mae"], c["total_mae"], c["winprob_brier"]
            L.append(
                f"| {b} | {_fmt(mm['poss_sim'],2)} / **{_fmt(mm['poss_sim_learned'],2)}** "
                f"| {_fmt(tm['poss_sim'],2)} / **{_fmt(tm['poss_sim_learned'],2)}** "
                f"| {_fmt(wb['poss_sim'],4)} / **{_fmt(wb['poss_sim_learned'],4)}** |")
        L.append("")

    # intelligence-coupled variant column (only if it was run)
    has_intel = any(
        summary["curve"][b]["margin_mae"].get("poss_sim_intel") is not None
        for b in summary["curve"])
    if has_intel:
        L.append("## Intelligence-coupled learned sim "
                 "(offense playstyle x opponent scheme/coverage, as-of-before)\n")
        L.append("Reference = the learned PossessionOutcomeModel WITHOUT intel "
                 "(`learned`). The intel sim adds team-pace-identity + offense "
                 "playstyle-mix + defense scheme/allowance signatures derived "
                 "leak-free from each team's OWN games strictly before this date.\n")
        L.append("| game-time | margin: learned / **intel** | total: learned / "
                 "**intel** | Brier: learned / **intel** | LogL: learned / **intel** |")
        L.append("|---|---|---|---|---|")
        for b in GRID_LABELS.values():
            if b not in summary["curve"]:
                continue
            c = summary["curve"][b]
            mm, tm = c["margin_mae"], c["total_mae"]
            wb, wl = c["winprob_brier"], c["winprob_logloss"]
            L.append(
                f"| {b} | {_fmt(mm['poss_sim_learned'],2)} / **{_fmt(mm['poss_sim_intel'],2)}** "
                f"| {_fmt(tm['poss_sim_learned'],2)} / **{_fmt(tm['poss_sim_intel'],2)}** "
                f"| {_fmt(wb['poss_sim_learned'],4)} / **{_fmt(wb['poss_sim_intel'],4)}** "
                f"| {_fmt(wl['poss_sim_learned'],4)} / **{_fmt(wl['poss_sim_intel'],4)}** |")
        L.append("")
        # intel-vs-learned and intel-vs-empirical verdicts
        for metric, label, ref in [
            ("winprob_brier", "win-prob Brier", "poss_sim_learned"),
            ("margin_mae", "final margin MAE", "poss_sim_learned"),
            ("total_mae", "final total MAE", "poss_sim_learned"),
            ("winprob_brier", "win-prob Brier vs EMPIRICAL sim", "poss_sim"),
        ]:
            wins = []
            for b in GRID_LABELS.values():
                if b not in summary["curve"]:
                    continue
                c = summary["curve"][b][metric]
                iv, rv = c.get("poss_sim_intel"), c.get(ref)
                if iv is None or rv is None:
                    continue
                if iv < rv:
                    wins.append(b)
            L.append(f"- **intel beats `{ref}` on {label}:** "
                     f"{len(wins)}/{len(summary['curve'])} buckets"
                     + (f" ({', '.join(wins)})" if wins else " (NONE)"))
        L.append("")

    # quick verdict block (computed)
    L.append("## Verdict (auto-computed: where does the SIM beat each bar?)\n")
    for metric, label, key, lower in [
        ("margin_mae", "final margin MAE", "snapshot_pace", True),
        ("total_mae", "final total MAE", "snapshot_pace", True),
        ("winprob_brier", "win-prob Brier vs sigmoid", "sigmoid_wp", True),
        ("winprob_brier", "win-prob Brier vs learned ridge", "learned_ridge", True),
        ("margin_mae", "final margin MAE vs learned ridge", "learned_ridge", True),
    ]:
        wins = []
        for b in GRID_LABELS.values():
            if b not in summary["curve"]:
                continue
            c = summary["curve"][b][metric]
            sim_v, base_v = c["poss_sim"], c[key]
            if sim_v is None or base_v is None:
                continue
            if (sim_v < base_v) == lower:
                wins.append(b)
        L.append(f"- **{label}:** SIM beats `{key}` at "
                 f"{len(wins)}/{len(summary['curve'])} buckets"
                 + (f" ({', '.join(wins)})" if wins else " (NONE)"))
    L.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=300,
                    help="chronological-even subsample size (0=all)")
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min-train", type=int, default=40)
    ap.add_argument("--n-sims", type=int, default=1500)
    ap.add_argument("--no-priors", action="store_true",
                    help="disable prior-form ppp/pace priors (sim uses league only)")
    ap.add_argument("--learned", action="store_true",
                    help="ALSO run the learned PossessionOutcomeModel sim "
                         "(trained walk-forward) alongside the empirical default")
    ap.add_argument("--intel", action="store_true",
                    help="ALSO run the INTELLIGENCE-COUPLED learned sim (offense "
                         "playstyle x opponent scheme/coverage as-of-before); "
                         "requires --learned")
    ap.add_argument("--out-tag", type=str, default="",
                    help="suffix for output files, e.g. '_full' -> "
                         "eval_possession_sim_full.{json,md}")
    args = ap.parse_args()

    if args.intel and not args.learned:
        print("[psim-eval] --intel implies --learned; enabling --learned")
        args.learned = True
    summary = run(args.max_games, args.folds, args.seed, args.min_train,
                  args.n_sims, use_priors=not args.no_priors,
                  learned=args.learned, intel=args.intel)
    tag = args.out_tag or ""
    json_path = os.path.join(PLAN_DIR, f"eval_possession_sim{tag}.json")
    md_path = os.path.join(PLAN_DIR, f"eval_possession_sim{tag}.md")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    write_markdown(summary, md_path)
    print(f"\n[psim-eval] wrote {json_path}")
    print(f"[psim-eval] wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
