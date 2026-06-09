"""HONEST second-by-second (per-event) in-game projection evaluation.

Goal (per .planning/ingame/SPEC.md Section 7): on HELD-OUT games, at each
clock-grid point, produce the continuous projection and score it against the
ACTUAL finals. Build a PER-GAME-TIME ERROR CURVE:
    * final-score MAE (margin + total)
    * home win-prob Brier
    * per-player-stat MAE (pts/reb/ast/fg3m/stl/blk/tov)
as a function of game-time-remaining (bucketed: endQ1/Q2/Q3 + ~6-min grid),
and compare against the BASELINES:
    (A) the current box-snapshot projector  scripts/predict_in_game.project_snapshot
    (B) naive minutes-paced extrapolation    current * total_game_min / elapsed_min
    (C) pregame L5 mean (player lines only)  from gamelog rows < game_date

LEAK DISCIPLINE (HARD HONESTY RULES):
  * State at clock-grid point t uses ONLY events with (period, elapsed) <= t in
    THIS game (reconstructed by src/ingame/state_featurizer.featurize_game, which
    is within-game-only and order-strict).
  * The learned engine (ContinuousProjector) is trained WALK-FORWARD: for each
    chronological fold, train on games strictly BEFORE the fold's earliest test
    date; evaluate ONLY on the later, held-out games. A test game is NEVER in the
    train set. Prior-form features fed to the engine come from games < game_date.
  * Baselines (A)/(B) are parameter-free closed-form extrapolators of CURRENT
    state -> leak-free by construction. (C) uses only gamelog rows < game_date.
  * Labels: team finals from PBP last event (cross-checked vs season_games
    home_win); player finals from gamelog_<pid>_<season>.json matched by
    GAME_DATE; player_id from boxscore_adv_<gid>.json roster (personid).

A NULL / NEGATIVE result reported truthfully is an acceptable outcome. We do NOT
ship a head that fails to beat its baseline on the held-out set.

Run:
    set NBA_OFFLINE=1
    python scripts/ingame/eval_second_by_second.py --max-games 400 --folds 3
Outputs:
    .planning/ingame/eval_curve.json
    .planning/ingame/eval_curve.md

Residual dump (for W-037/W-038 interval calibration):
    python scripts/ingame/eval_second_by_second.py --dump-residuals
Outputs:
    .planning/ingame/residuals_sbs.json   # per-(stat,bucket) signed residuals
    .planning/ingame/residuals_sbs.md     # summary (n, mean, std, p5/p25/p50/p75/p95)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault("NBA_OFFLINE", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import numpy as np  # noqa: E402

from src.ingame.state_featurizer import (  # noqa: E402
    load_pbp_events, featurize_game, discover_game_ids,
    REG_PERIOD_LEN, OT_PERIOD_LEN, REG_GAME_LEN_SEC,
)
from scripts.predict_in_game import (  # noqa: E402
    project_final as _baseline_project_final,
    clock_played_share as _baseline_share,
)

NBA_DIR = os.path.join(ROOT, "data", "nba")
PLAN_DIR = os.path.join(ROOT, ".planning", "ingame")
os.makedirs(PLAN_DIR, exist_ok=True)

PLAYER_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# Clock-grid: game-ELAPSED seconds at which we snapshot state and project.
# Mandatory endQ1/Q2/Q3 + a ~6-min grid through the game (skip t=0 and the
# final buzzer where projection == label trivially).
GRID_SEC = [360, 720, 1080, 1440, 1800, 2160, 2520]  # 6,12,18,24,30,36,42 min
GRID_LABELS = {
    360: "06min(midQ1)", 720: "12min(endQ1)", 1080: "18min(midQ2)",
    1440: "24min(endQ2/half)", 1800: "30min(midQ3)", 2160: "36min(endQ3)",
    2520: "42min(midQ4)",
}


# --------------------------------------------------------------------------- #
# Labels / roster
# --------------------------------------------------------------------------- #
def load_season_games() -> Dict[str, Dict[str, Any]]:
    """game_id -> {game_date, home_team, away_team, home_win, season}."""
    out: Dict[str, Dict[str, Any]] = {}
    for path in glob.glob(os.path.join(NBA_DIR, "season_games_*.json")):
        try:
            data = json.load(open(path, "r", encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for r in data.get("rows", []):
            gid = str(r.get("game_id", ""))
            if gid:
                out[gid] = {
                    "game_date": r.get("game_date"),
                    "home_team": r.get("home_team"),
                    "away_team": r.get("away_team"),
                    "home_win": r.get("home_win"),
                    "season": r.get("season"),
                }
    return out


def load_roster(game_id: str) -> Dict[Tuple[str, str], int]:
    """{(teamtricode, familyname_lower): personid} from boxscore_adv.

    This is a pure (team, last_name) -> player_id map for THIS game's roster;
    it carries no game state so it cannot leak. Same-last-name collisions on the
    same team are dropped (mapped to None / removed) rather than guessed.
    """
    path = os.path.join(NBA_DIR, f"boxscore_adv_{game_id}.json")
    if not os.path.exists(path):
        return {}
    try:
        data = json.load(open(path, "r", encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    counts: Dict[Tuple[str, str], int] = defaultdict(int)
    mapping: Dict[Tuple[str, str], int] = {}
    for p in data.get("players", []):
        tri = (p.get("teamtricode") or "").strip()
        fam = (p.get("familyname") or "").strip().lower()
        pid = p.get("personid")
        if tri and fam and pid is not None:
            key = (tri, fam)
            counts[key] += 1
            mapping[key] = int(pid)
    # drop collisions
    return {k: v for k, v in mapping.items() if counts[k] == 1}


_DATE_FMT_GAMELOG = "%b %d, %Y"


def _parse_gamelog_date(s: str):
    try:
        return datetime.strptime(s, _DATE_FMT_GAMELOG).date()
    except (ValueError, TypeError):
        return None


def _parse_iso_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


class GamelogStore:
    """Lazy per-player gamelog loader. Provides final-line label + L5 prior."""

    def __init__(self):
        self._cache: Dict[int, List[Dict[str, Any]]] = {}
        self._files_by_pid: Dict[int, List[str]] = defaultdict(list)
        for path in glob.glob(os.path.join(NBA_DIR, "gamelog_*.json")):
            m = re.match(r"gamelog_(\d+)_(.+)\.json$", os.path.basename(path))
            if m:
                self._files_by_pid[int(m.group(1))].append(path)

    def _rows(self, pid: int) -> List[Dict[str, Any]]:
        if pid in self._cache:
            return self._cache[pid]
        rows: List[Dict[str, Any]] = []
        for path in self._files_by_pid.get(pid, []):
            try:
                data = json.load(open(path, "r", encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for r in data if isinstance(data, list) else data.get("rows", []):
                d = _parse_gamelog_date(r.get("GAME_DATE", ""))
                if d is not None:
                    rows.append({"date": d, **r})
        rows.sort(key=lambda x: x["date"])
        self._cache[pid] = rows
        return rows

    def final_line(self, pid: int, game_date) -> Optional[Dict[str, float]]:
        for r in self._rows(pid):
            if r["date"] == game_date:
                return {
                    "pts": float(r.get("PTS", 0) or 0),
                    "reb": float(r.get("REB", 0) or 0),
                    "ast": float(r.get("AST", 0) or 0),
                    "fg3m": float(r.get("FG3M", 0) or 0),
                    "stl": float(r.get("STL", 0) or 0),
                    "blk": float(r.get("BLK", 0) or 0),
                    "tov": float(r.get("TOV", 0) or 0),
                    "min": float(r.get("MIN", 0) or 0),
                }
        return None

    def l5_prior(self, pid: int, game_date) -> Optional[Dict[str, float]]:
        """Mean of the 5 most recent games STRICTLY BEFORE game_date."""
        prior = [r for r in self._rows(pid) if r["date"] < game_date]
        if not prior:
            return None
        last5 = prior[-5:]
        out = {}
        for s in PLAYER_STATS:
            key = s.upper()
            vals = [float(r.get(key, 0) or 0) for r in last5]
            out[s] = float(np.mean(vals)) if vals else 0.0
        out["min"] = float(np.mean([float(r.get("MIN", 0) or 0) for r in last5]))
        return out


# --------------------------------------------------------------------------- #
# State extraction at grid points (leak-free; uses featurizer rows <= t)
# --------------------------------------------------------------------------- #
def grid_states(result: Dict[str, Any], game_id: str) -> Dict[int, Dict[str, Any]]:
    """For each grid second t, return the LAST event-state at game_elapsed <= t.

    Returns {t: {"game": game_row, "players": {(team,last_name): player_row}}}.
    Only includes a grid point if at least one event has occurred by t and the
    game actually reached t (game_remaining_sec > 0 at that row, i.e. not final).
    """
    game_rows = result["game"]
    player_rows = result["players"]
    # index player rows by event_idx for the snapshot at each event
    players_by_evidx: Dict[int, Dict[Tuple[str, str], Dict[str, Any]]] = defaultdict(dict)
    for pr in player_rows:
        players_by_evidx[pr["event_idx"]][(pr["team_abbrev"], pr["last_name"])] = pr

    out: Dict[int, Dict[str, Any]] = {}
    gi = 0
    for t in GRID_SEC:
        # find last game_row with game_elapsed_sec <= t
        chosen = None
        for gr in game_rows:
            if gr["game_elapsed_sec"] <= t:
                chosen = gr
            else:
                break
        if chosen is None:
            continue
        # require some elapsed time and that the game extends past t
        if chosen["game_elapsed_sec"] < 30:
            continue
        # game must have reached at least t (final game length > t)
        final_elapsed = game_rows[-1]["game_elapsed_sec"]
        if final_elapsed <= t + 5:
            continue
        out[t] = {
            "game": chosen,
            "players": players_by_evidx.get(chosen["event_idx"], {}),
        }
    return out


# --------------------------------------------------------------------------- #
# Baselines
# --------------------------------------------------------------------------- #
def _grid_period_clock(game_row: Dict[str, Any]) -> Tuple[int, float]:
    """Convert a grid game_row to (period, clock_remaining_min) for baselines."""
    period = int(game_row["period"])
    elapsed_in_period = int(game_row["elapsed_sec_in_period"])
    period_len = REG_PERIOD_LEN if period <= 4 else OT_PERIOD_LEN
    rem_sec = max(0, period_len - elapsed_in_period)
    return period, rem_sec / 60.0


def baseline_team_projection(game_row: Dict[str, Any]) -> Tuple[float, float]:
    """Naive minutes-paced team finals: current_score / played_share.

    This is baseline (B) for team score and matches project_snapshot's pace math
    at the team level. played_share clamps to 1.0 in OT (degrades to current).
    """
    period, clock_rem = _grid_period_clock(game_row)
    share = _baseline_share(period, clock_rem)
    hs, as_ = float(game_row["home_score"]), float(game_row["away_score"])
    if share <= 1e-6:
        return hs, as_
    return hs / share, as_ / share


def baseline_winprob(game_row: Dict[str, Any]) -> float:
    """Time-and-score logistic baseline for home win prob.

    Classic in-play heuristic: P(home win) = sigmoid(k * margin / sqrt(remaining)).
    Parameter-free-ish (fixed k); uses only current margin + time remaining.
    """
    margin = float(game_row["home_score"] - game_row["away_score"])
    rem_min = max(1.0, float(game_row["game_remaining_sec"]) / 60.0)
    # scale margin by remaining time: a lead late is worth more.
    z = 0.40 * margin / np.sqrt(rem_min)
    return float(1.0 / (1.0 + np.exp(-z)))


def baseline_player_snapshot(player_row: Dict[str, Any], game_row: Dict[str, Any],
                             pf: float) -> Dict[str, float]:
    """Baseline (A): the CURRENT box-snapshot projector project_snapshot's math.

    Uses scripts.predict_in_game.project_final per stat with foul factor. We
    intentionally drop the blowout factor here (it needs star/roster context the
    PBP state doesn't carry cleanly) -> this is the faithful pace+foul baseline.
    """
    period, clock_rem = _grid_period_clock(game_row)
    from src.prediction.live_factors import foul_trouble_factor
    ff = foul_trouble_factor(pf, period, clock_rem)
    out = {}
    for s in PLAYER_STATS:
        cur = float(player_row.get(s, 0) or 0)
        out[s] = _baseline_project_final(cur, period, clock_rem, foul_factor=ff)
    return out


def baseline_player_naive(player_row: Dict[str, Any], game_row: Dict[str, Any]) -> Dict[str, float]:
    """Baseline (B): naive minutes-paced on the player's OWN minutes.

    final = current * (player_total_expected_min / player_min_so_far). We proxy
    expected total min by scaling personal minutes to the game's played_share
    (same as project_final's player-clock basis).
    """
    min_so_far = float(player_row.get("min_so_far", 0) or 0)
    period, clock_rem = _grid_period_clock(game_row)
    out = {}
    for s in PLAYER_STATS:
        cur = float(player_row.get(s, 0) or 0)
        out[s] = _baseline_project_final(
            cur, period, clock_rem,
            player_clock_played_min=min_so_far if min_so_far > 0 else None,
        )
    return out


# --------------------------------------------------------------------------- #
# Learned engine: per-grid-bucket, per-target ridge regression, walk-forward
# --------------------------------------------------------------------------- #
# We train a SEPARATE simple learned projector per (grid-bucket t, target). The
# feature vector is the leak-free state at t. We use closed-form ridge regression
# (no GPU needed; deterministic; fast over hundreds of games) so the comparison
# is purely "can a learned correction on the same leak-free state beat the
# closed-form pace extrapolation?". This avoids any training-vs-eval confound.

TEAM_FEATS = [
    "played_share", "home_score", "away_score", "score_margin",
    "pace_poss_per_min", "home_efg", "away_efg", "home_tov_pct", "away_tov_pct",
    "home_ft_rate", "away_ft_rate", "game_remaining_sec",
]
# per-player features: state + own box-so-far + that stat's current value
PLAYER_BASE_FEATS = ["played_share", "game_remaining_sec", "min_so_far",
                     "pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "fga", "fgm"]


def _ridge_fit(X: np.ndarray, y: np.ndarray, lam: float = 10.0) -> np.ndarray:
    """Closed-form ridge with intercept. Returns weight vector (F+1,)."""
    n, f = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    A = Xb.T @ Xb + lam * np.eye(f + 1)
    A[0, 0] -= lam  # don't regularize intercept
    try:
        w = np.linalg.solve(A, Xb.T @ y)
    except np.linalg.LinAlgError:
        w = np.linalg.lstsq(Xb, y, rcond=None)[0]
    return w


def _ridge_pred(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    Xb = np.hstack([np.ones((X.shape[0], 1)), X])
    return Xb @ w


# --------------------------------------------------------------------------- #
# Main eval
# --------------------------------------------------------------------------- #
def build_game_record(game_id: str, meta: Dict[str, Any], store: GamelogStore
                      ) -> Optional[Dict[str, Any]]:
    """Reconstruct one game's grid-state + labels. Returns None if unusable."""
    home, away = meta.get("home_team"), meta.get("away_team")
    game_date = _parse_iso_date(meta.get("game_date") or "")
    if not home or not away or game_date is None:
        return None
    events = load_pbp_events(game_id)
    if not events:
        return None
    roster = load_roster(game_id)

    def resolver(team: str, last_name: str) -> Optional[int]:
        return roster.get((team, (last_name or "").strip().lower()))

    result = featurize_game(events, game_id, home, away,
                            player_id_resolver=resolver, emit_players=True)
    orient = result["orientation"]
    final_row = result["game"][-1]
    # team final labels from PBP last event
    home_final = float(final_row["home_score"])
    away_final = float(final_row["away_score"])
    if home_final <= 0 or away_final <= 0:
        return None
    # cross-check orientation vs season_games home_win
    home_win = meta.get("home_win")
    if home_win is not None and orient.get("resolved"):
        recon_home_win = 1 if home_final > away_final else 0
        if int(home_win) != recon_home_win:
            # orientation/label mismatch -> drop (don't risk inverted label)
            return None
    label_home_win = int(home_final > away_final) if home_win is None else int(home_win)

    grids = grid_states(result, game_id)
    if not grids:
        return None

    # player final labels via gamelog (by resolved pid + date)
    player_finals: Dict[int, Dict[str, float]] = {}
    for (team, last_name), pid in roster.items():
        lab = store.final_line(pid, game_date)
        if lab is not None:
            player_finals[pid] = lab

    return {
        "game_id": game_id,
        "game_date": game_date,
        "home_final": home_final,
        "away_final": away_final,
        "home_win": label_home_win,
        "grids": grids,
        "player_finals": player_finals,
        "store": store,
    }


def run(max_games: int, folds: int, seed: int, min_train: int,
        dump_residuals: bool = False) -> Dict[str, Any]:
    rng = np.random.default_rng(seed)
    season_games = load_season_games()
    store = GamelogStore()

    all_ids = [g for g in discover_game_ids() if g in season_games]
    # sort chronologically (walk-forward needs date order)
    all_ids = [g for g in all_ids if _parse_iso_date(season_games[g].get("game_date") or "")]
    all_ids.sort(key=lambda g: season_games[g]["game_date"])

    # subsample (chronological-stratified): keep order, take an evenly-spaced
    # subset so train/test folds still span time. SAY SO in the report.
    n_total = len(all_ids)
    if max_games and n_total > max_games:
        idx = np.linspace(0, n_total - 1, max_games).astype(int)
        sampled = [all_ids[i] for i in sorted(set(idx.tolist()))]
    else:
        sampled = all_ids
    print(f"[eval] {n_total} dated PBP games available; using {len(sampled)} "
          f"(chronological-even subsample={max_games})")

    # build records (this is the heavy step)
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
    print(f"[eval] {len(records)} usable game records ({n_fail} failed)")
    if len(records) < min_train + 10:
        raise SystemExit(f"too few usable games ({len(records)}) for WF eval")

    # walk-forward folds by date: split records into folds+1 chronological chunks
    dates = [r["game_date"] for r in records]
    uniq = sorted(set(dates))
    chunks = np.array_split(np.array(uniq, dtype=object), folds + 1)
    fold_test_dates = [set(chunks[k].tolist()) for k in range(1, folds + 1)]

    # accumulators: errors[bucket][method][metric] -> list of abs errors
    def _new_acc():
        return defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    acc = _new_acc()  # team + winprob
    pacc = _new_acc()  # player per-stat -> keyed bucket/method/stat
    # raw signed residuals: resid[bucket][stat][method] -> list of (proj - truth)
    resid: Dict[str, Dict[str, Dict[str, List[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )

    fold_summaries = []

    for fold_i, test_dates in enumerate(fold_test_dates):
        train_recs = [r for r in records if r["game_date"] < min(test_dates)]
        test_recs = [r for r in records if r["game_date"] in test_dates]
        if len(train_recs) < min_train or not test_recs:
            continue
        print(f"[fold {fold_i}] train={len(train_recs)} test={len(test_recs)} "
              f"(test dates {min(test_dates)}..{max(test_dates)})")

        # ---- train learned heads per grid bucket (on TRAIN ONLY) ----
        team_w: Dict[int, Dict[str, np.ndarray]] = {}
        wp_w: Dict[int, np.ndarray] = {}
        player_w: Dict[int, Dict[str, np.ndarray]] = {}
        for t in GRID_SEC:
            # team score heads (home_final, away_final) + winprob
            Xt, yh, ya, yw = [], [], [], []
            Xp_by_stat = defaultdict(list)
            yp_by_stat = defaultdict(list)
            for r in train_recs:
                if t not in r["grids"]:
                    continue
                gr = r["grids"][t]["game"]
                Xt.append([float(gr.get(f, 0) or 0) for f in TEAM_FEATS])
                yh.append(r["home_final"]); ya.append(r["away_final"]); yw.append(r["home_win"])
                # players
                for (team, last_name), prow in r["grids"][t]["players"].items():
                    pid = prow.get("player_id")
                    if pid is None or pid not in r["player_finals"]:
                        continue
                    fv = [float(prow.get(f, 0) or 0) for f in PLAYER_BASE_FEATS]
                    lab = r["player_finals"][pid]
                    for s in PLAYER_STATS:
                        Xp_by_stat[s].append(fv)
                        yp_by_stat[s].append(lab[s])
            if len(Xt) >= 20:
                Xt = np.array(Xt, dtype=np.float64)
                team_w[t] = {
                    "home": _ridge_fit(Xt, np.array(yh)),
                    "away": _ridge_fit(Xt, np.array(ya)),
                }
                wp_w[t] = _ridge_fit(Xt, np.array(yw, dtype=np.float64), lam=20.0)
            if Xp_by_stat["pts"] and len(Xp_by_stat["pts"]) >= 50:
                player_w[t] = {}
                for s in PLAYER_STATS:
                    Xp = np.array(Xp_by_stat[s], dtype=np.float64)
                    player_w[t][s] = _ridge_fit(Xp, np.array(yp_by_stat[s]))

        # ---- evaluate on TEST (held-out) ----
        for r in test_recs:
            for t, gd in r["grids"].items():
                gr = gd["game"]
                bucket = GRID_LABELS[t]
                # ===== team score =====
                # baseline (B naive pace)
                bh, ba = baseline_team_projection(gr)
                acc[bucket]["baseline_pace"]["margin"].append(
                    abs((bh - ba) - (r["home_final"] - r["away_final"])))
                acc[bucket]["baseline_pace"]["total"].append(
                    abs((bh + ba) - (r["home_final"] + r["away_final"])))
                # learned
                if t in team_w:
                    fv = np.array([[float(gr.get(f, 0) or 0) for f in TEAM_FEATS]])
                    lh = float(_ridge_pred(team_w[t]["home"], fv)[0])
                    la = float(_ridge_pred(team_w[t]["away"], fv)[0])
                    acc[bucket]["learned"]["margin"].append(
                        abs((lh - la) - (r["home_final"] - r["away_final"])))
                    acc[bucket]["learned"]["total"].append(
                        abs((lh + la) - (r["home_final"] + r["away_final"])))
                # ===== win prob (Brier) =====
                bw = baseline_winprob(gr)
                acc[bucket]["baseline_winprob"]["brier"].append((bw - r["home_win"]) ** 2)
                if t in wp_w:
                    fv = np.array([[float(gr.get(f, 0) or 0) for f in TEAM_FEATS]])
                    lw = float(np.clip(_ridge_pred(wp_w[t], fv)[0], 0.0, 1.0))
                    acc[bucket]["learned_winprob"]["brier"].append((lw - r["home_win"]) ** 2)
                # ===== player lines =====
                for (team, last_name), prow in gd["players"].items():
                    pid = prow.get("player_id")
                    if pid is None or pid not in r["player_finals"]:
                        continue
                    lab = r["player_finals"][pid]
                    # only score players who actually played (final min > 0)
                    if lab.get("min", 0) <= 0:
                        continue
                    pf = float(prow.get("pf", 0) or 0)
                    snap_proj = baseline_player_snapshot(prow, gr, pf)
                    naive_proj = baseline_player_naive(prow, gr)
                    # pregame L5
                    l5 = r["store"].l5_prior(pid, r["game_date"])
                    learned_fv = None
                    if t in player_w:
                        learned_fv = np.array([[float(prow.get(f, 0) or 0)
                                                for f in PLAYER_BASE_FEATS]])
                    for s in PLAYER_STATS:
                        truth = lab[s]
                        pacc[bucket]["snapshot"][s].append(abs(snap_proj[s] - truth))
                        pacc[bucket]["naive_pace"][s].append(abs(naive_proj[s] - truth))
                        if l5 is not None:
                            pacc[bucket]["pregame_l5"][s].append(abs(l5[s] - truth))
                        if learned_fv is not None:
                            cur = float(prow.get(s, 0) or 0)
                            pred = float(_ridge_pred(player_w[t][s], learned_fv)[0])
                            pacc[bucket]["learned"][s].append(abs(max(cur, pred) - truth))
                        # collect signed residuals (proj - truth) for interval calibration
                        resid[bucket][s]["snapshot"].append(snap_proj[s] - truth)
                        resid[bucket][s]["naive_pace"].append(naive_proj[s] - truth)
                        if l5 is not None:
                            resid[bucket][s]["pregame_l5"].append(l5[s] - truth)
                        if learned_fv is not None:
                            cur = float(prow.get(s, 0) or 0)
                            pred = float(_ridge_pred(player_w[t][s], learned_fv)[0])
                            resid[bucket][s]["learned"].append(max(cur, pred) - truth)

        fold_summaries.append({
            "fold": fold_i,
            "n_train": len(train_recs),
            "n_test": len(test_recs),
            "test_date_min": str(min(test_dates)),
            "test_date_max": str(max(test_dates)),
        })

    return _summarize(acc, pacc, fold_summaries, len(records), n_total,
                      resid if dump_residuals else None)


def _mean(xs):
    return float(np.mean(xs)) if xs else None


def _summarize(acc, pacc, fold_summaries, n_records, n_total,
               resid=None) -> Dict[str, Any]:
    team_curve = {}
    for bucket in GRID_LABELS.values():
        if bucket not in acc:
            continue
        team_curve[bucket] = {
            "n": len(acc[bucket]["baseline_pace"]["margin"]),
            "margin_mae": {
                "baseline_pace": _mean(acc[bucket]["baseline_pace"]["margin"]),
                "learned": _mean(acc[bucket]["learned"]["margin"]),
            },
            "total_mae": {
                "baseline_pace": _mean(acc[bucket]["baseline_pace"]["total"]),
                "learned": _mean(acc[bucket]["learned"]["total"]),
            },
            "winprob_brier": {
                "baseline": _mean(acc[bucket]["baseline_winprob"]["brier"]),
                "learned": _mean(acc[bucket]["learned_winprob"]["brier"]),
            },
        }
    player_curve = {}
    for bucket in GRID_LABELS.values():
        if bucket not in pacc:
            continue
        per_stat = {}
        for s in PLAYER_STATS:
            per_stat[s] = {
                "n": len(pacc[bucket]["snapshot"][s]),
                "snapshot": _mean(pacc[bucket]["snapshot"][s]),
                "naive_pace": _mean(pacc[bucket]["naive_pace"][s]),
                "pregame_l5": _mean(pacc[bucket]["pregame_l5"][s]),
                "learned": _mean(pacc[bucket]["learned"][s]),
            }
        player_curve[bucket] = per_stat
    out: Dict[str, Any] = {
        "meta": {
            "n_total_dated_pbp_games": n_total,
            "n_usable_records": n_records,
            "folds": fold_summaries,
            "grid_labels": GRID_LABELS,
            "baselines": {
                "team": "naive minutes-paced (current/played_share)",
                "winprob": "time-and-score logistic sigmoid(0.40*margin/sqrt(rem_min))",
                "player_snapshot": "scripts.predict_in_game.project_snapshot (pace+foul)",
                "player_naive_pace": "player-minutes-paced project_final",
                "player_pregame_l5": "mean of 5 games < game_date from gamelog",
            },
            "learned": "per-grid-bucket ridge regression on leak-free state, "
                       "trained WALK-FORWARD (train games strictly < test dates)",
            "honesty": "held-out only; walk-forward; labels PBP+gamelog; "
                       "orientation cross-checked vs season_games home_win",
        },
        "team_curve": team_curve,
        "player_curve": player_curve,
    }
    if resid is not None:
        out["residuals"] = {b: dict(sv) for b, sv in resid.items()}
    return out


def _fmt(v, nd=3):
    return f"{v:.{nd}f}" if isinstance(v, (int, float)) else " n/a "


def write_markdown(summary: Dict[str, Any], path: str) -> None:
    m = summary["meta"]
    lines = ["# In-Game Second-by-Second Eval — Honest Walk-Forward Curve\n"]
    lines.append(f"- Dated PBP games available: **{m['n_total_dated_pbp_games']}**; "
                 f"usable records (PBP+labels reconstructed): **{m['n_usable_records']}**")
    lines.append(f"- Folds (expanding-window, chronological): {len(m['folds'])}")
    for f in m["folds"]:
        lines.append(f"  - fold {f['fold']}: train={f['n_train']} test={f['n_test']} "
                     f"({f['test_date_min']}..{f['test_date_max']})")
    lines.append("- Leak posture: " + m["honesty"])
    lines.append("- Learned head: " + m["learned"])
    lines.append("")

    lines.append("## Team score + win prob (lower = better)\n")
    lines.append("| game-time | n | margin MAE pace | margin MAE learned | "
                 "total MAE pace | total MAE learned | Brier base | Brier learned |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for b in GRID_LABELS.values():
        if b not in summary["team_curve"]:
            continue
        c = summary["team_curve"][b]
        lines.append(
            f"| {b} | {c['n']} | {_fmt(c['margin_mae']['baseline_pace'],2)} | "
            f"{_fmt(c['margin_mae']['learned'],2)} | "
            f"{_fmt(c['total_mae']['baseline_pace'],2)} | "
            f"{_fmt(c['total_mae']['learned'],2)} | "
            f"{_fmt(c['winprob_brier']['baseline'],4)} | "
            f"{_fmt(c['winprob_brier']['learned'],4)} |")
    lines.append("")

    lines.append("## Player lines — per-stat MAE (lower = better)\n")
    lines.append("Methods: **snap**=box-snapshot projector (baseline A), "
                 "**naive**=player-minutes-paced (B), **L5**=pregame mean (C), "
                 "**learn**=walk-forward ridge.\n")
    for b in GRID_LABELS.values():
        if b not in summary["player_curve"]:
            continue
        lines.append(f"### {b}\n")
        lines.append("| stat | n | snap | naive | L5 | learn | best |")
        lines.append("|---|---|---|---|---|---|---|")
        for s in PLAYER_STATS:
            d = summary["player_curve"][b][s]
            cands = {k: d[k] for k in ("snapshot", "naive_pace", "pregame_l5", "learned")
                     if d[k] is not None}
            best = min(cands, key=cands.get) if cands else "n/a"
            best_map = {"snapshot": "snap", "naive_pace": "naive",
                        "pregame_l5": "L5", "learned": "learn"}
            lines.append(
                f"| {s} | {d['n']} | {_fmt(d['snapshot'])} | {_fmt(d['naive_pace'])} | "
                f"{_fmt(d['pregame_l5'])} | {_fmt(d['learned'])} | "
                f"{best_map.get(best, best)} |")
        lines.append("")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def _residual_stats(xs: List[float]) -> Dict[str, Any]:
    """Compute summary statistics for a list of signed residuals."""
    if not xs:
        return {"n": 0}
    arr = np.array(xs, dtype=np.float64)
    return {
        "n": len(arr),
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "p5": float(np.percentile(arr, 5)),
        "p25": float(np.percentile(arr, 25)),
        "p50": float(np.percentile(arr, 50)),
        "p75": float(np.percentile(arr, 75)),
        "p95": float(np.percentile(arr, 95)),
        "mad": float(np.median(np.abs(arr - np.median(arr)))),
    }


def write_residuals_json(summary: Dict[str, Any], path: str) -> None:
    """Write per-(stat,bucket) residual samples with summary stats to JSON.

    Output schema:
        {
          "<bucket_label>": {
            "<stat>": {
              "<method>": {
                "n": int, "mean": float, "std": float,
                "p5/p25/p50/p75/p95": float, "mad": float,
                "values": [float, ...]   # full raw sample for fitting
              }
            }
          }
        }
    """
    raw = summary.get("residuals", {})
    out: Dict[str, Any] = {
        "meta": {
            "description": (
                "Per-(stat, clock-bucket, method) held-out signed residuals "
                "(projection - truth) from eval_second_by_second.py walk-forward eval. "
                "Use for interval calibration (W-037/W-038): fit Laplace/Gaussian to "
                "`values` per stat/bucket, derive z-scores for 50/80/95% coverage."
            ),
            "sign_convention": "positive = model over-projected (projection > truth)",
            "methods": {
                "snapshot": "box-snapshot projector (baseline A: pace+foul)",
                "naive_pace": "player-minutes-paced project_final (baseline B)",
                "pregame_l5": "mean of 5 games < game_date from gamelog (baseline C)",
                "learned": "walk-forward ridge on leak-free state",
            },
            "stats": list(PLAYER_STATS),
            "buckets": list(GRID_LABELS.values()),
            "n_usable_records": summary["meta"]["n_usable_records"],
            "folds": summary["meta"]["folds"],
        },
        "by_bucket": {},
    }
    for bucket in GRID_LABELS.values():
        if bucket not in raw:
            continue
        bucket_out: Dict[str, Any] = {}
        for s in PLAYER_STATS:
            if s not in raw[bucket]:
                continue
            stat_out: Dict[str, Any] = {}
            for method, vals in raw[bucket][s].items():
                stats = _residual_stats(vals)
                stats["values"] = [round(v, 4) for v in vals]
                stat_out[method] = stats
            bucket_out[s] = stat_out
        out["by_bucket"][bucket] = bucket_out
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=str)


def write_residuals_markdown(summary: Dict[str, Any], path: str) -> None:
    """Write a human-readable summary table of residual stats per (bucket, stat)."""
    raw = summary.get("residuals", {})
    lines = ["# In-Game SBS Residuals — Per-(Stat, Bucket) Summary\n"]
    lines.append("_For interval calibration (W-037/W-038). "
                 "Sign: positive = over-projected. MAD = median absolute deviation._\n")
    for bucket in GRID_LABELS.values():
        if bucket not in raw:
            continue
        lines.append(f"## {bucket}\n")
        lines.append("| stat | method | n | mean | std | MAD | p5 | p25 | p50 | p75 | p95 |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for s in PLAYER_STATS:
            if s not in raw[bucket]:
                continue
            for method in ("snapshot", "naive_pace", "pregame_l5", "learned"):
                vals = raw[bucket][s].get(method, [])
                if not vals:
                    continue
                st = _residual_stats(vals)
                lines.append(
                    f"| {s} | {method} | {st['n']} | {_fmt(st['mean'])} | "
                    f"{_fmt(st['std'])} | {_fmt(st['mad'])} | "
                    f"{_fmt(st['p5'])} | {_fmt(st['p25'])} | {_fmt(st['p50'])} | "
                    f"{_fmt(st['p75'])} | {_fmt(st['p95'])} |"
                )
        lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=400,
                    help="chronological-even subsample size (0=all)")
    ap.add_argument("--folds", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--min-train", type=int, default=40)
    ap.add_argument("--dump-residuals", action="store_true",
                    help="emit raw per-(stat,bucket) signed residuals to "
                         ".planning/ingame/residuals_sbs.json + .md "
                         "(enables W-037/W-038 interval calibration fitting)")
    args = ap.parse_args()

    summary = run(args.max_games, args.folds, args.seed, args.min_train,
                  dump_residuals=args.dump_residuals)
    json_path = os.path.join(PLAN_DIR, "eval_curve.json")
    md_path = os.path.join(PLAN_DIR, "eval_curve.md")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    write_markdown(summary, md_path)
    print(f"\n[eval] wrote {json_path}")
    print(f"[eval] wrote {md_path}")

    if args.dump_residuals:
        if "residuals" not in summary or not summary["residuals"]:
            print("[eval] WARNING: no residuals collected — check that games/folds had test data")
            return 1
        res_json = os.path.join(PLAN_DIR, "residuals_sbs.json")
        res_md = os.path.join(PLAN_DIR, "residuals_sbs.md")
        write_residuals_json(summary, res_json)
        write_residuals_markdown(summary, res_md)
        print(f"[eval] wrote {res_json}")
        print(f"[eval] wrote {res_md}")
        # print a quick tally so the log entry has real numbers
        raw = summary["residuals"]
        print("\n[eval] Residual sample sizes per bucket (snapshot method, pts):")
        for bucket in GRID_LABELS.values():
            n = len(raw.get(bucket, {}).get("pts", {}).get("snapshot", []))
            print(f"  {bucket}: n={n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
