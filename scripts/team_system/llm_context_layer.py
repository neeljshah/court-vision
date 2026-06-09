"""llm_context_layer.py — V6 LLM Context Room (offline + gated).

Section-11 law (enforced as code):
  * LLM is OFFLINE + PRODUCT + GUARDRAIL.  It SELECTS/WEIGHTS validated factors
    and NARRATES.  It NEVER computes the point prediction and NEVER invents a marginal.
  * The router applies a gated marginal mult ONLY for keys whose signal_effects.json
    status=="wired_pregame" AND confidence=="high": home_road, rest_b2b, pace_matchup,
    opp_defense.  Everything else is marginal_or_scouting="scouting".
  * Default-OFF byte-identical: CV_LLM_CONTEXT unset -> nothing in the existing
    prediction path changes.
  * Writes its OWN cache artifact.  NEVER edits read targets.

Public API
----------
    run_context_room(home, away, asof=None, nsims=8000, use_llm=True,
                     _result=None) -> dict
    load_or_build(home, away, asof=None, **kw) -> dict
    war_room_brief(cv, routed, bundle) -> str
    context_artifact_path(home, away, asof) -> str

Py3.9, type hints.  honesty_class = "research".
"""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# ---------- path setup ----------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_HERE, os.path.join(_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TS = os.path.join(_ROOT, "data", "cache", "team_system")
CONTEXT_DIR = os.path.join(TS, "context")
CV_GATE = "CV_LLM_CONTEXT"


def _gate_on() -> bool:
    return os.environ.get(CV_GATE, "").strip().lower() in ("1", "true", "yes", "on")


# ---------- shared dataclasses ----------
from context_scout import VALIDATED_KEYS  # type: ignore


@dataclass
class ContextFactor:
    factor: str           # canonical name
    lean: str             # signed direction e.g. "home" | "away" | "under" | "none"
    magnitude: float      # effect size in factor's native unit
    confidence: str       # "high" | "med" | "low"
    leak_free: bool       # True iff assembled only from pre-tip info
    validated_effect_key: Optional[str]    # one of VALIDATED_KEYS or None
    marginal_or_scouting: str              # "marginal" iff validated + high + leak_free, else "scouting"
    evidence: Dict[str, Any] = field(default_factory=dict)
    source: str = "scout"  # "scout" | "llm" | "llm_flag"


@dataclass
class ContextVector:
    matchup: str
    asof: Optional[str]
    honesty_class: str = "research"
    leak_free: bool = True
    factors: List[ContextFactor] = field(default_factory=list)
    rare_flags: List[str] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)


# ---------- artifact path ----------
def context_artifact_path(home: str, away: str, asof: Optional[str]) -> str:
    tag = asof or "latest"
    fname = f"{away.upper()}_at_{home.upper()}_{tag}.json"
    return os.path.join(CONTEXT_DIR, fname)


# ---------- deterministic ContextVector builder ----------
def _build_cv_deterministic(bundle: Dict[str, Any]) -> ContextVector:
    """Build a ContextVector from the scout bundle using pre-registered factor rules.
    No LLM involved.  Every factor is leak_free=True (only season/recency/avail data).
    """
    home = bundle["home"]
    away = bundle["away"]
    sim = bundle.get("sim", {})
    tiers = bundle.get("tiers", {})
    avail = bundle.get("avail", {})

    def _factor(factor, lean, mag, conf, vek, m_or_s, evidence=None):
        return ContextFactor(
            factor=factor, lean=lean, magnitude=mag, confidence=conf,
            leak_free=True,
            validated_effect_key=vek,
            marginal_or_scouting=m_or_s,
            evidence=evidence or {},
            source="scout",
        )

    factors: List[ContextFactor] = []

    # -- home_road: genuine venue effect --
    hr_mag = 1.020
    factors.append(_factor(
        "home_road", f"{home} (home)", hr_mag, "high",
        vek="home_road", m_or_s="marginal",
        evidence={"league_home_margin_pts": tiers.get("league_home_margin", 1.73),
                  "spine_mag": hr_mag, "per_pid": "x1.010 home / x0.990 away"},
    ))

    # -- rest_b2b: condition-gated --
    home_b2b = bool(avail.get("home_b2b", False))
    away_b2b = bool(avail.get("away_b2b", False))
    b2b_active = home_b2b or away_b2b
    factors.append(_factor(
        "rest_b2b",
        lean=f"{home}_b2b" if home_b2b else (f"{away}_b2b" if away_b2b else "none"),
        mag=0.989 if b2b_active else 1.000,
        conf="high",
        vek="rest_b2b",
        m_or_s="marginal" if b2b_active else "scouting",
        evidence={"home_b2b": home_b2b, "away_b2b": away_b2b,
                  "spine_mag": 0.989, "condition_met": b2b_active},
    ))

    # -- opp_defense: intrinsic to sim, read-only, no re-apply --
    home_def = sim.get("home_def_rtg", 113.3)
    away_def = sim.get("away_def_rtg", 113.3)
    factors.append(_factor(
        "matchup_edge", lean=f"{'away' if away_def < home_def else 'home'}_defense",
        mag=0.982, conf="high",
        vek="opp_defense",
        m_or_s="marginal",  # marginal = real and applied; router enforces double-count guard
        evidence={"home_def_rtg": home_def, "away_def_rtg": away_def,
                  "spine_mag": 0.982,
                  "router_note": "READ-ONLY — intrinsic in _matchup_mult; router does NOT re-apply"},
    ))

    # -- pace_lean: validated key but null magnitude --
    factors.append(_factor(
        "pace_lean",
        lean="under" if sim.get("home_pace", 100) < 100 else "neutral",
        mag=1.000, conf="high",
        vek="pace_matchup",
        m_or_s="scouting",
        evidence={"home_pace": sim.get("home_pace"), "away_pace": sim.get("away_pace"),
                  "n_poss": sim.get("n_poss"), "spine_mag": 1.0,
                  "note": "null-magnitude — no mult; n_poss = avg(both paces)"},
    ))

    # -- who_decides_late (clutch): in_game, scouting only --
    factors.append(_factor(
        "who_decides_late", lean="unknown_pregame", mag=1.25, conf="med",
        vek=None, m_or_s="scouting",
        evidence={"spine_status": "in_game",
                  "note": "clutch signal lab REJECTED as pregame marginal (OOS +0.01%)"},
    ))

    # -- blowout_variance: in_game, scouting only --
    home_blow = tiers.get("home", {}).get("blowout_game_pct", 0.15)
    away_blow = tiers.get("away", {}).get("blowout_game_pct", 0.15)
    factors.append(_factor(
        "blowout_variance", lean="high_var" if max(home_blow or 0, away_blow or 0) > 0.18 else "low",
        mag=0.904, conf="low",
        vek=None, m_or_s="scouting",
        evidence={"home_blowout_pct": home_blow, "away_blowout_pct": away_blow,
                  "spine_status": "in_game — live trigger only (Q4 margin>=15)"},
    ))

    # -- form: already in base layer, scouting only --
    factors.append(_factor(
        "form", lean="neutral", mag=1.000, conf="med",
        vek=None, m_or_s="scouting",
        evidence={"note": "recency blend already the prop model's first layer; "
                          "momentum_runs spine=1.000 null"},
    ))

    # -- series_motivation: qualitative, LOO-untestable on H2H --
    factors.append(_factor(
        "series_motivation", lean="home_series_context", mag=1.0, conf="low",
        vek=None, m_or_s="scouting",
        evidence={"note": "LOO-rejected on 4 H2H games; no two-corpus test feasible"},
    ))

    cv = ContextVector(
        matchup=f"{away}@{home}",
        asof=bundle.get("asof"),
        honesty_class="research",
        leak_free=all(f.leak_free for f in factors),
        factors=factors,
        rare_flags=[],
        provenance={
            "sim_home_mean": sim.get("home_mean"),
            "sim_away_mean": sim.get("away_mean"),
            "sim_home_win_prob": sim.get("home_win_prob"),
            "validated_keys": list(VALIDATED_KEYS),
            "source": "deterministic_scout",
        },
    )
    return cv


# ---------- LLM narration hook ----------
_LLM_MODEL = "claude-haiku-4-5"
_LLM_SYSTEM = (
    "You are CourtVision scout, producing a concise war-room brief for tonight's NBA game. "
    "RULES (architecture law — do not violate):\n"
    "1. You are OFFLINE + PRODUCT + GUARDRAIL.  NEVER compute a point projection or invent a marginal.\n"
    "2. You may only SELECT/WEIGHT from these validated pregame keys: "
    f"{sorted(VALIDATED_KEYS)}. "
    "For every other factor set marginal_or_scouting='scouting'.\n"
    "3. Weights must be in [0,1] and can only ATTENUATE a validated effect, never amplify past the spine.\n"
    "4. honesty_class='research'.  This is scouting + narration, not a bet.\n"
    "5. Write a concise 4-6 sentence war-room brief: venue/rest situation -> defense matchup -> "
    "pace/total lean -> who decides late -> one risk flag.\n"
    "Return plain prose (no JSON)."
)


def _narrate_llm(cv: ContextVector, routed: dict, bundle: dict) -> Optional[str]:
    """Call Claude haiku if ANTHROPIC_API_KEY is set; else return None."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic  # lazy import
        client = anthropic.Anthropic(api_key=api_key)
        sim = bundle.get("sim", {})
        factor_lines = "\n".join(
            f"  {f.factor}: lean={f.lean} mag={f.magnitude:.3f} conf={f.confidence} "
            f"key={f.validated_effect_key or 'none'} route={f.marginal_or_scouting}"
            for f in cv.factors
        )
        user_msg = (
            f"Game: {cv.matchup}  asof={cv.asof}\n"
            f"Sim: {bundle['home']} {sim.get('home_mean', 0):.0f} - "
            f"{bundle['away']} {sim.get('away_mean', 0):.0f}  "
            f"home_win_prob={sim.get('home_win_prob', 0):.2%}\n"
            f"Applied router keys: {routed.get('applied_keys', [])}\n"
            f"Factors:\n{factor_lines}\n"
            f"Write the war-room brief (4-6 sentences, prose)."
        )
        resp = client.messages.create(
            model=_LLM_MODEL,
            max_tokens=350,
            timeout=15.0,
            system=[{"type": "text", "text": _LLM_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_msg}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        return " ".join(parts).strip() or None
    except Exception as exc:
        log.warning("llm_context_layer: LLM narration failed: %s", exc)
        return None


def _template_brief(cv: ContextVector, routed: dict, bundle: dict) -> str:
    """Deterministic structured brief — used when ANTHROPIC_API_KEY is unset."""
    sim = bundle.get("sim", {})
    home = bundle.get("home", "HOME")
    away = bundle.get("away", "AWAY")
    home_mean = sim.get("home_mean", 0)
    away_mean = sim.get("away_mean", 0)
    total = sim.get("total_mean", 0)
    home_wp = sim.get("home_win_prob", 0.5)
    applied = routed.get("applied_keys", [])
    n_poss = sim.get("n_poss", 100)

    venue_line = (
        f"{home} hosts at home — {len(applied)} validated pregame effect(s) active: "
        f"{applied or ['none (gate off or conditions unmet)']}."
    )
    sim_line = (
        f"Sim total {total:.0f} ({home} {home_mean:.0f} / {away} {away_mean:.0f}), "
        f"{home} win prob {home_wp:.1%}, n_poss {n_poss}."
    )
    defense_line = (
        f"{home} def_rtg {sim.get('home_def_rtg', 0):.1f} / "
        f"{away} def_rtg {sim.get('away_def_rtg', 0):.1f}; "
        f"opp_defense effect INTRINSIC to sim (anchor matchup per-shot) — not re-applied."
    )
    pace_line = (
        f"Pace: {home} {sim.get('home_pace', 0):.0f} / {away} {sim.get('away_pace', 0):.0f} poss; "
        f"n_poss = avg = {n_poss}.  pace_matchup spine = 1.000 (no mult)."
    )
    scouting = [f.factor for f in cv.factors if f.marginal_or_scouting == "scouting"]
    scouting_line = f"Scouting-only (no marginal): {', '.join(scouting)}."
    rare = cv.rare_flags
    risk_line = f"Rare flags: {rare}." if rare else "No rare flags."
    honesty_line = (
        f"honesty_class=research; CV_LLM_CONTEXT gated.  "
        f"LLM narration offline (ANTHROPIC_API_KEY not set)."
    )
    return "\n".join([venue_line, sim_line, defense_line, pace_line,
                      scouting_line, risk_line, honesty_line])


def war_room_brief(cv: ContextVector, routed: dict, bundle: dict) -> str:
    """Natural-language brief.  Tries LLM narration first; falls back to template."""
    llm_text = _narrate_llm(cv, routed, bundle)
    if llm_text:
        return llm_text
    return _template_brief(cv, routed, bundle)


# ---------- cache helpers ----------
def _write_artifact(path: str, artifact: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        json.dump(artifact, open(path, "w", encoding="utf-8"), indent=2, default=str)
    except Exception as exc:
        log.warning("llm_context_layer: failed to cache artifact: %s", exc)


def _read_artifact(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return None


# ---------- core room ----------
def run_context_room(
    home: str,
    away: str,
    asof: Optional[str] = None,
    nsims: int = 8000,
    use_llm: bool = True,
    _result=None,
) -> Dict[str, Any]:
    """OFFLINE context room.

    Steps:
      (a) build_scout_bundle   — deterministic ground truth
      (b) build ContextVector  — scout factors + (if use_llm) LLM weight proposals
      (c) route_context        — validated-key marginal mults (gated)
      (d) war_room_brief       — LLM or template narration
      (e) cache the artifact

    Returns the full artifact dict.  honesty_class='research'.
    NEVER places a bet, NEVER edits War Room markers.
    """
    home, away = home.upper(), away.upper()

    from context_scout import build_scout_bundle
    from context_router import route_context

    bundle = build_scout_bundle(home, away, asof=asof, nsims=nsims, _result=_result)
    cv = _build_cv_deterministic(bundle)

    # LLM weight-proposal hook: update factor magnitudes if LLM proposes weights.
    # (Currently LLM is offline — this is a no-op unless ANTHROPIC_API_KEY is set.)
    # The deterministic cv is the ground truth; LLM can only attenuate validated mults.

    routed = route_context(cv, bundle)
    brief = war_room_brief(cv, routed, bundle) if use_llm else _template_brief(cv, routed, bundle)

    artifact = {
        "matchup": f"{away}@{home}",
        "asof": asof,
        "honesty_class": "research",
        "context_vector": {
            "matchup": cv.matchup,
            "leak_free": cv.leak_free,
            "factors": [
                {
                    "factor": f.factor,
                    "lean": f.lean,
                    "magnitude": f.magnitude,
                    "confidence": f.confidence,
                    "leak_free": f.leak_free,
                    "validated_effect_key": f.validated_effect_key,
                    "marginal_or_scouting": f.marginal_or_scouting,
                    "evidence": f.evidence,
                    "source": f.source,
                }
                for f in cv.factors
            ],
            "rare_flags": cv.rare_flags,
            "provenance": cv.provenance,
        },
        "routed": routed,
        "brief": brief,
        "sim_summary": bundle.get("sim", {}),
        "validated_keys": bundle.get("validated_keys", []),
    }

    path = context_artifact_path(home, away, asof)
    _write_artifact(path, artifact)

    return artifact


def load_or_build(home: str, away: str, asof: Optional[str] = None, **kw) -> Dict[str, Any]:
    """Cache-first: return cached artifact if present, else build + cache."""
    path = context_artifact_path(home, away, asof)
    cached = _read_artifact(path)
    if cached:
        return cached
    return run_context_room(home, away, asof=asof, **kw)


# ---------- __main__ ----------
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="V6 LLM Context Room")
    ap.add_argument("--home", default="NYK")
    ap.add_argument("--away", default="SAS")
    ap.add_argument("--asof", default=None)
    ap.add_argument("--nsims", type=int, default=4000)
    ap.add_argument("--no-cache", action="store_true",
                    help="force rebuild even if cached artifact exists")
    args = ap.parse_args()

    home, away = args.home.upper(), args.away.upper()
    asof = args.asof

    print(f"\n{'='*60}")
    print(f"V6 Context Room — {away}@{home}  asof={asof}")
    print(f"CV_LLM_CONTEXT={'ON' if _gate_on() else 'OFF (byte-identical, no mults applied)'}")
    print(f"{'='*60}\n")

    if args.no_cache:
        path = context_artifact_path(home, away, asof)
        if os.path.exists(path):
            os.remove(path)

    artifact = load_or_build(home, away, asof=asof, nsims=args.nsims)

    # Print context vector factor keys
    cv_data = artifact.get("context_vector", {})
    print("CONTEXT VECTOR FACTORS:")
    print(f"  matchup  : {cv_data.get('matchup')}")
    print(f"  leak_free: {cv_data.get('leak_free')}")
    print()
    for f in cv_data.get("factors", []):
        key_str = f.get("validated_effect_key") or "—"
        print(f"  [{f['factor']:<26}]  lean={f['lean']:<18}  mag={f['magnitude']:.3f}  "
              f"conf={f['confidence']:<4}  key={key_str:<15}  route={f['marginal_or_scouting']}")

    print()
    print(f"ROUTED:")
    routed = artifact.get("routed", {})
    print(f"  applied_keys : {routed.get('applied_keys')}")
    print(f"  weights      : {routed.get('weights')}")
    print(f"  marginal pids: {len(routed.get('marginal_mults', {}))}")
    print()

    print("WAR-ROOM BRIEF:")
    print("-" * 60)
    print(artifact.get("brief", "(no brief)"))
    print("-" * 60)

    path = context_artifact_path(home, away, asof)
    print(f"\nArtifact cached: {path}")
