"""Train + PERSIST the v2 unified clock-conditioned player-line head (sbs_v2).

This is the *production-serving* trainer for the v2 player-line projector that
``scripts/ingame/eval_sbs_v2.py`` validated walk-forward (held-out, leak-free).
The eval re-fits a fresh model per fold with ``save=False`` so it can never see
the future; THIS script fits ONE model on ALL available leak-free state rows and
SAVES it to ``data/models/ingame/sbs_v2/`` so the shadow logger can load + serve
it on a live game.

What it does (identical feature contract + leak posture as the eval):
  * Reconstructs every game's leak-free grid-state via
    ``scripts.ingame.eval_second_by_second.build_game_record`` (within-game state
    only; truncation-invariant; orientation cross-checked vs season_games).
  * Assembles ONE pooled frame of (record, grid-t, player) rows in the v2 CORE
    feature namespace (clock + box-so-far + leak-free L5 prior) -- the variant the
    eval found best (v2_pace added ~nothing). The clock is a MODEL FEATURE so a
    single XGBoost per stat conditions on game-time.
  * Calls ``train_player_lines_v2(..., save=True)`` -> persists 7 boosters +
    manifest to ``sbs_v2/``.

LEAK NOTE: this trains the SHIPPED model on ALL games (no held-out split) -- that
is correct for a production model and does NOT contradict the honest eval: the
eval's walk-forward numbers are the truth-of-record for *how well it generalises*;
this just bakes the same design into a servable artifact. The features are pure
within-game accumulation + games-strictly-before priors, so there is no
as-of-today leak baked into the saved model.

Run:
    set NBA_OFFLINE=1
    python scripts/ingame/train_sbs_v2.py --max-games 400
    python scripts/ingame/train_sbs_v2.py --max-games 0 --rounds 400   # all games
"""
from __future__ import annotations

import argparse
import json
import os
import sys

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
)
from scripts.ingame.eval_sbs_v2 import (  # noqa: E402
    _assemble_player_frame, FEATURES_V2_CORE, FEATURES_V2_PACE,
)
from src.ingame.state_featurizer import discover_game_ids  # noqa: E402
from src.ingame.continuous_projection import (  # noqa: E402
    train_player_lines_v2, _select_device, SBS_V2_DIR, PLAYER_STATS,
)


def run(max_games: int, folds: int, rounds: int, device: str,
        use_pace: bool) -> dict:
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
    print(f"[train-v2] {n_total} dated PBP games; using {len(sampled)} "
          f"(chronological-even subsample={max_games})")

    records = []
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
    print(f"[train-v2] {len(records)} usable game records ({n_fail} failed)")
    if not records:
        raise SystemExit("no usable records to train on")

    df = _assemble_player_frame(records)
    print(f"[train-v2] pooled training rows: {len(df)}")

    feats = FEATURES_V2_PACE if use_pace else FEATURES_V2_CORE
    dev = device if device != "auto" else _select_device("cuda")
    print(f"[train-v2] device={dev}  features={'v2_pace' if use_pace else 'v2_core'} "
          f"({len(feats)})  rounds={rounds}")

    # walk_forward=True also writes the honest per-fold MAE into `metrics`; the
    # SHIPPED model is always the all-rows fit (train_player_lines_v2 contract).
    proj, metrics = train_player_lines_v2(
        df, features=feats, walk_forward=True,
        num_boost_round=rounds, device=dev, save=True, model_dir=SBS_V2_DIR,
    )
    saved = {s: f"final_{s} -> {SBS_V2_DIR}" for s in PLAYER_STATS
             if f"final_{s}" in proj.models}
    wf = {k: [round(x, 4) for x in v] for k, v in metrics.items()}
    print(f"[train-v2] saved heads: {sorted(proj.models.keys())}")
    print(f"[train-v2] walk-forward per-fold MAE: {json.dumps(wf, indent=2)}")
    print(f"[train-v2] model_dir -> {SBS_V2_DIR}")
    return {"n_records": len(records), "n_rows": len(df),
            "feature_variant": "v2_pace" if use_pace else "v2_core",
            "device": dev, "rounds": rounds, "wf_metrics": wf, "saved": saved}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-games", type=int, default=400,
                    help="chronological-even subsample size (0=all)")
    ap.add_argument("--folds", type=int, default=3, help="WF folds for the report")
    ap.add_argument("--rounds", type=int, default=400)
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument("--pace", action="store_true",
                    help="use the v2_pace feature set (default: v2_core, the "
                         "variant the eval found best)")
    args = ap.parse_args()
    run(args.max_games, args.folds, args.rounds, args.device, args.pace)
    return 0


if __name__ == "__main__":
    sys.exit(main())
