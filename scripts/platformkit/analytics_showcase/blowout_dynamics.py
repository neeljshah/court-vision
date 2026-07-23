"""Blowout dynamics: when does a game become 'decided'?

Per game in the joined grade corpora, order score ticks by game clock and find
each margin threshold's POINT OF NO RETURN -- the first tick from which
|home_score-away_score| stays >= threshold to the end (after the LAST reversion).
Report WHEN (game clock + fraction of game elapsed) and in WHAT SHARE of games it
happens, by sport x threshold. Describes games ALREADY PLAYED; reads only the
score path from state_summary (scores + inning/half or minute), never model/market
prob -- no calibration/forecast/edge claim. DESCRIPTIVE_ONLY, edge_claimed=False.

Corpora: data/cache/ingame_grade_joined/{mlb,soccer_intl}/*.jsonl (read-only,
game_id/ts/state_summary only; mlb_clean byte-dup not loaded). FLOORS (declared,
not tuned): MIN_TICKS_PER_GAME=10; MIN_GAMES_PER_THRESHOLD=10 (a cell reports
median/quartiles only at >=10 decided games, else keeps its n but is masked from
chart+headline). Truth source: docs/JOB_EVIDENCE_PACKET.md. Outputs: out/
blowout_dynamics.json + docs/img/blowout_dynamics.png (ONE figure, panel/sport).
CLI: python -m scripts.platformkit.analytics_showcase.blowout_dynamics [--check]
"""
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

# Reuse the existing joined-corpus loader (mlb_clean excluded by only calling mlb/soccer_intl).
try:
    from scripts.platformkit.analytics_showcase.state_conditioned_calibration import load_records
except ImportError:  # bare / script-mode execution
    from state_conditioned_calibration import load_records

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "blowout_dynamics.json"
OUT_PNG = REPO / "docs" / "img" / "blowout_dynamics.png"

MIN_TICKS_PER_GAME = 10
MIN_GAMES_PER_THRESHOLD = 10

SPORTS = {
    "mlb":         {"unit": "runs",  "clock": "inning", "thresholds": [2, 3, 4, 5]},
    "soccer_intl": {"unit": "goals", "clock": "minute", "thresholds": [1, 2, 3]},
}

_SCORE_RE = re.compile(r"home_score=([-\d.]+)\s+away_score=([-\d.]+)")
_INNING_RE = re.compile(r"inning=(\d+)")
_HALF_RE = re.compile(r"half=(\w+)")
_MINUTE_RE = re.compile(r"minute=(\d+)")


def _abs_margin(state):
    m = _SCORE_RE.search(state or "")
    if not m:
        return None
    return abs(float(m.group(1)) - float(m.group(2)))


def _clock(sport, state):
    """Continuous game clock: MLB inning + 0.5 for the bottom half; soccer minute."""
    s = state or ""
    if sport == "mlb":
        m = _INNING_RE.search(s)
        if not m:
            return None
        inn = float(m.group(1))
        h = _HALF_RE.search(s)
        return inn + (0.5 if (h and h.group(1).startswith("bot")) else 0.0)
    m = _MINUTE_RE.search(s)
    return float(m.group(1)) if m else None


def game_paths(sport):
    """Return (n_games_raw, {game_id: [(clock, abs_margin), ...] ordered by
    (clock, ts)}). Games with < MIN_TICKS_PER_GAME parseable ticks are dropped."""
    _files, recs = load_records(sport)
    by_game = defaultdict(list)
    for r in recs:
        gid = r.get("game_id")
        state = r.get("state_summary")
        if not gid or not state:
            continue
        am = _abs_margin(state)
        ck = _clock(sport, state)
        if am is None or ck is None:
            continue
        by_game[gid].append((ck, r.get("ts", ""), am))
    paths = {}
    for gid, ticks in by_game.items():
        if len(ticks) < MIN_TICKS_PER_GAME:
            continue
        ticks.sort(key=lambda t: (t[0], t[1]))
        paths[gid] = [(ck, am) for ck, _ts, am in ticks]
    return len(by_game), paths


def decided_point(abs_seq, thr):
    """Index of the first tick from which |margin| stays >= thr for the rest of
    the game (the point of no return). None if the final |margin| < thr (the game
    never became decided at this threshold). abs_seq must be in game-time order."""
    if not abs_seq or abs_seq[-1] < thr:
        return None
    last_below = -1
    for i, am in enumerate(abs_seq):
        if am < thr:
            last_below = i
    return last_below + 1  # first index from which it never drops below thr again


def analyze_threshold(paths, thr):
    clocks, clockfracs = [], []
    n_decided = 0
    for seq in paths.values():
        abs_seq = [a for _, a in seq]
        idx = decided_point(abs_seq, thr)
        if idx is None:
            continue
        n_decided += 1
        dclock = seq[idx][0]
        fclock = seq[-1][0]
        clocks.append(dclock)
        if fclock > 0:
            clockfracs.append(min(dclock / fclock, 1.0))
    n_total = len(paths)
    cell = {
        "threshold": thr,
        "n_games_total": n_total,
        "n_games_decided": n_decided,
        "decided_frac_of_games": round(n_decided / n_total, 4) if n_total else None,
        "masked_below_floor": n_decided < MIN_GAMES_PER_THRESHOLD,
    }
    if clocks and n_decided >= MIN_GAMES_PER_THRESHOLD:
        arr = np.asarray(clocks, dtype=float)
        fr = np.asarray(clockfracs, dtype=float)
        cell.update({
            "decided_clock_median": round(float(np.median(arr)), 3),
            "decided_clock_p25": round(float(np.percentile(arr, 25)), 3),
            "decided_clock_p75": round(float(np.percentile(arr, 75)), 3),
            "decided_clock_mean": round(float(arr.mean()), 3),
            "decided_clockfrac_median": round(float(np.median(fr)), 4),
            "decided_clockfrac_p25": round(float(np.percentile(fr, 25)), 4),
            "decided_clockfrac_p75": round(float(np.percentile(fr, 75)), 4),
        })
    return cell


def analyze_sport(sport):
    cfg = SPORTS[sport]
    n_games_raw, paths = game_paths(sport)
    return {
        "unit": cfg["unit"],
        "clock_field": cfg["clock"],
        "n_games_raw": n_games_raw,
        "n_games_usable": len(paths),
        "min_ticks_floor": MIN_TICKS_PER_GAME,
        "thresholds": [analyze_threshold(paths, t) for t in cfg["thresholds"]],
    }


def build_story(result):
    def phrase(cfg, c):
        return ("a %d-%s gap becomes permanent by median %s %.1f in %.0f%% of games"
                % (c["threshold"], cfg["unit"], cfg["clock"], c["decided_clock_median"],
                   100 * c["decided_frac_of_games"]))
    parts = []
    for sport, s in result["sports"].items():
        cfg = SPORTS[sport]
        cells = [c for c in s["thresholds"] if c.get("decided_clock_median") is not None]
        head = "%s (%d games): " % (sport, s["n_games_usable"])
        if not cells:
            parts.append(head + "no threshold cleared the >=%d-game floor." % MIN_GAMES_PER_THRESHOLD)
        elif len(cells) == 1:
            parts.append(head + phrase(cfg, cells[0]) + " (only threshold above floor).")
        else:
            parts.append(head + phrase(cfg, cells[0]) + "; " + phrase(cfg, cells[-1])
                         + " -- later and rarer as the gap grows.")
    return " ".join(parts) + " Descriptive game-flow only; no edge/ROI/$ claim."


def make_plot(result):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    sports = [s for s in SPORTS if s in result["sports"]]
    if not sports:
        return False
    fig, axes = plt.subplots(1, len(sports), figsize=(5.2 * len(sports), 5), sharey=True)
    if len(sports) == 1:
        axes = [axes]
    for ax, sport in zip(axes, sports):
        cfg = SPORTS[sport]
        xs, med, lo, hi, ann = [], [], [], [], []
        for c in result["sports"][sport]["thresholds"]:
            if c.get("decided_clockfrac_median") is None:
                continue
            xs.append(c["threshold"])
            med.append(c["decided_clockfrac_median"])
            lo.append(c["decided_clockfrac_p25"])
            hi.append(c["decided_clockfrac_p75"])
            ann.append((c["threshold"], c["decided_clockfrac_median"],
                        c["n_games_decided"], c["decided_clock_median"]))
        if xs:
            if len(xs) >= 2:
                ax.fill_between(xs, lo, hi, alpha=0.2, color="tab:blue", label="p25-p75")
            ax.plot(xs, med, "o-", color="tab:blue", label="median")
            for tx, ty, n, mc in ann:
                ax.annotate("n=%d\nmed %.1f%s" % (n, mc, cfg["clock"][:3]),
                            (tx, ty), textcoords="offset points", xytext=(6, 6), fontsize=7)
        else:
            ax.text(0.5, 0.5, "no threshold above floor", ha="center", va="center",
                    transform=ax.transAxes, fontsize=9)
        ax.set_title("%s (%s)" % (sport, cfg["unit"]))
        ax.set_xlabel("margin threshold (%s)" % cfg["unit"])
        ax.set_xticks(cfg["thresholds"])
        ax.set_ylim(0, 1)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8, loc="lower right")
    axes[0].set_ylabel("fraction of game elapsed when decided\n(median, IQR band)")
    fig.suptitle("When do games become 'decided'? First |margin| crossing that never reverts")
    fig.text(0.5, 0.005,
             "Source: data/cache/ingame_grade_joined/{mlb,soccer_intl} score paths. "
             "DESCRIPTIVE_ONLY, edge_claimed=False. Floors: >=%d ticks/game, >=%d games/threshold."
             % (MIN_TICKS_PER_GAME, MIN_GAMES_PER_THRESHOLD), ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=130)
    plt.close(fig)
    return True


def run():
    result = {
        "edge_claimed": False,
        "descriptive_only": True,
        "method": ("Per game, order score ticks by (game-clock, ts); a margin threshold's point "
                   "of no return is the first tick from which |home_score-away_score| stays "
                   ">= threshold to the end. Reads only the score path, not model/market prob."),
        "floors": {
            "min_ticks_per_game": MIN_TICKS_PER_GAME,
            "min_games_per_threshold": MIN_GAMES_PER_THRESHOLD,
            "note": ("declared once, not tuned to output; a (sport,threshold) cell below the "
                     "game floor keeps its n but is masked from chart + headline."),
        },
        "prior_art": ("Descriptive 'point of no return' / clinch-time measurement, in the tradition "
                      "of safe-lead heuristics (e.g. Bill James NBA safe-lead) and win-probability "
                      "clinch points. Not a new method; do not claim first-ever."),
        "sports": {},
        "skipped": [{"sport": "mlb_clean",
                     "reason": "byte-identical duplicate of mlb (per state_conditioned_calibration); not loaded"}],
    }
    for sport in SPORTS:
        result["sports"][sport] = analyze_sport(sport)
    result["story"] = build_story(result)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    result["plot_written"] = make_plot(result)
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    return result


def check():
    # 1) logic self-check on decided_point (no data needed)
    seq = [0, 1, 0, 2, 3, 2, 4]
    assert decided_point(seq, 2) == 3, decided_point(seq, 2)   # last dip below 2 is idx 2 -> 3
    assert decided_point(seq, 4) == 6, decided_point(seq, 4)   # only final tick >= 4
    assert decided_point(seq, 5) is None                        # final margin < 5
    assert decided_point([3, 3, 3], 2) == 0                     # never below -> decided at start
    assert decided_point([], 1) is None
    # 2) outputs nonzero + internally consistent
    assert OUT_JSON.exists() and OUT_JSON.stat().st_size > 0, OUT_JSON
    data = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    assert data.get("edge_claimed") is False
    assert data.get("sports"), "no sports analyzed"
    total_usable = sum(s.get("n_games_usable", 0) for s in data["sports"].values())
    assert total_usable > 0, "no usable games in any sport"
    for s in data["sports"].values():
        for c in s["thresholds"]:
            assert c["n_games_decided"] <= c["n_games_total"], c
            if c["decided_frac_of_games"] is not None:
                assert 0.0 <= c["decided_frac_of_games"] <= 1.0, c
            if c.get("decided_clockfrac_median") is not None:
                assert 0.0 <= c["decided_clockfrac_median"] <= 1.0, c
    assert OUT_PNG.exists() and OUT_PNG.stat().st_size > 0, OUT_PNG
    print("OK: blowout_dynamics self-check passed (%d usable games)" % total_usable)


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        check()
    else:
        res = run()
        print(json.dumps({
            "json_out": str(OUT_JSON),
            "png_out": str(OUT_PNG) if res.get("plot_written") else None,
            "story": res["story"],
            "usable_games": {s: v["n_games_usable"] for s, v in res["sports"].items()},
        }, indent=2, ensure_ascii=True))
