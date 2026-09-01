"""Render the reproducible retro multiplicity report from on-disk catalog classes."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Tuple

from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, eps_eff

_ROOT = Path(__file__).resolve().parents[3]
_REPORT = Path(__file__).with_name("retro_correction_report.txt")
RETRO_SWEEP_TRIALS = 85  # pre-registered historical sweep width; do not shrink to archive survivors.


def catalog_signals() -> List[Tuple[str, str]]:
    """Return (domain, class) pairs without importing human-gated signal code."""
    pairs: List[Tuple[str, str]] = []
    for path in sorted((_ROOT / "domains").glob("*/signal_catalog*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name.endswith("Signal"):
                pairs.append((path.parent.name, node.name))
    return pairs


def render_report(pairs: List[Tuple[str, str]]) -> str:
    """Render the evidence-limited retro judgment without inventing raw statistics."""
    k = RETRO_SWEEP_TRIALS
    lines = [
        "EVAL-GATE RETRO MULTIPLICITY CORRECTION",
        "Evidence boundary: 60 current catalog classes are on disk; historical per-signal",
        "DM vectors are not archived. Published catalog outcome is REJECT-first.",
        "Corrected verdict therefore preserves every documented REJECT. No survivor is inferred.",
        "",
        "signal                                      raw verdict  corrected verdict  n_trials",
        "------------------------------------------  -----------  -----------------  --------",
    ]
    for domain, name in pairs:
        signal = (domain + ":" + name)[:42]
        lines.append(f"{signal:<42}  {'REJECT':<11}  {'REJECT':<17}  {k:>8}")
    lines += ["", f"catalog_signals_on_disk={len(pairs)}  n_trials_this_sweep={k}  bonferroni_eps={eps_eff(DEFAULT_EPS, k):.8f}",
              "survivors=0", ""]
    return "\n".join(lines)


def write_report(path: Path = _REPORT) -> str:
    """Write and return the ASCII retro report."""
    text = render_report(catalog_signals())
    path.write_text(text, encoding="ascii")
    return text


if __name__ == "__main__":  # pragma: no cover
    print(write_report(), end="")
