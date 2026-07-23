"""Shared card infrastructure for the analytics_showcase "atlas" family.

Every atlas module (one per sport/entity-type) imports this file instead of
re-inventing its own compact-card renderer or manifest writer. All cards are
DESCRIPTIVE_ONLY (no edge/ROI claims -- see docs/JOB_EVIDENCE_PACKET.md) and
must stay small: dpi<=90, target <=45KB/card, hard guard <=60KB (one retry at
a lower dpi, then fail loud if still oversize).

Usage (by every atlas module that wants a card) -- the check_all gotcha:
check_all.py runs modules via `-m scripts.platformkit.analytics_showcase.X`,
but a module can also be run as a bare script, so import this file both ways:

    try:
        from scripts.platformkit.analytics_showcase.atlas_factory import (
            card_figure, write_manifest, slugify, card_path)
    except ImportError:
        from atlas_factory import card_figure, write_manifest, slugify, card_path

Usage (this file):
    python -m scripts.platformkit.analytics_showcase.atlas_factory --check
"""
import json
import re
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.axes import Axes

HERE = Path(__file__).parent
REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = HERE / "out"
MAX_CARD_BYTES = 60_000
DEFAULT_DPI = 90


def slugify(text: str) -> str:
    """ASCII/filesystem-safe slug: lowercase, non-alnum runs collapse to '_'."""
    s = re.sub(r"[^a-z0-9]+", "_", text.strip().lower())
    return s.strip("_") or "entity"


def card_path(sport: str, entity: str) -> Path:
    """Standard card location every atlas module should render to:
    docs/img/atlas/<sport>/<slug(entity)>.png
    """
    return REPO_ROOT / "docs" / "img" / "atlas" / sport / f"{slugify(entity)}.png"


def _save_with_size_guard(fig, path: Path, dpi: int, max_bytes: int = MAX_CARD_BYTES) -> tuple[int, int]:
    # ponytail: one retry at half dpi covers the realistic oversize case -- if it's
    # still too big after that, panel count/content is the real problem, not dpi.
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi)
    n_bytes = path.stat().st_size
    if n_bytes > max_bytes:
        dpi = max(40, dpi // 2)
        fig.savefig(path, dpi=dpi)
        n_bytes = path.stat().st_size
    assert n_bytes <= max_bytes, (
        f"{path.name} is {n_bytes}B even after one dpi retry (dpi={dpi}); "
        f"guard is {max_bytes}B -- shrink panel count/content, not just dpi"
    )
    return dpi, n_bytes


def card_figure(
    title: str,
    panels: Sequence[tuple[str, Callable[[Axes], None]]],
    source_artifact: str,
    floors: Any,
    as_of: str,
    out_path: Path,
    dpi: int = DEFAULT_DPI,
    descriptive_only: bool = True,
) -> dict:
    """Render one compact card (a 1-row strip of 2-4 mini-panels) to out_path.

    panels: 2-4 (panel_title, render_fn) pairs; render_fn(ax) draws onto that
    Axes -- this factory has no opinion on chart type, callers own their own
    plot calls (bar/line/scatter/text-stat/whatever the data needs).

    Always stamps a source-artifact + floor + as_of footer and, unless
    descriptive_only=False, a DESCRIPTIVE_ONLY badge. Applies the project's
    dpi<=90 / <=60KB size guard before returning.

    Returns {"path", "dpi", "bytes", "n_panels", "title"}.
    """
    assert 2 <= len(panels) <= 4, f"card_figure wants 2-4 panels, got {len(panels)}"
    assert 0 < dpi <= 90, f"card dpi must be <=90 (compact-card rail), got {dpi}"

    out_path = Path(out_path)
    n = len(panels)
    fig, axes = plt.subplots(1, n, figsize=(1.8 * n + 0.6, 2.3))

    for ax, (panel_title, render_fn) in zip(axes, panels):
        render_fn(ax)
        ax.set_title(panel_title, fontsize=7)
        ax.tick_params(labelsize=6)

    fig.suptitle(title, fontsize=9, fontweight="bold", y=0.99)

    footer = f"source: {source_artifact}  |  floor: {floors}  |  as_of: {as_of}"
    fig.text(0.01, 0.01, footer, fontsize=5.5, ha="left", va="bottom", color="#555555")
    if descriptive_only:
        fig.text(0.99, 0.01, "DESCRIPTIVE_ONLY", fontsize=6, ha="right", va="bottom",
                  color="#b33333", fontweight="bold")

    fig.tight_layout(rect=(0.0, 0.09, 1.0, 0.90))
    final_dpi, n_bytes = _save_with_size_guard(fig, out_path, dpi)
    plt.close(fig)

    return {"path": str(out_path), "dpi": final_dpi, "bytes": n_bytes, "n_panels": n, "title": title}


def write_manifest(sport: str, entries: Sequence[dict]) -> Path:
    """Write out/atlas_<sport>_manifest.json from a list of card entries.

    Each entry must carry: entity, card_path, key_numbers (dict), floors, as_of.
    Validates shape and writes verbatim -- does not compute, round, or inflate
    any number (counts/values are whatever the caller measured).
    """
    required = {"entity", "card_path", "key_numbers", "floors", "as_of"}
    for e in entries:
        missing = required - e.keys()
        assert not missing, f"manifest entry {e.get('entity', '?')} missing {sorted(missing)}"
        assert isinstance(e["key_numbers"], dict), f"key_numbers must be a dict: {e['entity']}"

    manifest = {
        "sport": sport,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "n_entries": len(entries),
        "entries": list(entries),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"atlas_{sport}_manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2), encoding="ascii")
    return out_path


def _check():
    import tempfile

    as_of = datetime.now(timezone.utc).isoformat()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_card = Path(tmp) / "synthetic_card.png"

        result = card_figure(
            title="Synthetic Check Entity",
            panels=[
                ("bars", lambda ax: ax.bar(["a", "b", "c"], [1, 3, 2])),
                ("line", lambda ax: ax.plot([0, 1, 2], [2, 1, 3])),
                ("scatter", lambda ax: ax.scatter([0, 1, 2], [1, 2, 0])),
            ],
            source_artifact="synthetic/self_check",
            floors="n>=1 (synthetic)",
            as_of=as_of,
            out_path=tmp_card,
        )
        assert tmp_card.exists(), "card_figure did not write a file"
        assert result["bytes"] <= MAX_CARD_BYTES, f"synthetic card is {result['bytes']}B, over the guard"
        assert result["dpi"] <= 90
        assert result["n_panels"] == 3

        entries = [{
            "entity": "Synthetic Check Entity",
            "card_path": str(tmp_card),
            "key_numbers": {"n": 3, "mean": 2.0},
            "floors": "n>=1 (synthetic)",
            "as_of": as_of,
        }]
        manifest_path = write_manifest("_selfcheck", entries)
        try:
            loaded = json.loads(manifest_path.read_text(encoding="ascii"))
            assert loaded["sport"] == "_selfcheck"
            assert loaded["n_entries"] == 1
            assert loaded["descriptive_only"] is True
            assert loaded["entries"][0]["entity"] == "Synthetic Check Entity"
            assert loaded["entries"][0]["key_numbers"]["n"] == 3
        finally:
            manifest_path.unlink(missing_ok=True)  # roundtrip check, not a real manifest -- don't leave it behind

        assert slugify("Nikola Jokic!!  MVP?") == "nikola_jokic_mvp"
        assert slugify("") == "entity"
        assert card_path("nba", "Nikola Jokic").name == "nikola_jokic.png"

        try:
            card_figure("bad", [("only_one", lambda ax: None)], "src", "floor", as_of, tmp_card)
            raise AssertionError("card_figure should reject <2 panels")
        except AssertionError as exc:
            assert "2-4 panels" in str(exc)

    print("check ok")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        print(__doc__)
