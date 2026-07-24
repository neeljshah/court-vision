"""share_chart.py -- presentation-grade shareable charts for showcase modules.

Given any module id from out/site_manifest.json, render a polished PNG to
docs/img/share/<id>.png in the webapp "Amber Console" palette (dark bg, amber
accent) with a source_artifact + as_of + "edge_claimed: false" footer stamp and
a repo-URL watermark. Module JSONs are heterogeneous (54 shapes), so extraction
is generic best-effort: richest numeric series -> bar chart; else big-number
summary card; else an honest "not_chartable" card. Never invents numbers.

CLI: --id <module> | --all | --check.  Ledger stores repo-relative ids only
(clone-safe, rejoined from REPO_ROOT at runtime).
"""
import argparse
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SHOWCASE = REPO_ROOT / "scripts" / "platformkit" / "analytics_showcase"
MANIFEST = SHOWCASE / "out" / "site_manifest.json"
LEDGER = SHOWCASE / "out" / "share_ledger.json"
SHARE_DIR = REPO_ROOT / "docs" / "img" / "share"
REPO_URL = "github.com/neeljshah/court-vision"

# Amber Console tokens (webapp/app/globals.css dark theme -- exact hex).
BG = "#0C0F15"        # --background
CARD = "#12161F"      # --card
INK = "#E7EAF2"       # --foreground
MUTED = "#8A93A6"     # --muted-foreground
BORDER = "#232A38"    # --border
AMBER = "#C9821A"     # --s-model (our series)
BLUE = "#3E9BE0"      # --s-market
AMBER_HL = "#E2A33C"  # --primary accent

# Keys that are metadata, never a data series.
META_KEYS = {
    "edge_claimed", "descriptive_only", "generated_at", "generated_from",
    "plot_written", "source_artifact", "as_of", "method", "methodology",
    "floors", "floor", "honest_note", "note", "notes", "verdict", "status",
    "label", "unit", "n", "n_rows", "count", "sports", "grains",
}


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def title_case(mid, manifest_title):
    if manifest_title:
        return manifest_title
    return mid.replace("_", " ").title()


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def module_entry(manifest, mid):
    for m in manifest.get("modules", []):
        if m.get("id") == mid:
            return m
    return None


def read_out_json(entry):
    """Load a module's out JSON, returning ({}, meta) tolerant of absence."""
    op = entry.get("out_path")
    if not op:
        return {}
    p = REPO_ROOT / op
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def extract_series(data):
    """Best-effort: return (labels, values) for the richest dict-of-numbers
    found (top level or one nesting deep), capped at 24 bars, or None."""
    best = None
    candidates = [data]
    for k, v in list(data.items()) if isinstance(data, dict) else []:
        if isinstance(v, dict):
            candidates.append(v)
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            # list of records: find a string-key + numeric-key pair
            rec = _series_from_records(v)
            if rec:
                candidates.append(rec)
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        pairs = [(k, v) for k, v in cand.items()
                 if k not in META_KEYS and _is_num(v)]
        if len(pairs) >= 2 and (best is None or len(pairs) > len(best)):
            best = pairs
    if not best:
        return None
    best = best[:24]
    return [str(k) for k, _ in best], [float(v) for _, v in best]


def _series_from_records(records):
    """Turn a list of {label, value} records into a {label: value} dict."""
    sample = records[0]
    name_key = next((k for k, v in sample.items() if isinstance(v, str)), None)
    val_key = next((k for k, v in sample.items()
                    if k not in META_KEYS and _is_num(v)), None)
    if not (name_key and val_key):
        return None
    out = {}
    for r in records[:24]:
        if isinstance(r.get(name_key), str) and _is_num(r.get(val_key)):
            out[r[name_key]] = r[val_key]
    return out or None


def extract_scalars(data):
    """Up to 6 headline scalar (label, value) pairs for a summary card."""
    if not isinstance(data, dict):
        return []
    out = []
    for k, v in data.items():
        if k in META_KEYS:
            continue
        if _is_num(v):
            out.append((k, v))
        elif isinstance(v, dict):
            for k2, v2 in v.items():
                if k2 not in META_KEYS and _is_num(v2):
                    out.append((f"{k}.{k2}", v2))
        if len(out) >= 6:
            break
    return out[:6]


def _footer(fig, entry, data):
    src = data.get("source_artifact") or entry.get("out_path") or "n/a"
    as_of = data.get("as_of") or entry.get("as_of") or "n/a"
    stamp = f"source: {src}   |   as_of: {as_of}   |   edge_claimed: false"
    fig.text(0.5, 0.028, stamp, ha="center", va="center",
             fontsize=6.4, color=MUTED, wrap=True)
    fig.text(0.5, 0.008, REPO_URL, ha="center", va="center",
             fontsize=6.0, color=BORDER, fontweight="bold")


def _style_ax(ax):
    ax.set_facecolor(CARD)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.grid(False)
    ax.tick_params(colors=MUTED, length=0, labelsize=8)


def render(mid, entry, data, plt):
    title = title_case(mid, entry.get("title"))
    fig = plt.figure(figsize=(10, 5.8), facecolor=BG)
    fig.text(0.5, 0.94, title, ha="center", fontsize=17,
             color=INK, fontweight="bold")

    series = extract_series(data)
    if series:
        labels, values = series
        ax = fig.add_axes([0.30, 0.14, 0.66, 0.72])
        _style_ax(ax)
        ypos = range(len(labels))
        colors = [AMBER if v >= 0 else BLUE for v in values]
        ax.barh(list(ypos), values, color=colors, height=0.62)
        ax.set_yticks(list(ypos))
        ax.set_yticklabels([l[:34] for l in labels], color=INK, fontsize=8)
        ax.invert_yaxis()
        span = max(abs(v) for v in values) or 1.0
        for y, v in zip(ypos, values):
            off = span * 0.015
            ax.text(v + (off if v >= 0 else -off), y, _fmt(v),
                    va="center", ha="left" if v >= 0 else "right",
                    color=AMBER_HL, fontsize=8, fontweight="bold")
        ax.axvline(0, color=BORDER, linewidth=1)
        ax.set_xlim(min(0, min(values)) - span * 0.18,
                    max(0, max(values)) + span * 0.18)
    else:
        _render_card(fig, data)

    _footer(fig, entry, data)
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    out = SHARE_DIR / f"{mid}.png"
    fig.savefig(out, dpi=150, facecolor=BG)
    plt.close(fig)
    return out


def _render_card(fig, data):
    scalars = extract_scalars(data)
    if not scalars:
        fig.text(0.5, 0.5, "not_chartable -- no numeric series in artifact",
                 ha="center", va="center", fontsize=12, color=MUTED)
        return
    n = len(scalars)
    cols = min(3, n)
    rows = (n + cols - 1) // cols
    for i, (k, v) in enumerate(scalars):
        r, c = divmod(i, cols)
        x = (c + 0.5) / cols
        y = 0.72 - r * (0.56 / max(rows, 1))
        fig.text(x, y, _fmt(v), ha="center", fontsize=26,
                 color=AMBER_HL, fontweight="bold")
        fig.text(x, y - 0.09, k.replace("_", " ")[:28], ha="center",
                 fontsize=8.5, color=MUTED)


def _fmt(v):
    if isinstance(v, float):
        if abs(v) >= 1000 or (v != 0 and abs(v) < 0.001):
            return f"{v:.3g}"
        return f"{v:+.3f}".rstrip("0").rstrip(".") if abs(v) < 1 else f"{v:.2f}"
    return str(v)


def read_ledger():
    if LEDGER.exists():
        try:
            return json.loads(LEDGER.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"rendered_ids": []}


def write_ledger(led):
    LEDGER.write_text(json.dumps(led, indent=2) + "\n", encoding="utf-8")


def do_render(mid, manifest, plt, led):
    entry = module_entry(manifest, mid)
    if entry is None:
        print(f"SKIP {mid}: not in manifest")
        return False
    data = read_out_json(entry)
    out = render(mid, entry, data, plt)
    rel = out.relative_to(REPO_ROOT).as_posix()
    if mid not in led["rendered_ids"]:
        led["rendered_ids"].append(mid)
    print(f"OK   {mid} -> {rel}")
    return True


def do_check():
    """Validate that every previously-rendered id still has its PNG."""
    led = read_ledger()
    ids = led.get("rendered_ids", [])
    if not ids:
        print("CHECK: ledger empty -- nothing rendered yet (PASS, vacuous)")
        return 0
    missing = [i for i in ids if not (SHARE_DIR / f"{i}.png").exists()]
    for i in ids:
        ok = (SHARE_DIR / f"{i}.png").exists()
        print(f"  {'PASS' if ok else 'FAIL'} {i}.png")
    if missing:
        print(f"CHECK FAIL: {len(missing)}/{len(ids)} recorded PNGs missing")
        return 1
    print(f"CHECK PASS: {len(ids)}/{len(ids)} recorded PNGs present")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Presentation-grade share charts.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--id", help="module id from site_manifest.json")
    g.add_argument("--all", action="store_true", help="render every module")
    g.add_argument("--check", action="store_true",
                   help="verify previously-rendered PNGs still exist")
    args = ap.parse_args()

    if args.check:
        raise SystemExit(do_check())

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    manifest = load_manifest()
    led = read_ledger()
    if args.all:
        n = sum(do_render(m["id"], manifest, plt, led)
                for m in manifest.get("modules", []))
        print(f"rendered {n} charts")
    else:
        do_render(args.id, manifest, plt, led)
    write_ledger(led)


if __name__ == "__main__":
    main()


def _selfcheck():
    """assert-based self-check for the extractors (run manually, not here)."""
    s = extract_series({"a": 1.0, "b": -2.0, "meta": "x", "generated_at": "t"})
    assert s == (["a", "b"], [1.0, -2.0]), s
    assert extract_series({"only_one": 3}) is None
    recs = {"rows": [{"name": "x", "v": 1}, {"name": "y", "v": 2}]}
    assert extract_series(recs) == (["x", "y"], [1.0, 2.0])
    assert extract_scalars({"acc": 0.9, "edge_claimed": False})[0][0] == "acc"
    print("selfcheck OK")
