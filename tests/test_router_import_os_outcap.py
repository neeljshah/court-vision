"""tests/test_router_import_os_outcap.py — module-level `import os` fix.

BUG: api/courtvision_router.py had NO module-level `import os` — only
function-local *aliased* imports (`import os as _os_lsa`, etc.). Three bare
`os.environ.get(...)` references therefore raised NameError that the enclosing
`try/except: pass` swallowed:

  * L3988 — CV_SIGNAL_PANEL  (in `tonight`)
  * L5794 — CV_OUT_DETECT_HARDEN  (in `api_box_score` box-card builder)
  * L5805 — CV_INGAME_RETURN     (in `api_box_score` box-card builder)

Consequence: the box-card live-availability section (manual OUT cap, hardened
stagnation auto-detect, player-return logic) was ENTIRELY DEAD on the box-card
display path whenever those flags were set — and golive.ps1 sets
CV_OUT_DETECT_HARDEN=1 + CV_INGAME_RETURN=1. The fix adds one module-level
`import os` so the bare references resolve.

These tests assert:
  (1) `os` is now a module-level attribute of the router (the fix).
  (2) BYTE-IDENTICAL: flags OFF + empty out-list => the box-card availability
      block is a genuine no-op (output == untouched input).
  (3) ACTIVATED logic is correct with flags ON:
        (i)   manual out-list   -> paced_final caps to current, _out_flag
        (ii)  stagnation detect  -> flat-minutes-across-period-boundary auto-OUT
        (iii) player return      -> OUT cleared, 0.75 reduced-minutes anchor

The box-card availability block lives inside `api_box_score` and depends only on
the `box` dict, `live_overlay`, `date`, `game_id` and a handful of module
helpers — so we exercise the EXACT source slice (compiled verbatim from the
router) in a namespace seeded with the router's real globals. This runs the
identical production lines without spinning up the full FastAPI/ML app stack.
"""
from __future__ import annotations

import json
import os
import sys
import textwrap

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import api.courtvision_router as R  # noqa: E402

# Source-line span (1-indexed, inclusive) of the box-card live-availability
# try/except block inside api_box_score. Located by anchor strings rather than
# hardcoded numbers so the test survives small edits above the block.
_BLOCK_START_ANCHOR = "# (2) minutes-stagnation (a rotation player whose minutes are frozen"
_BLOCK_END_ANCHOR = '_row["_out_flag"] = True'


def _extract_block() -> "compile":
    src = open(R.__file__, encoding="utf-8").read().splitlines(keepends=True)
    # find the `try:` that opens the availability block (the line right after the
    # multi-line comment that ends with the anchor) and the `except: pass` after
    # the END anchor.
    start_idx = None
    for i, line in enumerate(src):
        if _BLOCK_START_ANCHOR in line:
            # walk forward to the opening `try:`
            for j in range(i, i + 12):
                if src[j].strip() == "try:":
                    start_idx = j
                    break
            break
    assert start_idx is not None, "could not locate box-card try: block"
    end_idx = None
    for i in range(start_idx, len(src)):
        if _BLOCK_END_ANCHOR in src[i]:
            # the matching `except Exception:` + `pass` follow within a few lines
            for j in range(i, i + 6):
                if src[j].strip() == "pass":
                    end_idx = j
                    break
            break
    assert end_idx is not None, "could not locate box-card except: pass"
    block = textwrap.dedent("".join(src[start_idx:end_idx + 1]))
    assert block.splitlines()[0].strip() == "try:"
    assert block.splitlines()[-1].strip() == "pass"
    return compile(block, "<box-card-availability-block>", "exec")


_BLOCK = _extract_block()


def _make_box(p_name="Hurt Star", mp=18.0):
    return {
        "home": {"abbr": "AAA", "players": [
            {"player_name": p_name, "minutes_played": mp,
             "current": {"pts": 12, "reb": 4, "ast": 3, "fg3m": 1,
                         "stl": 1, "blk": 0, "tov": 2},
             "paced_final": {"pts": 28.0, "reb": 9.0, "ast": 7.0, "fg3m": 2.0,
                             "stl": 2.0, "blk": 0.0, "tov": 4.0}},
            {"player_name": "Active Guy", "minutes_played": 22.0,
             "current": {"pts": 15, "reb": 6, "ast": 2, "fg3m": 2,
                         "stl": 0, "blk": 1, "tov": 1},
             "paced_final": {"pts": 30.0, "reb": 11.0, "ast": 4.0, "fg3m": 4.0,
                             "stl": 0.0, "blk": 2.0, "tov": 2.0}},
        ]},
        "away": {"abbr": "BBB", "players": []},
    }


_OVERLAY = {"period": 3, "clock": "6:00", "home_team": "AAA",
            "away_team": "BBB", "home_score": 60, "away_score": 55}


def _run_block(box, date, game_id, live_overlay):
    """Execute the verbatim box-card block in a namespace mirroring the
    api_box_score scope. Globals are the router's real module dict (so `os` and
    every helper resolve EXACTLY as in production)."""
    g = dict(R.__dict__)
    g.update({"box": box, "date": date, "game_id": game_id,
              "live_overlay": live_overlay})
    exec(_BLOCK, g)
    return g["box"]


@pytest.fixture
def env_flags(monkeypatch):
    def _set(**flags):
        for k, v in flags.items():
            if v is None:
                monkeypatch.delenv(k, raising=False)
            else:
                monkeypatch.setenv(k, v)
    return _set


@pytest.fixture
def cv_fix_dir(tmp_path, monkeypatch):
    """Point the router's _ROOT/data/cache/cv_fix and data/live at tmp dirs so
    out/return lists and snapshots don't touch the real repo."""
    import pathlib
    root = tmp_path
    (root / "data" / "cache" / "cv_fix").mkdir(parents=True)
    (root / "data" / "live").mkdir(parents=True)
    monkeypatch.setattr(R, "_ROOT", root)
    monkeypatch.setattr(R, "_LIVE_DIR_PATH", root / "data" / "live")
    return root


# ── (1) the fix itself ────────────────────────────────────────────────────────

def test_module_level_os_is_defined():
    """The core fix: courtvision_router exposes a module-level `os`."""
    assert hasattr(R, "os"), "module-level `import os` missing — the fix regressed"
    assert R.os is os or R.os.__name__ == "os"


def test_no_nameerror_on_bare_os_reference():
    """The bare os.environ.get refs must resolve (not NameError) in module scope."""
    # If os were undefined, evaluating this in the module namespace would raise.
    val = eval("os.environ.get('CV_OUT_DETECT_HARDEN', '0')", dict(R.__dict__))
    assert val in ("0", "1") or isinstance(val, str)


# ── (2) byte-identical no-op with flags OFF + empty out-list ──────────────────

def test_box_card_byte_identical_flags_off(env_flags, cv_fix_dir):
    env_flags(CV_OUT_DETECT_HARDEN=None, CV_INGAME_RETURN=None)
    untouched = json.dumps(_make_box(), sort_keys=True)
    out = _run_block(_make_box(), "2026-06-04", "0042500999", _OVERLAY)
    assert json.dumps(out, sort_keys=True) == untouched, (
        "box-card block must be a no-op with flags off and no out-list")


def test_box_card_no_op_even_with_harden_when_no_outlist(env_flags, cv_fix_dir):
    """HARDEN on but <3 snapshots / no stagnation history -> still a no-op."""
    env_flags(CV_OUT_DETECT_HARDEN="1", CV_INGAME_RETURN="1")
    untouched = json.dumps(_make_box(), sort_keys=True)
    out = _run_block(_make_box(), "2026-06-04", "0042500999", _OVERLAY)
    assert json.dumps(out, sort_keys=True) == untouched


# ── (3i) manual out-list caps to current ──────────────────────────────────────

def test_manual_outlist_caps_to_current(env_flags, cv_fix_dir):
    env_flags(CV_OUT_DETECT_HARDEN="1", CV_INGAME_RETURN="1")
    out_path = cv_fix_dir / "data" / "cache" / "cv_fix" / "live_out_2026-06-04.json"
    out_path.write_text(json.dumps(["Hurt Star"]), encoding="utf-8")
    out = _run_block(_make_box(), "2026-06-04", "0042500999", _OVERLAY)
    hs, ag = out["home"]["players"]
    assert hs["paced_final"]["pts"] == 12.0  # capped to current
    assert hs["paced_final"]["reb"] == 4.0
    assert hs["paced_final"]["ast"] == 3.0
    assert hs.get("_out_flag") is True
    assert "OUT" in (hs.get("availability") or "")
    # the healthy teammate is untouched
    assert ag["paced_final"]["pts"] == 30.0
    assert ag.get("_out_flag") is None


def test_manual_outlist_dead_when_harden_off_but_manual_still_caps(env_flags, cv_fix_dir):
    """The MANUAL out cap fires from the out-list regardless of HARDEN (HARDEN
    only gates the *auto* stagnation detector). With both flags off, the manual
    cap still applies because the block reads the file unconditionally — this is
    the production-intended behavior the os-NameError was killing."""
    env_flags(CV_OUT_DETECT_HARDEN=None, CV_INGAME_RETURN=None)
    out_path = cv_fix_dir / "data" / "cache" / "cv_fix" / "live_out_2026-06-04.json"
    out_path.write_text(json.dumps(["Hurt Star"]), encoding="utf-8")
    out = _run_block(_make_box(), "2026-06-04", "0042500999", _OVERLAY)
    hs = out["home"]["players"][0]
    assert hs["paced_final"]["pts"] == 12.0
    assert hs.get("_out_flag") is True


# ── (3ii) stagnation auto-detect ──────────────────────────────────────────────

def _write_snaps(live_dir, gid, snaps):
    paths = []
    for ep, data in snaps.items():
        p = live_dir / f"{gid}_{ep}.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        paths.append(p)
    return paths


def test_stagnation_auto_out_across_period_boundary(env_flags, cv_fix_dir):
    env_flags(CV_OUT_DETECT_HARDEN="1", CV_INGAME_RETURN=None)
    gid = "0042599777"
    live_dir = cv_fix_dir / "data" / "live"
    E = 1_900_000_000_000
    # Stale Star: minutes FLAT 18.0 across T-12, T-6, now; period 2 -> 3 (cross).
    # Active Guy: minutes climbing (10 -> 16 -> 22), must NOT be flagged.
    _write_snaps(live_dir, gid, {
        E - 720_000: {"period": 2, "clock": "6:00",
                      "players": [{"name": "Stale Star", "min": 18.0},
                                  {"name": "Active Guy", "min": 10.0}]},
        E - 360_000: {"period": 3, "clock": "6:00",
                      "players": [{"name": "Stale Star", "min": 18.0},
                                  {"name": "Active Guy", "min": 16.0}]},
        E:           {"period": 3, "clock": "6:00",
                      "players": [{"name": "Stale Star", "min": 18.0},
                                  {"name": "Active Guy", "min": 22.0}]},
    })
    box = _make_box(p_name="Stale Star")
    out = _run_block(box, "2026-06-04", gid, _OVERLAY)
    ss, ag = out["home"]["players"]
    assert ss["paced_final"]["pts"] == 12.0  # auto-capped to current
    assert ss.get("_out_flag") is True
    assert "did not return" in (ss.get("availability") or "")
    # climbing-minutes teammate spared
    assert ag.get("_out_flag") is None
    assert ag["paced_final"]["pts"] == 30.0


def test_stagnation_does_not_fire_when_harden_off(env_flags, cv_fix_dir):
    env_flags(CV_OUT_DETECT_HARDEN=None, CV_INGAME_RETURN=None)
    gid = "0042599778"
    live_dir = cv_fix_dir / "data" / "live"
    E = 1_900_000_000_000
    _write_snaps(live_dir, gid, {
        E - 720_000: {"period": 2, "clock": "6:00",
                      "players": [{"name": "Stale Star", "min": 18.0}]},
        E - 360_000: {"period": 3, "clock": "6:00",
                      "players": [{"name": "Stale Star", "min": 18.0}]},
        E:           {"period": 3, "clock": "6:00",
                      "players": [{"name": "Stale Star", "min": 18.0}]},
    })
    box = _make_box(p_name="Stale Star")
    out = _run_block(box, "2026-06-04", gid, _OVERLAY)
    ss = out["home"]["players"][0]
    assert ss["paced_final"]["pts"] == 28.0   # untouched (auto-detect disabled)
    assert ss.get("_out_flag") is None


# ── (3iii) player return clears OUT + applies reduced-minutes anchor ──────────

def test_manual_return_clears_out_and_applies_anchor(env_flags, cv_fix_dir):
    env_flags(CV_OUT_DETECT_HARDEN="1", CV_INGAME_RETURN="1")
    gid = "0042599779"
    live_dir = cv_fix_dir / "data" / "live"
    E = 1_900_000_000_000
    _write_snaps(live_dir, gid, {
        E - 720_000: {"period": 2, "clock": "6:00",
                      "players": [{"name": "Stale Star", "min": 18.0}]},
        E - 360_000: {"period": 3, "clock": "6:00",
                      "players": [{"name": "Stale Star", "min": 18.0}]},
        E:           {"period": 3, "clock": "6:00",
                      "players": [{"name": "Stale Star", "min": 18.0}]},
    })
    # Stale Star is in the manual RETURN list -> OUT cleared, 0.75 anchor applied.
    ret_path = cv_fix_dir / "data" / "cache" / "cv_fix" / "live_return_2026-06-04.json"
    ret_path.write_text(json.dumps(["Stale Star"]), encoding="utf-8")
    box = _make_box(p_name="Stale Star")
    out = _run_block(box, "2026-06-04", gid, _OVERLAY)
    ss = out["home"]["players"][0]
    # pts: current 12, extra = paced 28 - 12 = 16; anchored = 12 + 0.75*16 = 24.0
    assert ss["paced_final"]["pts"] == 24.0
    assert ss.get("_out_flag") is None
    assert ss.get("_returned_flag") is True
    assert "RETURNED" in (ss.get("availability") or "")


def test_return_overrides_manual_out(env_flags, cv_fix_dir):
    """A name in BOTH live_out and live_return is treated as RETURNED."""
    env_flags(CV_OUT_DETECT_HARDEN="1", CV_INGAME_RETURN="1")
    base = cv_fix_dir / "data" / "cache" / "cv_fix"
    (base / "live_out_2026-06-04.json").write_text(
        json.dumps(["Hurt Star"]), encoding="utf-8")
    (base / "live_return_2026-06-04.json").write_text(
        json.dumps(["Hurt Star"]), encoding="utf-8")
    out = _run_block(_make_box(p_name="Hurt Star"), "2026-06-04", "0042599780", _OVERLAY)
    hs = out["home"]["players"][0]
    assert hs.get("_returned_flag") is True
    assert hs.get("_out_flag") is None
    # reduced-minutes anchor (not capped-to-current): pts = 12 + 0.75*16 = 24.0
    assert hs["paced_final"]["pts"] == 24.0
