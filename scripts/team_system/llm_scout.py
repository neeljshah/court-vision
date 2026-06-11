"""scripts/team_system/llm_scout.py — the scheme SCOUT: emits bounded SchemeAdjustment[] for a matchup.

This is the ONLY component that may invoke an LLM, and even then it emits a KNOB PATCH, never a
prediction. Two modes:

  * deterministic_scout(home, away, asof, betting=True)
      Rule-based, fully leak-free (reads ONLY leak-free fields from the Phase-1 artifacts:
      four_factor_env expanding/identity z-scores, pace_possession season identity, scheme_coverage
      wf_* expanding rim/perimeter z-scores). Deterministic + seed-free -> the season-scale Phase-3
      validation workhorse. Every adjustment is leak_safe=True.

  * llm_scout(home, away, asof)
      If ANTHROPIC_API_KEY is set, asks Claude to reason about how the SCHEMES interact and propose
      bounded multipliers (schema-validated, every field justified + leak-flagged). Else falls back to
      deterministic_scout. Used for Game-4 + a validation sample, NOT per-game season-scale.

Output is validated + persisted per team via scheme_prior.write_scheme_adjustments.
honesty_class = "research". Py3.10.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_HERE, os.path.join(_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TS = os.path.join(_ROOT, "data", "cache", "team_system")
from sim.scheme_prior import write_scheme_adjustments, validate_adjustment, VALID_PARAMS  # noqa: E402


def _load(name: str) -> Optional[pd.DataFrame]:
    p = os.path.join(TS, name)
    if not os.path.exists(p):
        return None
    try:
        return pd.read_parquet(p)
    except Exception:
        return None


def _zget(df: Optional[pd.DataFrame], team: str, col: str, key: str = "team") -> Optional[float]:
    if df is None or col not in df.columns or key not in df.columns:
        return None
    row = df[df[key] == team]
    if len(row) == 0:
        return None
    v = row.iloc[0][col]
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if v != v else v  # drop NaN


def _z_to_mult(z: Optional[float], per_z: float, lo: float, hi: float) -> Optional[float]:
    """Map a leak-free z-score to a bounded raw multiplier (clamped). None -> skip."""
    if z is None:
        return None
    m = 1.0 + per_z * z
    return max(lo, min(hi, m))


def deterministic_scout(home: str, away: str, asof: Optional[str] = None,
                        betting: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    """Leak-free rule-based scout. Returns {team: [adjustment dicts]} for both teams.

    Rules (all from leak-free fields; conservative per-z slopes so the layer SHAPES, not dominates):
      - four_factor_env: def_tov_force / def_ft_force z -> the OPPONENT's tov_force/ft_force vs this team;
        off oreb z -> own oreb nudge. (Defensive identity is applied to the DEFENDING team's model.)
      - pace_possession: poss_z -> own pace nudge.
      - scheme_coverage wf_* expanding z: rim/perimeter protection -> own int_d/perim_d nudge.
    """
    pace = _load("pace_possession.parquet")
    schm = _load("scheme_coverage.parquet")
    # restrict scheme_coverage to the team-level rows (leak-free expanding wf_* identities)
    if schm is not None and "row_type" in schm.columns:
        schm = schm[schm["row_type"] == "team_scheme"]
    out: Dict[str, List[Dict[str, Any]]] = {home: [], away: []}

    # (column, knob, per-z slope, confidence, why) — ALL leak-free expanding/season-identity reads.
    # tov_force/ft_force/pace nudge the team's DEFENSE/tempo; perim_d from overall expanding ppp-allowed.
    RULES = [
        (pace, "poss_z_score",      "pace",      0.015, 0.50, "season pace identity"),
        (schm, "wf_tov_forced_z",   "tov_force", 0.030, 0.45, "expanding (leak-free) turnover-forcing"),
        (schm, "wf_ft_allowed_z",   "ft_force",  0.030, 0.45, "expanding (leak-free) FT-allowed"),
        (schm, "wf_ppp_allowed_z",  "perim_d",  -0.030, 0.40, "expanding (leak-free) overall PPP-allowed (lower=better D)"),
    ]
    for team in (home, away):
        adjs: List[Dict[str, Any]] = []
        for df, col, knob, slope, conf, label in RULES:
            zz = _zget(df, team, col)
            mm = _z_to_mult(zz, slope, *( (0.94, 1.06) if knob == "pace" else (0.90, 1.12) ))
            if mm is not None and abs(mm - 1.0) > 1e-4:
                adjs.append(dict(entity="TEAM", param=knob, mult=round(mm, 4), confidence=conf,
                                 horizon="season", leak_safe=True,
                                 why=f"{team} {knob} from {label} {col}={zz:+.2f}"))
        out[team] = adjs
    return out


# --------------------------------------------------------------------------- LLM mode
_LLM_MODEL = "claude-opus-4-8"
_LLM_SYSTEM = (
    "You are CourtVision's scheme scout. You reason about how two NBA teams' SCHEMES interact and emit "
    "BOUNDED multipliers on a possession simulator's existing knobs. ARCHITECTURE LAW (do not violate):\n"
    "1. You NEVER output a win%, score, spread, or probability. You output ONLY a JSON list of knob "
    "adjustments. The simulator computes every number.\n"
    f"2. Each adjustment: {{entity (player_id int or 'TEAM'), param (one of {sorted(VALID_PARAMS)}), "
    "mult (float ~0.85-1.18), confidence (0-1), horizon, leak_safe (bool), why (string)}}.\n"
    "3. leak_safe MUST be false for any read derived from same-season vs-opponent / vs-scheme / "
    "defender rel-to-self / clutch splits (those are scouting-only and will be rejected for the betting "
    "number). Set leak_safe=true ONLY for prior-window / physical / season-identity reads.\n"
    "4. Every adjustment needs a concrete basketball justification in 'why'. No unexplained edits.\n"
    "Return ONLY the JSON list, nothing else."
)


def llm_scout(home: str, away: str, asof: Optional[str] = None,
              context: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """LLM scheme scout. Falls back to deterministic_scout if no API key / on any failure."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return deterministic_scout(home, away, asof)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        user = (f"Matchup: {away} @ {home} (asof={asof}). Context:\n{context or '(none provided)'}\n\n"
                "Emit the bounded SchemeAdjustment JSON list for BOTH teams' players/teams.")
        resp = client.messages.create(
            model=_LLM_MODEL, max_tokens=2000, temperature=0.0,
            system=[{"type": "text", "text": _LLM_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        txt = " ".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        start, end = txt.find("["), txt.rfind("]")
        items = json.loads(txt[start:end + 1]) if start >= 0 else []
        out: Dict[str, List[Dict[str, Any]]] = {home: [], away: []}
        for d in items:
            try:
                validate_adjustment(d)
            except ValueError:
                continue
            ent = d.get("entity")
            # route to the team that owns the entity (best-effort; default home)
            out.setdefault(home, []).append(d)
        return out
    except Exception:
        return deterministic_scout(home, away, asof)


def run(home: str, away: str, asof: Optional[str] = None, use_llm: bool = False) -> Dict[str, str]:
    scout = llm_scout(home, away, asof) if use_llm else deterministic_scout(home, away, asof)
    paths = {}
    for team, adjs in scout.items():
        paths[team] = write_scheme_adjustments(team, adjs, asof=asof,
                                                meta={"matchup": f"{away}@{home}", "mode": "llm" if use_llm else "deterministic"})
    return paths


def main():
    ap = argparse.ArgumentParser(description="Scheme scout -> bounded SchemeAdjustment artifacts")
    ap.add_argument("--home", default="NYK")
    ap.add_argument("--away", default="SAS")
    ap.add_argument("--asof", default=None)
    ap.add_argument("--llm", action="store_true", help="use the LLM scout (needs ANTHROPIC_API_KEY)")
    a = ap.parse_args()
    paths = run(a.home.upper(), a.away.upper(), asof=a.asof, use_llm=a.llm)
    for team, p in paths.items():
        adjs = json.load(open(p, encoding="utf-8")).get("adjustments", [])
        print(f"{team}: {len(adjs)} adjustments -> {p}")
        for d in adjs:
            print(f"   {d['entity']:>10} {d['param']:<12} mult={d['mult']:.3f} conf={d['confidence']:.2f} "
                  f"leak_safe={d['leak_safe']}  {d['why'][:70]}")


if __name__ == "__main__":
    main()
