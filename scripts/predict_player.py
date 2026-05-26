"""predict_player.py — actually use the model. CLI for live prop predictions.

Loads the production prop_pergame stack + quantile heads and prints
predictions + 80% intervals + L5 baseline + claimed edge per stat for ONE
player playing ONE opponent. The honest end-user surface — what you'd
actually run before a game to decide bets.

Usage:
    # By player name (NBA full_name lookup)
    python scripts/predict_player.py --name "Nikola Jokic" --opp DEN --home --rest 2
    python scripts/predict_player.py --name "Anthony Edwards" --opp PHX --away --rest 1

    # By player_id
    python scripts/predict_player.py --pid 203999 --opp LAL --home

Output (one row per stat):
    stat  | prediction | L5_avg | edge   | q10  q90  | recommended bet @ -110
    PTS   | 26.3       | 28.1   | -1.8   | 18  35    | UNDER 28.1 (62.7% modelled hit)
    ...
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, date as _date

import numpy as np


# Cache TTL for playergamelog (seconds): 6 hours.
_PLAYERLOG_TTL_SEC = 6 * 60 * 60

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_prediction_row, predict_pergame, _MIN_PLAYED, _num,
    _parse_date, _ewma,
)
from src.prediction.prop_quantiles import (  # noqa: E402
    predict_pergame_quantiles,
)
from src.data.injuries import (  # noqa: E402
    load_unavailable_players, load_soft_warn_players, lookup_status,
)
from src.data.lineups import (  # noqa: E402
    build_starter_index, teams_playing, classify_starter,
    STATUS_SCALE as _STATUS_SCALE,
    apply_minutes_scaling,
)


def _strip_accents(s: str) -> str:
    """Drop non-ASCII diacritics so 'Jokic' matches 'Nikola Jokic'."""
    import unicodedata  # noqa: PLC0415
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _resolve_player_id(name: str):
    """NBA full_name → player_id via nba_api static index. Diacritic-insensitive."""
    try:
        from nba_api.stats.static import players  # noqa: PLC0415
    except Exception as e:
        print(f"  [warn] nba_api unavailable: {e}")
        return None
    needle = _strip_accents(name).lower()
    candidates = players.get_players()
    for p in candidates:
        if _strip_accents(p["full_name"]).lower() == needle:
            return int(p["id"])
    # Fuzzy fallback: substring match (accent-stripped)
    for p in candidates:
        if needle in _strip_accents(p["full_name"]).lower():
            return int(p["id"])
    return None


def _detect_current_season() -> str:
    """NBA season string for today's date: 'YYYY-YY'.

    Season starts in October. From Oct 1 onward the season is current_year/(current_year+1).
    Before October it's the (current_year-1)/current_year season ending.
    """
    now = datetime.now()
    if now.month >= 10:
        start = now.year
    else:
        start = now.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _player_l5_l10(player_id: int, season: str, gamelog_dir: str) -> dict:
    """Quick L5 / L10 means per stat from the player's gamelog (no leak — uses
    all available cached games as 'prior')."""
    import glob
    import json
    path = os.path.join(gamelog_dir, f"gamelog_{player_id}_{season}.json")
    if not os.path.exists(path):
        # Fall back to previous season if this season's not cached
        for try_season in (season, f"{int(season[:4])-1}-{int(season[5:])-1:02d}"):
            p = os.path.join(gamelog_dir, f"gamelog_{player_id}_{try_season}.json")
            if os.path.exists(p):
                path = p
                break
        else:
            return {}
    try:
        games = json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}
    played = [g for g in games if _num(g.get("MIN")) >= _MIN_PLAYED]
    if not played:
        return {}
    box = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M",
           "stl": "STL", "blk": "BLK", "tov": "TOV"}
    out = {}
    for stat, col in box.items():
        vals = [_num(g.get(col)) for g in played]
        out[f"l5_{stat}"]  = round(sum(vals[-5:]) / max(1, len(vals[-5:])), 2)
        out[f"l10_{stat}"] = round(sum(vals[-10:]) / max(1, len(vals[-10:])), 2)
        out[f"ewma_{stat}"] = round(_ewma(vals), 2)
    return out


def _playerlog_cache_path(player_id: int, season: str) -> str:
    """Path under data/cache/playerlogs/<pid>_<season>.json."""
    cache_dir = os.path.join(PROJECT_DIR, "data", "cache", "playerlogs")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{int(player_id)}_{season}.json")


def _load_playerlog_cached(player_id: int, season: str,
                           ttl_sec: int = _PLAYERLOG_TTL_SEC,
                           now: float | None = None) -> list | None:
    """Read cached playergamelog rows if file exists and is fresh.

    Returns the list of row-dicts (each with at least GAME_DATE / MIN /
    START_POSITION) or None if cache miss / expired / unreadable.
    """
    path = _playerlog_cache_path(player_id, season)
    if not os.path.exists(path):
        return None
    now = time.time() if now is None else now
    try:
        age = now - os.path.getmtime(path)
    except OSError:
        return None
    if age > ttl_sec:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _save_playerlog_cache(player_id: int, season: str, rows: list) -> None:
    """Write playergamelog rows to disk cache (json, utf-8)."""
    path = _playerlog_cache_path(player_id, season)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rows, fh)
    except Exception:
        pass


def _fetch_playerlog(player_id: int, season: str,
                     lookback: int = 5) -> list | None:
    """Pull a starter-signal-shaped row list from nba_api.

    PlayerGameLog has MIN + GAME_DATE but NOT START_POSITION. To get the
    starter flag we look up the per-game traditional boxscore for the most
    recent `lookback` games and read START_POSITION from there.

    Returns a list of dicts with keys: GAME_DATE, MIN, START_POSITION,
    GAME_ID. None on failure. Cache-wrapped by _get_playerlog.
    """
    try:
        from nba_api.stats.endpoints import (  # noqa: PLC0415
            playergamelog, boxscoretraditionalv2,
        )
    except Exception:
        return None
    try:
        log = playergamelog.PlayerGameLog(player_id=int(player_id),
                                          season=season, timeout=10)
        gl_rows = log.get_normalized_dict().get("PlayerGameLog") or []
    except Exception:
        return None
    # Most-recent-first is the PlayerGameLog default; take top N.
    recent = gl_rows[: max(1, int(lookback))]
    out = []
    for gl in recent:
        gid = gl.get("Game_ID") or gl.get("GAME_ID")
        row = {
            "GAME_DATE": gl.get("GAME_DATE"),
            "MIN": gl.get("MIN"),
            "GAME_ID": gid,
            "START_POSITION": "",
        }
        if gid:
            try:
                bx = boxscoretraditionalv2.BoxScoreTraditionalV2(
                    game_id=gid, timeout=10)
                stats = bx.get_normalized_dict().get(
                    "PlayerStats") or []
                for s in stats:
                    if int(s.get("PLAYER_ID") or 0) == int(player_id):
                        row["START_POSITION"] = (
                            s.get("START_POSITION") or "")
                        # Prefer boxscore MIN if available (string fmt).
                        if s.get("MIN"):
                            row["MIN"] = s.get("MIN")
                        break
            except Exception:
                # Leave START_POSITION="" if boxscore fetch fails.
                pass
        out.append(row)
    return out


def _get_playerlog(player_id: int, season: str) -> list | None:
    """Cached playergamelog fetch. Reads disk cache if fresh, otherwise
    hits nba_api and writes the response back to disk."""
    cached = _load_playerlog_cached(player_id, season)
    if cached is not None:
        return cached
    rows = _fetch_playerlog(player_id, season)
    if rows is not None:
        _save_playerlog_cache(player_id, season, rows)
    return rows


def _starter_signal(rows: list, lookback: int = 5) -> dict:
    """Compute starter_rate, played_rate, and a human band label from the
    last `lookback` rows of a playergamelog response.

    START_POSITION is 'G'/'F'/'C' for starters and empty string for bench
    in the nba_api schema. MIN > 0 (or non-empty) = appeared.
    """
    if not rows:
        return {"games": 0, "starts": 0, "played": 0,
                "starter_rate": 0.0, "played_rate": 0.0,
                "band": "unknown", "message": "no recent gamelog rows"}
    recent = list(rows)[:max(1, int(lookback))]
    n = len(recent)
    starts = 0
    played = 0
    for r in recent:
        sp = r.get("START_POSITION") or ""
        if isinstance(sp, str) and sp.strip().upper() in {"G", "F", "C"}:
            starts += 1
        minv = r.get("MIN")
        # MIN can be int/float (PlayerGameLog) or "MM:SS" string (boxscore).
        # Treat 0 / "" / None / "0:00" as DNP.
        appeared = False
        if isinstance(minv, (int, float)):
            appeared = minv > 0
        elif isinstance(minv, str):
            s = minv.strip()
            if s and s not in {"0", "0:00", "0.0", "00:00"}:
                # "MM:SS" or "MM.SS" or "MM" — any leading-int > 0 counts.
                head = s.split(":")[0].split(".")[0]
                try:
                    appeared = int(head) > 0
                except ValueError:
                    appeared = True  # non-numeric but non-empty
        if appeared:
            played += 1
    starter_rate = starts / n
    played_rate = played / n
    if starter_rate >= 0.80 and played_rate >= 1.0:
        band = "full"
        message = "full starter confidence"
    elif starter_rate >= 0.40 or played_rate >= 0.60:
        band = "rotation"
        message = "rotation player — prediction assumes typical workload"
    else:
        band = "bench"
        message = ("WARNING: bench / out of rotation — predictions likely "
                   "overestimate")
    return {"games": n, "starts": starts, "played": played,
            "starter_rate": starter_rate, "played_rate": played_rate,
            "band": band, "message": message}


def _format_starter_line(sig: dict) -> str:
    """Render the starter_signal dict as a single-line indicator."""
    n = sig.get("games", 0)
    if n == 0:
        return f"  Recent role: {sig.get('message', 'unknown')}"
    starts = sig.get("starts", 0)
    played = sig.get("played", 0)
    sr = sig.get("starter_rate", 0.0) * 100
    pr = sig.get("played_rate", 0.0) * 100
    return (f"  Recent role: started {starts}/{n} games ({sr:.0f}%), "
            f"played {played}/{n} ({pr:.0f}%) — {sig['message']}")


def append_predictions_csv(
    out_path: str, player_id: int, name: str, opp: str,
    is_home: bool, stat_preds: dict,
    lineup_status: str = "", lineup_class: str = "",
    play_pct: str = "", injury_status: str = "",
) -> int:
    """Append one row per stat to out_path. Creates the file + header when absent.

    Schema (cycle 49 + 80):
        date, game_id, player_id, player, team, opp, venue, stat, pred,
        lineup_status, lineup_class, play_pct, injury_status

    Matches scripts/predict_slate.py save_predictions_csv. Cycle 80 added
    the four context columns so the daily ledger captures the lineup +
    injury context at PREDICTION time, enabling future empirical validation
    of any post-prediction adjustment (cycle 66/67 scale-by-status etc.)
    once 30+ days of predictions + actuals accumulate.

    Context columns default to "" — cycle 49 callers that don't pass them
    still produce a valid CSV with blank context, and append-mode against
    an existing pre-cycle-80 file would only mismatch the header (the
    header is only written on first-creation).

    `game_id` and `team` are empty for single-player runs (slate runs fill them).
    """
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    file_exists = os.path.exists(out_path) and os.path.getsize(out_path) > 0
    date_str = _date.today().isoformat()
    venue = "home" if is_home else "away"
    n = 0
    with open(out_path, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if not file_exists:
            w.writerow([
                "date", "game_id", "player_id", "player",
                "team", "opp", "venue", "stat", "pred",
                "lineup_status", "lineup_class", "play_pct", "injury_status",
            ])
        for stat in STATS:
            v = stat_preds.get(stat)
            if v is None:
                continue
            w.writerow([
                date_str, "", player_id, name,
                "", opp, venue, stat, f"{float(v):.4f}",
                lineup_status, lineup_class, play_pct, injury_status,
            ])
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--name", help="Player NBA full name (e.g. 'Nikola Jokic')")
    grp.add_argument("--pid",  type=int, help="Player ID (NBA stats.com)")
    ap.add_argument("--opp", required=True, help="Opponent team abbrev (e.g. LAL)")
    ven = ap.add_mutually_exclusive_group()
    ven.add_argument("--home", action="store_true", help="Player's team is HOME (default)")
    ven.add_argument("--away", action="store_true", help="Player's team is AWAY")
    ap.add_argument("--rest", type=float, default=2.0, help="Days rest (default 2)")
    ap.add_argument("--season", default=None, help="Season override (e.g. '2024-25'). Default: current.")
    ap.add_argument("--lookback-games", type=int, default=5,
                    help="N recent games to compute starter_rate over (default 5)")
    ap.add_argument("--require-starter", action="store_true",
                    help="Exit 2 if starter_rate < 0.4 (skips non-starters in batch flows)")
    ap.add_argument("--save", nargs="?", const="__default__", default=None,
                    help="Append predictions to CSV. Bare flag → data/predictions/<today>.csv "
                         "(same path/schema as predict_slate --save). With arg → that path.")
    ap.add_argument("--injuries", nargs="?", const="__default__", default=None,
                    help="Cross-reference data/injuries_<today>.json. Exits 2 if the player "
                         "is listed OUT/DOUBTFUL/NOT-WITH-TEAM (unless --include-injured). "
                         "QUESTIONABLE players proceed with a soft-warn line.")
    ap.add_argument("--include-injured", action="store_true",
                    help="Override --injuries: continue prediction even when the player is OUT.")
    ap.add_argument("--lineups", nargs="?", const="__default__", default=None,
                    help="Cross-reference data/lineups_<today>.json (cycle 61 rotowire scrape). "
                         "Prints a one-line classification (starter / questionable / bench / no-game).")
    ap.add_argument("--require-starter-lineup", action="store_true",
                    help="Exit 2 if the player isn't classified 'starter' or 'questionable' "
                         "in tonight's lineup data — for batch flows that only want starters.")
    ap.add_argument("--scale-by-status", action="store_true",
                    help="Cycle 66. Scale every stat prediction by the lineup classification: "
                         "questionable*0.75, bench*0.30, no-game*0.0, starter*1.0. Requires --lineups.")
    args = ap.parse_args()

    season = args.season or _detect_current_season()
    pid = args.pid
    name = args.name
    if pid is None:
        pid = _resolve_player_id(name)
        if pid is None:
            print(f"  [fail] could not resolve player name '{name}' — try --pid instead.")
            sys.exit(1)
    elif name is None:
        name = f"player_id={pid}"

    is_home = not args.away
    gamelog_dir = os.path.join(PROJECT_DIR, "data", "nba")
    model_dir = os.path.join(PROJECT_DIR, "data", "models")

    print(f"\n  Player: {name}  (id={pid})")
    print(f"  Game:   {'home' if is_home else 'away'} vs {args.opp}    season={season}    rest={args.rest}d")

    # Lineup cross-reference (cycle 63) — runs before injury / playergamelog
    # so no-game players exit before any expensive nba_api fetch.
    # Cycle 80: also captures context for the predictions ledger.
    lineup_cls = "unknown"
    ctx_lineup_status = ""
    ctx_play_pct = ""
    if args.lineups is not None:
        lu_path = (os.path.join(PROJECT_DIR, "data",
                                  f"lineups_{_date.today().isoformat()}.json")
                    if args.lineups == "__default__" else args.lineups)
        starter_idx = build_starter_index(lu_path)
        tonight = teams_playing(lu_path)
        # We don't know the player's team here without an API call; pass None
        # so classify_starter falls back to the "bench if in-index else default" branch.
        lineup_cls = classify_starter(name, starter_idx, teams_tonight=tonight)
        rec = starter_idx.get(name.lower())
        if rec:
            ctx_lineup_status = rec["lineup_status"]
            ctx_play_pct = str(rec["play_pct"])
            print(f"  Lineup:   {lineup_cls.upper()} ({rec['lineup_status']}, "
                  f"{rec['pos']}, play_pct={rec['play_pct']}"
                  + (f", inj={rec['injury']}" if rec['injury'] else "") + ")")
        else:
            print(f"  Lineup:   {lineup_cls.upper()} (not in tonight's starter list)")
        if args.require_starter_lineup and lineup_cls not in ("starter", "questionable"):
            print(f"  [skip] --require-starter-lineup set and classification "
                  f"is '{lineup_cls}' — exiting.")
            sys.exit(2)
    elif args.scale_by_status:
        print("  [warn] --scale-by-status set without --lineups; "
              "scaling defaults to 1.0 (no effect).")

    # Injury cross-reference (cycle 53) — runs before the starter signal so a
    # listed-OUT player exits before the expensive playergamelog fetch.
    ctx_injury_status = ""
    if args.injuries is not None and not args.include_injured:
        inj_path = (os.path.join(PROJECT_DIR, "data",
                                  f"injuries_{_date.today().isoformat()}.json")
                    if args.injuries == "__default__" else args.injuries)
        unav = load_unavailable_players(inj_path)
        soft = load_soft_warn_players(inj_path)
        status = lookup_status(name, unav, soft)
        if status:
            ctx_injury_status = status
        if status in unav.values():
            print(f"  [skip] {name} listed {status} in injury report — exiting (use --include-injured to override).")
            sys.exit(2)
        if status:    # QUESTIONABLE
            print(f"  [warn] {name} listed {status} in injury report — proceeding with reduced confidence.")

    # Starter / playing-time signal — uses live playergamelog (cached 6h).
    log_rows = _get_playerlog(pid, season)
    sig = _starter_signal(log_rows or [], lookback=args.lookback_games)
    print(_format_starter_line(sig))
    if args.require_starter and sig.get("starter_rate", 0.0) < 0.4:
        print(f"  [skip] --require-starter set and starter_rate="
              f"{sig['starter_rate']:.2f} < 0.40 — exiting.")
        sys.exit(2)
    print()

    row = build_prediction_row(pid, args.opp, season, is_home=is_home,
                               rest_days=args.rest, gamelog_dir=gamelog_dir)
    if row is None:
        print(f"  [fail] no gamelog cached for player_id={pid} season={season}.")
        sys.exit(2)

    l5 = _player_l5_l10(pid, season, gamelog_dir)

    print(f"  {'stat':4s} | {'pred':>6s} | {'L5':>5s} | {'L10':>5s} | {'edge':>6s} | {'q10':>5s} {'q90':>5s} | bet @ -110")
    print(f"  -----+--------+-------+-------+--------+-----------+-------------------")
    stat_preds = {}
    # R15_W1: pre-fetch the live ESPN availability factor once for this player.
    try:
        from src.prediction.injury_availability import (
            get_availability_factor as _avail,
        )
        _avail_factor = _avail(player_id=pid, player_name=name)
    except Exception:
        _avail_factor = 1.0
    for stat in STATS:
        pred = predict_pergame(stat, row, model_dir)
        if pred is None:
            print(f"  {stat.upper():4s} | (no model)")
            continue
        # R15_W1: apply availability to the q50 point estimate (predict_pergame
        # itself is player-agnostic so the dampener is applied here at the
        # script layer the same way predict_player_pergame does internally).
        pred = round(float(pred) * float(_avail_factor), 2)
        stat_preds[stat] = pred
        l5_val = l5.get(f"l5_{stat}", None)
        l10_val = l5.get(f"l10_{stat}", None)
        edge = (pred - l5_val) if l5_val is not None else None
        # R15_W1: pass pid so q10/q50/q90 receive the same availability dampener.
        qint = predict_pergame_quantiles(stat, row, model_dir,
                                         player_id=pid, player_name=name) or {}
        q10 = qint.get("q10", "—")
        q90 = qint.get("q90", "—")
        q10_s = f"{q10:.1f}" if isinstance(q10, (int, float)) else q10
        q90_s = f"{q90:.1f}" if isinstance(q90, (int, float)) else q90
        l5s  = f"{l5_val:.1f}" if l5_val is not None else "—"
        l10s = f"{l10_val:.1f}" if l10_val is not None else "—"
        edge_s = f"{edge:+.2f}" if edge is not None else "—"
        # Bet recommendation: if |edge| > 0.5 stat unit, suggest the side
        bet = ""
        if edge is not None:
            if edge > 0.5:
                bet = f"OVER  line~{l5_val:.1f}"
            elif edge < -0.5:
                bet = f"UNDER line~{l5_val:.1f}"
            else:
                bet = "  (no edge)"
        print(f"  {stat.upper():4s} | {pred:6.2f} | {l5s:>5s} | {l10s:>5s} | {edge_s:>6s} | {q10_s:>5s} {q90_s:>5s} | {bet}")
    print()

    # Cycle 66: apply minutes-status scaling before save. Prints an
    # explainer line if any scaling factor != 1.0 was applied.
    if args.scale_by_status and lineup_cls in _STATUS_SCALE \
            and _STATUS_SCALE[lineup_cls] != 1.0:
        scaled = apply_minutes_scaling(stat_preds, lineup_cls)
        factor = _STATUS_SCALE[lineup_cls]
        print(f"  [scale] applied {factor:.2f}x scaling for '{lineup_cls}' classification:")
        for stat in STATS:
            if stat in stat_preds and stat in scaled:
                print(f"    {stat.upper():4s} {stat_preds[stat]:>6.2f} -> {scaled[stat]:>6.2f}")
        stat_preds = scaled

    if args.save is not None and stat_preds:
        # Schema mirrors predict_slate so single-player + slate runs append to
        # the same daily ledger; backtest harness can join on (date, player_id, stat).
        out = (os.path.join(PROJECT_DIR, "data", "predictions",
                            f"{_date.today().isoformat()}.csv")
               if args.save == "__default__" else args.save)
        n = append_predictions_csv(
            out, pid, name, args.opp, is_home, stat_preds,
            lineup_status=ctx_lineup_status,
            lineup_class=(lineup_cls if args.lineups is not None else ""),
            play_pct=ctx_play_pct,
            injury_status=ctx_injury_status,
        )
        print(f"  Wrote {n} prediction rows → {out}")


if __name__ == "__main__":
    main()
