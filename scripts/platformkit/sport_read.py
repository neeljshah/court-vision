"""scripts.platformkit.sport_read — Per-sport intelligence READ on the brain seam.

LLM (if any) writes narrative prose only; gate+engine compute every number.
Returns understanding + calibrated surface, NEVER an un-gated pick.
Default: LLM-OFF.  Markets efficient; calibration not edge.

Public API:
    build_sport_read(sport, jd=None, root=None, use_llm=None, top_k=6) -> dict
    render_markdown(read: dict) -> str
CLI:
    python -m scripts.platformkit.sport_read --sport nba [--json] [--markdown]
"""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.sport_read_specs import (
    HONEST_BANNER as _HONEST_BANNER,
    PROVENANCE_MODULES as _PROVENANCE_MODULES,
    QUERY_SPECS as _QUERY_SPECS,
    SAFE_TEMPLATE as _SAFE_TEMPLATE,
    DEFAULT_PRIORS as _DEFAULT_PRIORS,
)


def _classify_hits(hits: list) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {"archetypes": [], "schemes": [], "trends": []}
    kind_map = {"archetype": "archetypes", "scheme": "schemes", "trend": "trends"}
    seen: set = set()
    for h in hits:
        bucket = kind_map.get(h.kind)
        # MLB/Tennis tag their scheme notes 'concept' (DefensiveSchemes/), so they
        # never reach the 'schemes' bucket via kind alone — route them by provenance.
        if bucket is None and h.kind == "concept" and "scheme" in (h.provenance or "").lower():
            bucket = "schemes"
        if bucket and h.provenance not in seen:
            seen.add(h.provenance)
            out[bucket].append({"title": h.title, "provenance": h.provenance,
                                 "prevalence": h.prevalence})
    return out


def _safe_narrative(sport: str, scout: dict, surface: Optional[dict]) -> str:
    return _SAFE_TEMPLATE.format(
        sport=sport.upper(),
        n_archetypes=len(scout["archetypes"]),
        n_schemes=len(scout["schemes"]),
        surface_note=(
            "Calibrated engine surface attached (totals/spread/moneyline from sim joint "
            "distribution); use as structural context, not a pick. "
        ) if surface is not None else "No simulation surface provided (jd=None). ",
    )


def _llm_narrative(sport: str, scout: dict, priors: dict,
                   surface: Optional[dict], model: str) -> str:
    try:
        import anthropic  # noqa: PLC0415
    except ImportError:
        return _safe_narrative(sport, scout, surface)
    try:
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        arch = ", ".join(a["title"] for a in scout["archetypes"]) or "none found"
        sch  = ", ".join(s["title"] for s in scout["schemes"]) or "none found"
        trnd = ", ".join(t["title"] for t in scout["trends"]) or "none found"
        msg = (
            f"Sport: {sport.upper()}\nArchetypes: {arch}\nSchemes: {sch}\nTrends: {trnd}\n"
            f"Market verdict: {priors.get('market_efficiency','efficient')}; "
            f"signals: {priors.get('tested_signals','REJECT')}\n"
            f"Surface present: {'yes' if surface else 'no'}\n\n"
            "Write 2-3 sentences on the style landscape and honest market verdict. "
            "If surface present, direct reader to use it as structural context only. "
            "DO NOT state any probability, odds, edge %, ROI, or betting outcome."
        )
        resp = client.messages.create(
            model=model, max_tokens=256,
            system=(
                "Sport-intelligence narrator. MUST NOT state probability, odds, ROI, "
                "expected value, edge, 'bet', 'pick', 'profitable', or 'guaranteed'. "
                "Never claim market inefficiency. Concise honest prose only."
            ),
            messages=[{"role": "user", "content": msg}],
        )
        return resp.content[0].text.strip()
    except Exception:  # noqa: BLE001
        return _safe_narrative(sport, scout, surface)


def build_sport_read(
    sport: str,
    jd: Any = None,
    root: Optional[Path] = None,
    use_llm: Optional[bool] = None,
    top_k: int = 6,
) -> Dict[str, Any]:
    """Build a per-sport intelligence READ dict.

    Returns sport, banner, scout, priors, surface (or None), narrative,
    critique, edge_claimed (always False), provenance.
    All numbers come only from surface; no un-gated pick key exists.
    """
    sport_lower = sport.lower()
    competence: Optional[Dict[str, Any]] = None
    # SCOUT
    try:
        from scripts.platformkit.brain_query import (  # noqa: PLC0415
            brain_query, prior_verdicts, _resolve_root,
        )
        rp = root if isinstance(root, Path) else (Path(root) if root else None)
        seen: set = set()
        hits: list = []
        for tmpl, knd in _QUERY_SPECS:
            for h in brain_query(tmpl.format(sport=sport_lower), sport=sport_lower,
                                 kind=knd, root=rp, top_k=top_k):
                if h.path not in seen:
                    seen.add(h.path); hits.append(h)
        scout = _classify_hits(hits)
        priors = prior_verdicts(sport=sport_lower, root=rp)
    except Exception:  # noqa: BLE001
        scout = {"archetypes": [], "schemes": [], "trends": []}
        priors = dict(_DEFAULT_PRIORS)
    # COMPETENCE (isolated: a card-parse error must NOT discard good scout/priors)
    try:
        from scripts.platformkit.brain_query import _resolve_root  # noqa: PLC0415
        from scripts.platformkit.model_card import parse_card_metrics  # noqa: PLC0415
        rp2 = root if isinstance(root, Path) else (Path(root) if root else None)
        competence = parse_card_metrics(sport_lower, _resolve_root(rp2))
    except Exception:  # noqa: BLE001
        competence = None
    # SURFACE
    surface: Optional[Dict[str, Any]] = None
    if jd is not None:
        try:
            from scripts.platformkit.pipeline_integration import assemble_read  # noqa: PLC0415
            surface = assemble_read(sport_lower, jd).get("surface")
        except Exception:  # noqa: BLE001
            surface = None
    # NARRATIVE
    model = os.environ.get("CV_READ_MODEL", "claude-opus-4-8")
    want = use_llm is True or (use_llm is None and bool(os.environ.get("ANTHROPIC_API_KEY")))
    if use_llm is False:
        want = False
    narrative = (_llm_narrative(sport_lower, scout, priors, surface, model)
                 if want else _safe_narrative(sport_lower, scout, surface))
    # SELF-CHECK
    chips = [i["provenance"] for cat in ("archetypes", "schemes", "trends")
             for i in scout[cat] if i.get("provenance")]
    from scripts.platformkit.brain_critic import critique_finding  # noqa: PLC0415
    crit = critique_finding({"claim": narrative, "citations": chips},
                            dedup_threshold=0.6, min_citation=0.0)
    if crit.edge_claim_detected:
        narrative = _safe_narrative(sport_lower, scout, surface)
        crit = critique_finding({"claim": narrative, "citations": chips},
                                dedup_threshold=0.6, min_citation=0.0)
    return {
        "sport": sport_lower,
        "banner": _HONEST_BANNER,
        "scout": scout,
        "priors": priors,
        "competence": competence,
        "surface": surface,
        "narrative": narrative,
        "critique": {"passes": crit.passes, "edge_claim_detected": crit.edge_claim_detected,
                     "citation_coverage": round(crit.citation_coverage, 4),
                     "reasons": crit.reasons},
        "edge_claimed": False,
        "provenance": _PROVENANCE_MODULES,
    }


def render_markdown(read: Dict[str, Any]) -> str:
    """Render a per-sport intelligence read as human-readable Markdown."""
    sport = read.get("sport", "unknown").upper()
    L: List[str] = [f"## Per-Sport Intelligence Read — {sport}", "",
                    f"> **{read.get('banner', '')}**", ""]
    scout = read.get("scout", {})

    def _section(header: str, items: list, empty: str) -> None:
        L.append(f"### {header}")
        if items:
            for it in items:
                prov = it.get("provenance", "")
                prev = f"  _(prevalence={it['prevalence']:.3f})_" if "prevalence" in it else ""
                L.append(f"- **{it['title']}**{prev}  `{prov}`")
        else:
            L.append(f"- _{empty}_")
        L.append("")

    _section("Style Landscape — Archetypes", scout.get("archetypes", []),
             "no archetype notes found in vault for this sport")
    _section("Schemes", scout.get("schemes", []), "no scheme notes found")
    _section("Trends", scout.get("trends", []), "no trend notes found")

    priors = read.get("priors", {})
    L += [
        "### Honest Market Verdict (Empirical)",
        f"- Market efficiency: **{priors.get('market_efficiency', 'efficient')}**",
        f"- Tested signals: **{priors.get('tested_signals', 'REJECT')}**",
        f"- edge_claimed: **{read.get('edge_claimed', False)}**",
    ]
    if priors.get("note"):
        L.append(f"- Note: _{priors['note']}_")
    L.append("")

    comp = read.get("competence")
    if comp:
        L += [
            "### Model Competence _(validated OOS — knows what it knows)_",
            f"- Calibrated rating: Brier **{comp['brier']}** · logloss {comp['logloss']} · "
            f"ECE **{comp['ece']}** (calibrator: {comp.get('calibrator')})",
            "- A calibration metric, NOT a market edge.", "",
        ]

    surface = read.get("surface")
    if surface is not None:
        L.append("### Calibrated Engine Surface _(structure context, not a pick)_")
        ml = surface.get("moneyline", {})
        if ml:
            tie = f"  tie={ml['tie']:.4f}" if "tie" in ml else ""
            L.append(f"- Moneyline: home={ml.get('home',0.0):.4f}  away={ml.get('away',0.0):.4f}{tie}")
        means = surface.get("score_means", {})
        if means:
            L.append(f"- Score means: home={means.get('home',0.0):.1f}  away={means.get('away',0.0):.1f}")
        totals = surface.get("totals", [])
        if totals:
            t = totals[0]
            L.append(f"- Totals ({t['line']:g}): over={t['over']:.4f}  under={t['under']:.4f}")
        L.append("")
    else:
        L += ["### Surface", "- _(no JointDistribution provided — no numbers fabricated)_", ""]

    crit = read.get("critique", {})
    L += [
        "### Intelligence Narrative", read.get("narrative", ""), "",
        "### Self-Check (brain_critic)",
        f"- passes: **{crit.get('passes', False)}**",
        f"- edge_claim_detected: **{crit.get('edge_claim_detected', False)}**",
        f"- citation_coverage: {crit.get('citation_coverage', 0.0):.2f}",
    ]
    for r in crit.get("reasons", []):
        L.append(f"  - {r}")
    L += ["", "### Provenance"] + [f"- `{p}`" for p in read.get("provenance", [])]
    return "\n".join(L)


def _cli(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="sport_read: per-sport intelligence READ; no edge.")
    ap.add_argument("--sport", default="nba")
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--use-llm", action="store_true", default=False)
    ap.add_argument("--demo-surface", action="store_true", default=False,
                    help="Build demo JointDistribution to show real surface.")
    a = ap.parse_args(argv)
    jd = None
    if a.demo_surface:
        import numpy as np  # noqa: PLC0415
        from scripts.platformkit.sim_framework import JointDistribution  # noqa: PLC0415
        rng = np.random.default_rng(42)
        mu = (112.0, 109.0) if a.sport.lower() == "nba" else (2.0, 1.8)
        sig = 12.0 if a.sport.lower() == "nba" else 1.2
        h = np.clip(rng.normal(mu[0], sig, 3000), 0, None)
        aw = np.clip(rng.normal(mu[1], sig, 3000), 0, None)
        jd = JointDistribution(np.stack([h, aw], axis=1), joint_quality="simulated")
    read = build_sport_read(sport=a.sport, jd=jd,
                            use_llm=a.use_llm if a.use_llm else None, top_k=a.top_k)
    if a.json:
        def _j(o: Any) -> Any:
            try:
                import numpy as _np  # noqa: PLC0415
                if isinstance(o, _np.floating): return float(o)
                if isinstance(o, _np.integer): return int(o)
            except ImportError:
                pass
            raise TypeError(type(o))
        print(json.dumps(read, indent=2, default=_j))
        return 0
    print(render_markdown(read))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
