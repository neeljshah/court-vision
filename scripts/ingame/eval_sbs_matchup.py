"""HONEST walk-forward eval of the MATCHUP-AWARE in-game player-line head.

This answers ONE question, straight: does appending the leak-free
opponent/matchup feature block (``src.ingame.matchup_features``) to the validated
v2 clock+pace player-line head IMPROVE held-out per-event line projections vs the
SAME v2 head WITHOUT matchup -- and where (which stat, which game-time)?

It scores THREE heads per (stat, game-time bucket), all walk-forward held-out,
on the SAME folds / universe / record-reconstruction / grid as
``scripts/ingame/eval_sbs_v2.py`` (we import that harness's machinery verbatim so
the comparison is confound-free with ``eval_curve_v2.json``):

  (P) PRODUCTION box-snapshot projector  scripts.predict_in_game.project_snapshot
      (the real production bar; identical ``baseline_player_snapshot`` v2 uses)
  (B) v2_pace  = the current SBS v2 head, FEATURES_V2_PACE, NO matchup columns
      (this IS the validated SBS win -- the head matchup must beat)
  (M) v2_matchup = v2_pace's features + the leak-free opponent/matchup block
      appended (trained via ``train_player_lines_v2_matchup``)

WIN DEFINITION (do not overclaim):
  A (stat, bucket) cell is a MATCHUP WIN only if  v2_matchup < v2_pace  on the
  held-out set (matchup-awareness genuinely helps the in-game head out-of-sample).
  We ALSO report v2_matchup vs production snapshot. A NULL / regression result is
  a valid, honest outcome -- if matchup context does not help, we say so plainly.
  Per-event (every grid snapshot of every held-out player), NOT per-second.

LEAK DISCIPLINE (inherited from eval_sbs_v2 + matchup_features; HARD HONESTY):
  * Event-state at grid point t uses ONLY events <= t in THIS game
    (src.ingame.state_featurizer; truncation-invariant, tested).
  * Walk-forward: BOTH heads train ONLY on games with game_date < min(test fold
    dates). A test game is NEVER trained on. Identical fold construction to
    eval_sbs_v2.
  * The matchup block for an event uses ONLY the OPPONENT team's identity + that
    opponent's defensive profile from games STRICTLY BEFORE this game's date, and
    (for the edge scalars) the player's gamelog rows strictly before -- enforced
    inside src.ingame.matchup_features and proven by tests/test_matchup_features
    (as-of invariance). We ALSO re-assert that invariance at runtime here (see
    ``_assert_matchup_as_of_invariance``) so a regression in the feature module
    fails this eval loudly rather than silently leaking.
  * Labels: team finals from PBP last event (orientation cross-checked vs
    season_games.home_win); player finals from gamelog by (pid, GAME_DATE).

Run (GPU auto, CPU fallback; subsample for speed -- SAY SO in the report):
    set NBA_OFFLINE=1
    python scripts/ingame/eval_sbs_matchup.py --max-games 220 --folds 3
Outputs:
    .planning/ingame/eval_sbs_matchup.json
    .planning/ingame/eval_sbs_matchup.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("NBA_OFFLINE", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import numpy as np  # noqa: E402

# Reuse the v2 harness machinery VERBATIM so this comparison is confound-free with
# eval_curve_v2.json: same record reconstruction, same grid, same baselines, same
# v2 feature mapping (_build_v2_row), same FEATURES_V2_PACE base head.
from scripts.ingame.eval_second_by_second import (  # noqa: E402
    GamelogStore, load_season_games, build_game_record,
    baseline_player_snapshot, _parse_iso_date,
    GRID_LABELS, PLAYER_STATS,
)
from scripts.ingame.eval_sbs_v2 import (  # noqa: E402
    FEATURES_V2_PACE, _build_v2_row,
)
from src.ingame.state_featurizer import discover_game_ids  # noqa: E402
from src.ingame.continuous_projection import (  # noqa: E402
    train_player_lines_v2, train_player_lines_v2_matchup,
    build_matchup_feature_list, matchup_feature_columns, _select_device,
)
from src.ingame.matchup_features import (  # noqa: E402
    matchup_feature_row, self_check_as_of_invariance,
)

PLAN_DIR = os.path.join(ROOT, ".planning", "ingame")
os.makedirs(PLAN_DIR, exist_ok=True)

# The matchup feature list = base v2 (pace) head + the opponent/matchup columns.
FEATURES_V2_MATCHUP: Tuple[str, ...] = build_matchup_feature_list(FEATURES_V2_PACE)
_MU_COLS: Tuple[str, ...] = matchup_feature_columns()


# --------------------------------------------------------------------------- #
# Anti-leak guard: re-assert the matchup vector is a pure function of
# (opponent identity, games strictly before as_of). If the feature module ever
# regresses to fold in a same-day / future game, this eval fails loud.
# --------------------------------------------------------------------------- #
def _assert_matchup_as_of_invariance() -> None:
    for opp in ("BOS", "DEN", "MIA", "OKC", "LAL"):
        if self_check_as_of_invariance(opp) is not True:
            raise SystemExit(
                f"matchup as-of invariance FAILED for {opp} -- refusing to run a "
                "leak-suspect eval. Fix src/ingame/matchup_features.py first."
            )
    # An earlier cutoff must never incorporate a game on/after that cutoff: assert
    # determinism + that the EARLY vector does not change when recomputed (it is a
    # pure function of games < as_of, which cannot include the as_of-day game).
    a = matchup_feature_row("XXX", "BOS", "2024-02-01", is_home=False)
    b = matchup_feature_row("XXX", "BOS", "2024-02-01", is_home=False)
    if a != b:
        raise SystemExit("matchup vector is non-deterministic -- leak-suspect.")


# --------------------------------------------------------------------------- #
# Training-frame assembly (mirror of eval_sbs_v2._assemble_player_frame) with the
# leak-free matchup block appended per event.
#   * own_team = the player's team_abbrev (carried on the player row, state<=t).
#   * opp_team = the OTHER of (home_team, away_team) from season_games meta
#     (identity only -- no game outcome).
#   * as_of    = the game date -> matchup_feature_row uses ONLY opponent games
#     strictly before it (leak-free by construction; re-asserted above).
#   * is_home  = (own_team == home_team).
# The matchup row is memoised per (opp, as_of, is_home) so a full grid is cheap.
# Edge scalars are intentionally OFF here (include_edges=False): the base v2
# matchup head's feature_columns() block is the opponent-axis only, matching the
# trained model's feature list exactly (no silent column drift).
# --------------------------------------------------------------------------- #
def _assemble_matchup_frame(records: List[Dict[str, Any]],
                            meta_by_gid: Dict[str, Dict[str, Any]]):
    """One row per (record, grid-t, player): v2 pace features + matchup block +
    final_<stat> targets + game_date. Pure function of leak-free inputs."""
    import pandas as pd
    mu_cache: Dict[Tuple[str, str, bool], Dict[str, float]] = {}
    rows: List[Dict[str, Any]] = []
    for r in records:
        store = r["store"]
        gid = r["game_id"]
        m = meta_by_gid.get(gid, {})
        home_t = (m.get("home_team") or "").strip().upper()
        away_t = (m.get("away_team") or "").strip().upper()
        as_of = str(r["game_date"])[:10]
        for t, gd in r["grids"].items():
            grow = gd["game"]
            for (own_team, _ln), prow in gd["players"].items():
                pid = prow.get("player_id")
                if pid is None or pid not in r["player_finals"]:
                    continue
                lab = r["player_finals"][pid]
                if lab.get("min", 0) <= 0:
                    continue
                own = (own_team or "").strip().upper()
                # opponent = the other team; skip if we can't resolve it cleanly
                if own == home_t and away_t:
                    opp, is_home = away_t, True
                elif own == away_t and home_t:
                    opp, is_home = home_t, False
                else:
                    continue
                l5 = store.l5_prior(pid, r["game_date"])
                fr = _build_v2_row(prow, grow, l5)
                key = (opp, as_of, is_home)
                if key not in mu_cache:
                    mu_cache[key] = matchup_feature_row(
                        own, opp, as_of, is_home=is_home, include_edges=False)
                fr.update(mu_cache[key])
                # production snapshot baseline (the BAR) -- carried per row so the
                # whole test eval is vectorized (no per-row Python predict loop).
                pf = float(prow.get("pf", 0) or 0)
                snap = baseline_player_snapshot(prow, grow, pf)
                for s in PLAYER_STATS:
                    fr[f"final_{s}"] = float(lab[s])
                    fr[f"_snap_{s}"] = float(snap[s])
                fr["game_date"] = as_of
                fr["_grid_t"] = t
                rows.append(fr)
    return pd.DataFrame(rows)


def _batch_project(proj, df, feats: Sequence[str]):
    """Vectorized projection: for every row in ``df``, return {stat: np.ndarray of
    floored final projections}. Mirrors UnifiedPlayerLineProjector.project exactly
    (predict then floor at p_<stat>_so_far) but in ONE DMatrix per stat instead of
    one per (row, stat) -- the ONLY change is batching for eval speed, not math."""
    import xgboost as xgb
    out: Dict[str, "np.ndarray"] = {}
    n = len(df)
    if n == 0:
        return {s: np.zeros(0) for s in PLAYER_STATS}
    X = df[list(feats)].to_numpy(dtype=np.float32)
    dm = xgb.DMatrix(X)
    for stat in PLAYER_STATS:
        tgt = f"final_{stat}"
        if tgt not in proj.models:
            continue
        booster, bfeats = proj.models[tgt]
        # booster feature order may differ from `feats`; rebuild if so.
        if tuple(bfeats) != tuple(feats):
            Xb = df[list(bfeats)].to_numpy(dtype=np.float32)
            pred = booster.predict(xgb.DMatrix(Xb))
        else:
            pred = booster.predict(dm)
        cur = df[f"p_{stat}_so_far"].to_numpy(dtype=np.float64)
        out[stat] = np.maximum(cur, pred.astype(np.float64))
    return out


# --------------------------------------------------------------------------- #
# Main eval
# --------------------------------------------------------------------------- #
def run(max_games: int, folds: int, seed: int, min_train: int,
        num_boost_round: int, device: str) -> Dict[str, Any]:
    _assert_matchup_as_of_invariance()

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
    print(f"[mu-eval] {n_total} dated PBP games available; using {len(sampled)} "
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
    print(f"[mu-eval] {len(records)} usable game records ({n_fail} failed)")
    if len(records) < min_train + 10:
        raise SystemExit(f"too few usable games ({len(records)}) for WF eval")

    dates = [r["game_date"] for r in records]
    uniq = sorted(set(dates))
    chunks = np.array_split(np.array(uniq, dtype=object), folds + 1)
    fold_test_dates = [set(chunks[k].tolist()) for k in range(1, folds + 1)]

    # accumulators: pacc[bucket][method][stat] -> list of abs errors (pooled WF)
    pacc = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    fold_summaries = []
    mu_real_frac: List[float] = []  # fraction of rows with a non-degenerate mu block

    dev = device if device != "auto" else _select_device("cuda")
    print(f"[mu-eval] xgboost device = {dev}")
    print(f"[mu-eval] base head features: {len(FEATURES_V2_PACE)}; "
          f"matchup head features: {len(FEATURES_V2_MATCHUP)} "
          f"(+{len(FEATURES_V2_MATCHUP) - len(FEATURES_V2_PACE)} matchup cols)")

    for fold_i, test_dates in enumerate(fold_test_dates):
        train_recs = [r for r in records if r["game_date"] < min(test_dates)]
        test_recs = [r for r in records if r["game_date"] in test_dates]
        if len(train_recs) < min_train or not test_recs:
            continue
        print(f"[fold {fold_i}] train={len(train_recs)} test={len(test_recs)} "
              f"(test {min(test_dates)}..{max(test_dates)})")

        # Assemble ONE frame carrying BOTH base + matchup columns; the base head
        # reads FEATURES_V2_PACE, the matchup head reads FEATURES_V2_MATCHUP, so
        # both train on IDENTICAL rows (only the column subset differs -> the only
        # variable is the matchup block).
        df_tr = _assemble_matchup_frame(train_recs, season_games)
        print(f"  [train] player-rows: {len(df_tr)}")
        # diagnostic: how often the matchup block is the REAL (non-zero) profile
        if len(df_tr):
            nonzero = (df_tr[list(_MU_COLS)].abs().sum(axis=1) > 1e-9).mean()
            mu_real_frac.append(float(nonzero))

        # (B) base v2 pace head -- the validated SBS win, NO matchup
        proj_base, _ = train_player_lines_v2(
            df_tr, features=FEATURES_V2_PACE, walk_forward=False,
            num_boost_round=num_boost_round, device=dev, save=False,
        )
        # (M) matchup-aware head -- base pace features + opponent/matchup block
        proj_mu, _, _used = train_player_lines_v2_matchup(
            df_tr, base_features=FEATURES_V2_PACE, walk_forward=False,
            num_boost_round=num_boost_round, device=dev, save=False,
        )

        # ===== evaluate on TEST (held-out) =====================================
        # Assemble the held-out frame ONCE (same rows for all three methods: the
        # production snapshot baseline is carried per row as _snap_<stat>, truths
        # as final_<stat>, bucket via _grid_t). Both heads batch-predict on the
        # SAME frame -> identical (player,grid) universe; only the matchup block
        # differs. Vectorized -> no per-row Python predict loop.
        df_te = _assemble_matchup_frame(test_recs, season_games)
        print(f"  [test] player-rows: {len(df_te)}")
        if len(df_te) == 0:
            fold_summaries.append({
                "fold": fold_i, "n_train": len(train_recs), "n_test": len(test_recs),
                "test_date_min": str(min(test_dates)),
                "test_date_max": str(max(test_dates))})
            continue
        base_pred = _batch_project(proj_base, df_te, FEATURES_V2_PACE)
        mu_pred = _batch_project(proj_mu, df_te, FEATURES_V2_MATCHUP)
        grid_t = df_te["_grid_t"].to_numpy()
        for s in PLAYER_STATS:
            truth = df_te[f"final_{s}"].to_numpy(dtype=np.float64)
            snap_err = np.abs(df_te[f"_snap_{s}"].to_numpy(dtype=np.float64) - truth)
            base_err = np.abs(base_pred[s] - truth)
            mu_err = np.abs(mu_pred[s] - truth)
            for t in set(grid_t.tolist()):
                bucket = GRID_LABELS[int(t)]
                mask = grid_t == t
                pacc[bucket]["snapshot"][s].extend(snap_err[mask].tolist())
                pacc[bucket]["v2_pace"][s].extend(base_err[mask].tolist())
                pacc[bucket]["v2_matchup"][s].extend(mu_err[mask].tolist())

        fold_summaries.append({
            "fold": fold_i, "n_train": len(train_recs), "n_test": len(test_recs),
            "test_date_min": str(min(test_dates)), "test_date_max": str(max(test_dates)),
        })

    return _summarize(pacc, fold_summaries, len(records), n_total, dev,
                      num_boost_round, mu_real_frac)


def _mean(xs):
    return float(np.mean(xs)) if xs else None


def _summarize(pacc, fold_summaries, n_records, n_total, dev, nbr,
               mu_real_frac) -> Dict[str, Any]:
    player_curve = {}
    for bucket in GRID_LABELS.values():
        if bucket not in pacc:
            continue
        per_stat = {}
        for s in PLAYER_STATS:
            base = _mean(pacc[bucket]["v2_pace"][s])
            mu = _mean(pacc[bucket]["v2_matchup"][s])
            snap = _mean(pacc[bucket]["snapshot"][s])
            delta_vs_base = (mu - base) if (mu is not None and base is not None) else None
            delta_vs_snap = (mu - snap) if (mu is not None and snap is not None) else None
            per_stat[s] = {
                "n": len(pacc[bucket]["v2_pace"][s]),
                "snapshot": snap,
                "v2_pace": base,
                "v2_matchup": mu,
                "delta_mu_minus_base": delta_vs_base,   # <0 = matchup WINS vs base
                "delta_mu_minus_snap": delta_vs_snap,   # <0 = matchup beats production
                "matchup_beats_base": (delta_vs_base is not None and delta_vs_base < 0),
                "matchup_beats_snapshot": (delta_vs_snap is not None and delta_vs_snap < 0),
            }
        player_curve[bucket] = per_stat
    return {
        "meta": {
            "n_total_dated_pbp_games": n_total,
            "n_usable_records": n_records,
            "folds": fold_summaries,
            "grid_labels": GRID_LABELS,
            "device": dev,
            "num_boost_round": nbr,
            "matchup_real_profile_frac_per_fold": mu_real_frac,
            "matchup_columns": list(_MU_COLS),
            "base_head_features": list(FEATURES_V2_PACE),
            "matchup_head_features": list(FEATURES_V2_MATCHUP),
            "win_definition": "a (stat,bucket) cell is a MATCHUP WIN iff "
                              "v2_matchup MAE < v2_pace MAE on the held-out set "
                              "(matchup-awareness helps the in-game head). delta = "
                              "v2_matchup - v2_pace (negative = matchup wins).",
            "baselines": {
                "snapshot": "scripts.predict_in_game.project_snapshot (pace+foul) "
                            "= PRODUCTION bar",
                "v2_pace": "current SBS v2 head, FEATURES_V2_PACE, NO matchup "
                           "(the validated SBS win matchup must beat)",
                "v2_matchup": "v2_pace features + leak-free opponent/matchup block "
                              "(train_player_lines_v2_matchup)",
            },
            "honesty": "held-out only; walk-forward (train dates < test dates); "
                       "SAME folds/universe/grid as eval_curve_v2.json; matchup "
                       "block leak-free (opponent identity + games strictly before "
                       "game_date), as-of invariance re-asserted at runtime; "
                       "per-event not per-second; NULL/regression reported straight.",
        },
        "player_curve": player_curve,
    }


def _fmt(v, nd=3):
    return f"{v:.{nd}f}" if isinstance(v, (int, float)) else " n/a "


def _signed(v, nd=4):
    if not isinstance(v, (int, float)):
        return " n/a "
    return f"{v:+.{nd}f}"


def write_markdown(summary: Dict[str, Any], path: str) -> None:
    m = summary["meta"]
    L = ["# In-Game v2 MATCHUP-AWARE — Honest Walk-Forward Player-Line Curve\n"]
    L.append(f"- Dated PBP games: **{m['n_total_dated_pbp_games']}**; usable "
             f"records: **{m['n_usable_records']}**; xgb device: **{m['device']}**; "
             f"rounds: {m['num_boost_round']}")
    L.append(f"- Folds (expanding-window, chronological): {len(m['folds'])}")
    for f in m["folds"]:
        L.append(f"  - fold {f['fold']}: train={f['n_train']} test={f['n_test']} "
                 f"({f['test_date_min']}..{f['test_date_max']})")
    rf = m.get("matchup_real_profile_frac_per_fold") or []
    if rf:
        L.append(f"- matchup REAL-profile coverage (frac of train rows w/ non-zero "
                 f"opponent block) per fold: {[round(x, 3) for x in rf]}")
    L.append("- " + m["honesty"])
    L.append("- **win rule:** " + m["win_definition"])
    L.append(f"- matchup columns appended ({len(m['matchup_columns'])}): "
             f"`{', '.join(m['matchup_columns'])}`\n")

    L.append("## Player lines — per-stat MAE (lower = better)\n")
    L.append("Methods: **snap**=production snapshot (bar), **base**=v2 pace head "
             "(NO matchup), **mu**=v2 matchup head. `Δ(mu-base)` <0 ⇒ matchup WINS "
             "vs base; `mu<base?` / `mu<snap?` are the win flags.\n")
    for b in GRID_LABELS.values():
        if b not in summary["player_curve"]:
            continue
        L.append(f"### {b}\n")
        L.append("| stat | n | snap | base | mu | Δ(mu-base) | mu<base? | mu<snap? |")
        L.append("|---|---|---|---|---|---|---|---|")
        for s in PLAYER_STATS:
            d = summary["player_curve"][b][s]
            L.append(
                f"| {s} | {d['n']} | {_fmt(d['snapshot'])} | {_fmt(d['v2_pace'])} | "
                f"{_fmt(d['v2_matchup'])} | {_signed(d['delta_mu_minus_base'])} | "
                f"{'Y' if d['matchup_beats_base'] else '.'} | "
                f"{'Y' if d['matchup_beats_snapshot'] else '.'} |")
        L.append("")

    # ---- headline roll-up: half-game (endQ2) + endQ3, and per-stat win count ----
    L.append("## Headline — does matchup-awareness beat the SBS-base head?\n")
    half = "24min(endQ2/half)"
    eq3 = "36min(endQ3)"
    pc = summary["player_curve"]
    for label, b in (("Half (endQ2)", half), ("endQ3", eq3)):
        if b not in pc:
            continue
        wins = [s for s in PLAYER_STATS if pc[b][s]["matchup_beats_base"]]
        L.append(f"**{label}** — matchup beats base on "
                 f"{len(wins)}/{len(PLAYER_STATS)} stats: "
                 f"{', '.join(wins) if wins else 'NONE'}")
        for s in PLAYER_STATS:
            d = pc[b][s]
            L.append(f"  - {s}: base {_fmt(d['v2_pace'])} → mu {_fmt(d['v2_matchup'])} "
                     f"(Δ {_signed(d['delta_mu_minus_base'])})")
        L.append("")

    # per-stat: in how many buckets does matchup beat base?
    L.append("### Per-stat win-count across all game-time buckets\n")
    L.append("| stat | buckets won (mu<base) / total | mean Δ(mu-base) |")
    L.append("|---|---|---|")
    for s in PLAYER_STATS:
        buckets = [b for b in pc if s in pc[b]]
        won = sum(1 for b in buckets if pc[b][s]["matchup_beats_base"])
        deltas = [pc[b][s]["delta_mu_minus_base"] for b in buckets
                  if pc[b][s]["delta_mu_minus_base"] is not None]
        mean_d = float(np.mean(deltas)) if deltas else None
        L.append(f"| {s} | {won}/{len(buckets)} | {_signed(mean_d)} |")
    L.append("")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=220,
                    help="chronological-even subsample size (0=all); SAY SO in report")
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min-train", type=int, default=40)
    ap.add_argument("--rounds", type=int, default=300)
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    args = ap.parse_args()

    summary = run(args.max_games, args.folds, args.seed, args.min_train,
                  args.rounds, args.device)
    json_path = os.path.join(PLAN_DIR, "eval_sbs_matchup.json")
    md_path = os.path.join(PLAN_DIR, "eval_sbs_matchup.md")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    write_markdown(summary, md_path)
    print(f"\n[mu-eval] wrote {json_path}")
    print(f"[mu-eval] wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
