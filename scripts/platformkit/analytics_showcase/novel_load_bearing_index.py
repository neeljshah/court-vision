"""Novel stat #4 -- Load-Bearing Index (LBI).

METRIC: per team, its single most-indispensable player's win-prob dependence,
under TWO independent estimators, plus an agreement flag. Gives a league
fragility spectrum from "one-star-fragile" to "distributed".

TWO ESTIMATORS (per team):
    (a) Elo on/off  : delta_winprob = p_win_with - p_win_without   (cf_star_removal.json)
    (b) raw with/without : delta_win_rate = win_rate_active - win_rate_missed, taken as the
        team's MAX over qualified players                          (ctx_lineup_proxy.json)
    agreement = the SAME player is ranked #1 by both estimators (name-normalized).

Reads two committed artifacts; edge_claimed=False -- a DESCRIPTIVE fragility map,
not a causal player-impact or edge claim.

Usage:
    python -m scripts.platformkit.analytics_showcase.novel_load_bearing_index
    python -m scripts.platformkit.analytics_showcase.novel_load_bearing_index --check
"""
import json
import os
import unicodedata

try:
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:
    from _clone_safe import verify_recorded_artifact

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHOWCASE = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase")
IN_ELO = os.path.join(SHOWCASE, "out", "cf_star_removal.json")       # estimator (a)
IN_RAW = os.path.join(SHOWCASE, "out", "ctx_lineup_proxy.json")      # estimator (b)
OUT_JSON = os.path.join(SHOWCASE, "out", "novel_load_bearing_index.json")
OUT_PNG = os.path.join(ROOT, "docs", "img", "novel_load_bearing_index.png")

PRIOR_ART_VERDICT = "INCREMENTAL"
PRIOR_ART_CITATION = (
    "On/Off Win Probability tables (inpredictable, stats.inpredictable.com/nba/onoff.php), "
    "'record-without-star' splits, and player-impact-on-win-chances (arXiv 1604.03186) all "
    "exist. Single-method fragility is NOT new. The novel twist is a standardized league-wide "
    "fragility ranking CROSS-VALIDATED by two independent estimators with an agreement flag."
)
DECLARED_CONFOUNDS = [
    "both estimators carry the ROSTER CONFOUND both source files label explicitly: why a player "
    "missed is entangled with injury clustering, rest, blowout pulls, and replacement lineup -- "
    "none controlled. NOT a causal player-impact estimate.",
    "the feeds cover DIFFERENT seasons (Elo on/off = 2024-25; raw with/without = 2025-26), so "
    "agreement is DIRECTIONAL corroboration, not a paired estimate.",
    "estimator (a) is win prob vs a league-average opponent on a neutral floor; estimator (b) is "
    "raw team win-rate active-vs-missed. The two axes are related but not the same scale.",
]


def _norm(name):
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(c for c in s.lower() if c.isalnum())


def build():
    elo = json.loads(open(IN_ELO, encoding="utf-8").read())
    raw = json.loads(open(IN_RAW, encoding="utf-8").read())

    # estimator (a): one top player per team already
    a_by_team = {t["team_abbr"].upper(): t for t in elo.get("teams", [])}

    # estimator (b): per team, the max-delta_win_rate qualified player
    b_by_team = {}
    for p in raw.get("players", []):
        team = (p.get("team") or "").upper()
        if not team:
            continue
        cur = b_by_team.get(team)
        if cur is None or p["delta_win_rate"] > cur["delta_win_rate"]:
            b_by_team[team] = p

    rows = []
    for team in sorted(set(a_by_team) | set(b_by_team)):
        a = a_by_team.get(team)
        b = b_by_team.get(team)
        agree = None
        if a and b:
            agree = _norm(a.get("player_name")) == _norm(b.get("player_name"))
        rows.append({
            "team": team,
            "estimator_a_elo_onoff": None if not a else {
                "player_name": a.get("player_name"),
                "delta_winprob": a.get("delta_winprob"),
                "on_off_net_rating_delta": a.get("on_off_net_rating_delta"),
            },
            "estimator_b_raw_withwithout": None if not b else {
                "player_name": b.get("player_name"),
                "delta_win_rate": b.get("delta_win_rate"),
                "n_active": b.get("n_active"),
                "n_missed": b.get("n_missed"),
            },
            "agreement_same_player": agree,
        })
    # fragility spectrum: rank by estimator (a) delta_winprob (complete for all 30 teams)
    rows.sort(key=lambda r: (r["estimator_a_elo_onoff"] or {}).get("delta_winprob", -1), reverse=True)

    both = [r for r in rows if r["agreement_same_player"] is not None]
    n_agree = sum(1 for r in both if r["agreement_same_player"])

    payload = {
        "stat_name": "Load-Bearing Index",
        "abbrev": "LBI",
        "edge_claimed": False,
        "descriptive_only": True,
        "metric_definition": "Per team, the win-prob dependence on its single most-indispensable player, under two independent estimators, with a cross-method agreement flag.",
        "formula": "LBI_a = max_player (p_win_with - p_win_without) [Elo on/off]; LBI_b = max_player (win_rate_active - win_rate_missed) [raw]; agreement = same #1 player.",
        "source_artifacts": [
            os.path.relpath(IN_ELO, ROOT).replace("\\", "/"),
            os.path.relpath(IN_RAW, ROOT).replace("\\", "/"),
        ],
        "as_of": {"estimator_a": elo.get("as_of"), "estimator_b": raw.get("as_of")},
        "prior_art_verdict": PRIOR_ART_VERDICT,
        "prior_art_citation": PRIOR_ART_CITATION,
        "declared_confounds": DECLARED_CONFOUNDS,
        "agreement_summary": {"n_teams_both_estimators": len(both), "n_agree": n_agree,
                              "agree_rate": round(n_agree / len(both), 4) if both else None},
        "results": rows,
        "headline": _headline(rows, both, n_agree),
        "index_card": None,
        "plot_written": False,
    }
    payload["index_card"] = _card(payload)
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload


def _headline(rows, both, n_agree):
    if not rows:
        return "No teams available."
    top = rows[0]
    a = top["estimator_a_elo_onoff"] or {}
    rate = f"{n_agree}/{len(both)}" if both else "n/a"
    return (f"Most one-star-fragile: {top['team']} ({a.get('player_name')}, "
            f"delta_winprob {a.get('delta_winprob')}). Two estimators name the same #1 player "
            f"for {rate} teams (directional cross-check, different seasons).")


def _card(p):
    return {
        "stat_name": p["stat_name"], "abbrev": p["abbrev"], "module": "novel_load_bearing_index",
        "formula": p["formula"], "prior_art_verdict": p["prior_art_verdict"],
        "headline": p["headline"], "edge_claimed": False,
        "source_artifacts": p["source_artifacts"],
        "chart": os.path.relpath(OUT_PNG, ROOT).replace("\\", "/"),
        "n_results": len(p["results"]),
    }


def plot(payload):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    pts = [r for r in payload["results"] if r["estimator_a_elo_onoff"] and r["estimator_b_raw_withwithout"]]
    if not pts:
        return False
    xs = [r["estimator_a_elo_onoff"]["delta_winprob"] for r in pts]
    ys = [r["estimator_b_raw_withwithout"]["delta_win_rate"] for r in pts]
    colors = ["#2b8a3e" if r["agreement_same_player"] else "#888888" for r in pts]
    fig, ax = plt.subplots(figsize=(7.5, 6.5))
    ax.scatter(xs, ys, c=colors, s=45, zorder=3)
    for r, x, yv in zip(pts, xs, ys):
        ax.annotate(r["team"], (x, yv), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.axhline(0, color="gray", linewidth=0.6)
    ax.axvline(0, color="gray", linewidth=0.6)
    ax.set_xlabel("estimator (a): Elo on/off delta_winprob  [2024-25]")
    ax.set_ylabel("estimator (b): raw win_rate active-minus-missed  [2025-26]")
    ax.set_title("Load-Bearing Index: two-estimator team fragility\n"
                 "green = both estimators name the same #1 player. edge_claimed=False", fontsize=10)
    fig.tight_layout()
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)
    return True


def _validate(d):
    assert d["edge_claimed"] is False
    assert d["results"], "no teams"


def check():
    if not (os.path.exists(IN_ELO) and os.path.exists(IN_RAW)):
        verify_recorded_artifact(OUT_JSON, _validate, "novel_load_bearing_index")
        return
    payload = build()
    _validate(payload)
    den = next((r for r in payload["results"] if r["team"] == "DEN"), None)
    assert den and abs(den["estimator_a_elo_onoff"]["delta_winprob"] - 0.5822) < 1e-4, den
    cha = next((r for r in payload["results"] if r["team"] == "CHA"), None)
    assert cha and abs(cha["estimator_b_raw_withwithout"]["delta_win_rate"] - 0.4543) < 1e-4, cha
    payload["plot_written"] = plot(payload)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"OK: novel_load_bearing_index ({len(payload['results'])} teams, "
          f"agree {payload['agreement_summary']['n_agree']}/{payload['agreement_summary']['n_teams_both_estimators']}, "
          f"plot={payload['plot_written']})")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        check()
    else:
        p = build()
        p["plot_written"] = plot(p)
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=2)
        print(json.dumps({"headline": p["headline"], "agreement_summary": p["agreement_summary"],
                          "top5_fragile": [{"team": r["team"],
                                            "a": r["estimator_a_elo_onoff"],
                                            "b": r["estimator_b_raw_withwithout"],
                                            "agree": r["agreement_same_player"]} for r in p["results"][:5]]}, indent=2))
