"""
Tennis showcase: reuses the ALREADY-COMPUTED tennis gate receipts -- does NOT
recompute anything. Tennis has a served live model (4th live sport) but no
ingame_grade_joined corpus locally, so this pulls the two real gate verdicts
that DO exist on disk:

1. pregame_prior cross-corpus (data/frontend/ingame/gate_tennis.json) --
   true ATP<->WTA cross-corpus test of blend(p0, BASE, w) vs BASE alone.
   verdict: REPLICATED (calibration only, no market comparison in this file).
2. ingame_detail surface-context (data/frontend/ingame/surface_hold_verdict.json,
   built here via `python -m domains.tennis.surface_hold_ingame_gate`) --
   does a surface-specific hold% prior beat a surface-blind one as an in-game
   detail layer? verdict: REJECT (honest null, both tours, planted-null control
   passed). Prints as an example of a preregistered gate correctly killing a
   plausible-sounding feature.

Both verdicts are CALIBRATION-only (held-out Brier / DM test), never a market
edge. If either receipt file is missing, that sport's block degrades to
status:local_corpus_absent with the exact artifact path needed -- the honest
refusal pattern, not a silent skip.

Output: out/tennis_showcase.json (+ docs/img/tennis_showcase.png if either
receipt has a numeric fold series to plot).
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "tennis_showcase.json"
OUT_PNG = REPO / "docs" / "img" / "tennis_showcase.png"

PREGAME_PATH = REPO / "data" / "frontend" / "ingame" / "gate_tennis.json"
SURFACE_PATH = REPO / "data" / "frontend" / "ingame" / "surface_hold_verdict.json"

CALIBRATION_CAVEAT = (
    "CALIBRATION only (held-out Brier / Diebold-Mariano test) -- never a market "
    "edge or $ claim. vs_close comparison, if any, is stated explicitly per block."
)


def _load(path: Path, needed_for: str) -> dict:
    if not path.exists():
        return {
            "status": "local_corpus_absent",
            "needed_artifact": str(path.relative_to(REPO)).replace("\\", "/"),
            "reason": f"{needed_for} -- artifact not present in this local clone/pod.",
        }
    return json.loads(path.read_text(encoding="ascii", errors="ignore"))


def _pregame_block() -> dict:
    raw = _load(PREGAME_PATH, "pregame_prior cross-corpus ATP<->WTA replication")
    if raw.get("status") == "local_corpus_absent":
        return raw
    return {
        "status": "ok",
        "source": str(PREGAME_PATH.relative_to(REPO)).replace("\\", "/"),
        "layer": raw["layer"],
        "design": raw["design"],
        "base_model": raw["base_model"],
        "verdict": raw["verdict"],
        "vs_close": raw["vs_close"],
        "coverage": raw["coverage"],
        "directions": {
            "atp_train_wta_test": {
                "n_train_states": raw["b_to_a"]["n_train_states"],
                "n_test_states": raw["b_to_a"]["n_test_states"],
                "brier_base": raw["b_to_a"]["brier_base"],
                "brier_prior": raw["b_to_a"]["brier_prior"],
                "brier_delta": raw["b_to_a"]["brier_delta"],
                "dm_p": raw["b_to_a"]["dm_p"],
                "prior_beats_base": raw["b_to_a"]["prior_beats_base"],
            },
            "wta_train_atp_test": {
                "n_train_states": raw["a_to_b"]["n_train_states"],
                "n_test_states": raw["a_to_b"]["n_test_states"],
                "brier_base": raw["a_to_b"]["brier_base"],
                "brier_prior": raw["a_to_b"]["brier_prior"],
                "brier_delta": raw["a_to_b"]["brier_delta"],
                "dm_p": raw["a_to_b"]["dm_p"],
                "prior_beats_base": raw["a_to_b"]["prior_beats_base"],
            },
        },
        "caveats": raw["caveats"],
    }


def _surface_block() -> dict:
    raw = _load(SURFACE_PATH, "ingame_detail surface-context hold% gate")
    if raw.get("status") == "local_corpus_absent":
        return raw
    return {
        "status": "ok",
        "source": str(SURFACE_PATH.relative_to(REPO)).replace("\\", "/"),
        "layer": raw["layer"],
        "design": raw["design"],
        "base_model": raw["base_model"],
        "verdict": raw["verdict"],
        "reason": raw["reason"],
        "vs_close": raw["vs_close"],
        "planted_null_dies": raw["planted_null_dies"],
        "tours": {
            tour: {
                "n_states_joined": raw[tour]["n_states_joined"],
                "pooled_brier_h0_blind": raw[tour]["real"]["pooled_brier_h0"],
                "pooled_brier_h1_surface": raw[tour]["real"]["pooled_brier_h1"],
                "pooled_delta_h1_minus_h0": raw[tour]["real"]["pooled_delta_h1_minus_h0"],
                "sign_holds_ge_2of3": raw[tour]["real"]["sign_holds_ge_2of3"],
                "n_folds": [
                    {
                        "fold": f["fold"], "n_test": f["n_test"],
                        "brier_h0": f["brier_h0"], "brier_h1": f["brier_h1"], "dm_p": f["dm_p"],
                    }
                    for f in raw[tour]["real"]["folds"]
                ],
            }
            for tour in ("atp", "wta")
        },
    }


def build_showcase() -> dict:
    pregame = _pregame_block()
    surface = _surface_block()
    both_absent = pregame.get("status") == "local_corpus_absent" and surface.get(
        "status") == "local_corpus_absent"
    return {
        "status": "local_corpus_absent" if both_absent else "ok",
        "sport": "tennis",
        "caveat": CALIBRATION_CAVEAT,
        "note": (
            "tennis has a served live model but no ingame_grade_joined corpus "
            "locally -- this showcase surfaces the two REAL preregistered gate "
            "receipts that ARE present (pregame cross-corpus + ingame surface-"
            "context detail layer), not a recomputed ingame_grade summary."
        ),
        "pregame_prior_cross_corpus": pregame,
        "ingame_surface_context": surface,
    }


def render_chart(showcase: dict, path: Path) -> None:
    surf = showcase["ingame_surface_context"]
    if surf.get("status") != "ok":
        return
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    for ax, tour in zip(axes, ("atp", "wta")):
        t = surf["tours"][tour]
        folds = t["n_folds"]
        x = [f["fold"] for f in folds]
        ax.plot(x, [f["brier_h0"] for f in folds], "o-", color="#2a6fbf", label="H0 surface-blind")
        ax.plot(x, [f["brier_h1"] for f in folds], "s-", color="#c0392b", label="H1 surface-specific")
        ax.set_title(f"{tour.upper()}: {t['n_states_joined']} states\nverdict={surf['verdict']}", fontsize=9)
        ax.set_xlabel("walk-forward fold")
        ax.set_ylabel("Brier (lower=better)")
        ax.legend(fontsize=7)
    fig.suptitle("tennis in-game detail layer: surface-specific vs surface-blind hold% prior\n"
                 "(CALIBRATION only, no market comparison)", fontsize=9)
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
    # ponytail: minimal smoke check against the real stores, not a fixture suite
    showcase = build_showcase()
    assert showcase["status"] in ("ok", "local_corpus_absent")
    for key in ("pregame_prior_cross_corpus", "ingame_surface_context"):
        block = showcase[key]
        assert block["status"] in ("ok", "local_corpus_absent")
        if block["status"] == "local_corpus_absent":
            assert "needed_artifact" in block
        else:
            assert "verdict" in block
    print("check ok")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        result = main()
        print(json.dumps({
            "status": result["status"],
            "pregame_status": result["pregame_prior_cross_corpus"]["status"],
            "surface_status": result["ingame_surface_context"]["status"],
        }, indent=2))
        print(f"wrote {OUT_JSON}")
        if result["status"] == "ok":
            print(f"wrote {OUT_PNG}")
