"""scripts.platformkit.calibration_banner -- the startup CALIBRATION CONTEXT banner.

The ONE thing the buyer-facing CLI (predict_matchup) prints on startup, to stderr, so
the --json stdout stays machine-parseable: last OOS Brier (the frozen golden anchor,
IN-CORPUS badge), the devigged-close Brier, the last recalibration date, and the binding
"calibration not edge; pregame market is efficient" framing.

The number is sourced from eval_gate/baselines/*.json so it stays honest and frozen,
never authored here. On a fresh clone with no baselines it degrades to a static line.

The full per-sport / per-market RELIABILITY DIAGRAMS live in the authoritative generator
`scripts.platformkit.calibration_record` (which pulls real per-row probs from the
eval-gate walk_forward + the ledger fixture and writes docs/CALIBRATION_RECORD.md). This
module deliberately does NOT duplicate that -- it is just the lightweight startup banner.

BINDING: decision-support, NOT a $ edge. edge_claimed is always False. No retracted
number is ever printed. ASCII only. <=300 LOC.
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import List, Optional

_HERE = pathlib.Path(__file__).resolve().parent
_BASELINE_DIR = _HERE / "eval_gate" / "baselines"

# golden anchor the banner quotes (a frozen, synthetic, IN-CORPUS calibration anchor).
_ANCHOR = "nba_2024_25"


def load_anchor(name: str = _ANCHOR) -> Optional[dict]:
    """Read one frozen baseline json (frozen OOS anchor). None if absent (fresh clone)."""
    p = _BASELINE_DIR / f"{name}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="ascii"))
    except Exception:  # noqa: BLE001 - banner is best-effort, never fatal
        return None


def banner_lines(name: str = _ANCHOR) -> List[str]:
    """Build the calibration-context banner as ASCII lines (pure, no side effects)."""
    a = load_anchor(name)
    head = "CALIBRATION CONTEXT -- decision-support, NOT a $ edge."
    framing = ("  calibration not edge; pregame market is efficient -- we MATCH the "
               "close, never beat it. In-game state conditioning is the measured, "
               "calibrated gap. See docs/CALIBRATION_RECORD.md.")
    if a is None:
        return [head,
                "  last OOS Brier: unavailable on this clone (frozen baselines are local).",
                framing]
    synth = " [SYNTHETIC ANCHOR]" if a.get("_synthetic") else ""
    bm, bc = a.get("brier_model"), a.get("brier_close")
    bm_s = f"{bm:.4f}" if isinstance(bm, (int, float)) else "n/a"
    bc_s = f"{bc:.4f}" if isinstance(bc, (int, float)) else "n/a"
    return [
        head,
        f"  last OOS Brier (nba ml, golden anchor{synth}): {bm_s}  [SOURCE: model in-corpus]",
        f"  devigged-close Brier: {bc_s}  [SOURCE: devigged-market]   "
        f"verdict: {a.get('verdict', 'MATCHES_CLOSE')}",
        f"  last recalibration: {a.get('frozen_at', 'unknown')}",
        framing,
    ]


def calib_context(name: str = _ANCHOR) -> str:
    """One-line form of the banner (for callers that want a compact string)."""
    return " ".join(ln.strip() for ln in banner_lines(name))


def print_banner(stream=None, name: str = _ANCHOR) -> None:
    """Print the banner to stderr (default) so --json stdout stays machine-parseable."""
    out = stream if stream is not None else sys.stderr
    for ln in banner_lines(name):
        print(ln, file=out)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="calibration_banner",
        description="Print the startup CALIBRATION CONTEXT banner (offline, honest).")
    ap.add_argument("--oneline", action="store_true", help="emit the one-line form")
    args = ap.parse_args(argv)
    if args.oneline:
        print(calib_context())
    else:
        for ln in banner_lines():
            print(ln)
    print("(full reliability diagrams: python -m scripts.platformkit.calibration_record)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
