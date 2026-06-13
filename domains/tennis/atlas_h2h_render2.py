"""domains.tennis.atlas_h2h_render2 — Rematch-effects renderer (split from atlas_h2h_render).

Consumed by atlas_h2h_render (re-exported) and ultimately by atlas_h2h.build_h2h().
F5-clean: stdlib + pathlib only.  No src.* / kernel.* / other-domain imports.
No edge / betting language anywhere.  No person names.
"""
from __future__ import annotations

import pathlib
from typing import Dict, List


def _frontmatter(tags: List[str]) -> List[str]:
    """Return standard YAML frontmatter lines."""
    tag_lines = [f"  - {t}" for t in tags]
    return ["---", "tags:"] + tag_lines + ["---"]


def _write(path: pathlib.Path, lines: List[str]) -> pathlib.Path:
    """Write lines as UTF-8 text, always ending with a newline."""
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def render_rematch_effects(
    rematch_eff: Dict[str, float],
    out_dir: pathlib.Path,
) -> pathlib.Path:
    """Emit _Rematch_Effects.md — rematch win-rate shift after first meeting."""
    out_dir.mkdir(parents=True, exist_ok=True)

    q_pairs = int(rematch_eff.get("qualifying_pairs", 0))
    repeat_pct = float(rematch_eff.get("first_winner_repeats_pct", 0.0))
    sample = int(rematch_eff.get("sample_size", 0))

    if q_pairs > 0:
        summary = (
            f"Across **{q_pairs:,}** pairs with at least two meetings "
            f"({sample:,} sequential matchups analysed), the first-meeting winner "
            f"also won the second meeting in **{repeat_pct:.1f}%** of cases."
        )
        if repeat_pct > 55:
            interp = (
                "This rate above 55% suggests a moderate momentum or psychological "
                "carry-over from the first encounter."
            )
        elif repeat_pct < 45:
            interp = (
                "This rate below 45% suggests a reversal tendency — opponents adjust "
                "after the first meeting."
            )
        else:
            interp = (
                "This rate near 50% is consistent with no systematic rematch advantage; "
                "each encounter is largely independent."
            )
    else:
        summary = "Insufficient data to compute rematch effects in this corpus window."
        interp = ""

    lines = _frontmatter(["sport/tennis", "matchup", "aggregate", "rematch"]) + [
        "",
        "# H2H Rematch Effects",
        "",
        "[[_Matchups_Index|← Matchups Index]] · [[_Index|← Tennis Index]]",
        "",
        "Does winning the first meeting between two players predict winning "
        "the second?  This note quantifies corpus-wide rematch carry-over.",
        "",
        "## First-Meeting Winner Repeat Rate",
        "",
        summary,
        "",
        "### Interpretation",
        "",
        interp if interp else "No interpretation available (insufficient data).",
        "",
        "### Methodology",
        "",
        "- For each pair with two or more meetings, matches are sorted by date.",
        "- A 'repeat' is when the first-meeting winner also wins the second meeting.",
        "- Only the first two meetings per pair are used to avoid selection bias "
        "from high-frequency rivalries.",
        "",
        "---",
        "#sport/tennis #matchup #aggregate #rematch",
    ]

    return _write(out_dir / "_Rematch_Effects.md", lines)
