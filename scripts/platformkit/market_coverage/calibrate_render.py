"""market_coverage.calibrate_render -- ASCII scoreboard rendering for calibrate.py.

Pure presentation, split out so the calibration ENGINE (calibrate.py) stays <=300 LOC.
Takes the engine's family spec + verdict vocabulary as arguments (no import back into
calibrate, so there is no circular import). Emits CALIBRATION verdicts only -- never a $
claim. Stdlib only. ASCII. Per-file test: covered via test_calibrate.py (build_scoreboard).
"""
from __future__ import annotations

from typing import Dict, List


def fmt_market_row(r: dict) -> str:
    """One markdown table row for a calibrated market (handles missing-close cells)."""
    b = f"{r['brier']:.4f}" if r.get("brier") is not None else "n/a"
    bc = f"{r['brier_close']:.4f}" if r.get("brier_close") is not None else "  --  "
    bss = f"{r['bss_vs_close']:+.4f}" if r.get("bss_vs_close") is not None else "  --  "
    dmp = f"{r['dm_p']:.3f}" if r.get("dm_p") is not None else " -- "
    ece_s = f"{r['ece']:.4f}" if r.get("ece") is not None else "n/a"
    flag = (" [" + ", ".join(r["flags"]) + "]") if r.get("flags") else ""
    return (f"| {r['market']:<34} | {r['n']:>4} | {b} | {ece_s} | {bc} | {bss} "
            f"| {dmp:>5} | {r['data_status']:<18} | {r['verdict']}{flag} |")


def build_scoreboard(results: Dict[str, List[dict]], *, families: Dict[str, dict],
                     enumeration: List[str], disclaimer: str, flag_fwd_clv: str,
                     v_efficient: str, v_calib: str, v_suggestive: str,
                     v_behind: str, v_abstain: str) -> List[str]:
    """Render the per-market calibration scoreboard. CALIBRATION verdicts only, no $."""
    lines: List[str] = [
        "# Market-Coverage Calibration Scoreboard", "",
        "> " + disclaimer, "",
        "Reliability + Brier vs the (Shin-devigged) close for EVERY market across the "
        "7 families. Verdicts are CALIBRATION verdicts -- never $ claims.", "",
    ]
    tot = n_eff = n_calib = n_sugg = n_behind = n_abstain = 0
    for fam in enumeration:
        if fam not in results:
            continue
        spec = families[fam]
        lines += [f"## {fam}   [{spec['liquidity']}]", "", f"{spec['note']}", "",
                  "| market | n | brier | ece | brier_close | bss | dm_p | data_status | verdict |",
                  "|--------|---|-------|-----|-------------|-----|------|-------------|---------|"]
        for r in results[fam]:
            lines.append(fmt_market_row(r))
            tot += 1
            v = r["verdict"]
            n_eff += v == v_efficient
            n_calib += v == v_calib
            n_sugg += v == v_suggestive
            n_behind += v == v_behind
            n_abstain += v == v_abstain
        lines.append("")
    lines += [
        "## Summary", "",
        f"- markets calibrated: {tot}",
        f"- MARKET-EFFICIENT HERE (match the close): {n_eff}",
        f"- CALIBRATED (no local close -- VALIDATION_PENDING): {n_calib}",
        f"- BEHIND (trail the close, honest): {n_behind}",
        f"- SUGGESTIVE (soft-line beat -- {flag_fwd_clv}): {n_sugg}",
        f"- ABSTAIN (too few rows): {n_abstain}", "",
        "THE HONEST CATCH: the obscure / prop / combo / SGP / in-game-micro lane -- "
        "where the mispricing edge would live -- has NO local historical close, so "
        "those markets are PRICED + CALIBRATED now but only VALIDATABLE via forward "
        "capture (the forward_capture clock). Real $ is further capped by book limits. "
        "No survivor is claimed; every soft-line beat carries '" + flag_fwd_clv + "'.", "",
        "Reproduce (offline, deterministic, < 60s):", "```",
        "python -m scripts.platformkit.market_coverage.calibrate", "```",
    ]
    return lines
