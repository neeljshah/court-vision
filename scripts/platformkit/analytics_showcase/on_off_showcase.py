"""
On/off net-rating showcase: reuses the ALREADY-COMPUTED nba_lineup_context
net_rating_delta claim (data/cache/intel_claims/nba_lineup_context_claims.jsonl)
-- does NOT recompute from raw PBP.

CRITICAL HONESTY RULE (matches the source claim family, binding, user-established):
every value here is an on/off DELTA, not a causal player-impact estimate. Who
shares the floor with a player correlates with coach trust, opponent strength,
and garbage-time usage (the ROSTER CONFOUND), none of which is controlled for.
The caveat is declared on EVERY row of the output, not just once at the top.

Input:  data/cache/intel_claims/nba_lineup_context_claims.jsonl
        (claim_id nba_lineup_context_net_rating_delta_<season>, full population
        above the preregistered floor, no top-N cap)
Output: out/on_off_showcase.json + docs/img/on_off_showcase.png
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
OUT_JSON = HERE / "out" / "on_off_showcase.json"
OUT_PNG = Path(__file__).resolve().parents[3] / "docs" / "img" / "on_off_showcase.png"
CLAIMS_STORE = (
    Path(__file__).resolve().parents[3] / "data" / "cache" / "intel_claims"
    / "nba_lineup_context_claims.jsonl"
)
CLAIM_ID_PREFIX = "nba_lineup_context_net_rating_delta_"

ROSTER_CONFOUND_CAVEAT = (
    "ROSTER CONFOUND: this on/off delta is NOT a causal player-impact estimate -- "
    "who shares the floor with a player correlates with coach trust, opponent "
    "strength, and garbage-time usage, and none of those are controlled for here. "
    "DESCRIPTIVE_ONLY, not a predictive or edge claim."
)


def _load_net_rating_claims() -> dict[str, dict]:
    """season -> raw claim dict, straight from the store (no recompute)."""
    if not CLAIMS_STORE.exists():
        return {}
    out = {}
    for line in CLAIMS_STORE.read_text(encoding="ascii").splitlines():
        if not line.strip():
            continue
        claim = json.loads(line)
        if claim["claim_id"].startswith(CLAIM_ID_PREFIX):
            season = claim["claim_id"][len(CLAIM_ID_PREFIX):]
            out[season] = claim
    return out


def _distribution(values: list[float]) -> dict:
    n = len(values)
    if n == 0:
        return {"n": 0}
    s = sorted(values)

    def pct(p: float) -> float:
        idx = min(n - 1, int(round(p * (n - 1))))
        return round(s[idx], 4)

    return {
        "n": n, "min": round(s[0], 4), "p25": pct(0.25), "median": pct(0.5),
        "p75": pct(0.75), "max": round(s[-1], 4),
        "mean": round(sum(values) / n, 4),
    }


def build_showcase() -> dict:
    by_season = _load_net_rating_claims()
    if not by_season:
        return {
            "status": "degraded", "reason": "store missing or has no "
            f"{CLAIM_ID_PREFIX}* claims at {CLAIMS_STORE}",
            "caveat": ROSTER_CONFOUND_CAVEAT, "seasons": {},
        }

    seasons_out = {}
    for season, claim in sorted(by_season.items()):
        ranking = claim["ranking"]
        values = [r["value"] for r in ranking]

        def _rows(items):
            return [
                {
                    "rank": r["rank"], "player_id": r["player_id"],
                    "team_id": r["team_id"], "player_name": r["player_name"],
                    "net_rating_delta": r["value"], "min_on": r["n"],
                    "caveat": ROSTER_CONFOUND_CAVEAT,
                }
                for r in items
            ]

        seasons_out[season] = {
            "status": "ok",
            "question": claim["question"],
            "formula": claim["criteria"]["formula"],
            "min_sample": claim["criteria"]["min_sample"],
            "n_considered": claim["n_considered"],
            "n_excluded_below_floor": claim["n_excluded_below_floor"],
            "n_ranked": len(ranking),
            "distribution": _distribution(values),
            "top_15": _rows(ranking[:15]),
            "bottom_15": _rows(sorted(ranking, key=lambda r: r["value"])[:15]),
            "caveats": claim["caveats"],
        }

    return {
        "status": "ok", "source_claim_store": str(
            CLAIMS_STORE.relative_to(Path(__file__).resolve().parents[3])
        ).replace("\\", "/"),
        "metric": "net_rating_delta = net_rating_on_per48 - net_rating_off_per48",
        "caveat": ROSTER_CONFOUND_CAVEAT,
        "seasons": seasons_out,
    }


def render_chart(showcase: dict, path: Path) -> None:
    seasons = [s for s, v in showcase["seasons"].items() if v.get("status") == "ok"]
    fig, axes = plt.subplots(1, max(len(seasons), 1), figsize=(7 * max(len(seasons), 1), 6), squeeze=False)
    axes = axes[0]

    for ax, season in zip(axes, seasons):
        data = showcase["seasons"][season]
        top = data["top_15"]
        bot = list(reversed(data["bottom_15"]))
        names = [r["player_name"] for r in top] + [r["player_name"] for r in bot]
        vals = [r["net_rating_delta"] for r in top] + [r["net_rating_delta"] for r in bot]
        colors = ["#2a9d5c"] * len(top) + ["#c0392b"] * len(bot)
        y = range(len(names))
        ax.barh(y, vals, color=colors)
        ax.set_yticks(y)
        ax.set_yticklabels(names, fontsize=7)
        ax.invert_yaxis()
        ax.axvline(0, color="black", linewidth=0.6)
        ax.set_title(f"{season}: top/bottom-15 net_rating_delta\n(ROSTER CONFOUND -- descriptive only)", fontsize=9)
        ax.set_xlabel("net_rating_on_per48 - net_rating_off_per48", fontsize=8)

    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main() -> dict:
    showcase = build_showcase()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(showcase, indent=2))
    if showcase["status"] == "ok":
        render_chart(showcase, OUT_PNG)
    return showcase


def _check():
    # ponytail: minimal smoke check against the real store, not a fixture suite
    showcase = build_showcase()
    assert showcase["status"] in ("ok", "degraded")
    if showcase["status"] == "ok":
        for season, data in showcase["seasons"].items():
            assert len(data["top_15"]) <= 15
            assert len(data["bottom_15"]) <= 15
            assert all(r["caveat"] == ROSTER_CONFOUND_CAVEAT for r in data["top_15"])
            if len(data["top_15"]) > 1:
                assert data["top_15"][0]["net_rating_delta"] >= data["top_15"][-1]["net_rating_delta"]
    print("check ok")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        result = main()
        print(json.dumps({"status": result["status"], "seasons": list(result.get("seasons", {}))}, indent=2))
        print(f"wrote {OUT_JSON}")
        if result["status"] == "ok":
            print(f"wrote {OUT_PNG}")
