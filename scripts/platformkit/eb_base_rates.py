"""eb_base_rates.py — Empirical-Bayes regularized per-(team, season) base rates.

Applies the C15 hierarchical pooled priors (``hier_priors.eb_beta_binomial``) to a
GENUINELY SPARSE real grain: a team's WIN rate within a single SEASON (~82 NBA /
~162 MLB games — noisy).  EB shrinks each (team, season) rate toward the pooled
league mean (~0.5, since wins are zero-sum), more for short seasons.  The result is
written as a browsable brain artifact so the organized brain carries *regularized*
team base rates instead of over-trusting small single-season samples.

A PRIOR IS NOT AN EDGE.  Shrinkage improves small-sample ESTIMATES; it does not
imply beating the market.  Heavy (pandas) load is lazy inside the default loader;
tests inject grouped records so the EB logic stays pytest-clean.

CLI: ``python -m scripts.platformkit.eb_base_rates [--sport nba] [--json] [--write]``
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np

from scripts.platformkit.hier_priors import eb_beta_binomial

_REPO_ROOT = Path(__file__).resolve().parents[2]

# sport -> how to read games + name the winner.  team_a/team_b are home/away cols;
# win_col is 1 when the HOME team won.
_SPORT_CFG: Dict[str, Dict[str, str]] = {
    "nba": {"path": "data/domains/basketball_nba/games.parquet",
            "team_a": "home_team", "team_b": "away_team",
            "win_col": "home_win", "season": "season"},
    "mlb": {"path": "data/domains/mlb/games.parquet",
            "team_a": "home_team", "team_b": "away_team",
            "win_col": "target_home_win", "season": "season"},
}
_ORG_DIR = {"nba": "NBA", "mlb": "MLB"}
_NOTE = ("A PRIOR IS NOT AN EDGE — EB shrinkage regularizes sparse single-season "
         "team rates toward the pooled mean; it does not imply beating the market.")

Loader = Callable[[str], List[Dict]]


def _default_loader(sport: str) -> List[Dict]:
    """Read games and group to per-(team, season) {team, season, k=wins, n=games}.

    Heavy (pandas) — imported here, never at module top.
    """
    import pandas as pd  # noqa: PLC0415

    cfg = _SPORT_CFG[sport]
    df = pd.read_parquet(_REPO_ROOT / cfg["path"])
    a, b, w, s = cfg["team_a"], cfg["team_b"], cfg["win_col"], cfg["season"]
    home = pd.DataFrame({"team": df[a], "season": df[s], "won": df[w].astype(float)})
    away = pd.DataFrame({"team": df[b], "season": df[s], "won": 1.0 - df[w].astype(float)})
    both = pd.concat([home, away], ignore_index=True)
    g = both.groupby(["team", "season"])["won"].agg(["sum", "count"]).reset_index()
    return [{"team": str(r.team), "season": str(r.season),
             "k": float(r.sum), "n": float(r.count)} for r in g.itertuples()]


def build_for_sport(sport: str, *, loader: Optional[Loader] = None) -> Dict:
    """EB-shrink per-(team, season) win rates for *sport*.

    Returns sport, n_groups, prior (a,b,pooled_mean,kappa), groups (each with raw +
    shrunk rate and the shrink magnitude), mean_abs_shrink, and the honest note.
    """
    if sport not in _SPORT_CFG:
        return {"sport": sport, "error": f"sport not wired (have {list(_SPORT_CFG)})",
                "note": _NOTE}
    load = loader or _default_loader
    try:
        records = load(sport)
    except Exception as exc:  # noqa: BLE001
        return {"sport": sport, "error": str(exc), "note": _NOTE}
    if not records:
        return {"sport": sport, "error": "no records", "note": _NOTE}

    k = np.array([r["k"] for r in records], dtype=float)
    n = np.array([r["n"] for r in records], dtype=float)
    eb = eb_beta_binomial(k, n)
    raw, shrunk = eb["raw_rates"], eb["shrunk_rates"]

    groups = []
    for i, r in enumerate(records):
        groups.append({
            "team": r["team"], "season": r["season"], "n": int(n[i]),
            "raw_rate": round(float(raw[i]), 4),
            "shrunk_rate": round(float(shrunk[i]), 4),
            "abs_shrink": round(float(abs(shrunk[i] - raw[i])), 4),
        })
    groups.sort(key=lambda x: (-x["abs_shrink"], x["team"], x["season"]))
    return {
        "sport": sport,
        "n_groups": len(records),
        "prior": {"a": round(eb["a"], 4), "b": round(eb["b"], 4),
                  "pooled_mean": round(eb["pooled_mean"], 4),
                  "kappa": round(eb["kappa"], 2)},
        "mean_abs_shrink": round(float(np.mean(np.abs(shrunk - raw))), 4),
        "groups": groups,
        "note": _NOTE,
    }


def _render_md(rep: Dict) -> str:
    p = rep["prior"]
    lines = [
        "---\ntags: [organized, base-rates, eb]\n---",
        f"# {rep['sport'].upper()} — EB-Regularized Team Base Rates (per season)\n",
        f"> **{_NOTE}**\n",
        f"**Pooled prior:** Beta(a={p['a']}, b={p['b']}) · pooled_mean={p['pooled_mean']} "
        f"· kappa={p['kappa']} · groups={rep['n_groups']} · "
        f"mean |shrink|={rep['mean_abs_shrink']}\n",
        "Each (team, season) win rate is shrunk toward the pooled mean — more for "
        "short seasons (small n). Largest shrinkage first.\n",
        "| Team | Season | Games | Raw rate | EB shrunk | |Δ| |",
        "|------|--------|------:|---------:|----------:|----:|",
    ]
    for grp in rep["groups"][:60]:
        lines.append(f"| {grp['team']} | {grp['season']} | {grp['n']} | "
                     f"{grp['raw_rate']:.3f} | {grp['shrunk_rate']:.3f} | {grp['abs_shrink']:.3f} |")
    return "\n".join(lines) + "\n"


def write_artifact(sport: str, rep: Dict, organized_root: Optional[Path] = None) -> Optional[str]:
    """Write the per-sport base-rate brain artifact; return the path (or None)."""
    if "error" in rep or sport not in _ORG_DIR:
        return None
    root = organized_root or (_REPO_ROOT / "vault" / "_Organized")
    out = root / _ORG_DIR[sport] / "_Team_Base_Rates_EB.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render_md(rep), encoding="utf-8")
    return str(out)


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    sport = None
    if "--sport" in argv:
        i = argv.index("--sport")
        sport = argv[i + 1] if i + 1 < len(argv) else None
    sports = [sport] if sport else list(_SPORT_CFG)
    out: Dict[str, Dict] = {}
    for sp in sports:
        rep = build_for_sport(sp)
        if "--write" in argv:
            rep["artifact"] = write_artifact(sp, rep)
        out[sp] = rep
    if "--json" in argv:
        print(json.dumps({s: {k: v for k, v in r.items() if k != "groups"}
                          for s, r in out.items()}, indent=2))
        return 0
    for sp, rep in out.items():
        if "error" in rep:
            print(f"\n[{sp}] ERROR: {rep['error']}")
            continue
        p = rep["prior"]
        print(f"\n[{sp}] {rep['n_groups']} (team,season) groups · prior Beta("
              f"{p['a']},{p['b']}) pooled={p['pooled_mean']} kappa={p['kappa']} "
              f"· mean|shrink|={rep['mean_abs_shrink']}")
        for grp in rep["groups"][:5]:
            print(f"   {grp['team']:<5} {grp['season']:<8} n={grp['n']:>3} "
                  f"raw={grp['raw_rate']:.3f} -> shrunk={grp['shrunk_rate']:.3f} "
                  f"(abs_shrink={grp['abs_shrink']:.3f})")
        if rep.get("artifact"):
            print(f"   artifact -> {rep['artifact']}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
