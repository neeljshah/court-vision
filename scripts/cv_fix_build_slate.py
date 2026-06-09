"""
cv_fix_build_slate.py — build data/predictions/slate_<date>.csv for a slate so the
CourtVision /tonight page serves REAL model bets (not the synthesized fallback).

For each NBA game on the date (from games_lookup.json, nba_stats_official entries):
  * derive home_abbr / away_abbr / nba gid
  * pull each rostered player's q50 projection from predictions_cache_<date>.parquet
    (matchup-agnostic; team col set from each player's latest game)
  * set venue (home/away) + opp, write the slate row schema the router expects.

If predictions_cache_<date>.parquet is missing, build it first via build_prediction_cache
(matchup-agnostic, ~all active players). If games_lookup lacks the date's games, fetch
them from NBA ScoreboardV2 and add nba_stats_official entries.

Usage:
    python scripts/cv_fix_build_slate.py --date 2026-05-30
    python scripts/cv_fix_build_slate.py --date 2026-05-30 --gid 0042500317
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
LOOKUP = os.path.join(ROOT, "data", "cache", "games_lookup.json")
PRED_DIR = os.path.join(ROOT, "data", "predictions")
CACHE_DIR = os.path.join(ROOT, "data", "cache")
STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _slate_game_id(gid):
    """Game id written to the slate CSV consumed by the live /tonight regrade.

    Default (CV_SLATE_PAD_GAMEID unset/OFF) = the LEGACY ``int(gid)`` which STRIPS the
    leading zeros of the 10-digit NBA id ('0042500317' -> 42500317). That strip silently
    disables the live in-game regrade on /tonight: the router's snapshot/alias lookups are
    keyed by the zero-padded id, so the int form never matches and the page keeps showing
    STALE pregame projections during live games (HARDENING_PUNCHLIST_SWEEP3_2026-06-02.md #0).

    With CV_SLATE_PAD_GAMEID ON the zero-padded id is preserved (numeric NBA ids only;
    non-numeric KAMBI/hex keys pass through unchanged). Default OFF is byte-identical to the
    legacy behavior. Flipping it ON is a real-money live-page behavior change (it RESTORES the
    regrade) -> RECOMMEND: flip ON and rebuild the slate; verify the slate game_id == the
    padded id and that /tonight applies a live regrade against data/live/<padded>_*.json.
    """
    if os.environ.get("CV_SLATE_PAD_GAMEID", "").strip().lower() in ("1", "true", "yes", "on"):
        return str(gid).zfill(10) if str(gid).isdigit() else str(gid)
    return int(gid)  # legacy default (byte-identical) — strips leading zeros


def _et_date_of_start(start_time: str) -> str:
    """NBA evening tip stored as next-UTC-day (e.g. 2026-05-31T00:10Z) belongs to the
    prior ET date (2026-05-30). Approximate ET as UTC-4/5: subtract a day if hour < 6Z."""
    try:
        import datetime as dt
        t = dt.datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ")
        if t.hour < 6:
            t = t - dt.timedelta(days=1)
        return t.strftime("%Y-%m-%d")
    except Exception:
        return start_time[:10]


def _ensure_games_lookup(date: str) -> None:
    """If games_lookup has no NBA game for `date`, fetch the slate from NBA
    ScoreboardV2 and add nba_stats_official entries. Fully guarded — never raises."""
    try:
        lookup = json.load(open(LOOKUP, encoding="utf-8"))
        have = any(i.get("_source") == "nba_stats_official" and i.get("home_abbr")
                   and _et_date_of_start(i.get("start_time", "")) == date
                   for i in lookup.values())
        if have:
            return
        from src.data import nba_api_headers_patch  # noqa: F401
        from nba_api.stats.endpoints import scoreboardv2
        from nba_api.stats.static import teams as _teams
        id2abbr = {t["id"]: t["abbreviation"] for t in _teams.get_teams()}
        sb = scoreboardv2.ScoreboardV2(game_date=date, timeout=45)
        gh = sb.game_header.get_data_frame()
        added = 0
        for _, r in gh.iterrows():
            gid = str(r["GAME_ID"])
            home = id2abbr.get(int(r["HOME_TEAM_ID"]), "")
            away = id2abbr.get(int(r["VISITOR_TEAM_ID"]), "")
            est = str(r.get("GAME_DATE_EST", ""))[:10] or date
            if not (home and away) or gid in lookup:
                continue
            import datetime as _dt
            try:
                utc_day = (_dt.datetime.strptime(est, "%Y-%m-%d") + _dt.timedelta(days=1)).strftime("%Y-%m-%d")
            except Exception:
                utc_day = est
            lookup[gid] = {
                "home_abbr": home, "away_abbr": away,
                "start_time": f"{utc_day}T00:10:00Z",  # placeholder ET-evening tip (UTC next day)
                "label": f"{away} @ {home}", "_source": "nba_stats_official",
            }
            added += 1
        if added:
            json.dump(lookup, open(LOOKUP, "w", encoding="utf-8"), indent=1)
            print(f"[build_slate] auto-added {added} NBA game(s) to games_lookup from ScoreboardV2")
    except Exception as e:
        print(f"[build_slate] games_lookup auto-populate skipped ({e!r})")


def _games_for_date(date: str, gid_filter: str | None):
    _ensure_games_lookup(date)
    lookup = json.load(open(LOOKUP, encoding="utf-8"))
    games = {}
    for gid, info in lookup.items():
        if info.get("_source") != "nba_stats_official":
            continue
        if not (info.get("home_abbr") and info.get("away_abbr")):
            continue
        st = info.get("start_time", "")
        if _et_date_of_start(st) != date:
            continue
        if gid_filter and gid != gid_filter:
            continue
        games[gid] = info
    return games


def _norm(name: str) -> str:
    return " ".join(str(name or "").lower().replace(".", "").replace("'", "").split())


def out_players(date: str) -> set:
    """OUT players for a date = scraped injury feed (OUT/DOUBTFUL/NOT WITH TEAM)
    UNION the canonical OUT override file (data/cache/cv_fix/live_out_<date>.json).

    Single canonical file: live_out_<date>.json is the ONE override file read by
    all consumers — golive slate builder (here), live router (courtvision_router.py),
    and the CV_INGAME_RETURN path.  The legacy manual_out_<date>.json is kept as a
    read-only fallback so old files are not silently dropped; new operators MUST
    write to live_out_<date>.json only.
    Returns normalized names."""
    out = set()
    # 1. scraped feed
    pq = os.path.join(CACHE_DIR, f"nba_injuries_{date}.parquet")
    if os.path.exists(pq):
        try:
            import pandas as pd
            df = pd.read_parquet(pq)
            bad = {"OUT", "DOUBTFUL", "NOT WITH TEAM"}
            for _, r in df.iterrows():
                if str(r.get("status", "")).upper() in bad:
                    out.add(_norm(r.get("player_name")))
        except Exception as e:
            print(f"[build_slate] injury parquet read failed: {e!r}")
    # 2. canonical override (live_out_<date>.json — single file for all consumers)
    live_out = os.path.join(ROOT, "data", "cache", "cv_fix", f"live_out_{date}.json")
    if os.path.exists(live_out):
        try:
            for nm in json.load(open(live_out, encoding="utf-8-sig")):
                out.add(_norm(nm))
        except Exception as e:
            print(f"[build_slate] live_out read failed: {e!r}")
    else:
        # Legacy fallback: read manual_out_<date>.json if live_out not yet created
        # (e.g. golive.ps1 hasn't run on this date yet, or an old file exists).
        man = os.path.join(ROOT, "data", "cache", "cv_fix", f"manual_out_{date}.json")
        if os.path.exists(man):
            try:
                for nm in json.load(open(man, encoding="utf-8")):
                    out.add(_norm(nm))
            except Exception as e:
                print(f"[build_slate] manual_out (legacy fallback) read failed: {e!r}")
    return out


# CV_VAC_BUMP_GATED (VAC_BUMP_ACCURACY_VALIDATION.md): the FLAT vac bump HURTS
# served MAE (+0.57%); it only HELPS at HIGH vacated-load share (PTS/REB ~3-4%).
# When ON, the bump fires ONLY for vac_share >= _VAC_SHARE_GATE and ONLY on the
# validated stats {pts, reb} (AST's coefficient is mis-tuned). Default OFF.
_VAC_SHARE_GATE: float = 0.60
_VAC_GATED_STATS = frozenset({"pts", "reb"})


def _vac_bump_gated() -> bool:
    return (os.environ.get("CV_VAC_BUMP_GATED", "").strip().lower()
            not in ("", "0", "false", "no", "off"))


def _vac_bump_enabled() -> bool:
    """True iff CV_SLATE_VAC_BUMP is set truthy (default OFF = byte-identical)."""
    return os.environ.get("CV_SLATE_VAC_BUMP", "").strip().lower() in (
        "1", "true", "yes", "on", "y", "t")


def _haircut_enabled() -> bool:
    """True iff CV_SLATE_HAIRCUT is set truthy (default OFF = byte-identical).

    When ON: apply the OOF-consistent garbage-time haircut to PTS/REB/AST in
    the slate path so served predictions match the validated OOF behaviour.
    This is a pure correctness fix (53% of games have |spread|>=6; avg ~4.18%
    over-prediction without it).  Default OFF preserves byte-identical behaviour.

    DOUBLE-COUNT NOTE: when BOTH CV_SLATE_HAIRCUT and CV_SLATE_VAC_BUMP are ON,
    the live_adjustment blowout term (fires at |spread|>12, k=-0.0035) would
    also apply, causing double-haircut on extreme blowouts.  The haircut is the
    OOF-consistent term (bins 6/10/14, factors 0.98/0.95/0.92) and is the
    primary blowout correction.  _apply_vac_bump() therefore passes
    game_spread=None to adjust_projection when this flag is ON, zeroing the
    live_adjustment blowout term and preventing double-counting.  Pace (total)
    and vacated-load terms in live_adjustment are unaffected.
    """
    return os.environ.get("CV_SLATE_HAIRCUT", "").strip().lower() in (
        "1", "true", "yes", "on", "y", "t")


def _load_spread_for_game(date: str, home: str, away: str) -> "float | None":
    """Return |home_spread| for the game, or None if unavailable.

    Priority:
      1. data/pregame_spreads.parquet — the OOF-consistent source (same source
         used by predict_pergame's _get_pregame_spreads; best coverage for the
         current season).
      2. Tonight's mainline file (data/lines/<date>_*_mainline.csv, loaded via
         live_context.load_mainline) — used when pregame_spreads lacks coverage
         for today (e.g. spreads parquet not yet refreshed for tonight's games).

    Returns the absolute spread magnitude (|home_spread|) so that
    apply_garbage_time_haircut's abs() call inside the function
    is a no-op duplicate; passing this value as ``home_spread`` is fine
    because apply_garbage_time_haircut only uses abs() internally.

    Never raises — returns None on any failure so the haircut is a graceful
    no-op for games without line data.
    """
    # ── 1. pregame_spreads.parquet (OOF-consistent source) ───────────────────
    try:
        from src.prediction.prop_pergame import _get_pregame_spreads  # noqa: PLC0415
        import datetime as _dt  # noqa: PLC0415
        sp = _get_pregame_spreads()
        try:
            gdate = _dt.datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            gdate = _dt.datetime.now()
        rec = sp.features(home, away, gdate)
        hs = rec.get("home_spread")
        if hs is not None:
            return abs(float(hs))
    except Exception:
        pass

    # ── 2. Tonight's mainline fallback (live_context) ────────────────────────
    try:
        from src.prediction.live_context import load_mainline as _lm  # noqa: PLC0415
        mainline = _lm(date)
        if mainline:
            key = frozenset([home.upper(), away.upper()])
            if key in mainline:
                sa = mainline[key].get("spread_abs")
                if sa is not None:
                    return float(sa)
            # Also try loose match (live_context may use different abbrevs)
            for k, v in mainline.items():
                if home.upper() in k or away.upper() in k:
                    sa = v.get("spread_abs")
                    if sa is not None:
                        return float(sa)
    except Exception:
        pass

    return None


def _apply_slate_haircut(cache, games: dict, date: str) -> int:
    """CV_SLATE_HAIRCUT (default OFF = byte-identical).

    Applies apply_garbage_time_haircut to PTS/REB/AST q50/q10/q90/sigma for
    every player in the cache, using the REAL game spread from pregame_spreads
    (or mainline fallback).  Matches the behaviour in predict_pergame (the OOF
    path) so served predictions on the webpage equal the validated OOF values.

    home_spread convention: apply_garbage_time_haircut uses abs() internally,
    so passing spread_abs (unsigned) is equivalent to passing the signed spread.
    The function is a no-op for |spread|<6, non-volume stats, and None spreads.

    Returns n_rows_haircutted (players whose q50 changed; 0 when flag is OFF or
    no blowout games today).

    DOUBLE-COUNT PROTECTION: when CV_SLATE_HAIRCUT is ON, _apply_vac_bump()
    passes game_spread=None to live_adjustment.adjust_projection so that the
    live_adjustment blowout term (slack=12, k=-0.0035) is suppressed.  Only the
    OOF-consistent haircut applies.  Pace and vac-load terms are unaffected.
    """
    if not _haircut_enabled():
        return 0
    try:
        from src.prediction.prop_pergame import apply_garbage_time_haircut as _hc  # noqa: PLC0415
        import pandas as _pd  # noqa: PLC0415
    except Exception:
        return 0

    # Build {team: spread_abs} for tonight's games
    team_spread: dict = {}
    for gid, info in games.items():
        home, away = info["home_abbr"], info["away_abbr"]
        sa = _load_spread_for_game(date, home, away)
        if sa is not None:
            team_spread[home] = sa
            team_spread[away] = sa

    if not team_spread:
        return 0  # no spreads available tonight -> graceful no-op

    n_haircutted = 0
    for idx in cache.index:
        team = str(cache.at[idx, "team"]).upper()
        sa = team_spread.get(team)
        if sa is None:
            continue  # no spread for this team's game -> no-op
        stat = str(cache.at[idx, "stat"]).lower()
        q50 = float(cache.at[idx, "q50"])
        if q50 == 0:
            continue
        # apply_garbage_time_haircut(pred, stat, home_spread):
        # it calls abs(home_spread) internally so passing spread_abs is correct.
        new_q50 = _hc(q50, stat, sa)
        if abs(new_q50 - q50) < 1e-9:
            continue  # haircut was a no-op (stat not in PTS/REB/AST, or |spread|<6)
        ratio = new_q50 / q50
        cache.at[idx, "q50"] = round(new_q50, 3)
        for qcol in ("q10", "q90", "sigma"):
            if qcol in cache.columns and _pd.notna(cache.at[idx, qcol]):
                cache.at[idx, qcol] = round(float(cache.at[idx, qcol]) * ratio, 3)
        n_haircutted += 1
    return n_haircutted


def _make_pid_resolver(cache):
    """Return resolve_pid(name)->Optional[int], offline-safe.

    Prefers the prediction cache's own player_name->player_id map (no network); falls
    back to the nba_api static roster only when a name isn't in the cache. Accent- and
    punctuation-insensitive to match the injury feed's spelling against cache names.
    """
    def _key(s: str) -> str:
        import unicodedata as _ud
        base = str(s or "").strip().lower().replace(".", "").replace("'", "")
        base = _ud.normalize("NFKD", base).encode("ascii", "ignore").decode()
        return " ".join(base.split())

    name2pid = {}
    try:
        for nm, pid in zip(cache["player_name"], cache["player_id"]):
            k = _key(nm)
            if k and k not in name2pid:
                name2pid[k] = int(pid)
    except Exception:
        pass

    def _resolve(name):
        k = _key(name)
        if k in name2pid:
            return name2pid[k]
        try:
            from nba_api.stats.static import players as _pl  # noqa: PLC0415
            for p in _pl.get_players():
                if _key(p["full_name"]) == k:
                    return int(p["id"])
        except Exception:
            return None
        return None

    return _resolve


def _build_vac_map(date: str, cache):
    """{TEAM: {vac_min, vac_pts, n_out}} for tonight's confirmed-OUT regulars.

    Uses the SAME validated availability layer the CLI path (compare_to_lines.py)
    feeds into live_adjustment — src/prediction/availability.team_vacated_map. The
    #1 plumbing gap is that the webpage q50 never sees who's OUT, so a player whose
    creator/teammate sits gets NO vacated-load bump (the one lever that beats closes,
    see MEMORY vac_load/vac_ast + docs/VS_VEGAS_ASSESSMENT.md §3). Reads the official
    injury feed (data/injuries_<date>.json) -> empty/zeros when the feed is stale or
    missing (today's feed is stale @ 2026-05-31 — un-stale it for live use). Never raises.
    """
    try:
        from src.prediction import availability as _avail  # noqa: PLC0415
    except Exception:
        return {}, None
    try:
        return _avail.team_vacated_map(date, _make_pid_resolver(cache)), _avail
    except Exception:
        return {}, None


def _live_context_for_teams(date: str, teams: "list[str]") -> "dict[str, dict]":
    """Return {team_abbrev: {total, spread_abs}} from tonight's mainline (pin>dk>fd>bov).

    Reads data/lines/<date>_<book>_mainline.csv via live_context.context_for_team.
    Returns empty dict on any failure (best-effort; no-op when lines absent).
    Uses CV_LIVE_CONTEXT flag (default ON when CV_SLATE_VAC_BUMP is ON — the pace/
    blowout terms are only activated if the mainline file exists for tonight).
    """
    if not _vac_bump_enabled():
        return {}
    try:
        from src.prediction.live_context import load_mainline as _lm  # noqa: PLC0415
    except Exception:
        return {}
    try:
        mainline = _lm(date)
    except Exception:
        return {}
    if not mainline:
        return {}
    # Build team -> {total, spread_abs} by scanning every game key
    out: dict = {}
    for key, rec in mainline.items():
        for t in key:
            out[t] = rec
    # Only return entries for teams we actually have players for
    return {t: out[t] for t in teams if t in out}


def _apply_vac_bump(cache, date: str):
    """Mutate the prediction cache in place: bump each ACTIVE player's q50/q10/q90
    using the complete freshness path:
      (1) vacated-load from tonight's confirmed OUTs (availability -> injuries_<date>.json)
      (2) pace from tonight's live game total (live_context -> pin_mainline.csv)
      (3) blowout haircut from tonight's live spread magnitude

    Safety: availability.out_players_by_team() has a date-field freshness guard ->
    if injuries_<date>.json is missing OR its "date" field != date, vac_map = {} -> no-op.
    When CV_SLATE_VAC_BUMP is OFF this is a strict byte-identical no-op.

    After bumping, writes the modified cache back to predictions_cache_<date>.parquet
    so _predictions_overlay (which reads the cache directly) also sees the bumped q50
    on its next TTL cycle. This fixes the Gap G plumbing hole.

    Returns n_bumped (players whose q50 changed).
    """
    if not _vac_bump_enabled():
        return 0
    vac_map, _avail = _build_vac_map(date, cache)
    # vac_map may be empty (feed missing/stale) — that's the safety no-op path;
    # we still apply pace/blowout if mainline exists.
    try:
        from src.prediction import live_adjustment as _la  # noqa: PLC0415
    except Exception:
        return 0
    import pandas as pd  # noqa: PLC0415

    # Build per-game live context (total + spread_abs) for pace/blowout terms.
    all_teams = [str(t) for t in cache["team"].dropna().unique()]
    live_ctx = _live_context_for_teams(date, all_teams)

    # If neither vac_map nor live_ctx has anything, skip entirely.
    if not vac_map and not live_ctx:
        return 0

    # Per-player L10 PTS (from the player's PTS q50 row) drives vac_share.
    pts_by_pid = {int(r["player_id"]): float(r["q50"])
                  for _, r in cache[cache["stat"] == "pts"].iterrows()}
    n_bumped = 0
    for pid in cache["player_id"].unique():
        pid = int(pid)
        team = (cache.loc[cache["player_id"] == pid, "team"].iloc[0]
                if (cache["player_id"] == pid).any() else None)
        team_upper = (team or "").upper()

        # Vacated-load share (zero if feed stale/missing — safety guard in availability)
        share = 0.0
        if vac_map and _avail is not None and team_upper in vac_map:
            vac = _avail.player_vacated(pts_by_pid.get(pid, 0.0), team, vac_map)
            share = float(vac.get("vac_share") or 0.0)

        # Live pace/blowout context (None if mainline absent)
        ctx = live_ctx.get(team_upper, {}) if live_ctx else {}
        game_total = ctx.get("total")       # e.g. 228.5
        game_spread = ctx.get("spread_abs") # e.g. 7.5

        # DOUBLE-COUNT PROTECTION: when CV_SLATE_HAIRCUT is ON, the OOF-consistent
        # garbage-time haircut (bins 6/10/14, factors 0.98/0.95/0.92) is applied
        # separately in _apply_slate_haircut().  The live_adjustment blowout term
        # (slack=12, k=-0.0035) would double-haircut extreme blowout games
        # (|spread|>12), so we suppress it here by passing game_spread=None to
        # adjust_projection.  Pace (game_total) and vacated-load (share) are
        # unaffected — only the blowout component is zeroed.
        if _haircut_enabled():
            game_spread = None  # blowout handled by _apply_slate_haircut, not here

        # Skip if no adjustment applies
        if share <= 0.0 and game_total is None and game_spread is None:
            continue

        pmask = cache["player_id"] == pid
        base = {str(s).lower(): float(q)
                for s, q in zip(cache.loc[pmask, "stat"], cache.loc[pmask, "q50"])}
        # CV_VAC_BUMP_GATED: restrict the vacated-load bump to the validated
        # high-share PTS/REB regime (the flat bump hurts MAE; see helper above).
        # Pace/blowout terms are unaffected (vac_stats/vac_min_share gate only vac).
        if _vac_bump_gated():
            adj = _la.adjust_projection(
                base, vac_share=share, game_total=game_total, game_spread=game_spread,
                vac_min_share=_VAC_SHARE_GATE, vac_stats=_VAC_GATED_STATS,
            )
        else:
            adj = _la.adjust_projection(
                base, vac_share=share, game_total=game_total, game_spread=game_spread
            )
        bumped = False
        for idx in cache.index[pmask]:
            st = str(cache.at[idx, "stat"]).lower()
            q0 = float(cache.at[idx, "q50"])
            qn = float(adj.get(st, q0))
            if abs(qn - q0) < 1e-9 or q0 == 0:
                continue
            ratio = qn / q0
            cache.at[idx, "q50"] = round(qn, 3)
            for qc in ("q10", "q90", "sigma"):
                if qc in cache.columns and pd.notna(cache.at[idx, qc]):
                    cache.at[idx, qc] = round(float(cache.at[idx, qc]) * ratio, 3)
            bumped = True
        if bumped:
            n_bumped += 1
    return n_bumped


def _ensure_cache(date: str) -> str:
    path = os.path.join(CACHE_DIR, f"predictions_cache_{date}.parquet")
    if os.path.exists(path):
        return path
    print(f"[build_slate] predictions_cache_{date}.parquet missing — building (this can take a while)...")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_prediction_cache.py"),
                    "--season", "2025-26", "--out", path], cwd=ROOT, env=env, check=False)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--gid", default=None, help="restrict to one NBA game_id")
    ap.add_argument(
        "--ensure-lookup-only", action="store_true",
        help=(
            "G-008: pre-seed games_lookup.json for DATE via ScoreboardV2 and exit "
            "immediately without building the slate CSV. Run this WITH network access "
            "BEFORE setting NBA_OFFLINE=1 (e.g. from a nightly scheduler or the "
            "first step of go-live). If the lookup already has an nba_stats_official "
            "entry for DATE, this is a fast no-op. Never raises."
        ),
    )
    args = ap.parse_args()
    # G-008: --ensure-lookup-only pre-seeds games_lookup.json and exits.
    # Used by golive.ps1 before NBA_OFFLINE=1 is set, and by any nightly scheduler
    # that wants to warm the lookup ahead of offline game-night operations.
    if args.ensure_lookup_only:
        _ensure_games_lookup(args.date)
        return
    import pandas as pd

    games = _games_for_date(args.date, args.gid)
    if not games:
        print(f"[build_slate] no nba_stats_official games in games_lookup for {args.date}. "
              f"Add the game (home/away/start_time/_source=nba_stats_official) and retry.")
        sys.exit(1)
    print(f"[build_slate] {len(games)} game(s) for {args.date}: "
          + ", ".join(f"{g['away_abbr']}@{g['home_abbr']}" for g in games.values()))

    cache_path = _ensure_cache(args.date)
    if not os.path.exists(cache_path):
        print(f"[build_slate] cache build failed: {cache_path}"); sys.exit(2)
    cache = pd.read_parquet(cache_path)

    # ── Injury exclusion: drop OUT players from BOTH the box-score cache and the
    # bets so the page never shows inactive players (e.g. Jalen Williams / Aaron
    # Wiggins). Feed + manual override; rewrite the cache so /api/box_score (which
    # reads the parquet) is corrected too.
    out_set = out_players(args.date)
    if out_set:
        before = cache["player_name"].nunique()
        cache["_norm"] = cache["player_name"].map(_norm)
        slate_teams = set()
        for info in games.values():
            slate_teams.update([info["home_abbr"], info["away_abbr"]])
        # ── Redistribute OUT players' usage to active teammates (conserve ~90% of
        # the team total per stat, proportional to each active's projection; cap a
        # single player's boost at 1.4x). Without this, deleting a starter tanks the
        # team total + win prob unrealistically (market prices the redistribution).
        REDIST, CAP = 0.90, 1.40
        for team in slate_teams:
            for stat in STATS:
                tmask = (cache["team"] == team) & (cache["stat"] == stat)
                tm = cache[tmask]
                if tm.empty:
                    continue
                omask = tm["_norm"].isin(out_set)
                removed = float(tm.loc[omask, "q50"].clip(lower=0).sum()) * REDIST
                act = tm[~omask]
                denom = float(act["q50"].clip(lower=0).sum())
                if removed <= 0 or denom <= 0:
                    continue
                for idx in act.index:
                    q = float(cache.at[idx, "q50"])
                    add = removed * (max(0.0, q) / denom)
                    newq = min(q + add, q * CAP if q > 0 else add)
                    ratio = (newq / q) if q > 0 else 1.0
                    cache.at[idx, "q50"] = round(newq, 3)
                    for qc in ("q10", "q90", "sigma"):
                        if qc in cache.columns and pd.notna(cache.at[idx, qc]):
                            cache.at[idx, qc] = round(float(cache.at[idx, qc]) * ratio, 3)
        mask_out = cache["_norm"].isin(out_set)
        dropped = sorted(cache.loc[mask_out, "player_name"].unique())
        cache = cache[~mask_out].drop(columns=["_norm"])
        cache.to_parquet(cache_path, index=False)
        print(f"[build_slate] injury filter: dropped {len(dropped)} OUT, redistributed usage "
              f"({before}->{cache['player_name'].nunique()} players): {dropped}")

    # ── CV_SLATE_VAC_BUMP (default OFF = byte-identical) ──────────────────────
    # Apply the complete freshness path (vacated-load + pace/blowout) to ACTIVE
    # players' q50 so the webpage reflects who is OUT + tonight's pace context.
    # Safety: availability has a date-field guard -> stale/missing feed = no-op.
    # After bumping, write the cache back to predictions_cache_<date>.parquet so
    # _predictions_overlay (Gap G fix) also picks up the bumped q50 on its next
    # TTL cycle (60s). Strict no-op when the flag is OFF.
    try:
        _n_vac = _apply_vac_bump(cache, args.date)
        if _n_vac:
            print(f"[build_slate] CV_SLATE_VAC_BUMP: applied freshness bump to "
                  f"{_n_vac} active player(s) (vac-load+pace+blowout)")
            # Gap G fix: write bumped cache back so _predictions_overlay sees updated q50.
            # Atomic write: tmp file + rename so the API never reads a partial write.
            import tempfile as _tf
            _tmp_fd, _tmp_path = _tf.mkstemp(
                prefix=".", suffix=".parquet", dir=os.path.dirname(cache_path))
            os.close(_tmp_fd)
            try:
                cache.to_parquet(_tmp_path, index=False)
                os.replace(_tmp_path, cache_path)
                print(f"[build_slate] CV_SLATE_VAC_BUMP: wrote bumped cache -> {cache_path}")
            except Exception as _we:
                print(f"[build_slate] cache writeback failed ({_we!r}) — overlay may lag one TTL")
                try:
                    os.unlink(_tmp_path)
                except OSError:
                    pass
    except Exception as _vexc:
        print(f"[build_slate] vac-bump skipped ({_vexc!r})")

    # ── CV_SLATE_HAIRCUT (default OFF = byte-identical) ───────────────────────
    # Apply the OOF-consistent garbage-time haircut to PTS/REB/AST in the slate
    # path so served predictions match the validated OOF behaviour.
    #
    # Without this, the cache is built with opp_team="OPP" -> home_spread=None
    # -> haircut is a no-op -> served PTS/REB/AST are 2-8% too HIGH on
    # blowout-expected games (53% of games have |spread|>=6, avg ~4.18% bias).
    # OOF was validated WITH the haircut (predict_pergame applies it when spread
    # is known); served was validated WITHOUT it.  This restores consistency.
    #
    # DOUBLE-COUNT: when CV_SLATE_VAC_BUMP is also ON, the live_adjustment
    # blowout term is suppressed in _apply_vac_bump (game_spread=None passed to
    # adjust_projection) so only the OOF-consistent haircut applies.
    try:
        _n_hc = _apply_slate_haircut(cache, games, args.date)
        if _n_hc:
            print(f"[build_slate] CV_SLATE_HAIRCUT: applied garbage-time haircut to "
                  f"{_n_hc} row(s) (PTS/REB/AST on |spread|>=6 games)")
            # Gap-G (overlay-bypass) fix: _predictions_overlay reads the
            # predictions_cache parquet DIRECTLY (api/_predictions_overlay.py
            # -> _build_home_data overlay), bypassing the slate CSV. Without
            # writing the haircut back, the /api/home model_projection / edge /
            # rec served the UN-haircut q50 while /tonight + /api/slate served
            # the haircut q50 — an internal divergence (~8% on |spread|>=14
            # blowouts: Brunson PTS 25.71 cache vs 23.65 slate). Mirror the
            # CV_SLATE_VAC_BUMP writeback above (atomic tmp+rename) so BOTH
            # surfaces serve the same validated (haircut-applied) value on its
            # next overlay TTL cycle (60s). Strictly gated: only reached when
            # _n_hc>0, which only happens with CV_SLATE_HAIRCUT ON AND a real
            # blowout spread — so flag OFF stays byte-identical (no writeback).
            import tempfile as _tf2
            _tmp_fd2, _tmp_path2 = _tf2.mkstemp(
                prefix=".", suffix=".parquet", dir=os.path.dirname(cache_path))
            os.close(_tmp_fd2)
            try:
                cache.to_parquet(_tmp_path2, index=False)
                os.replace(_tmp_path2, cache_path)
                print(f"[build_slate] CV_SLATE_HAIRCUT: wrote haircut cache -> {cache_path} "
                      f"(overlay Gap-G fix)")
            except Exception as _we2:
                print(f"[build_slate] haircut cache writeback failed ({_we2!r}) "
                      f"— /api/home overlay may serve un-haircut q50")
                try:
                    os.unlink(_tmp_path2)
                except OSError:
                    pass
        elif _haircut_enabled():
            print("[build_slate] CV_SLATE_HAIRCUT: ON but no spread data found "
                  "— haircut is a no-op (check pregame_spreads.parquet or mainline CSV)")
    except Exception as _hcexc:
        print(f"[build_slate] slate-haircut skipped ({_hcexc!r})")

    rows = []
    for gid, info in games.items():
        home, away = info["home_abbr"], info["away_abbr"]
        gid_out = _slate_game_id(gid)
        sub = cache[cache["team"].isin([home, away])]
        if sub.empty:
            print(f"[build_slate] WARN: cache has no players for {away}@{home} "
                  f"(teams in cache: {sorted(cache['team'].unique())[:6]}...)")
            continue
        for _, r in sub.iterrows():
            team = r["team"]
            row = {
                "date": args.date, "game_id": gid_out, "player_id": int(r["player_id"]),
                "player": r["player_name"], "team": team,
                "opp": away if team == home else home,
                "venue": "home" if team == home else "away",
                "stat": r["stat"], "pred": round(float(r["q50"]), 2),
                "lineup_status": "", "lineup_class": "", "play_pct": "", "injury_status": "",
            }
            # Plumb raw q10/q90 so grade_bet can use per-row heteroscedastic sigma
            # (CV_ROW_SIGMA flag). These columns come from predictions_cache which
            # stores RAW (pre-calibration) quantile bounds.
            for qcol in ("q10", "q90"):
                if qcol in r.index and pd.notna(r[qcol]):
                    row[qcol] = round(float(r[qcol]), 3)
                else:
                    row[qcol] = ""
            rows.append(row)
    if not rows:
        print("[build_slate] no rows produced — cache/team mismatch."); sys.exit(3)

    out = pd.DataFrame(rows)
    os.makedirs(PRED_DIR, exist_ok=True)
    out_path = os.path.join(PRED_DIR, f"slate_{args.date}.csv")
    out.to_csv(out_path, index=False)
    print(f"[build_slate] wrote {out_path}: {len(out)} rows, "
          f"{out.player.nunique()} players, teams {sorted(out.team.unique())}")


if __name__ == "__main__":
    main()
