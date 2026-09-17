"""Re-render a showcase chart PNG from its ALREADY-PUBLISHED out/<id>.json.

Why this exists: several analytics artifacts were regenerated (revision 2) from
a re-segmented corpus, but their docs/img PNGs were left at revision 1, so the
module page and the paper figures printed numbers the artifact no longer holds.
Re-running the producers would need the raw corpus AND would rewrite the JSON;
this driver instead calls each producer's own plot function with the published
JSON, so the picture can only ever show what the artifact says. No JSON is
written here, ever.

ponytail: one dispatch table instead of a --plot-only flag bolted onto 17
producers. Add a module by adding one row to PLOTTERS.

Run:   python -m scripts.platformkit.analytics_showcase.replot_from_json --all
       python -m scripts.platformkit.analytics_showcase.replot_from_json calibration_stability
       python -m scripts.platformkit.analytics_showcase.replot_from_json --all --stage
Check: python -m scripts.platformkit.analytics_showcase.replot_from_json --check
"""
import argparse
import hashlib
import importlib
import json
import os
import shutil
import sys

os.environ.setdefault("MPLBACKEND", "Agg")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT_DIR = os.path.join(REPO_ROOT, "scripts", "platformkit", "analytics_showcase", "out")
IMG_DIR = os.path.join(REPO_ROOT, "docs", "img")
STAGE_DIR = os.path.join(REPO_ROOT, "webapp", "public", "img", "showcase")
PKG = "scripts.platformkit.analytics_showcase."


def _int_keys(d):
    """JSON turns int checkpoint keys into strings; plot code sorts + plots them
    numerically, so put them back when every key is an integer."""
    if isinstance(d, dict) and d and all(str(k).lstrip("-").isdigit() for k in d):
        return {int(k): v for k, v in d.items()}
    return d


def _dict_values_only(d):
    """calibration_over_time.json is sport -> months plus scalar as_of/corpus."""
    return {k: v for k, v in d.items() if isinstance(v, dict)}


def _live(buckets):
    return {k: v for k, v in buckets.items() if isinstance(v, dict) and v.get("status") != "no_data"}


# id -> (producer module suffix, callable(module, published_json) -> renders OUT_PNG)
PLOTTERS = {
    "brier_skill_scores": lambda m, d: m.make_plot(d),
    "calibration_stability": lambda m, d: m.make_plot(d),
    "market_disagreement_profile": lambda m, d: m.make_plot(d),
    "soccer_calibration_pack": lambda m, d: m.make_plot(d),
    "blowout_dynamics": lambda m, d: m.make_plot(d),
    "kernel_transfer": lambda m, d: m.plot(d),
    "novel_live_clock_fraction": lambda m, d: m.plot(d),
    "novel_market_foresight_premium": lambda m, d: m.plot(d),
    "calibration_by_market_type": lambda m, d: m.make_chart(d["market_types"]),
    "residual_anatomy": lambda m, d: m.make_chart(d["ranked_worst_segments"], m.OUT_PNG),
    "residual_autocorrelation": lambda m, d: m.make_chart(d["sports"], m.OUT_PNG),
    "why_attribution": lambda m, d: m.make_chart(d, m.OUT_PNG),
    "calibration_over_time": lambda m, d: m.plot(_dict_values_only(d), m.OUT_PNG),
    "info_arrival_curve": lambda m, d: m.plot({s: _int_keys(v) for s, v in d["checkpoints"].items()}, m.OUT_PNG),
    "market_convergence": lambda m, d: m.plot({s: _int_keys(v) for s, v in d["checkpoints"].items()}, m.OUT_PNG),
    "market_overreaction": lambda m, d: m.plot(_live(d["buckets"]), m.OUT_PNG),
    "comeback_atlas": lambda m, d: m._render_png(d, m._OUT_PNG),
}


def md5(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def png_path(module_id):
    return os.path.join(IMG_DIR, module_id + ".png")


def replot(module_id, stage=False):
    """Render docs/img/<id>.png from out/<id>.json. Returns a result row."""
    if module_id not in PLOTTERS:
        raise KeyError("no plot dispatch for " + module_id)
    json_path = os.path.join(OUT_DIR, module_id + ".json")
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    out_png = png_path(module_id)
    before = md5(out_png)
    mod = importlib.import_module(PKG + module_id)
    PLOTTERS[module_id](mod, data)
    after = md5(out_png)
    if after is None:
        raise RuntimeError("plot function wrote no PNG for " + module_id)
    row = {
        "id": module_id,
        "as_of": data.get("as_of") or data.get("generated_at"),
        "md5_before": before,
        "md5_after": after,
        "changed": before != after,
        "staged": False,
    }
    if stage:
        os.makedirs(STAGE_DIR, exist_ok=True)
        shutil.copy2(out_png, os.path.join(STAGE_DIR, module_id + ".png"))
        row["staged"] = md5(os.path.join(STAGE_DIR, module_id + ".png")) == after
    return row


def check():
    """Self-check: every dispatch row names a real artifact whose producer
    exposes the callable we dispatch to, and rendering one module from its
    published JSON leaves that JSON untouched."""
    for module_id in PLOTTERS:
        assert os.path.exists(os.path.join(OUT_DIR, module_id + ".json")), "missing artifact " + module_id
        importlib.import_module(PKG + module_id)
    target = "market_overreaction"
    json_path = os.path.join(OUT_DIR, target + ".json")
    before_json = md5(json_path)
    row = replot(target)
    assert row["md5_after"], row
    assert md5(json_path) == before_json, "replot must never rewrite " + json_path
    assert _int_keys({"10": 1, "2": 1}) == {10: 1, 2: 1}
    assert _int_keys({"a": 1}) == {"a": 1}
    assert _dict_values_only({"mlb": {}, "as_of": "2026-09-16"}) == {"mlb": {}}
    assert _live({"a": {"status": "no_data"}, "b": {"n": 1}}) == {"b": {"n": 1}}
    print("OK: replot_from_json self-check passed")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", help="module ids to replot")
    ap.add_argument("--all", action="store_true", help="replot every dispatchable module")
    ap.add_argument("--stage", action="store_true", help="also copy the PNG to webapp/public/img/showcase/")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if args.check:
        check()
        return 0
    ids = sorted(PLOTTERS) if args.all else args.ids
    if not ids:
        ap.error("pass module ids or --all")
    rows = [replot(i, stage=args.stage) for i in ids]
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
