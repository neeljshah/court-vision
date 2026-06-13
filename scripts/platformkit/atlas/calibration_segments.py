"""scripts.platformkit.atlas.calibration_segments — Per-sport calibration-by-segment note.

Emits vault/Sports/_Calibration_Segments.md: per sport, reliability diagram by
probability decile (predicted vs observed + n) and per-season ECE.
Honest: calibration is a RELIABILITY diagnostic only — well-calibrated != profitable.
Soccer O/U miscalibration surfaced honestly. Person-free; no edge claimed.
F5-clean: stdlib + numpy + pandas; domain adapters imported lazily.

DRY note: ECE computation delegates to kernel.validation.proof_metrics.ece and
reliability bins delegate to scripts.platformkit.calibration_conformance._reliability_bins
(shared implementations — no local reimplementation).
"""
from __future__ import annotations

import math
import pathlib
import time
from typing import List, Optional, Tuple

from kernel.validation.proof_metrics import ece as _kernel_ece
from scripts.platformkit.calibration_conformance import (
    _reliability_bins as _cc_reliability_bins,
)
from scripts.platformkit.atlas.obsidian_emit import frontmatter, md_table, write_note

_OUT_FILENAME = "_Calibration_Segments.md"
N_BINS: int = 10

# (sport_id, display, adapter_module, adapter_class, group_col)
# NBA excluded: no FeatureBundle adapter/signal_catalog; NBA uses a separate gate path.
_SPORT_SPECS: List[Tuple[str, str, str, str, str]] = [
    ("tennis_atp", "Tennis (ATP)", "domains.tennis.adapter", "TennisAdapter", "year"),
    ("soccer_fd",  "Soccer (O/U 2.5)", "domains.soccer.adapter", "SoccerAdapter", "season"),
    ("mlb_sbro",   "MLB (Home ML)",    "domains.mlb.adapter",    "MLBAdapter",    "season"),
    ("nba_espn",   "NBA (Home ML)",    "domains.basketball_nba.adapter", "NBAAdapter", "season"),
]

_SOCCER_NOTE = (
    "**Known diagnostic note (soccer):** the Poisson O/U model may show systematic "
    "over-prediction of P(Over 2.5) in moderate-lambda ranges. "
    "This is a reliability gap — it does not imply a betting edge. "
    "Calibration != profitable; markets price Poisson lambda efficiently."
)


# ---------------------------------------------------------------------------
# Lazy data loader
# ---------------------------------------------------------------------------

def _load_bundle(repo_root: pathlib.Path, adapter_module: str, adapter_class: str) -> Optional[object]:
    """Import adapter and call feature_bundle(hypothesis=None, seasons=[]). None on any error."""
    try:
        import importlib
        mod = importlib.import_module(adapter_module)
        adapter = getattr(mod, adapter_class)(repo_root=repo_root)
        return adapter.feature_bundle(hypothesis=None, seasons=[])
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Calibration math — delegates to shared implementations (DRY)
# ---------------------------------------------------------------------------

def _reliability_bins(probs: object, outcomes: object) -> List[Tuple[float, float, float, float, int]]:
    """Return (lo, hi, mean_pred, mean_obs, n) for N_BINS equal-width bins.

    Delegates to scripts.platformkit.calibration_conformance._reliability_bins;
    converts BinResult dataclasses to the internal tuple format used by renderers.
    """
    import numpy as np
    p, o = np.asarray(probs, float), np.asarray(outcomes, float)
    return [
        (b.bin_lo, b.bin_hi, b.mean_pred, b.mean_obs, b.n)
        for b in _cc_reliability_bins(p, o, N_BINS)
    ]


def _segment_ece(probs: object, outcomes: object,
                 dates: List[str]) -> List[Tuple[str, int, float]]:
    """Per-calendar-year ECE: [(year_str, n, ece), ...] for years with n >= 5."""
    import numpy as np, pandas as pd  # noqa: E401
    p, o = np.asarray(probs, float), np.asarray(outcomes, float)
    yrs = pd.Series(pd.to_datetime(dates)).dt.year.astype(str).to_numpy()
    segs = []
    for yr in sorted(set(yrs)):
        mask = yrs == yr
        n_s = int(mask.sum())
        if n_s < 5:
            continue
        # Delegate ECE to kernel — avoids redundant per-bin round-trip
        ece = _kernel_ece(p[mask], o[mask], bins=N_BINS)
        if not math.isnan(ece):
            segs.append((yr, n_s, ece))
    return segs


# ---------------------------------------------------------------------------
# Note section renderers
# ---------------------------------------------------------------------------

def _header_section() -> List[str]:
    return [
        "## What These Numbers Are", "",
        "> **Honest framing:** RELIABILITY diagnostics — per-probability-bucket calibration",
        "> and per-season ECE from each sport's real walk-forward corpus.",
        ">",
        "> **Calibration != edge.** Well-calibrated means P(outcome=1 | pred=p) ≈ p.",
        "> It does NOT mean the model outperforms the closing line or that any edge exists.",
        "> Every signal candidate REJECTS through src.loop.gate. REJECT = honest success.",
        ">",
        "> Soccer O/U 2.5 may show systematic over-prediction in moderate-λ ranges —",
        "> surfaced honestly; does not imply a market edge.", "",
    ]


def _sport_section(display: str, sport_id: str,
                   bins: List[Tuple[float, float, float, float, int]],
                   segs: List[Tuple[str, int, float]],
                   ece: float, n: int) -> List[str]:
    ece_s = f"{ece:.4f}" if not math.isnan(ece) else "n/a"
    L: List[str] = [
        f"### {display}", "",
        f"- **Corpus n:** {n:,}",
        f"- **Overall ECE (10-bin):** {ece_s}",
        "- **Reliability note:** ECE < 0.05 = PASS, < 0.10 = WARN, >= 0.10 = FAIL"
        " — reliability quality only, NOT edge.", "",
    ]
    if sport_id == "soccer_fd":
        L += [f"> {_SOCCER_NOTE}", ""]
    L += ["#### Reliability Diagram (Probability Deciles)", ""]
    rows = [
        ([f"[{lo:.1f},{hi:.1f})", f"{mp:.4f}", f"{mo:.4f}", str(n_b), f"{abs(mo-mp):.4f}"]
         if n_b else [f"[{lo:.1f},{hi:.1f})", "—", "—", "0", "—"])
        for lo, hi, mp, mo, n_b in bins
    ]
    L += [md_table(["Bin", "Pred (mean)", "Obs (freq)", "n", "Gap (|obs-pred|)"], rows), ""]
    if segs:
        L += ["#### Per-Season ECE (reliability quality by segment)", ""]
        L += [md_table(["Season / Year", "n", "ECE"],
                       [[s, str(sn), f"{se:.4f}"] for s, sn, se in segs]), ""]
    else:
        L += ["> No segments with n >= 5 found (single season or absent dates).", ""]
    return L


def _skipped_section(skipped: List[str]) -> List[str]:
    if not skipped:
        return []
    return (["## Skipped Sports (corpus absent)", ""]
            + [f"- **{s}** — corpus files not found or adapter import failed; "
               "run the domain ingest script to populate." for s in skipped]
            + [""])


def _links_section() -> List[str]:
    return [
        "## Source Notes", "",
        "- [[_Hub]] — multi-sport registry (Up)",
        "- [[_Base_Rates]] — cross-sport unconditional outcome frequencies",
        "- [[_World_Model]] — cross-sport platform knowledge synthesis",
        "- [[_Signals_Hub]] — cross-sport signal-discovery aggregator",
        "",
    ]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_calibration_segments(vault_sports_dir: Optional[pathlib.Path] = None) -> pathlib.Path:
    """Compute per-sport calibration-by-segment diagnostics; write _Calibration_Segments.md.

    Per sport: reliability diagram by probability decile + per-season ECE.
    Honest: calibration is a reliability diagnostic only.  No edge claimed.
    Person-free.  Gracefully skips absent corpora.
    """
    import numpy as np  # noqa: F401 — imported for type usage in helpers
    if vault_sports_dir is None:
        repo_root = pathlib.Path(__file__).resolve().parents[3]
        vault_sports_dir = repo_root / "vault" / "Sports"
    else:
        repo_root = pathlib.Path(vault_sports_dir).resolve().parents[1]
    vault_sports_dir = pathlib.Path(vault_sports_dir)
    if not vault_sports_dir.is_dir():
        raise FileNotFoundError(f"vault/Sports dir not found: {vault_sports_dir}")

    sport_sections: List[str] = []
    skipped: List[str] = []
    computed: List[str] = []

    for sport_id, display, adapter_module, adapter_class, group_col in _SPORT_SPECS:
        bundle = _load_bundle(repo_root, adapter_module, adapter_class)
        if bundle is None:
            skipped.append(display)
            continue
        try:
            import numpy as np_
            raw_p = np_.asarray(bundle.signal_col, dtype=float)
            raw_o = np_.asarray(bundle.target, dtype=float)
            valid = ~(np_.isnan(raw_p) | np_.isnan(raw_o))
            probs, outcomes = raw_p[valid], raw_o[valid]
            n_total = int(len(probs))
            if n_total == 0:
                skipped.append(display)
                continue
            dates_raw = list(getattr(bundle, "dates", None) or [])
            valid_dates = [str(dates_raw[i]) for i in range(len(raw_p)) if valid[i]]
            bins = _reliability_bins(probs, outcomes)
            overall_ece = _kernel_ece(probs, outcomes, bins=N_BINS)
            segs = _segment_ece(probs, outcomes, valid_dates) if valid_dates else []
        except Exception:  # noqa: BLE001
            skipped.append(display)
            continue
        sport_sections += _sport_section(display, sport_id, bins, segs, overall_ece, n_total)
        sport_sections += ["---", ""]
        computed.append(display)

    fm = frontmatter({
        "tags":             ["calibration", "reliability", "meta", "cross-sport", "honest"],
        "generated":        time.strftime("%Y-%m-%d"),
        "sports_computed":  len(computed),
        "sports_skipped":   len(skipped),
        "calibration_note": '"well-calibrated != profitable; no edge claimed"',
    })
    L: List[str] = [
        fm, "",
        "# Per-Sport Calibration by Segment", "",
        "> **Auto-generated** by `scripts/platformkit/atlas/calibration_segments.py`"
        " — do not hand-edit.  Re-run `build_calibration_segments()` to refresh.", "",
        "> **Honest framing:** reliability diagnostics only.  Calibration != edge.",
        "> No durable betting edge is claimed.  REJECT = honest success criterion.", "",
        "Up: [[_Hub]]", "", "---", "",
    ]
    L += _header_section()
    L += ["---", ""]
    if sport_sections:
        L += ["## Per-Sport Reliability Diagnostics", ""] + sport_sections
    skip_sec = _skipped_section(skipped)
    if skip_sec:
        L += skip_sec + ["---", ""]
    L += _links_section()
    L += [
        "---", "",
        f"*Generated {time.strftime('%Y-%m-%d %H:%M:%S')} · "
        f"{len(computed)} sport(s) computed · {len(skipped)} skipped · "
        "person-free · calibration != edge · no edge claimed*", "",
        "_PRIVATE research.  Reliability diagnostics only.  No edge claimed._",
    ]
    return write_note(vault_sports_dir / _OUT_FILENAME, "\n".join(L) + "\n")


if __name__ == "__main__":
    import sys
    vault_arg = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    print(f"Written: {build_calibration_segments(vault_arg)}")
