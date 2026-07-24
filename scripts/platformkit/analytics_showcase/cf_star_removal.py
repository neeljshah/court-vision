"""
Counterfactual star-removal win-probability deltas (NBA).

QUESTION: "How many pregame win-probability points is each team's top player
worth?" -- estimated by REMOVING the player's measured on/off net-rating
contribution from the team's strength and re-pricing win prob through the
repo's OWN Elo->prob curve.

METHOD (declared, not tuned to output):
  1. Team strength R = end-of-2024-25 Elo (data/models/elo_state.json).
  2. Each team's "star" = its player with the largest on/off net_rating_delta
     (data/cache/intel_claims/nba_lineup_context_claims.jsonl, 2024_25 slice,
     already floored at min_on>=500 / n_games>=30 by the source claim).
  3. star_elo = net_rating_delta * ELO_PER_NETRATING_POINT, converting the
     on/off point swing into Elo points. Conversion is FROZEN and anchored to
     the repo's own ELO_HFA=76 Elo ~ 3.0-pt home edge (76/3.0 = 25.33 Elo/pt),
     NOT fit to make any name look bigger or smaller.
  4. p_with     = elo_logistic(R - 1500)          [vs league-average, neutral]
     p_without  = elo_logistic(R - star_elo - 1500)
     delta_winprob = p_with - p_without.

CEILING / HONESTY (declared on EVERY row):
  On/off net_rating_delta OVERSTATES an individual's marginal value -- it is a
  full-lineup on-vs-off swing entangled with the ROSTER CONFOUND (who else is on
  the floor, coach trust, opponent strength, garbage time), none controlled for.
  So these deltas are a CEILING, not a causal player-value estimate. The
  net-rating->Elo conversion is itself a declared assumption. DESCRIPTIVE_ONLY,
  edge_claimed=False -- NOT a betting/ROI claim.

Output: out/cf_star_removal.json + docs/img/cf_star_removal.png (top-15).
Usage:
    python -m scripts.platformkit.analytics_showcase.cf_star_removal
    python -m scripts.platformkit.analytics_showcase.cf_star_removal --check
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:
    from _clone_safe import verify_recorded_artifact

REPO_ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
OUT_JSON = HERE / "out" / "cf_star_removal.json"
OUT_PNG = REPO_ROOT / "docs" / "img" / "cf_star_removal.png"
ELO_STATE = REPO_ROOT / "data" / "models" / "elo_state.json"
CLAIMS_STORE = REPO_ROOT / "data" / "cache" / "intel_claims" / "nba_lineup_context_claims.jsonl"
CLAIM_ID = "nba_lineup_context_net_rating_delta_2024_25"
AS_OF = "2024-25 (Elo end-of-season) x 2024_25 on/off slice"

# Frozen, anchored, NOT tuned to output. ELO_HFA=76 Elo ~ 3.0-pt home edge
# (elo_config.ELO_HFA) -> 76/3.0 = 25.33 Elo per point of net rating.
ELO_PER_NETRATING_POINT = 76.0 / 3.0
REF_ELO = 1500.0  # league-average opponent, neutral site

CEILING_CAVEAT = (
    "CEILING: on/off net_rating_delta overstates marginal individual value "
    "(ROSTER CONFOUND -- full-lineup on-vs-off swing, not controlled for "
    "teammates/opponent/coach-trust/garbage-time). net_rating->Elo conversion "
    "is a declared frozen assumption. DESCRIPTIVE_ONLY, not a causal or edge claim."
)

# Frozen NBA numeric team_id -> corpus/Elo abbreviation (stable league IDs).
TEAM_ID_ABBR: dict[int, str] = {
    1610612737: "ATL", 1610612738: "BOS", 1610612739: "CLE", 1610612740: "NOP",
    1610612741: "CHI", 1610612742: "DAL", 1610612743: "DEN", 1610612744: "GSW",
    1610612745: "HOU", 1610612746: "LAC", 1610612747: "LAL", 1610612748: "MIA",
    1610612749: "MIL", 1610612750: "MIN", 1610612751: "BKN", 1610612752: "NYK",
    1610612753: "ORL", 1610612754: "IND", 1610612755: "PHI", 1610612756: "PHX",
    1610612757: "POR", 1610612758: "SAC", 1610612759: "SAS", 1610612760: "OKC",
    1610612761: "TOR", 1610612762: "UTA", 1610612763: "MEM", 1610612764: "WAS",
    1610612765: "DET", 1610612766: "CHA",
}


def elo_logistic(rating_diff: float) -> float:
    """Repo Elo->prob curve: 1/(1+10^(-d/400)). d in Elo points."""
    return 1.0 / (1.0 + 10.0 ** (-rating_diff / 400.0))


def _load_elo() -> dict[str, float]:
    if not ELO_STATE.exists():
        return {}
    return json.loads(ELO_STATE.read_text(encoding="ascii"))["ratings"]


def _load_top_star_per_team() -> dict[int, dict]:
    """team_id -> its highest-on/off-delta player row (from the source claim)."""
    if not CLAIMS_STORE.exists():
        return {}
    best: dict[int, dict] = {}
    for line in CLAIMS_STORE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        claim = json.loads(line)
        if claim["claim_id"] != CLAIM_ID:
            continue
        for r in claim["ranking"]:
            tid = r["team_id"]
            if tid not in best or r["value"] > best[tid]["value"]:
                best[tid] = r
        break
    return best


def build() -> dict:
    elo = _load_elo()
    stars = _load_top_star_per_team()
    if not elo or not stars:
        return {
            "status": "not_buildable",
            "reason": f"missing source(s): elo_state={ELO_STATE.exists()}, "
                      f"claims={CLAIMS_STORE.exists()}",
            "caveat": CEILING_CAVEAT, "edge_claimed": False, "teams": [],
        }

    rows = []
    unmatched = []
    for tid, star in stars.items():
        abbr = TEAM_ID_ABBR.get(tid)
        if abbr is None or abbr not in elo:
            unmatched.append(tid)
            continue
        R = elo[abbr]
        star_elo = star["value"] * ELO_PER_NETRATING_POINT
        p_with = elo_logistic(R - REF_ELO)
        p_without = elo_logistic(R - star_elo - REF_ELO)
        rows.append({
            "team_abbr": abbr,
            "player_name": star["player_name"],
            "player_id": star["player_id"],
            "on_off_net_rating_delta": round(star["value"], 3),
            "min_on": round(star.get("n", 0.0), 1),
            "team_elo": round(R, 2),
            "star_elo_removed": round(star_elo, 1),
            "p_win_with": round(p_with, 4),
            "p_win_without": round(p_without, 4),
            "delta_winprob": round(p_with - p_without, 4),
            "caveat": CEILING_CAVEAT,
        })
    rows.sort(key=lambda r: r["delta_winprob"], reverse=True)

    return {
        "status": "ok",
        "label": "DESCRIPTIVE_ONLY",
        "edge_claimed": False,
        "question": "How many pregame win-prob points is each team's top on/off "
                    "player worth vs a league-average opponent (neutral site)?",
        "as_of": AS_OF,
        "source_artifacts": [
            "data/models/elo_state.json",
            "data/cache/intel_claims/nba_lineup_context_claims.jsonl (" + CLAIM_ID + ")",
        ],
        "method": {
            "rating_to_prob_curve": "repo Elo logistic 1/(1+10^(-d/400))",
            "star_rating_removed": "on_off_net_rating_delta * ELO_PER_NETRATING_POINT",
            "elo_per_netrating_point": round(ELO_PER_NETRATING_POINT, 4),
            "elo_per_netrating_point_anchor": "elo_config.ELO_HFA=76 Elo ~ 3.0-pt home edge (76/3.0)",
            "reference_opponent_elo": REF_ELO,
            "site": "neutral",
            "weights_tuned_to_output": False,
        },
        "assumptions_and_floors": [
            "on/off deltas are pre-floored by the source claim (min_on>=500, n_games>=30).",
            "net-rating->Elo conversion is a single FROZEN constant, anchored to HFA, not fit.",
            "star_elo subtracted linearly from team Elo; nonlinearity of the logistic curve "
            "means the same on/off delta yields a larger win-prob swing for mid-strength teams.",
            "win prob is vs a league-average (1500) opponent on a neutral floor, NOT a real matchup.",
        ],
        "caveat": CEILING_CAVEAT,
        "n_teams": len(rows),
        "unmatched_team_ids": unmatched,
        "teams": rows,
    }


def render_chart(result: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    top = result["teams"][:15][::-1]
    labels = [f"{r['player_name']} ({r['team_abbr']})" for r in top]
    vals = [r["delta_winprob"] * 100.0 for r in top]
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.barh(range(len(labels)), vals, color="#8e44ad")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("counterfactual win-prob points lost if removed (CEILING)")
    ax.set_title("Star-removal win-prob delta -- top 15 (NBA, 2024-25)\n"
                 "CEILING via on/off net-rating; DESCRIPTIVE_ONLY", fontsize=10)
    fig.text(0.5, 0.005,
             "Source: data/models/elo_state.json + intel_claims " + CLAIM_ID
             + " | as_of " + AS_OF + " | edge_claimed=False",
             ha="center", fontsize=6.5, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> dict:
    result = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2))
    if result["status"] == "ok" and result["teams"]:
        render_chart(result, OUT_PNG)
        result["plot_written"] = True
        OUT_JSON.write_text(json.dumps(result, indent=2))
    return result


def _validate(data: dict) -> None:
    assert data["status"] in ("ok", "not_buildable"), data.get("status")
    assert data["edge_claimed"] is False
    if data["status"] == "ok":
        assert data["teams"], "ok status but no teams"
        # monotone-sorted by delta_winprob, descending
        deltas = [t["delta_winprob"] for t in data["teams"]]
        assert deltas == sorted(deltas, reverse=True), "teams not sorted by delta"
        for t in data["teams"]:
            assert t["caveat"] == CEILING_CAVEAT
            assert 0.0 <= t["p_win_with"] <= 1.0 and 0.0 <= t["p_win_without"] <= 1.0
            # tolerance widened: each side is independently rounded to 4dp, so their
            # difference can differ from the (also rounded) delta by up to ~2e-4.
            assert abs(t["delta_winprob"] - (t["p_win_with"] - t["p_win_without"])) < 2e-4


def _check() -> None:
    # curve + math self-check (no heavy data dependency)
    assert abs(elo_logistic(0.0) - 0.5) < 1e-9
    assert elo_logistic(400.0) > elo_logistic(0.0) > elo_logistic(-400.0)
    # removing a positive-value star lowers win prob -> positive delta
    R, val = 1500.0, 10.0
    star_elo = val * ELO_PER_NETRATING_POINT
    d = elo_logistic(R - REF_ELO) - elo_logistic(R - star_elo - REF_ELO)
    assert d > 0, d
    if CLAIMS_STORE.exists() and ELO_STATE.exists():
        _validate(build())
        print("cf_star_removal self-check OK (live data)")
    else:
        verify_recorded_artifact(OUT_JSON, _validate, "cf_star_removal")


if __name__ == "__main__":
    if "--check" in sys.argv:
        _check()
    else:
        res = main()
        print(json.dumps({"status": res["status"], "n_teams": res.get("n_teams"),
                          "unmatched": res.get("unmatched_team_ids")}, indent=2))
        for t in res.get("teams", [])[:5]:
            nm = t["player_name"].encode("ascii", "replace").decode()
            print(f"  {nm} ({t['team_abbr']}): delta_winprob={t['delta_winprob']:+.3f}")
        print(f"wrote {OUT_JSON}")
