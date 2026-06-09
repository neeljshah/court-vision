"""book_line_error_probe.py — hunt for STRUCTURAL in-play book line errors.

THE DIFFERENT ANGLE (vs grade_ingame_*.py):
  The existing graders ask "is our PLAYER projection more accurate than the
  book's line?". That is an accuracy bet and we are at the model's ceiling.

  This probe instead models where the BOOK'S LIVE LINE is *structurally* wrong
  because of how the book derives it (current stat + a naive remaining-
  projection, repriced by automated rules). We characterize four known book
  in-play line flaws, detect each from the LINE TIME-SERIES + the live game
  STATE time-series, and — only when a flaw is present AND our model agrees the
  line is wrong — simulate the bet and settle vs the FINAL at real odds.

  This is edge from market microstructure, not from projecting the player better.

FLAWS HUNTED (see docs/_audits/INPLAY_BOOK_LINE_ERRORS.md for the full writeup):
  1. OVERREACT  — book bumps a scoring line UP right after a scoring burst;
                  production mean-reverts -> bumped line too high -> UNDER edge.
  2. INCOHERENCE— book's component lines (pts/reb/ast) drift internally
                  incoherent.  NOTE: the classic PTS-vs-PRA collapse CANNOT
                  fire here (no PRA line exists in any archive) — we say so and
                  test the only coherence signal the data supports instead.
  3. FOULBLOW   — book lags repricing a star in foul trouble or a developing
                  blowout (minutes about to drop) -> remaining-stat line too
                  high -> UNDER edge.
  4. STALE      — book line lags the latest possessions; our live-fed model is
                  ahead (this is just model_closer% on line MOVES).

HONEST FRAMING (non-negotiable): only 3 games / 2 matchups of real in-play lines
exist, and the moving-main-line flaws (#1,#3) are DraftKings-only (FanDuel posts
an over-only alt ladder that collapses to ~2 distinct lines). EVERYTHING here is
DIRECTIONAL MECHANISM CHARACTERIZATION, not an edge claim. n is tiny. The
deliverable is the detector + a characterized hypothesis ready to validate as
the corpus auto-grows (200/500-game gate).

Re-uses the proven loaders from grade_ingame_vs_vegas.py. NEW script only; does
not touch the model / serve / golive paths.

Output -> stdout + (optional) JSON via --save.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
import unicodedata
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
LINES_DIR = _ROOT / "data" / "lines"
LIVE_DIR = _ROOT / "data" / "live"

sys.path.insert(0, str(_ROOT / "scripts" / "ingame"))
from grade_ingame_vs_vegas import (  # noqa: E402
    _name_key, _parse_epoch_ms, _nearest, _payout,
    load_finals, load_model_series, load_model_series_game_record,
)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk")
SCORING_STATS = ("pts", "fg3m")  # the stats a book bumps after a scoring burst


# --------------------------------------------------------------------------- #
# Game-id <-> date <-> shadow-log mapping (matches grade_ingame_pooled).      #
# --------------------------------------------------------------------------- #
GAMES = [
    # (model_game_id, inplay_date, log_type, has_dk)
    ("0042500316", "2026-05-28", "unified_shadow", False),  # FD only -> no moving main line
    ("0042500317", "2026-05-30", "unified_shadow", True),
    ("0042500401", "2026-06-03", "game_record", True),
]


# --------------------------------------------------------------------------- #
# 1. DK main-line time-series (the only book with a real moving main line).   #
# --------------------------------------------------------------------------- #
def load_dk_mainline_series(date: str, name_to_pid: dict, book: str = "dk"):
    """series[(pid, stat)] = sorted list of dicts with the book's MAIN line at
    each capture, plus a de-dup'd LINE-MOVE event stream.

    Main line per capture = the alt-ladder tier with the smallest |op - up|
    (the balanced tier the book treats as its line) — same selection rule the
    proven grader uses, but we keep the full trajectory instead of one obs.

    Returns (series, moves) where:
      series[(pid,stat)] = [ {ep, line, op, up}, ... ]  (every capture, sorted)
      moves[(pid,stat)]  = [ {ep, line, op, up, prev_line}, ... ] (line CHANGES)
    """
    path = LINES_DIR / f"{date}_{book}_inplay.csv"
    if not path.exists():
        return {}, {}

    def _f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    grouped: dict[tuple, list[tuple]] = defaultdict(list)
    for r in csv.DictReader(open(path, encoding="utf-8")):
        stat = (r.get("stat") or "").strip().lower()
        if stat not in STATS:
            continue
        pid = name_to_pid.get(_name_key(r.get("player_name", "")))
        if pid is None:
            continue
        ep = _parse_epoch_ms(r.get("captured_at", ""))
        if ep is None:
            continue
        line = _f(r.get("line"))
        if line is None:
            continue
        grouped[(pid, stat, ep)].append((line, _f(r.get("over_price")),
                                         _f(r.get("under_price"))))

    series: dict[tuple, list[dict]] = defaultdict(list)
    for (pid, stat, ep), tiers in grouped.items():
        def _spread(t):
            line, op, up = t
            if op is None or up is None:
                return float("inf")
            return abs(op - up)
        tiers.sort(key=_spread)
        line, op, up = tiers[0]
        series[(pid, stat)].append({"ep": ep, "line": line, "op": op, "up": up})

    moves: dict[tuple, list[dict]] = {}
    for k, lst in series.items():
        lst.sort(key=lambda d: d["ep"])
        mv = []
        prev = None
        for d in lst:
            if prev is None or d["line"] != prev:
                e = dict(d)
                e["prev_line"] = prev
                mv.append(e)
                prev = d["line"]
        moves[k] = mv
    return dict(series), moves


# --------------------------------------------------------------------------- #
# 2. Live game-STATE time-series (per player: cumulative stat, min, pf,        #
#    plus team score margin) — for burst / foul / blowout detection.          #
# --------------------------------------------------------------------------- #
def _cap_ep(d: dict) -> int | None:
    ca = (d.get("captured_at") or "").strip().replace("Z", "+00:00")
    if not ca:
        return None
    try:
        dt = datetime.fromisoformat(ca)
    except ValueError:
        try:
            dt = datetime.strptime(ca, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _clock_to_sec(clock: str | None) -> float | None:
    """'11:37' -> 697.0 seconds remaining in the period; 'PT11M37S' too."""
    if not clock:
        return None
    c = str(clock).strip()
    if c.startswith("PT"):
        # ISO8601 duration PT##M##S
        c = c[2:]
        mins = secs = 0.0
        num = ""
        for ch in c:
            if ch.isdigit() or ch == ".":
                num += ch
            elif ch == "M":
                mins = float(num or 0); num = ""
            elif ch == "S":
                secs = float(num or 0); num = ""
        return mins * 60 + secs
    if ":" in c:
        mm, ss = c.split(":", 1)
        try:
            return float(mm) * 60 + float(ss)
        except ValueError:
            return None
    return None


def _game_elapsed_sec(period: int, clock_sec: float | None) -> float | None:
    """Approx total elapsed game seconds (regulation periods are 720s)."""
    if period is None or period <= 0:
        return 0.0
    if clock_sec is None:
        return (period - 1) * 720.0  # period start
    if period <= 4:
        return (period - 1) * 720.0 + (720.0 - clock_sec)
    # OT = 300s each
    return 4 * 720.0 + (period - 5) * 300.0 + (300.0 - clock_sec)


def load_state_series(gid: str):
    """state[pid] = sorted list of snapshots:
        {ep, period, clock_sec, elapsed, pts, reb, ast, fg3m, stl, blk, min, pf}
    team_state = sorted list of {ep, margin_abs, leader_team, period, clock_sec}
    pid_team[pid] = team tricode (for margin sign).
    Post-final-score frozen snapshots are dropped (the running total can't
    exceed the final, and we drop ties-to-final to avoid post-game freeze).
    """
    fs = glob.glob(str(LIVE_DIR / f"{gid}_*.json"))
    raw = []
    final_total = -1
    for p in fs:
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if not d.get("players"):
            continue
        ep = _cap_ep(d)
        if ep is None:
            continue
        tot = (d.get("home_score") or 0) + (d.get("away_score") or 0)
        final_total = max(final_total, tot)
        raw.append((ep, tot, d))
    raw.sort()

    state: dict[int, list[dict]] = defaultdict(list)
    team_state: list[dict] = []
    pid_team: dict[int, str] = {}
    seen_final = False
    for ep, tot, d in raw:
        # drop the post-game frozen tail: once the running total hits the final
        # AND we have already seen play, subsequent identical-total snaps are
        # frozen box repeats. We keep the FIRST time we reach the final (that is
        # the genuine end state) but drop the long frozen tail after it.
        if final_total > 0 and tot >= final_total:
            if seen_final:
                continue
            seen_final = True
        period = d.get("period")
        clock_sec = _clock_to_sec(d.get("clock"))
        elapsed = _game_elapsed_sec(period, clock_sec)
        hs = d.get("home_score") or 0
        as_ = d.get("away_score") or 0
        team_state.append({
            "ep": ep, "margin_abs": abs(hs - as_),
            "period": period, "clock_sec": clock_sec, "elapsed": elapsed,
            "home_team": d.get("home_team"), "away_team": d.get("away_team"),
            "leader_home": hs >= as_,
        })
        for pl in d["players"]:
            pid = pl.get("player_id")
            if pid is None:
                continue
            pid_team.setdefault(pid, pl.get("team"))
            state[pid].append({
                "ep": ep, "period": period, "clock_sec": clock_sec,
                "elapsed": elapsed,
                "pts": pl.get("pts"), "reb": pl.get("reb"), "ast": pl.get("ast"),
                "fg3m": pl.get("fg3m"), "stl": pl.get("stl"), "blk": pl.get("blk"),
                "min": pl.get("min"), "pf": pl.get("pf"),
            })
    for k in state:
        state[k].sort(key=lambda r: r["ep"])
    team_state.sort(key=lambda r: r["ep"])
    return dict(state), team_state, pid_team


def _state_at(slist: list[dict], ep: int):
    """Nearest snapshot at or before ep (no lookahead). None if none precede."""
    times = [s["ep"] for s in slist]
    i = bisect_left(times, ep)
    j = i - 1
    if j < 0:
        return None
    return slist[j]


def _state_before(slist: list[dict], ep: int, lookback_ms: int):
    """Snapshot nearest to (ep - lookback_ms), at or before it. None if none."""
    target = ep - lookback_ms
    times = [s["ep"] for s in slist]
    i = bisect_left(times, target)
    j = i - 1
    if j < 0:
        return None
    return slist[j]


# --------------------------------------------------------------------------- #
# 3. Flaw detectors. Each returns True/False given the state at a line MOVE.   #
# --------------------------------------------------------------------------- #
def detect_overreaction(stat: str, mv: dict, pstate: list[dict],
                        burst_window_ms: int, burst_thresh: float) -> dict | None:
    """OVERREACT: the book bumped a SCORING line UP, and the player just had a
    scoring burst (gained >= burst_thresh of the stat in the last
    burst_window) within the last few wall-clock minutes. Mean-reversion says
    the bumped line is too rich -> the structural error is on the OVER side, so
    the exploit is UNDER.

    Returns a signal dict if the flaw fires, else None.
    """
    if stat not in SCORING_STATS:
        return None
    if mv.get("prev_line") is None:
        return None
    if mv["line"] <= mv["prev_line"]:
        return None  # line did not move UP
    s_now = _state_at(pstate, mv["ep"])
    s_then = _state_before(pstate, mv["ep"], burst_window_ms)
    if s_now is None or s_then is None:
        return None
    v_now = s_now.get(stat)
    v_then = s_then.get(stat)
    if v_now is None or v_then is None:
        return None
    burst = v_now - v_then
    if burst < burst_thresh:
        return None
    return {
        "flaw": "OVERREACT", "side": "under",
        "line_jump": mv["line"] - mv["prev_line"],
        "burst": burst, "cur": v_now,
    }


def detect_foulblowout(stat: str, mv: dict, pstate: list[dict],
                       team_state: list[dict],
                       blowout_margin: float = 18.0) -> dict | None:
    """FOULBLOW: at the moment of the line move the player is in foul trouble
    (on pace to foul out — >=4 PF in regulation, or >=3 in the first half) OR a
    blowout is developing (|margin| >= blowout_margin in 2nd half). The book is
    slow to cut the remaining-minutes projection, so the remaining-stat line is
    too high -> UNDER. Only meaningful for counting stats (all of them).

    Returns a signal dict if the flaw fires, else None.
    """
    s = _state_at(pstate, mv["ep"])
    if s is None:
        return None
    period = s.get("period") or 0
    pf = s.get("pf")
    minutes = s.get("min") or 0.0
    sig = {}
    foul_trouble = False
    if pf is not None and minutes >= 1.0:
        if period <= 2 and pf >= 3:
            foul_trouble = True
        elif period >= 3 and pf >= 4:
            foul_trouble = True
    blowout = False
    ts = _state_at(team_state, mv["ep"])
    margin = ts.get("margin_abs") if ts else None
    if ts and period >= 3 and margin is not None and margin >= blowout_margin:
        blowout = True
    if not (foul_trouble or blowout):
        return None
    sig.update({
        "flaw": "FOULBLOW", "side": "under",
        "foul_trouble": foul_trouble, "blowout": blowout,
        "pf": pf, "margin": margin, "period": period,
    })
    return sig


# --------------------------------------------------------------------------- #
# 4. Settlement / model attachment.                                           #
# --------------------------------------------------------------------------- #
def _settle(side: str, line: float, op: float | None, up: float | None,
            actual: float):
    """Return (won, pnl) for betting `side` at the posted odds."""
    if abs(actual - line) < 1e-9:
        return None  # push
    over = side == "over"
    won = (actual > line) if over else (actual < line)
    odds = op if over else up
    return won, _payout(odds, won)


def _agg():
    return {"n": 0, "model_agrees": 0, "model_closer": 0,
            "bet_n": 0, "bet_w": 0, "pnl": 0.0,
            "ae_line": 0.0, "ae_model": 0.0,
            "episodes": 0, "n_players": 0}


# Independent-episode collapse: consecutive qualifying moves on the same
# (pid, stat, flaw) within EPISODE_GAP_MS are ONE underlying bet (the line just
# jitters around the same mispricing). We keep the LAST qualifying move in each
# episode (freshest line) so n reflects independent decisions, not autocorr ticks.
EPISODE_GAP_MS = 6 * 60 * 1000  # 6 minutes wall-clock


def _collapse_episodes(records: list[dict]) -> list[dict]:
    """records: raw per-move fired-signal dicts for ONE (pid, stat, flaw).
    Returns one record per contiguous episode (last move in each)."""
    if not records:
        return []
    records.sort(key=lambda r: r["ep"])
    episodes = []
    cur = [records[0]]
    for r in records[1:]:
        if r["ep"] - cur[-1]["ep"] > EPISODE_GAP_MS:
            episodes.append(cur[-1])  # keep freshest move in the episode
            cur = [r]
        else:
            cur.append(r)
    episodes.append(cur[-1])
    return episodes


def _accumulate(a: dict, recs: list[dict], min_odds: float):
    """Fold a list of (already episode-collapsed) records into accumulator a."""
    players = set()
    for rec in recs:
        a["n"] += 1
        players.add(rec["pid"])
        actual = rec["actual"]
        model = rec["model"]
        line = rec["line"]
        if rec["model_agrees"]:
            a["model_agrees"] += 1
        if actual is not None:
            a["ae_line"] += abs(line - actual)
            if model is not None:
                a["ae_model"] += abs(model - actual)
                if abs(model - actual) < abs(line - actual):
                    a["model_closer"] += 1
        bet = rec.get("bet")
        if bet is not None:
            a["bet_n"] += 1
            a["bet_w"] += int(bet["won"])
            a["pnl"] += bet["pnl"]
    a["episodes"] += len(recs)
    a["_players"] = a.get("_players", set()) | players
    a["n_players"] = len(a["_players"])


def probe_game(gid: str, date: str, log_type: str, has_dk: bool,
               tol_sec: int, burst_window_sec: float, burst_thresh: float,
               margin: float, min_odds: float) -> dict:
    """Run all detectors over one game's DK line moves. Returns per-flaw
    accumulators (after collapsing autocorrelated ticks to independent
    episodes) + a list of fired-signal records.

    Controls:
      control_allmoves   — accuracy of the book line on EVERY DK line move.
      control_modelunder — UNDER bets on every line move where the model agrees
                           the line is too high (NO flaw filter). This is the
                           honest benchmark the flaw filters must BEAT to claim
                           the edge is microstructure, not just model-under.
    """
    actuals, _ = load_finals(gid)
    if log_type == "game_record":
        mseries, name_to_pid = load_model_series_game_record(gid)
    else:
        mseries, name_to_pid = load_model_series(gid)
    pstate, team_state, _pid_team = load_state_series(gid)

    out = {
        "gid": gid, "date": date,
        "flaws": {"OVERREACT": _agg(), "FOULBLOW": _agg()},
        "control_allmoves": _agg(),
        "control_modelunder": _agg(),
        "signals": [],
        "n_line_moves": 0,
        "dk_available": has_dk,
    }
    if not has_dk:
        return out

    _series, moves = load_dk_mainline_series(date, name_to_pid)
    tol_ms = tol_sec * 1000
    burst_window_ms = int(burst_window_sec * 1000)

    # raw fired records, bucketed by (pid, stat, flaw) for episode collapse
    raw: dict[tuple, list[dict]] = defaultdict(list)
    # raw model-under control records, bucketed by (pid, stat) for collapse
    raw_mu: dict[tuple, list[dict]] = defaultdict(list)

    def _make_rec(pid, stat, mv, model, actual, sig, side, do_bet):
        model_agrees = (model is not None and model < mv["line"] - margin)
        rec = {
            "gid": gid, "pid": pid, "stat": stat, "ep": mv["ep"],
            "line": mv["line"], "prev_line": mv["prev_line"],
            "op": mv["op"], "up": mv["up"], "model": model, "actual": actual,
            "model_agrees": model_agrees,
        }
        if sig:
            rec.update({k: v for k, v in sig.items()})
        if do_bet and actual is not None and model_agrees:
            odds = mv["op"] if side == "over" else mv["up"]
            if odds is not None and abs(odds) >= min_odds:
                res = _settle(side, mv["line"], mv["op"], mv["up"], actual)
                if res is not None:
                    won, pnl = res
                    rec["bet"] = {"side": side, "odds": odds,
                                  "won": won, "pnl": pnl}
        return rec

    for (pid, stat), mvlist in moves.items():
        ps = pstate.get(pid, [])
        actual = actuals.get((pid, stat))
        msl = mseries.get((pid, stat))
        for mv in mvlist:
            if mv.get("prev_line") is None:
                continue
            out["n_line_moves"] += 1
            model = None
            if msl:
                got = _nearest(msl, mv["ep"], tol_ms, no_lookahead=True)
                if got is not None:
                    model = got[2]

            # control: every line move (accuracy only)
            if actual is not None:
                c = out["control_allmoves"]
                c["n"] += 1
                c["ae_line"] += abs(mv["line"] - actual)
                if model is not None:
                    c["ae_model"] += abs(model - actual)
                    if abs(model - actual) < abs(mv["line"] - actual):
                        c["model_closer"] += 1

            # control: model-under benchmark (no flaw filter)
            if model is not None and model < mv["line"] - margin:
                raw_mu[(pid, stat)].append(
                    _make_rec(pid, stat, mv, model, actual, None, "under", True))

            # flaw detectors
            s_over = detect_overreaction(stat, mv, ps, burst_window_ms,
                                         burst_thresh)
            if s_over:
                raw[(pid, stat, "OVERREACT")].append(
                    _make_rec(pid, stat, mv, model, actual, s_over,
                              s_over["side"], True))
            s_fb = detect_foulblowout(stat, mv, ps, team_state)
            if s_fb:
                raw[(pid, stat, "FOULBLOW")].append(
                    _make_rec(pid, stat, mv, model, actual, s_fb,
                              s_fb["side"], True))

    # collapse to independent episodes and accumulate
    for (pid, stat, flaw), recs in raw.items():
        eps = _collapse_episodes(recs)
        _accumulate(out["flaws"][flaw], eps, min_odds)
        out["signals"].extend(eps)
    mu_eps = []
    for (pid, stat), recs in raw_mu.items():
        mu_eps.extend(_collapse_episodes(recs))
    _accumulate(out["control_modelunder"], mu_eps, min_odds)

    # finalize player counts
    for a in (out["control_modelunder"], out["flaws"]["OVERREACT"],
              out["flaws"]["FOULBLOW"]):
        a["n_players"] = len(a.get("_players", set()))
    return out


# --------------------------------------------------------------------------- #
# 5. Reporting.                                                               #
# --------------------------------------------------------------------------- #
def _pool_into(dst: dict, src: dict):
    """Sum numeric fields and union the _players set."""
    for f in ("n", "model_agrees", "model_closer", "bet_n", "bet_w", "pnl",
              "ae_line", "ae_model", "episodes"):
        dst[f] += src.get(f, 0)
    dst["_players"] = dst.get("_players", set()) | src.get("_players", set())
    dst["n_players"] = len(dst["_players"])


def _fmt_agg(label: str, a: dict) -> str:
    n = a["n"] or 1
    bn = a["bet_n"] or 1
    npl = a.get("n_players", len(a.get("_players", set())))
    return (f"{label:<18} n={a['n']:>4} (pl={npl:>2})  "
            f"model_agree={a['model_agrees']:>4}  "
            f"model_closer={a['model_closer']/n*100:>5.1f}%  "
            f"MAE_line={a['ae_line']/n:>5.2f}  "
            f"bet_n={a['bet_n']:>4}  win={a['bet_w']/bn*100:>5.1f}%  "
            f"ROI={a['pnl']/bn*100:>+7.2f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol-sec", type=int, default=180)
    ap.add_argument("--burst-window-sec", type=float, default=180.0,
                    help="wall-clock lookback to measure a scoring burst")
    ap.add_argument("--burst-thresh", type=float, default=3.0,
                    help="min stat gained in the window to count as a 'burst' "
                         "(3 pts in 3 game-min after a line bump is a real "
                         "over-reaction pattern; sweep 2-5 for sensitivity)")
    ap.add_argument("--margin", type=float, default=0.5,
                    help="min |line-model| for the model to 'agree' the line is wrong")
    ap.add_argument("--min-odds", type=float, default=100.0,
                    help="drop |odds|<min_odds (the +900%% payout trap)")
    ap.add_argument("--save", default=None)
    args = ap.parse_args()

    print("=" * 92)
    print("IN-PLAY BOOK STRUCTURAL LINE-ERROR PROBE  (n=3 games / 2 matchups — "
          "DIRECTIONAL ONLY)")
    print("=" * 92)
    print(f"tol={args.tol_sec}s  burst_window={args.burst_window_sec:.0f}s  "
          f"burst_thresh={args.burst_thresh}  agree_margin={args.margin}  "
          f"min_odds={args.min_odds}")
    print("Flaws: OVERREACT(line bumped UP after scoring burst->UNDER), "
          "FOULBLOW(foul-trouble/blowout->UNDER).")
    print("PTS-vs-PRA incoherence flaw is NOT testable here (no PRA line exists "
          "in any archive) — reported as N/A.\n")

    per_game = []
    pooled = {"OVERREACT": _agg(), "FOULBLOW": _agg()}
    pooled_ctrl = _agg()
    pooled_mu = _agg()
    for gid, date, lt, has_dk in GAMES:
        r = probe_game(gid, date, lt, has_dk,
                       tol_sec=args.tol_sec,
                       burst_window_sec=args.burst_window_sec,
                       burst_thresh=args.burst_thresh,
                       margin=args.margin, min_odds=args.min_odds)
        per_game.append(r)
        tag = "DK" if has_dk else "FD-only (no moving main line -> SKIP)"
        print(f"-- {gid}  {date}  [{lt}]  {tag} --")
        if not has_dk:
            print("   (no DraftKings archive; FanDuel posts an over-only alt "
                  "ladder with ~2 distinct main lines -> flaws #1/#3 not "
                  "detectable)\n")
            continue
        print(f"   DK line moves: {r['n_line_moves']}  "
              f"(episodes collapsed at {EPISODE_GAP_MS//60000}min gap)")
        print("   " + _fmt_agg("CONTROL(all-acc)", r["control_allmoves"]))
        print("   " + _fmt_agg("CTRL(model-under)", r["control_modelunder"]))
        for flaw in ("OVERREACT", "FOULBLOW"):
            print("   " + _fmt_agg(flaw, r["flaws"][flaw]))
            _pool_into(pooled[flaw], r["flaws"][flaw])
        _pool_into(pooled_ctrl, r["control_allmoves"])
        _pool_into(pooled_mu, r["control_modelunder"])
        print()

    print("=" * 92)
    print("POOLED across DK games (2 games / 2 matchups — NOT VALIDATED, "
          "episodes collapsed):")
    print("  " + _fmt_agg("CONTROL(all-acc)", pooled_ctrl))
    print("  " + _fmt_agg("CTRL(model-under)", pooled_mu))
    for flaw in ("OVERREACT", "FOULBLOW"):
        print("  " + _fmt_agg(flaw, pooled[flaw]))
    print("\n  READ: a flaw is only 'microstructure edge' if it BEATS "
          "CTRL(model-under).\n  If a flaw ROI ~= model-under ROI, the edge is "
          "just betting the model's UNDER, not the book flaw.")
    print("=" * 92)

    if args.save:
        def _clean(a: dict) -> dict:
            return {k: v for k, v in a.items() if k != "_players"}

        def _clean_game(g: dict) -> dict:
            out = {}
            for k, v in g.items():
                if k == "signals":
                    continue
                if k == "flaws":
                    out[k] = {fk: _clean(fv) for fk, fv in v.items()}
                elif isinstance(v, dict) and "n" in v:
                    out[k] = _clean(v)
                else:
                    out[k] = v
            return out

        out = {
            "config": vars(args),
            "games": [_clean_game(g) for g in per_game],
            "signals": [s for g in per_game for s in g["signals"]],
            "pooled": {
                "control_allmoves": _clean(pooled_ctrl),
                "control_modelunder": _clean(pooled_mu),
                "OVERREACT": _clean(pooled["OVERREACT"]),
                "FOULBLOW": _clean(pooled["FOULBLOW"]),
            },
        }
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(json.dumps(out, indent=2, default=str),
                                   encoding="utf-8")
        print(f"\nSaved: {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
