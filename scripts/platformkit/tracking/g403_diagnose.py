"""G403 diagnostics: sealed reason taxonomy, binding-offset test, shot-category audit."""

from __future__ import annotations

import math
import re
from typing import Mapping, Optional, Sequence

CATEGORIES = ("RIM_HARDWARE", "BENCH_BALL", "JERSEY", "OTHER_OBJECT",
              "SAME_OBJECT_LOCALISATION", "UNRESOLVED")

_SAME_STRONG = re.compile(r"both crops agree|both centres|both rater centres|same ball|"
                          r"midpoint of the two centres")
_SAME_WEAK = re.compile(r"centre closer|centre within|centre essentially on it|centre adopted|"
                        r"centre ~\d|within \d+ px|centre on it")
_RIM = re.compile(r"rim hardware|hoop hardware|hoop/board hardware|rim and net|occluded by the net|"
                  r"is the rim|consistent with the rim|backboard|near the rim")
_BENCH = re.compile(r"(basketball|ball|rounded object)[^.;]{0,30}(at|near|in front of|beside) the bench")
_BALLISH = re.compile(r"basketball|\bball\b|rounded object")
_NO_BALL = re.compile(r"no ball|no identifiable ball|shows no ball|not resolvable|cannot be confirmed|"
                      r"cannot be identified|cannot be separated|not established|no separable ball|"
                      r"too small to be the ball|not confirmable|no centre can be confirmed")
_JERSEY = re.compile(r"jersey|shorts")
_OTHER = re.compile(r"graphic|ad board|led board|advertis|score|clock|court logo|bare court|"
                    r"bare floor|blurred floor|open floor|open court|sideline|stands|crowd|"
                    r"spectator|jacket|black background|\barm\b|legs|shoulder|banner|bench|"
                    r"player|defender|hands only|no ball in frame|no ball anywhere")


def categorize(basis: str, resolved_label: str) -> tuple[str, str]:
    """Join one existing adjudication reason to the sealed categories (primary, secondary).

    SAME_OBJECT_LOCALISATION means the only object the adjudication names is the game
    ball itself -- a centre offset on one ball, or one rater not reporting that ball.
    UNRESOLVED means the adjudication names no object for the disputed centre.
    """
    text = basis.lower()
    named: list[str] = []
    if _RIM.search(text):
        named.append("RIM_HARDWARE")
    if _BENCH.search(text):
        named.append("BENCH_BALL")
    if _JERSEY.search(text):
        named.append("JERSEY")
    if _OTHER.search(text):
        named.append("OTHER_OBJECT")
    named = [name for name in CATEGORIES if name in named]
    same = resolved_label == "VISIBLE" and (_SAME_STRONG.search(text) or _SAME_WEAK.search(text))
    if not named:
        if resolved_label == "VISIBLE" and not _NO_BALL.search(text):
            return "SAME_OBJECT_LOCALISATION", ""
        return "UNRESOLVED", ""
    if resolved_label == "VISIBLE" and _SAME_STRONG.search(text):
        return "SAME_OBJECT_LOCALISATION", named[0]
    return named[0], ("SAME_OBJECT_LOCALISATION" if same else (named[1] if len(named) > 1 else ""))


def centre_bar_px(diameter: Optional[float], height: int) -> float:
    """The sealed centre rule: max(3 px, diameter_720p / 2) at the frame's native height."""
    if not diameter or not height:
        return 3.0
    return max(3.0, (diameter * (720.0 / height)) / 2.0)


def _centre(row: Mapping[str, object], who: str) -> Optional[tuple[float, float, float]]:
    try:
        cx, cy, diameter = (float(row["%s_cx" % who]), float(row["%s_cy" % who]), float(row["%s_d" % who]))
    except (KeyError, TypeError, ValueError):
        return None
    return cx, cy, diameter


def binding_offset(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Test one round's answers for a one-card id-to-image binding slip.

    ALIGNED / SLIPPED is the convention-free contrast: whichever of the same-position
    or next-position partner centre is closer. `strict_lead_match` additionally
    requires the next-position match to sit inside the sealed centre rule.
    """
    aligned = slipped = indeterminate = strict = 0
    detail: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        terra = _centre(row, "terra")
        if terra is None:
            indeterminate += 1
            continue
        same = _centre(row, "sol")
        lead = _centre(rows[index + 1], "sol") if index + 1 < len(rows) else None
        d_same = math.hypot(terra[0] - same[0], terra[1] - same[1]) if same else None
        d_lead = math.hypot(terra[0] - lead[0], terra[1] - lead[1]) if lead else None
        verdict = "INDETERMINATE"
        if d_same is not None and d_lead is not None:
            verdict = "SLIPPED" if d_lead < d_same else "ALIGNED"
            aligned += verdict == "ALIGNED"
            slipped += verdict == "SLIPPED"
        else:
            indeterminate += 1
        if d_lead is not None and lead is not None and d_lead <= centre_bar_px(lead[2], int(row["height"])):
            strict += 1
        detail.append({"position": row.get("position"), "frame_key": row.get("frame_key"),
                       "verdict": verdict,
                       "d_same_px": None if d_same is None else round(d_same, 3),
                       "d_lead_px": None if d_lead is None else round(d_lead, 3)})
    return {"aligned": aligned, "slipped": slipped, "indeterminate": indeterminate,
            "strict_lead_match": strict, "detail": detail}


_STOP = frozenset({"no", "the", "a", "in", "on", "at", "of", "only", "and"})


def _tokens(text: str) -> frozenset[str]:
    return frozenset(word for word in re.findall(r"[a-z]+", text.lower()) if word not in _STOP)


def reason_alignment(reasons: Sequence[tuple[str, str]]) -> dict[str, float]:
    """Mean Jaccard of sol's reason against terra's same-position and previous-position text."""
    def jaccard(left: str, right: str) -> float:
        a, b = _tokens(left), _tokens(right)
        return len(a & b) / len(a | b) if a | b else 0.0
    same = [jaccard(sol, terra) for terra, sol in reasons]
    lead = [jaccard(reasons[i][1], reasons[i - 1][0]) for i in range(1, len(reasons))]
    return {"same_mean": round(sum(same) / len(same), 4) if same else 0.0,
            "lead_mean": round(sum(lead) / len(lead), 4) if lead else 0.0,
            "n_same": len(same), "n_lead": len(lead)}


# Shot-category audit: the G403 finisher's own eye read of 30 evenly indexed native
# sheets (global index 5, 15, ... 295 of the sealed 300-card order), recorded before
# any state label was consulted. UNCLASSIFIED is retained, never reassigned.
SHOT_AUDIT: dict[int, tuple[str, str]] = {
    5: ("PLAYER_CLOSEUP", "NON_PLAY"), 15: ("LIVE_PLAY_WIDE", "PLAY"),
    25: ("LIVE_PLAY_WIDE", "PLAY"), 35: ("PLAYER_CLOSEUP", "NON_PLAY"),
    45: ("LIVE_PLAY_WIDE", "PLAY"), 55: ("LIVE_PLAY_WIDE", "PLAY"),
    65: ("CROWD", "NON_PLAY"), 75: ("DEAD_BALL_SETUP", "NON_PLAY"),
    85: ("LIVE_PLAY_WIDE", "PLAY"), 95: ("BENCH_SIDELINE", "NON_PLAY"),
    105: ("LIVE_PLAY_WIDE", "PLAY"), 115: ("LIVE_PLAY_WIDE", "PLAY"),
    125: ("LIVE_PLAY_WIDE", "PLAY"), 135: ("LIVE_PLAY_WIDE", "PLAY"),
    145: ("LIVE_PLAY_TIGHT", "PLAY"), 155: ("PLAYER_CLOSEUP", "NON_PLAY"),
    165: ("LIVE_PLAY_WIDE", "PLAY"), 175: ("PLAYER_CLOSEUP", "NON_PLAY"),
    185: ("LIVE_PLAY_WIDE", "PLAY"), 195: ("LIVE_PLAY_WIDE", "PLAY"),
    205: ("PLAYER_CLOSEUP", "NON_PLAY"), 215: ("DEAD_BALL_SETUP", "NON_PLAY"),
    225: ("LIVE_PLAY_WIDE", "PLAY"), 235: ("LIVE_PLAY_WIDE", "PLAY"),
    245: ("SIDELINE_OFFICIALS", "NON_PLAY"), 255: ("LIVE_PLAY_WIDE", "PLAY"),
    265: ("UNCLASSIFIED", "UNCLASSIFIED"), 275: ("PLAYER_CLOSEUP", "NON_PLAY"),
    285: ("BENCH_SIDELINE", "NON_PLAY"), 295: ("LIVE_PLAY_WIDE", "PLAY"),
}


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    """95 pct Wilson interval, so a 30-card share is never reported as a point census."""
    if total == 0:
        return (0.0, 0.0)
    z = 1.959964
    phat = successes / total
    denom = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denom
    spread = z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total)) / denom
    return (round(max(0.0, centre - spread), 4), round(min(1.0, centre + spread), 4))
