"""scripts.platformkit.ingame.ingame_gumbo_mlb -- MLB GUMBO live-state extractor (LANE 2).

STANDALONE module: given a GUMBO payload (bootstrap `feed/live` snapshot, OR a payload
already produced by applying a diffPatch batch), emit one compact live-state tick:
    {game_pk, ts, inning, half, outs, balls, strikes, base_state, base_label,
     score_home, score_away, batter_id, pitcher_id, pitcher_pitches, pitch_velo_last}

VERIFIED-LIVE GROUND TRUTH (2026-07-04, gamePk 824417, White Sox @ Guardians, In Progress,
probed directly against statsapi.mlb.com):

(a) FULLUPDATE TRAP IS THE OBSERVED NORM. `GET .../feed/live/diffPatch?startTimecode=<ts>`
    was probed 3 ways (near-identical ts echo-back, 5-min-old ts, mid-game logical events)
    and EVERY response was a full GUMBO dict (gamePk/link/metaData/gameData/liveData),
    never an RFC6902 `{diff:[...]}` list, with metaData.logicalEvents describing the change
    (observed: ['fullUpdate'], ['newBatter', 'batterSwitchedToRightHanded']). This module
    handles BOTH shapes: a dict with 'liveData' -> full snapshot (extract directly); a list
    of patch docs -> apply RFC6902 ops against the last known full state (apply_patch), with
    fallback to a full re-fetch if any doc carries a 'fullUpdate' logicalEvent or patching
    fails. Never assume list-of-patches is the only shape.

(b) FIELDING-POSITION TRAP CONFIRMED LIVE. `linescore.defense.first/second/third` are the
    DEFENSE's fielders (e.g. defense.first = Jacob Gonzalez, Chicago's 1B) -- NEVER base
    runners. Baserunners are `linescore.offense.first/second/third` (offense.first = Rhys
    Hoskins, on base for Cleveland) OR `plays.currentPlay.matchup.postOnFirst/Second/Third`
    (person dict when occupied, None when empty) -- VERIFIED postOnFirst == offense.first
    for the same runner. Primary source: matchup.postOn*; fallback: linescore.offense.*.
    defense.* is NEVER read for base occupancy.

(c) NO WIN-PROBABILITY FIELD observed anywhere in GUMBO; this module emits none.

Leak-free / honest: reads only the CURRENT snapshot; returns {} when inning/half/outs are
unavailable; never raises; ASCII; no src/kernel/domains imports; no network here (pure
parsing) -- the poller module does the fetching.

WIRE SPEC (additive, future integration lane -- do NOT apply automatically): in
ingame_live_state.py's MLB branch, after the live-state dict is built, merge in
`gumbo_fields = extract_state(gumbo_payload); state_diff.update({k: v for k, v in
gumbo_fields.items() if k not in ("game_pk", "ts")})`. Additive-only (new keys), never
overwrites existing state_diff keys; requires a gamePk<->game_id join (game_pk_bridge.py
in domains/mlb/) which this lane does NOT attempt.

RFC6902 patch-apply / fullUpdate-fallback machinery lives in the sidecar
ingame_gumbo_mlb_patch.py (split out to keep this file under the LOC budget) and is
re-exported here for callers.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platformkit/ingame/test_ingame_gumbo_mlb.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from scripts.platformkit.ingame.ingame_gumbo_mlb_patch import (  # noqa: F401 (re-export)
    GumboDoc, apply_diffpatch_response, apply_patch, is_full_update)


def _int_or_none(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _occupied(person: Any) -> bool:
    return isinstance(person, dict) and bool(person.get("id"))


def _bases_dict(on1: bool, on2: bool, on3: bool) -> Dict[str, Any]:
    bs = (1 if on1 else 0) | (2 if on2 else 0) | (4 if on3 else 0)
    return {"on_first": on1, "on_second": on2, "on_third": on3, "base_state": bs}


def base_state_from_matchup(matchup: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Base occupancy from matchup.postOnFirst/Second/Third (the CURRENT at-bat's runner
    state) -- NEVER from linescore.defense.* (fielding positions, see trap (b))."""
    if not isinstance(matchup, dict):
        return None
    if not any(k in matchup for k in ("postOnFirst", "postOnSecond", "postOnThird")):
        return None
    return _bases_dict(_occupied(matchup.get("postOnFirst")),
                        _occupied(matchup.get("postOnSecond")),
                        _occupied(matchup.get("postOnThird")))


def base_state_from_offense(linescore: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fallback base occupancy: linescore.offense.first/second/third (the BATTING team's
    runners). linescore.DEFENSE.first/second/third are fielders and must never be read
    for base occupancy -- trap (b), confirmed live 2026-07-04."""
    offense = linescore.get("offense") if isinstance(linescore, dict) else None
    if not isinstance(offense, dict):
        return None
    return _bases_dict(_occupied(offense.get("first")),
                        _occupied(offense.get("second")),
                        _occupied(offense.get("third")))


def base_state_from_runners(runners: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Base occupancy purely from a currentPlay.runners[] movement list: a runner is
    occupying a base at 'end' of their most recent movement within this play IF
    movement.isOut is falsy and movement.end is one of '1B'/'2B'/'3B'. Used only when
    neither matchup.postOn* nor linescore.offense.* is available (e.g. a raw play-only
    fixture)."""
    on1 = on2 = on3 = False
    for r in runners if isinstance(runners, list) else []:
        mv = r.get("movement", {}) if isinstance(r, dict) else {}
        if not isinstance(mv, dict) or mv.get("isOut"):
            continue
        end = mv.get("end")
        on1 = on1 or end == "1B"
        on2 = on2 or end == "2B"
        on3 = on3 or end == "3B"
    return _bases_dict(on1, on2, on3)


_BASE_LABEL = {0: "---", 1: "1--", 2: "-2-", 3: "12-",
               4: "--3", 5: "1-3", 6: "-23", 7: "123"}


def extract_state(doc: GumboDoc) -> Dict[str, Any]:
    """Extract the compact live-state tick from a full GUMBO snapshot dict.

    Returns {} when inning/half/outs are unavailable (honest: no fabricated tick).
    """
    if not isinstance(doc, dict):
        return {}
    live = doc.get("liveData", {})
    linescore = live.get("linescore", {}) if isinstance(live, dict) else {}
    if not isinstance(linescore, dict) or not linescore:
        return {}

    inning = _int_or_none(linescore.get("currentInning"))
    half = linescore.get("inningState") or linescore.get("inningHalf")
    outs = _int_or_none(linescore.get("outs"))
    if inning is None or not half or outs is None:
        return {}

    plays = live.get("plays", {}) if isinstance(live, dict) else {}
    current_play = plays.get("currentPlay", {}) if isinstance(plays, dict) else {}
    matchup = current_play.get("matchup", {}) if isinstance(current_play, dict) else {}

    bases = base_state_from_matchup(matchup)
    if bases is None:
        bases = base_state_from_offense(linescore)
    if bases is None:
        bases = base_state_from_runners(current_play.get("runners", []))

    out: Dict[str, Any] = {
        "game_pk": doc.get("gamePk"),
        "ts": doc.get("metaData", {}).get("timeStamp") if isinstance(doc.get("metaData"), dict) else None,
        "inning": inning,
        "half": half,
        "outs": outs,
        "base_state": bases["base_state"],
        "base_label": _BASE_LABEL[bases["base_state"]],
        "on_first": bases["on_first"], "on_second": bases["on_second"], "on_third": bases["on_third"],
    }
    for k in ("balls", "strikes"):
        v = _int_or_none(linescore.get(k))
        if v is not None:
            out[k] = v

    teams_ls = linescore.get("teams", {}) if isinstance(linescore.get("teams"), dict) else {}
    for side, key in (("away", "score_away"), ("home", "score_home")):
        side_d = teams_ls.get(side)
        runs = side_d.get("runs") if isinstance(side_d, dict) else None
        if runs is not None:
            out[key] = _int_or_none(runs)

    batter = matchup.get("batter") if isinstance(matchup, dict) else None
    pitcher = matchup.get("pitcher") if isinstance(matchup, dict) else None
    if isinstance(batter, dict) and batter.get("id") is not None:
        out["batter_id"] = batter["id"]
    if isinstance(pitcher, dict) and pitcher.get("id") is not None:
        out["pitcher_id"] = pitcher["id"]

    pitcher_id = out.get("pitcher_id")
    if pitcher_id is not None:
        npitches = _pitcher_num_pitches(live, pitcher_id)
        if npitches is not None:
            out["pitcher_pitches"] = npitches

    velo = _last_pitch_velo(current_play)
    if velo is not None:
        out["pitch_velo_last"] = velo

    return out


def _pitcher_num_pitches(live: Dict[str, Any], pitcher_id: Any) -> Optional[int]:
    """boxscore.teams.{home,away}.players.ID<pitcher_id>.stats.pitching.numberOfPitches."""
    box = live.get("boxscore", {}) if isinstance(live, dict) else {}
    teams = box.get("teams", {}) if isinstance(box, dict) else {}
    key = "ID%s" % pitcher_id
    for side in ("home", "away"):
        players = teams.get(side, {}).get("players", {}) if isinstance(teams.get(side), dict) else {}
        p = players.get(key)
        if isinstance(p, dict):
            n = p.get("stats", {}).get("pitching", {}).get("numberOfPitches")
            iv = _int_or_none(n)
            if iv is not None:
                return iv
    return None


def _last_pitch_velo(current_play: Dict[str, Any]) -> Optional[float]:
    """Latest playEvents[].pitchData.startSpeed among isPitch events, most recent last."""
    if not isinstance(current_play, dict):
        return None
    events = current_play.get("playEvents", [])
    if not isinstance(events, list):
        return None
    for ev in reversed(events):
        if not isinstance(ev, dict) or not ev.get("isPitch"):
            continue
        pd = ev.get("pitchData", {})
        speed = pd.get("startSpeed") if isinstance(pd, dict) else None
        try:
            return float(speed)
        except (TypeError, ValueError):
            continue
    return None


__all__ = [
    "extract_state", "apply_patch", "apply_diffpatch_response", "is_full_update",
    "base_state_from_matchup", "base_state_from_offense", "base_state_from_runners",
    "GumboDoc",
]
