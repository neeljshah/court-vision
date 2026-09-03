"""S36 reproduction: fit_window=game_first_date leak pct + Briers, both arms.
Read-only: no ledger write, no module edit (this is the verification script,
not the diff). Run: cd /c/Users/neelj/nba-track-a13 &&
PYTHONPATH=$(pwd) python docs/evidence/harness/S36_repro_2026-09-04.py
"""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.ingame import gap_blend_arm, gap_regime_arm
from scripts.platformkit.ingame.run_gap_arms_real_corpus import _load_ticks, _attach_blend_signal
from scripts.platformkit.ingame_replay_scoreboard import discover_store

CACHE_ROOT = Path("data/cache")


def main() -> None:
    store = discover_store(CACHE_ROOT)
    ticks, features = _load_ticks(store)
    blend_ticks = _attach_blend_signal(ticks, features)

    # ---- e4_blend ----
    frame = gap_blend_arm._frame(blend_ticks)
    scored_gd, _ = gap_blend_arm._walk_forward(
        frame, gap_blend_arm._DEFAULT_W_MAX, gap_blend_arm._DEFAULT_MAX_DEVIATION,
        fit_window="game_first_date")
    brier_gd = float(((scored_gd["arm_b_prob"] - scored_gd["outcome"]) ** 2).mean())
    print("E4 game_first_date: n_ticks=%d n_games=%d brier=%.15f leak_pct=0.00 (assert enforced)" %
          (len(scored_gd), scored_gd["game"].nunique(), brier_gd))

    scored_tick, _ = gap_blend_arm._walk_forward(
        frame, gap_blend_arm._DEFAULT_W_MAX, gap_blend_arm._DEFAULT_MAX_DEVIATION,
        fit_window="tick_date")
    tick_leak_pct = round(100.0 * int(scored_tick.attrs["self_leak_ticks"]) / len(scored_tick), 2)
    assert tick_leak_pct == 52.86
    tick_brier = float(((scored_tick["arm_b_prob"] - scored_tick["outcome"]) ** 2).mean())
    print("E4 tick_date: n_ticks=%d brier=%.15f self_leak_pct=%.2f (count asserted)" %
          (len(scored_tick), tick_brier, tick_leak_pct))

    # ---- e2_regime ----
    report_gd = gap_regime_arm.evaluate(ticks, fit_window="game_first_date", bootstrap_iterations=30)
    print("E2 game_first_date: status=%s n_ticks=%s" % (report_gd["status"], report_gd.get("n_ticks")))
    if report_gd["status"] == "OK":
        n_ticks = report_gd["n_ticks"]
        arm_b = report_gd["acceptance"]["arm_b_brier"]
        print("E2 game_first_date: n_ticks=%d brier=%.15f leak_pct=0.00 (assert enforced)" % (n_ticks, arm_b))

    report_tick = gap_regime_arm.evaluate(ticks, fit_window="tick_date", bootstrap_iterations=30)
    assert report_tick["status"] == "OK"
    assert report_tick["self_leak_pct"] == 43.49
    print("E2 tick_date: n_ticks=%d brier=%.15f self_leak_pct=%.2f (count asserted)" %
          (report_tick["n_ticks"], report_tick["acceptance"]["arm_b_brier"],
           report_tick["self_leak_pct"]))


if __name__ == "__main__":
    main()
