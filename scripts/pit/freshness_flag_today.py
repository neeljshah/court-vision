"""freshness_flag_today.py — THE FRESHNESS OPERATOR TOOL (advisory, read-only).

The ONE prediction lever the 2026-06-01 campaign proved is REAL and capturable is
SAME-DAY FRESHNESS, realized as CLV: when a primary creator is CONFIRMED OUT, his
assists re-route to teammates and the model has NO `vac_ast` feature, so we can
(a) SIZE UP the already-validated gated-AST book on the surviving beneficiaries
and (b) flag starter-UNDERs in projected blowouts — and bet them at the OPENER,
BEFORE the close prices the inactive news. The edge lives ONLY pre-close (timing/
CLV), which is why a closing-line backtest shows ~0 (the close already adjusted).
See docs/_audits/{PRED_EXP_freshness_reproject,INTEL_SELECTION_WIRING,
FRESHNESS_PIPELINE_SPEC}_2026-06-01.md.

THIS TOOL is what an operator runs the moment inactive news drops. Given a slate
date + a CONFIRMED-OUT player list, it:

  1. Builds the leak-free `vac_ast` / `vac_pts` / `n_out` for every affected team
     from the CONFIRMED-OUT set (reusing exp_freshness_reproject.build_vac_signals'
     box-appearance recipe restricted to the confirmed-out players, so it works on
     a LIVE slate with no box score yet).
  2. Identifies the BENEFICIARY props on each affected team — surviving players who
     are meaningful assist sources (own as-of L10 AST >= 2) — and flags the
     gated-AST SIZE-UP via intel_selection.vac_ast_size_multiplier.
  3. Optionally flags the BLOWOUT starter-UNDER candidates (starters on a team in a
     projected blowout) via intel_selection.blowout_under_flag, when an as-of SRS
     mismatch is supplied (the live path attaches it; absent => that section is
     skipped, not faked).
  4. Prints the flagged size-up bets + blowout candidates — an advisory checklist
     for an OPENER bet. It PLACES NOTHING and EDITS NO PRODUCTION STATE.

Default-safe: prints a checklist. Never writes to the ledger, the live page, or any
production file. Optional --json-out writes a snapshot to data/cache/freshness/ for
the CLV tracker to pair against the close later (advisory artifact only).

It reuses the gated, default-OFF intel_selection helpers but passes enabled=True
explicitly (the operator is asking "if I turned the lever ON, what fires?") — it
does NOT flip any env flag or touch the live selection path.

Run:
    # confirmed-out list inline (names; team optional via "Name@TEAM"):
    conda run -n basketball_ai python scripts/pit/freshness_flag_today.py \
        --date 2026-06-01 --out "Tyrese Haliburton,Pascal Siakam@IND"

    # confirmed-out list from a JSON file ([{"player":"...","team":"IND"}, ...]
    # or {"out":[...]} or a bare ["Name", ...]):
    conda run -n basketball_ai python scripts/pit/freshness_flag_today.py \
        --date 2026-06-01 --out-json data/cache/confirmed_out_2026-06-01.json

    # also surface blowout starter-UNDERs from a supplied per-team as-of SRS map:
    ... --srs-json '{"IND": -2.1, "OKC": 7.4}'  --blowout-hca 2.5

Honest boundary: this tool selects/sizes; it cannot PROVE the edge. The proof is
forward CLV — did the flagged OPENER bets beat the Pinnacle close? Validate with
scripts/gate1_clv_pinnacle.py once real opener+close snapshots accrue (Oct 2026 per
the roadmap). See the FRESHNESS_PIPELINE_SPEC doc, section "Forward-CLV validation".
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date as _date_cls
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ── path bootstrap: standalone, reuses only the two existing helpers ──────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))  # .../nba-ai-system
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Reuse the VALIDATED leak-free vac_* builder (box-appearance recipe extended to AST).
from exp_freshness_reproject import build_vac_signals  # noqa: E402

# Reuse the GATED selection/sizing levers (we pass enabled=True explicitly —
# we do NOT flip the env flags; this is "what WOULD fire", advisory only).
try:
    from src.prediction.intel_selection import (  # noqa: E402
        vac_ast_size_multiplier,
        blowout_under_flag,
    )
except Exception:  # degrade gracefully if the prod module isn't importable
    def vac_ast_size_multiplier(stat, edge, line, vac_ast, is_playoff, enabled=None):
        # Mirror the validated gate inline so the tool still works standalone.
        if not enabled or is_playoff or str(stat).lower() != "ast":
            return 1.0
        try:
            if abs(float(edge)) < 0.75 or float(line) > 7.5 or float(vac_ast) < 3.0:
                return 1.0
        except (TypeError, ValueError):
            return 1.0
        return 1.5 if float(vac_ast) >= 6.0 else 1.25

    def blowout_under_flag(stat, side, role, blowout_risk, is_playoff,
                           enabled=None, *, threshold=None, as_score=True):
        if not enabled or is_playoff or str(side).lower() != "under":
            return 0.0 if as_score else False
        is_starter = (str(role).strip().lower() in {"starter", "start", "starting", "s"})
        if not is_starter:
            try:
                is_starter = float(role) >= 28.0
            except (TypeError, ValueError):
                is_starter = False
        if not is_starter:
            return 0.0 if as_score else False
        # blowout_risk: bool, or [0,1] percentile (>=0.75), or raw |margin|+threshold
        ok = False
        if isinstance(blowout_risk, bool):
            ok = blowout_risk
        else:
            try:
                v = float(blowout_risk)
                ok = (v >= threshold) if threshold is not None else (0.0 <= v <= 1.0 and v >= 0.75)
            except (TypeError, ValueError):
                ok = False
        if not ok:
            return 0.0 if as_score else False
        if not as_score:
            return True
        return 1.0 if str(stat).lower() == "pts" else 0.5


NBA = os.path.join(_ROOT, "data", "nba")
CACHE = os.path.join(_ROOT, "data", "cache")

# Live-slate gating thresholds — must mirror intel_selection / the lever docs.
_VAC_AST_MIN = 3.0          # vacated L10 AST of confirmed-out regulars => "creator out"
_BENEF_OWN_AST_MIN = 2.0    # surviving player is a meaningful assist source
_AST_GATE_LINE = 7.5        # gated-AST closing-line cap (informational on a live slate)
_STARTER_MIN_MIN = 28.0     # as-of L10 minutes => "starter"
_DEFAULT_SEASON = "2025-26"
_DEFAULT_HCA = 2.5          # home-court SRS bump for the blowout exp-margin


# ─────────────────────────────────────────────────────────────────────────────
# 0. confirmed-OUT input parsing
# ─────────────────────────────────────────────────────────────────────────────
def parse_out_arg(out_str: Optional[str], out_json: Optional[str]) -> List[Dict]:
    """Return a list of {"player": name, "team": abbr|None} from CLI inputs.

    --out  : comma-separated "Name" or "Name@TEAM" tokens.
    --out-json: a JSON file shaped as any of:
        [{"player": "...", "team": "IND"}, ...]
        {"out": [{"player": ...}, ...]}  |  {"players": [...]}
        ["Name1", "Name2", ...]
    """
    rows: List[Dict] = []
    if out_str:
        for tok in out_str.split(","):
            tok = tok.strip()
            if not tok:
                continue
            if "@" in tok:
                nm, tm = tok.split("@", 1)
                rows.append({"player": nm.strip(), "team": tm.strip().upper() or None})
            else:
                rows.append({"player": tok, "team": None})
    if out_json:
        with open(out_json, encoding="utf-8") as fh:
            payload = json.load(fh)
        if isinstance(payload, dict):
            payload = payload.get("out") or payload.get("players") or []
        for item in payload:
            if isinstance(item, str):
                rows.append({"player": item.strip(), "team": None})
            elif isinstance(item, dict):
                nm = (item.get("player") or item.get("player_name")
                      or item.get("name") or "").strip()
                if not nm:
                    continue
                tm = (item.get("team") or "").strip().upper() or None
                rows.append({"player": nm, "team": tm})
    return rows


def load_name_pid_team(season: str) -> Dict[str, Tuple[int, Optional[str]]]:
    """name.lower() -> (player_id, team) from player_avgs_<season>.json (+ fallback)."""
    out: Dict[str, Tuple[int, Optional[str]]] = {}
    for s in (season, "2024-25", "2023-24"):
        p = os.path.join(NBA, f"player_avgs_{s}.json")
        if not os.path.exists(p):
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        for nm, info in d.items():
            pid = info.get("player_id")
            if pid is None:
                continue
            key = nm.strip().lower()
            if key not in out:
                out[key] = (int(pid), (info.get("team") or None))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 1. confirmed-OUT vac_* recomputation (LIVE-slate variant of build_vac_signals)
#    The committed build_vac_signals uses box-appearance ground truth (who DIDN'T
#    play) which needs a finished box score. On a LIVE slate we don't have that —
#    so we reuse its leak-free as-of L10 roster machinery but define "out" by the
#    OPERATOR-SUPPLIED confirmed-OUT set instead of box absence. We do that by
#    asking build_vac_signals for the as-of L10 of EVERY player up to `date`, then
#    aggregating vacated load for the confirmed-out pids per team here.
# ─────────────────────────────────────────────────────────────────────────────
def asof_l10_table(season: str) -> pd.DataFrame:
    """Per (pid, team) the most-recent as-of L10 min/pts/ast BEFORE `season`'s
    latest game — derived from the SAME signal dict build_vac_signals emits, so the
    L10 numbers are byte-for-byte the validated leak-free quantities.

    build_vac_signals keys on (pid, iso-date) of games the player PLAYED; we take,
    per pid, the row with the latest date (the freshest as-of L10) plus its team.
    """
    sig = build_vac_signals(season)  # {(pid, iso): {own_team, own_l10_min, own_l10_ast, ...}}
    latest: Dict[int, Tuple[str, dict]] = {}
    for (pid, iso), rec in sig.items():
        cur = latest.get(pid)
        if cur is None or iso > cur[0]:
            latest[pid] = (iso, rec)
    rows = []
    for pid, (iso, rec) in latest.items():
        rows.append({
            "player_id": pid,
            "asof_date": iso,
            "team": rec.get("own_team"),
            "l10_min": float(rec.get("own_l10_min") or 0.0),
            "l10_ast": float(rec.get("own_l10_ast") or 0.0),
            # team_played_l10ast is the surviving-share denominator the re-proj uses
            "team_l10ast_sum": float(rec.get("team_played_l10ast") or 0.0),
        })
    return pd.DataFrame(rows)


def compute_team_vacancies(out_rows: List[Dict], l10: pd.DataFrame,
                           name_idx: Dict[str, Tuple[int, Optional[str]]]) -> Dict[str, dict]:
    """Aggregate vacated L10 load per team from the confirmed-OUT set.

    Returns {team: {vac_ast, vac_pts_proxy, n_out, out_players:[...]}}. vac_pts is
    not separately carried by the L10 table here (the AST lever is the bettable one);
    we report vacated L10 MIN as the PTS-vacancy proxy for the blowout context.
    """
    # map confirmed-out names -> (pid, team, l10_ast, l10_min)
    by_pid = {int(r.player_id): r for r in l10.itertuples(index=False)}
    teams: Dict[str, dict] = {}
    unresolved: List[str] = []
    for row in out_rows:
        nm = row["player"].strip().lower()
        pid_team = name_idx.get(nm)
        if pid_team is None:
            unresolved.append(row["player"])
            continue
        pid, roster_team = pid_team
        rec = by_pid.get(pid)
        team = row.get("team") or (rec.team if rec is not None else None) or roster_team
        if team is None:
            unresolved.append(row["player"])
            continue
        team = team.upper()
        l10_ast = float(rec.l10_ast) if rec is not None else 0.0
        l10_min = float(rec.l10_min) if rec is not None else 0.0
        t = teams.setdefault(team, {"vac_ast": 0.0, "vac_min": 0.0, "n_out": 0,
                                    "out_players": []})
        t["vac_ast"] += l10_ast
        t["vac_min"] += l10_min
        t["n_out"] += 1
        t["out_players"].append({"player": row["player"], "player_id": pid,
                                 "l10_ast": round(l10_ast, 2), "l10_min": round(l10_min, 1)})
    return teams, unresolved


# ─────────────────────────────────────────────────────────────────────────────
# 2. beneficiary identification (gated-AST SIZE-UP candidates)
# ─────────────────────────────────────────────────────────────────────────────
def find_beneficiaries(team: str, vac: dict, l10: pd.DataFrame,
                       is_playoff: bool) -> List[Dict]:
    """Surviving players on `team` who are meaningful assist sources => gated-AST
    SIZE-UP candidates. Each gets the intel_selection multiplier (passed a sentinel
    edge/line that SATISFIES the gate, since on a live slate the operator confirms
    the real edge/line against the book; the multiplier here answers 'IF this lands
    in the gated-AST window, what size-up applies for this vacancy')."""
    if vac["vac_ast"] < _VAC_AST_MIN:
        return []
    out_pids = {p["player_id"] for p in vac["out_players"]}
    cands = []
    for r in l10.itertuples(index=False):
        if r.team != team or int(r.player_id) in out_pids:
            continue
        if float(r.l10_ast) < _BENEF_OWN_AST_MIN:
            continue
        # surviving-share of the team's remaining L10 assist production
        denom = float(r.team_l10ast_sum) or 0.0
        share = (float(r.l10_ast) / denom) if denom > 1e-6 else 0.0
        mult = vac_ast_size_multiplier(
            stat="ast",
            edge=0.75,                 # sentinel: at the gate floor (operator confirms real edge)
            line=_AST_GATE_LINE,       # sentinel: at the gate line cap
            vac_ast=vac["vac_ast"],
            is_playoff=is_playoff,
            enabled=True,              # "what WOULD fire" — does NOT flip env flags
        )
        cands.append({
            "player_id": int(r.player_id),
            "l10_ast": round(float(r.l10_ast), 2),
            "share_of_remaining_ast": round(share, 3),
            "size_multiplier": round(mult, 3),
            "est_reroute_ast": round(share * vac["vac_ast"], 2),
        })
    cands.sort(key=lambda c: c["est_reroute_ast"], reverse=True)
    return cands


# ─────────────────────────────────────────────────────────────────────────────
# 3. blowout starter-UNDER candidates (optional; needs an as-of SRS map)
# ─────────────────────────────────────────────────────────────────────────────
def find_blowout_starters(srs_map: Dict[str, float], matchups: List[Tuple[str, str]],
                          l10: pd.DataFrame, hca: float, is_playoff: bool,
                          srs_quartile_thr: Optional[float]) -> List[Dict]:
    """For each (home, away) matchup, compute exp_margin = srs(home)-srs(away)+hca;
    a top-quartile |exp_margin| game flags ITS STARTERS' model-UNDERs (esp. PTS).
    The operator supplies the per-team as-of SRS map and (optionally) the
    top-quartile threshold fit on prior games; absent threshold => use |margin|>=10
    as a conservative blowout cut (documented in the spec)."""
    out: List[Dict] = []
    thr = srs_quartile_thr if srs_quartile_thr is not None else 10.0
    by_team_starters: Dict[str, List[int]] = {}
    for r in l10.itertuples(index=False):
        if float(r.l10_min) >= _STARTER_MIN_MIN and r.team:
            by_team_starters.setdefault(r.team, []).append(int(r.player_id))
    for home, away in matchups:
        sh, sa = srs_map.get(home), srs_map.get(away)
        if sh is None or sa is None:
            continue
        em = sh - sa + hca
        blowout = abs(em) >= thr
        if not blowout:
            continue
        # both teams' starters are blowout-UNDER candidates (the trailing team's
        # starters sit late; on the leading side too, blowouts pull starter minutes)
        for team in (home, away):
            for pid in by_team_starters.get(team, []):
                score = blowout_under_flag(
                    stat="pts", side="under", role="starter",
                    blowout_risk=abs(em), is_playoff=is_playoff,
                    enabled=True, threshold=thr, as_score=True,
                )
                if score > 0.0:
                    out.append({
                        "team": team, "player_id": pid, "exp_margin": round(em, 1),
                        "favored": team == (home if em > 0 else away),
                        "under_upweight_score_pts": score,
                    })
    return out


def load_matchups(season: str, date_iso: str) -> List[Tuple[str, str]]:
    """(home, away) matchups for `date_iso` from season_games_<season>.json, if present."""
    p = os.path.join(NBA, f"season_games_{season}.json")
    if not os.path.exists(p):
        return []
    try:
        rows = json.load(open(p, encoding="utf-8")).get("rows", [])
    except Exception:
        return []
    ms = []
    for r in rows:
        if str(r.get("game_date", "")).startswith(date_iso) and "home_team" in r:
            ms.append((r["home_team"], r["away_team"]))
    return ms


# ─────────────────────────────────────────────────────────────────────────────
# 4. report
# ─────────────────────────────────────────────────────────────────────────────
def name_for_pid(name_idx: Dict[str, Tuple[int, Optional[str]]], pid: int) -> str:
    for nm, (p, _t) in name_idx.items():
        if p == pid:
            return nm.title()
    return f"pid:{pid}"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="FRESHNESS operator tool: flag gated-AST SIZE-UP beneficiaries "
                    "+ blowout starter-UNDERs the moment confirmed-OUT news drops "
                    "(advisory, read-only, places nothing).")
    ap.add_argument("--date", default=None, help="Slate date YYYY-MM-DD (default: today).")
    ap.add_argument("--out", default=None,
                    help="Confirmed-OUT players, comma-separated 'Name' or 'Name@TEAM'.")
    ap.add_argument("--out-json", default=None,
                    help="JSON file of confirmed-OUT players (see module docstring).")
    ap.add_argument("--season", default=_DEFAULT_SEASON, help="Gamelog season slug.")
    ap.add_argument("--playoff", action="store_true",
                    help="Mark slate as playoffs (forces BOTH levers to no-op — "
                         "the AST edge breaks and the blowout minutes mechanism "
                         "inverts in the postseason).")
    ap.add_argument("--srs-json", default=None,
                    help="JSON {team: asof_srs} to enable the blowout starter-UNDER "
                         "section (absent => that section is skipped, not faked).")
    ap.add_argument("--blowout-hca", type=float, default=_DEFAULT_HCA,
                    help="Home-court SRS bump for exp_margin (default 2.5).")
    ap.add_argument("--blowout-thr", type=float, default=None,
                    help="Top-quartile |exp_margin| cut from PRIOR games (leak-free). "
                         "Absent => conservative |margin|>=10.")
    ap.add_argument("--json-out", action="store_true",
                    help="Also write an advisory snapshot to data/cache/freshness/ "
                         "for later CLV pairing (writes ONLY under data/cache, never "
                         "the ledger or live page).")
    args = ap.parse_args(argv)

    date_iso = args.date or _date_cls.today().isoformat()
    out_rows = parse_out_arg(args.out, args.out_json)
    if not out_rows:
        print("[freshness] no confirmed-OUT players supplied (--out / --out-json). "
              "Nothing to flag.")
        return 1

    print("#" * 76)
    print(f"# FRESHNESS FLAGS — slate {date_iso}  |  {'PLAYOFF (levers OFF)' if args.playoff else 'regular season'}")
    print(f"# confirmed-OUT supplied: {len(out_rows)}  |  ADVISORY ONLY — places nothing")
    print("#" * 76)

    name_idx = load_name_pid_team(args.season)
    l10 = asof_l10_table(args.season)
    teams, unresolved = compute_team_vacancies(out_rows, l10, name_idx)
    if unresolved:
        print(f"\n[warn] could not resolve (name->pid/team): {unresolved}")

    # ── section A: gated-AST SIZE-UP beneficiaries ──────────────────────────
    print("\n" + "=" * 76)
    print(" A. gated-AST SIZE-UP beneficiaries (creator OUT => re-route assists)")
    print("=" * 76)
    any_a = False
    snapshot = {"date": date_iso, "playoff": args.playoff, "teams": {}, "blowout": []}
    for team in sorted(teams):
        vac = teams[team]
        out_names = ", ".join(p["player"] for p in vac["out_players"])
        flagged = (vac["vac_ast"] >= _VAC_AST_MIN) and not args.playoff
        tag = "FLAG (creator out)" if flagged else "below vac_ast gate"
        print(f"\n  {team}: vac_ast={vac['vac_ast']:.1f} vac_min={vac['vac_min']:.0f} "
              f"n_out={vac['n_out']}  [{tag}]  OUT: {out_names}")
        team_snap = {"vac_ast": round(vac["vac_ast"], 2), "vac_min": round(vac["vac_min"], 1),
                     "n_out": vac["n_out"], "out_players": vac["out_players"],
                     "beneficiaries": []}
        if flagged:
            benef = find_beneficiaries(team, vac, l10, is_playoff=args.playoff)
            for b in benef:
                any_a = True
                nm = name_for_pid(name_idx, b["player_id"])
                print(f"      -> {nm:<26} AST OVER  size x{b['size_multiplier']:.2f}  "
                      f"(L10 AST {b['l10_ast']}, share {b['share_of_remaining_ast']:.0%}, "
                      f"~+{b['est_reroute_ast']} reroute)  | BET THE OPENER")
                b["player"] = nm
                team_snap["beneficiaries"].append(b)
        snapshot["teams"][team] = team_snap
    if not any_a:
        print("\n  (no gated-AST SIZE-UP flags — no confirmed-out creator cleared "
              "vac_ast>=3, or playoff slate.)")

    # ── section B: blowout starter-UNDER candidates (optional) ──────────────
    print("\n" + "=" * 76)
    print(" B. blowout starter-UNDER candidates (esp. PTS)")
    print("=" * 76)
    if args.srs_json:
        srs_map = {k.upper(): float(v) for k, v in json.loads(
            args.srs_json if args.srs_json.strip().startswith("{")
            else open(args.srs_json, encoding="utf-8").read()).items()}
        matchups = load_matchups(args.season, date_iso)
        if not matchups:
            print(f"  [warn] no matchups for {date_iso} in season_games_{args.season}.json "
                  "— cannot compute exp_margin. Section skipped.")
        else:
            bl = find_blowout_starters(srs_map, matchups, l10, args.blowout_hca,
                                       is_playoff=args.playoff, srs_quartile_thr=args.blowout_thr)
            if not bl:
                print("  (no top-quartile blowout games on this slate, or playoff.)")
            for b in bl:
                nm = name_for_pid(name_idx, b["player_id"])
                fav = "FAV" if b["favored"] else "DOG"
                print(f"  {b['team']} {fav}  {nm:<26} PTS UNDER  upweight={b['under_upweight_score_pts']:.2f}  "
                      f"(exp_margin {b['exp_margin']:+.1f})  | BET THE OPENER")
                b["player"] = nm
            snapshot["blowout"] = bl
    else:
        print("  (skipped — pass --srs-json {team: asof_srs} to enable. Not faked.)")

    # ── optional advisory snapshot (NEVER the ledger/live page) ─────────────
    if args.json_out:
        outdir = os.path.join(CACHE, "freshness")
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, f"freshness_flags_{date_iso}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2)
        print(f"\n[freshness] advisory snapshot -> {path}")

    print("\n" + "#" * 76)
    print("# ADVISORY ONLY. Confirm each real edge/line against the OPENER before "
          "betting.")
    print("# Validate the lever with forward CLV: scripts/gate1_clv_pinnacle.py "
          "(opener vs close).")
    print("#" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
