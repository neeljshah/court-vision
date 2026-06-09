#!/usr/bin/env python
"""Fold an idempotent `## Outcome Impact` section into every canonical player +
team vault note, sourced from data/cache/intel_outcome/ artifacts.

This is the SINGLE WRITER for the OUTCOME-IMPACT marker block. It is fully
idempotent: re-running replaces everything between the markers, so a second run
produces no diff.

Sources (all read-only):
  - team_strength.json        (2025-26 SRS / record / totals / home-road)
  - team_schedule_spots.json  (2025-26 B2B vs rested)
  - player_availability.json  (2025-26 "who decides games" IN/OUT swings)
  - player_availability_v2.json (2025-26 OPPONENT-ADJUSTED IN/OUT margin swing, leak-safe)
  - player_plusminus.json     (2025-26 onoff-adjusted impact + 2024-25 ridge-RAPM)
  - player_onoff.json         (2024-25 PRIOR-SEASON on/off swing)
  - lineup_combos_v2.json     (2024-25 box net-rating; by_player/by_team partners/duos)
  - clutch_outcome.json       (2025-26 clutch records / player closer impact + leaderboard)
  - game_control.json         (2025-26 blowout/variance/quarter-net/lead-at-half — TEAM only)
  - team_injury_context.json  (2025-26 team fragility + most-indispensable, opp-adjusted — TEAM only)
  - who_decides_consensus.json   (multi-method consensus z + lone-method disagreement flags — PLAYER only)
  - player_stat_outcome.json     (2025-26 per-stat win-driver decomposition; dominant_driver — PLAYER only)
  - player_situational_outcome.json (2025-26 home/road +/- split + B2B fade — PLAYER only)
  - dossiers/<TRI>.json,
    dossiers/player_<pid>.json (Opus outcome_read narratives appended at section end)

Partner/duo names are rendered via a pid->clean-name map built from the vault
note H1 titles (NOT the raw artifact `name` strings, which are unicode-garbled
for some players, e.g. "Schr Der" -> "Schröder").

SCOUTING ONLY — association, not proven causation. Not a graded betting edge.

Usage:
    python scripts/intel/outcome/fold_outcome_impact.py            # write
    python scripts/intel/outcome/fold_outcome_impact.py --dry-run  # report only
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# --- repo-root anchored paths (script lives in scripts/intel/outcome/) ---
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", "..", ".."))
INTEL_DIR = os.path.join(REPO_ROOT, "data", "cache", "intel_outcome")
PLAYERS_DIR = os.path.join(REPO_ROOT, "vault", "Intelligence", "Players")
TEAMS_DIR = os.path.join(REPO_ROOT, "vault", "Intelligence", "Teams")

START = "<!-- OUTCOME-IMPACT START -->"
END = "<!-- OUTCOME-IMPACT END -->"
SCHEME_END = "<!-- SCHEME-AUTO END -->"
ROSTER_START = "<!-- ROSTER-AUTO START -->"

DISCLAIMER = (
    "_SCOUTING — association, not proven causation; not a graded betting edge._"
)


# --------------------------------------------------------------------------- #
# IO helpers
# --------------------------------------------------------------------------- #
def load_json(name: str) -> Optional[dict]:
    path = os.path.join(INTEL_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_dossier(rel: str) -> Optional[dict]:
    """Load a single dossier JSON (relative to INTEL_DIR), or None if absent."""
    path = os.path.join(INTEL_DIR, rel)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def fmt_signed(v: Any, nd: int = 2, suffix: str = "") -> str:
    if v is None:
        return "n/a"
    try:
        return f"{float(v):+.{nd}f}{suffix}"
    except (TypeError, ValueError):
        return "n/a"


def fmt_num(v: Any, nd: int = 1, suffix: str = "") -> str:
    if v is None:
        return "n/a"
    try:
        return f"{float(v):.{nd}f}{suffix}"
    except (TypeError, ValueError):
        return "n/a"


def fmt_pct(v: Any, nd: int = 1) -> str:
    """Fraction (0..1) -> percentage string with sign-free magnitude."""
    if v is None:
        return "n/a"
    try:
        return f"{float(v) * 100:.{nd}f}%"
    except (TypeError, ValueError):
        return "n/a"


def fmt_signed_pct(v: Any, nd: int = 1) -> str:
    if v is None:
        return "n/a"
    try:
        return f"{float(v) * 100:+.{nd}f}pp"
    except (TypeError, ValueError):
        return "n/a"


# --------------------------------------------------------------------------- #
# Marker fold (idempotent)
# --------------------------------------------------------------------------- #
def build_block(section_md: str) -> str:
    """Wrap the section body in the marker pair (no surrounding blank lines)."""
    return f"{START}\n\n{section_md.rstrip()}\n\n{END}"


def splice_markers(text: str, block: str, insert_fn) -> Tuple[str, bool]:
    """Replace existing marker block, or insert via insert_fn(text, block).

    Returns (new_text, changed).
    """
    i = text.find(START)
    j = text.find(END)
    if i != -1 and j != -1 and j > i:
        new = text[:i] + block + text[j + len(END):]
        return new, (new != text)
    # no markers yet -> insert
    new = insert_fn(text, block)
    return new, (new != text)


def _insert_at_eof(text: str, block: str) -> str:
    base = text.rstrip("\n")
    return f"{base}\n\n{block}\n"


def _insert_team(text: str, block: str) -> str:
    """Between SCHEME-AUTO END and ROSTER-AUTO START if both exist; elif after
    SCHEME-AUTO END; else EOF."""
    se = text.find(SCHEME_END)
    if se != -1:
        after_se = se + len(SCHEME_END)
        rs = text.find(ROSTER_START, after_se)
        if rs != -1:
            # insert between the two markers
            head = text[:after_se].rstrip("\n")
            tail = text[rs:]
            return f"{head}\n\n{block}\n\n{tail}"
        # after SCHEME-AUTO END only
        head = text[:after_se].rstrip("\n")
        tail = text[after_se:]
        sep = "\n\n" if tail.strip() else "\n"
        return f"{head}\n\n{block}{sep}{tail.lstrip(chr(10))}" if tail.strip() else f"{head}\n\n{block}\n"
    return _insert_at_eof(text, block)


# --------------------------------------------------------------------------- #
# Note index
# --------------------------------------------------------------------------- #
def build_player_note_index() -> Dict[str, str]:
    idx: Dict[str, str] = {}
    for path in glob.glob(os.path.join(PLAYERS_DIR, "*.md")):
        fname = os.path.basename(path)
        pid = fname.split("_", 1)[0]
        # first match wins; pids are unique prefixes in practice
        idx.setdefault(pid, path)
    return idx


def _titlecase_slug(slug: str) -> str:
    """Fallback clean name from a filename slug (e.g. 'nikola_joki' -> 'Nikola Joki')."""
    return " ".join(w.capitalize() for w in slug.split("_") if w)


def build_clean_name_index() -> Dict[str, str]:
    """pid -> canonical clean name from each vault note's H1 `# <Name>` title.

    This is the AUTHORITATIVE source for partner/duo display names — the raw
    artifact `name` fields are unicode-garbled for some players. Fallback to a
    title-cased filename slug if a note has no H1.
    """
    idx: Dict[str, str] = {}
    for path in glob.glob(os.path.join(PLAYERS_DIR, "*.md")):
        fname = os.path.basename(path)
        pid = fname.split("_", 1)[0]
        slug = fname[: -len(".md")].split("_", 1)[1] if "_" in fname[: -len(".md")] else ""
        h1: Optional[str] = None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    s = line.strip()
                    if s.startswith("# "):
                        h1 = s[2:].strip()
                        break
        except OSError:
            h1 = None
        idx.setdefault(pid, h1 or _titlecase_slug(slug))
    return idx


def clean_name(name_map: Dict[str, str], pid: Any, fallback: Optional[str] = None) -> str:
    """Resolve a partner/duo display name from the clean-name map by id.

    `pid` may be int or str (artifact ids are ints). Falls back to the artifact
    name string (or '?') for players with no vault note (e.g. minor traded
    players), which is the best available rendering.
    """
    if pid is not None:
        nm = name_map.get(str(pid))
        if nm:
            return nm
    return fallback or "?"


# --------------------------------------------------------------------------- #
# Player section
# --------------------------------------------------------------------------- #
def player_section(
    pid: str,
    avail: Optional[dict],
    avail_adj: Optional[float],
    pm: Optional[dict],
    rapm: Optional[dict],
    onoff: Optional[dict],
    lineup: Optional[dict],
    clutch: Optional[dict],
    closer_rank: Optional[int],
    dossier_read: Optional[str],
    name_map: Dict[str, str],
    consensus: Optional[dict] = None,
    stat_outcome: Optional[dict] = None,
    situational: Optional[dict] = None,
    render_b2b: bool = True,
) -> str:
    lines: List[str] = ["## Outcome Impact", ""]

    # --- Who decides games (2025-26) ---
    lines.append("**Who decides games (2025-26)** — team performance with him IN vs OUT:")
    if avail:
        n_in = avail.get("n_in")
        n_out = avail.get("n_out")
        role = avail.get("role", "n/a")
        wp = avail.get("winpct_swing")
        ms = avail.get("margin_swing")
        z = avail.get("margin_swing_z")
        ts = avail.get("total_swing")
        ps = avail.get("pace_swing")
        conf = avail.get("confidence", "n/a")
        if n_out in (0, None) or (isinstance(n_out, (int, float)) and n_out == 0):
            lines.append(
                f"- Iron-man / unmeasured this season — played effectively every game "
                f"(n_in={n_in}, n_out={n_out}); IN/OUT swing not estimable. Role: {role}."
            )
        else:
            # raw + opponent-adjusted (leak-safe, schedule-strength removed) margin swing
            adj_bit = ""
            if avail_adj is not None:
                adj_bit = f" (opp-adj: {fmt_signed(avail_adj, 1)})"
            lines.append(
                f"- Win% swing (IN−OUT): {fmt_signed_pct(wp)}  ·  "
                f"Margin swing: {fmt_signed(ms, 1)} pts{adj_bit} (z={fmt_num(z, 2)}, "
                f"n_in={n_in} / n_out={n_out})"
            )
            lines.append(
                f"- Total swing: {fmt_signed(ts, 1)} pts  ·  "
                f"Pace swing: {fmt_signed(ps, 1)}  ·  "
                f"Role: {role}  ·  confidence: {conf}"
            )
            if avail_adj is not None:
                lines.append(
                    "- _opp-adj margin swing removes schedule strength "
                    "(opponent SRS, leak-safe as-of) — cleaner read than raw; but "
                    "availability swing is per-player noisy (split-half ~0.39) — trust "
                    "multi-method consensus over a lone swing._"
                )
            if avail.get("confound_flag"):
                note = avail.get("confound_note") or "schedule/teammate confound"
                lines.append(f"- ⚠️ Confound: {note}")
    else:
        lines.append("- Not in the 2025-26 availability sample (no IN/OUT swing measured).")
    # multi-method consensus reliability flag (highest priority)
    for cl in _consensus_lines(consensus):
        lines.append(cl)
    lines.append("")

    # --- Adjusted impact ---
    lines.append("**Adjusted impact** (points per 100 possessions):")
    adj = pm.get("adj_impact") if pm else None
    rp = rapm.get("rapm_per100") if rapm else None
    if pm or rapm:
        bits = []
        if pm is not None:
            bits.append(f"2025-26 on/off-adjusted: {fmt_signed(adj, 2)}/100")
        if rapm is not None:
            bits.append(f"2024-25 ridge-RAPM: {fmt_signed(rp, 2)}/100")
        lines.append("- " + "  ·  ".join(bits))
        interp = _impact_interp(adj if pm else None, rp if rapm else None)
        if interp:
            lines.append(f"- {interp}")
    else:
        lines.append("- No adjusted-impact estimate available.")
    lines.append("")

    # --- On/off (2024-25 prior season) ---
    lines.append("**On/off (2024-25, prior season):**")
    if onoff:
        sw = onoff.get("onoff_swing")
        on_net = onoff.get("on_net")
        off_net = onoff.get("off_net")
        oc = onoff.get("confidence", "n/a")
        lines.append(
            f"- Last season net-rating swing: {fmt_signed(sw, 1)}/100 "
            f"(on {fmt_signed(on_net, 1)} vs off {fmt_signed(off_net, 1)}; confidence: {oc})"
        )
    else:
        lines.append("- No 2024-25 on/off split on file.")

    # --- Clutch (2025-26) ---
    clutch_line = _player_clutch_line(clutch, closer_rank)
    if clutch_line:
        lines.append("")
        lines.append("**Clutch (2025-26):**")
        lines.append(f"- {clutch_line}")

    # --- Lineup partners (2024-25 prior season, box net/100) ---
    partner_line = _player_partner_line(lineup, name_map)
    if partner_line:
        lines.append("")
        lines.append("**Lineup partners (2024-25, net/100):**")
        lines.append(f"- {partner_line}")

    # --- Win lever (per-stat outcome driver, 2025-26) ---
    win_lever = _win_lever_line(stat_outcome)
    if win_lever:
        lines.append("")
        lines.append(win_lever)

    # --- Home/road + B2B splits (2025-26) ---
    splits = _splits_line(situational, render_b2b)
    if splits:
        lines.append("")
        lines.append(splits)

    lines.append("")
    lines.append(DISCLAIMER)

    # --- Opus outcome read (narrative, appended last) ---
    if dossier_read:
        lines.append("")
        lines.append(f"**Outcome read:** {dossier_read.strip()}")

    return "\n".join(lines)


def _player_clutch_line(clutch: Optional[dict], closer_rank: Optional[int]) -> str:
    """Compact clutch line; 'small clutch sample' if low_n, else pts/impact/rank/n."""
    if not clutch:
        return ""
    if clutch.get("low_n"):
        n = clutch.get("n_clutch")
        return f"small clutch sample (n_clutch={n}) — not estimable"
    cp = clutch.get("clutch_pts")
    ci = clutch.get("clutch_impact")
    n = clutch.get("n_clutch")
    rank_bit = ""
    # closers_leaderboard is the full ranked list; only surface a notably high rank.
    if closer_rank is not None and closer_rank <= 30:
        rank_bit = f" (closer rank #{closer_rank})"
    return (
        f"clutch pts {fmt_num(cp, 1)}, impact {fmt_signed(ci, 2)}{rank_bit}; "
        f"n_clutch={n}"
    )


def _player_partner_line(lineup: Optional[dict], name_map: Dict[str, str]) -> str:
    """Top-2 best + top-1 worst lineup partners from lineup_combos_v2 by_player.

    Partner names are resolved via the clean-name map (keyed on `partner_id`)
    so unicode-garbled artifact strings never render.
    """
    if not isinstance(lineup, dict):
        return ""
    best = lineup.get("best_partners") or []
    worst = lineup.get("worst_partners") or []

    def fmt_p(p: dict) -> str:
        nm = clean_name(name_map, p.get("partner_id"), p.get("name"))
        return f"{nm} ({fmt_signed(p.get('net'), 1)}, {p.get('poss')} poss)"

    bits: List[str] = []
    if best:
        bits.append("best: " + ", ".join(fmt_p(p) for p in best[:2]))
    if worst:
        bits.append("worst: " + fmt_p(worst[0]))
    return "  ·  ".join(bits)


def _consensus_lines(consensus: Optional[dict]) -> List[str]:
    """ONE consensus line (+ optional lone-method ⚠️) for the who-decides block.

    `consensus` is a per-player dict {consensus_z, rank, why?} prebuilt by main()
    from who_decides_consensus.json (consensus_top + disagreements). Renders only
    when the player appears in at least one of those two lists.
    """
    if not isinstance(consensus, dict):
        return []
    out: List[str] = []
    cz = consensus.get("consensus_z")
    if cz is not None:
        rank = consensus.get("rank")
        rank_bit = f", rank #{rank}/25" if rank is not None else ""
        out.append(f"- _Multi-method consensus: z={fmt_num(cz, 2)}{rank_bit}._")
    why = consensus.get("why")
    if why:
        out.append(
            f"- ⚠️ lone-method signal — {why}; corroboration weak."
        )
    return out


def _win_lever_line(stat_outcome: Optional[dict]) -> str:
    """ONE per-stat win-driver line (2025-26). Only when dominant_driver is a real
    bucket (scoring/playmaking/defense) and the player qualified (n>=30)."""
    if not isinstance(stat_outcome, dict):
        return ""
    driver = stat_outcome.get("dominant_driver")
    if driver not in ("scoring", "playmaking", "defense"):
        return ""
    if (stat_outcome.get("n") or 0) < 30:
        return ""
    return (
        f"**Win lever (2025-26):** his team's wins track his {driver} most "
        f"(descriptive, collinear — scouting)."
    )


def _splits_line(situational: Optional[dict], render_b2b: bool) -> str:
    """ONE home/road (+ optional B2B-fade) split line (2025-26).

    Home/road renders when valid (hr_confidence != 'insufficient'). The rest/B2B
    clause is gated on BOTH that player's rest split being valid
    (rest_confidence != 'insufficient') AND the global stale-state guard
    (render_b2b) having passed in main()."""
    if not isinstance(situational, dict):
        return ""
    hr_ok = situational.get("hr_confidence") != "insufficient"
    if not hr_ok:
        return ""
    home_pm = situational.get("home_pm")
    road_pm = situational.get("road_pm")
    n_home = situational.get("n_home")
    n_road = situational.get("n_road")
    if home_pm is None or road_pm is None:
        return ""
    line = (
        f"**Splits:** home/road +/- {fmt_signed(home_pm, 1)}/{fmt_signed(road_pm, 1)} "
        f"(n={n_home}/{n_road})"
    )
    rest_ok = situational.get("rest_confidence") != "insufficient"
    b2b_fade = situational.get("b2b_fade")
    n_b2b = situational.get("n_b2b")
    if render_b2b and rest_ok and b2b_fade is not None:
        line += f"; B2B fade {fmt_signed(b2b_fade, 1)} (n={n_b2b})"
    return line


def _impact_interp(adj: Optional[float], rp: Optional[float]) -> str:
    def tier(v: Optional[float]) -> Optional[str]:
        if v is None:
            return None
        if v >= 3.0:
            return "high-positive"
        if v >= 1.0:
            return "positive"
        if v > -1.0:
            return "roughly neutral"
        if v > -3.0:
            return "negative"
        return "high-negative"

    primary = adj if adj is not None else rp
    t = tier(primary)
    if t is None:
        return ""
    season = "2025-26 on/off-adj" if adj is not None else "2024-25 RAPM"
    return (
        f"Interpretation: {t} on-court value ({season}); on/off-adjusted removes "
        f"team strength but not specific teammates — order signal, not a causal effect."
    )


# --------------------------------------------------------------------------- #
# Team section
# --------------------------------------------------------------------------- #
def team_section(
    tri: str,
    strength: Optional[dict],
    league_str: Optional[dict],
    sched: Optional[dict],
    league_sched: Optional[dict],
    avail_players: List[Tuple[str, dict]],
    onoff_team: List[dict],
    lineup_team: Optional[Any],
    clutch_team: Optional[dict],
    game_control: Optional[dict],
    injury_ctx: Optional[dict],
    dossier_read: Optional[str],
    name_map: Dict[str, str],
) -> str:
    lines: List[str] = ["## Outcome Impact", ""]

    # --- Team strength ---
    lines.append("**Team strength (2025-26):**")
    if strength:
        srs = strength.get("srs_rating")
        rank = strength.get("srs_rank")
        wins = strength.get("wins")
        losses = strength.get("losses")
        margin = strength.get("margin_pg")
        avg_total = strength.get("avg_game_total")
        tot_vs_lg = strength.get("game_total_vs_league")
        hm = strength.get("home_margin_pg")
        rm = strength.get("road_margin_pg")
        lean = "n/a"
        if tot_vs_lg is not None:
            lean = "OVER lean" if tot_vs_lg > 0 else ("UNDER lean" if tot_vs_lg < 0 else "neutral")
        lines.append(
            f"- SRS {fmt_signed(srs, 2)} (rank {rank}/30)  ·  "
            f"Record {wins}-{losses}  ·  Margin/g {fmt_signed(margin, 1)}"
        )
        lines.append(
            f"- Avg game total {fmt_num(avg_total, 1)} "
            f"({fmt_signed(tot_vs_lg, 1)} vs league → {lean})  ·  "
            f"Home margin {fmt_signed(hm, 1)} / Road margin {fmt_signed(rm, 1)}"
        )
    else:
        lines.append("- No 2025-26 team-strength record on file.")
    lines.append("")

    # --- Schedule spots ---
    lines.append("**Schedule spots (2025-26 B2B vs rested):**")
    if sched:
        b2b_wp = sched.get("b2b_winpct")
        b2b_m = sched.get("b2b_margin")
        rest_m = sched.get("rested_margin")
        delta = sched.get("b2b_margin_delta")
        n_b2b = sched.get("n_b2b")
        note = sched.get("notes", "")
        fade = ""
        if note == "fades_b2b":
            fade = "fades on B2B"
        elif note:
            fade = note.replace("_", " ")
        lines.append(
            f"- B2B: win% {fmt_pct(b2b_wp)}, margin {fmt_signed(b2b_m, 1)}  vs  "
            f"rested margin {fmt_signed(rest_m, 1)}"
        )
        lines.append(
            f"- B2B margin delta: {fmt_signed(delta, 1)} pts over n={n_b2b} B2Bs"
            + (f"  ·  {fade}" if fade else "")
        )
    else:
        lines.append("- No B2B/rested split on file.")
    lines.append("")

    # --- Clutch (2025-26) ---
    lines.append("**Clutch (2025-26):**")
    cl = _team_clutch_line(clutch_team)
    lines.append(f"- {cl}" if cl else "- No clutch record on file.")
    lines.append("")

    # --- Game control (2025-26) ---
    lines.append("**Game control (2025-26):**")
    for gc_ln in _game_control_lines(game_control):
        lines.append(f"- {gc_ln}")

    # --- Injury fragility (2025-26, opp-adjusted) — ONE compact line ---
    frag_ln = _team_fragility_line(injury_ctx)
    if frag_ln:
        lines.append(f"- {frag_ln}")
    lines.append("")

    # --- Roster outcome leaders ---
    lines.append("**Roster outcome leaders:**")
    leaders = _roster_leaders(avail_players)
    if leaders:
        lines.append("- Top 3 who decide games (2025-26, by margin swing, high-confidence):")
        for nm, ms, z, n_out in leaders:
            lines.append(f"    - {nm}: {fmt_signed(ms, 1)} pts (z={fmt_num(z, 2)}, n_out={n_out})")
    else:
        lines.append("- Top who-decides-games: none with a high-confidence IN/OUT split.")
    best, worst = _onoff_best_worst(onoff_team)
    if best:
        lines.append(
            f"- Best 2024-25 on/off: {best['name']} ({fmt_signed(best['onoff_swing'], 1)}/100)"
        )
    if worst:
        lines.append(
            f"- Worst 2024-25 on/off: {worst['name']} ({fmt_signed(worst['onoff_swing'], 1)}/100)"
        )
    if not best and not worst:
        lines.append("- No high-confidence 2024-25 on/off leaders on file.")

    # --- On-court duos (2024-25 prior season, box net/100) ---
    duo_lines = _team_duo_lines(lineup_team, name_map)
    if duo_lines:
        lines.append("")
        lines.append("**On-court duos (2024-25, net/100):**")
        for ln in duo_lines:
            lines.append(f"- {ln}")

    lines.append("")
    lines.append(DISCLAIMER)

    # --- Opus outcome read (narrative, appended last) ---
    if dossier_read:
        lines.append("")
        lines.append(f"**Outcome read:** {dossier_read.strip()}")

    return "\n".join(lines)


def _team_clutch_line(clutch: Optional[dict]) -> str:
    """Clutch record + winpct delta vs overall + clutch net + close/choke read."""
    if not clutch:
        return ""
    w = clutch.get("clutch_w")
    l = clutch.get("clutch_l")
    delta = clutch.get("clutch_winpct_delta")
    net = clutch.get("clutch_net")
    n = clutch.get("n_clutch_games")
    # close/choke read: combine clutch_net sign with winpct delta vs overall.
    read = "neutral in the clutch"
    try:
        d = float(delta) if delta is not None else 0.0
        nv = float(net) if net is not None else 0.0
        if nv >= 1.0 and d >= 0.05:
            read = "clutch-positive (over-performs close games)"
        elif nv <= -1.0 and d <= -0.05:
            read = "choke-leaning (under-performs close games)"
        elif d <= -0.08:
            read = "under-performs vs overall in close games"
        elif d >= 0.08:
            read = "over-performs vs overall in close games"
    except (TypeError, ValueError):
        pass
    return (
        f"clutch record {w}-{l} (win% delta vs overall {fmt_signed_pct(delta)}), "
        f"clutch net {fmt_signed(net, 1)}/100 over n={n} games — {read}"
    )


def _game_control_lines(gc: Optional[dict]) -> List[str]:
    if not gc:
        return ["No game-control profile on file."]
    bw = gc.get("blowout_win_pct")
    bl = gc.get("blowout_loss_pct")
    aam = gc.get("avg_abs_margin")
    q4 = gc.get("q4_net")
    lah = gc.get("lead_at_half_winpct")
    cb = gc.get("comeback_rate")
    cgr = gc.get("close_game_rate")
    return [
        f"Blowouts: win {fmt_num(bw, 1)}% / loss {fmt_num(bl, 1)}%  ·  "
        f"close-game rate {fmt_num(cgr, 1)}%  ·  variance (avg abs margin) {fmt_num(aam, 1)}",
        f"Q4 net {fmt_signed(q4, 1)}/100  ·  lead-at-half win% {fmt_num(lah, 1)}%  ·  "
        f"comeback rate {fmt_num(cb, 1)}%",
    ]


def _team_duo_lines(lineup_team: Optional[Any], name_map: Dict[str, str]) -> List[str]:
    """Top-2 best & bottom-2 worst on-court duos by net rating (by_team entry).

    Duo member names are resolved via the clean-name map (keyed on `players`
    ids), falling back to the positionally-matched artifact `names` string only
    for ids with no vault note.
    """
    if not isinstance(lineup_team, dict):
        return []
    best = lineup_team.get("best_pairs") or []
    worst = lineup_team.get("worst_pairs") or []

    def fmt_pair(p: dict) -> str:
        ids = p.get("players") or []
        raw = p.get("names") or []
        parts: List[str] = []
        for i, pid in enumerate(ids):
            fb = raw[i] if i < len(raw) else None
            parts.append(clean_name(name_map, pid, fb))
        if not parts and raw:
            parts = [str(x) for x in raw]
        nm = " + ".join(parts) if parts else "?"
        return f"{nm} ({fmt_signed(p.get('net'), 1)}, {p.get('poss')} poss)"

    out: List[str] = []
    if best:
        out.append("Best: " + "; ".join(fmt_pair(p) for p in best[:2]))
    if worst:
        # worst_pairs are ordered most-negative-first per artifact; take first 2.
        out.append("Worst: " + "; ".join(fmt_pair(p) for p in worst[:2]))
    return out


def _team_fragility_line(injury_ctx: Optional[dict]) -> str:
    """ONE compact opp-adjusted injury-fragility line (2025-26).

    Uses the team's highest-confidence indispensable player: the first
    `most_indispensable` entry with high/medium confidence (falls back to the
    precomputed `most_indispensable_high_conf`, then list head). The drop is that
    player's opponent-adjusted IN-vs-OUT margin swing (`margin_swing_adj`).
    """
    if not isinstance(injury_ctx, dict):
        return ""
    indis = injury_ctx.get("most_indispensable") or []
    pick = next(
        (p for p in indis if (p.get("confidence") in ("high", "medium"))),
        None,
    )
    if pick is None:
        pick = injury_ctx.get("most_indispensable_high_conf")
    if pick is None and indis:
        pick = indis[0]
    if not isinstance(pick, dict):
        return ""
    nm = pick.get("name", "?")
    drop = pick.get("margin_swing_adj")
    n_out = pick.get("n_out")
    if drop is None:
        return ""
    return (
        f"**Injury fragility:** drops ~{fmt_num(drop, 1)} pts without {nm} "
        f"(opp-adj, n_out={n_out})"
    )


def _roster_leaders(avail_players: List[Tuple[str, dict]]) -> List[Tuple[str, float, float, int]]:
    """Top 3 high-confidence players by margin_swing (most positive = decides games)."""
    cand = [
        p
        for _, p in avail_players
        if p.get("confidence") == "high" and p.get("margin_swing") is not None
    ]
    cand.sort(key=lambda p: p.get("margin_swing", 0.0), reverse=True)
    out = []
    for p in cand[:3]:
        out.append(
            (p.get("name", "?"), p.get("margin_swing"), p.get("margin_swing_z"), p.get("n_out"))
        )
    return out


def _onoff_best_worst(team_rows: List[dict]) -> Tuple[Optional[dict], Optional[dict]]:
    hi = [r for r in team_rows if r.get("confidence") == "high" and r.get("onoff_swing") is not None]
    if not hi:
        return None, None
    best = max(hi, key=lambda r: r["onoff_swing"])
    worst = min(hi, key=lambda r: r["onoff_swing"])
    return best, worst


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report, do not write")
    args = ap.parse_args()

    strength_doc = load_json("team_strength.json") or {}
    sched_doc = load_json("team_schedule_spots.json") or {}
    avail_doc = load_json("player_availability.json") or {}
    avail_v2_doc = load_json("player_availability_v2.json") or {}
    pm_doc = load_json("player_plusminus.json") or {}
    onoff_doc = load_json("player_onoff.json") or {}
    lineup_doc = load_json("lineup_combos_v2.json") or {}
    clutch_doc = load_json("clutch_outcome.json") or {}
    gc_doc = load_json("game_control.json") or {}
    injury_doc = load_json("team_injury_context.json") or {}
    consensus_doc = load_json("who_decides_consensus.json") or {}
    stat_outcome_doc = load_json("player_stat_outcome.json") or {}
    situational_doc = load_json("player_situational_outcome.json") or {}

    team_strength = strength_doc.get("teams", {})
    league_str = strength_doc.get("league", {})
    team_sched = sched_doc.get("teams", {})
    league_sched = sched_doc.get("league", {})
    avail_players = avail_doc.get("players", {})
    pm_players = pm_doc.get("players", {})
    rapm_players = pm_doc.get("rapm_2024_25", {}).get("players", {})
    onoff_players = onoff_doc.get("players", {})
    onoff_by_team = onoff_doc.get("by_team", {})
    # BUGFIX: lineup_combos_v2 keys players under `by_player` (not `players`).
    lineup_players = lineup_doc.get("by_player", {})
    lineup_by_team = lineup_doc.get("by_team", {})
    clutch_players = clutch_doc.get("players", {})
    clutch_teams = clutch_doc.get("teams", {})
    gc_teams = gc_doc.get("teams", {})
    injury_teams = injury_doc.get("teams", {})
    # v2 opponent-adjusted IN/OUT margin swing, keyed by pid -> margin_swing_adj
    avail_v2_players = avail_v2_doc.get("players", {})

    # closers leaderboard -> {pid(str): rank(int)}
    closer_rank: Dict[str, int] = {}
    for entry in clutch_doc.get("closers_leaderboard", []) or []:
        rpid = str(entry.get("player_id"))
        if entry.get("rank") is not None:
            closer_rank[rpid] = entry["rank"]

    # ----- consensus per-player map: pid(str) -> {consensus_z, rank?, why?} -----
    consensus_map: Dict[str, dict] = {}
    for i, entry in enumerate(consensus_doc.get("consensus_top", []) or []):
        cpid = str(entry.get("pid"))
        consensus_map[cpid] = {"consensus_z": entry.get("consensus_z"), "rank": i + 1}
    for entry in consensus_doc.get("disagreements", []) or []:
        cpid = str(entry.get("pid"))
        rec = consensus_map.setdefault(cpid, {})
        # lone-method players carry a consensus_z too (often weak); keep it if present
        if "consensus_z" not in rec and entry.get("consensus_z") is not None:
            rec["consensus_z"] = entry.get("consensus_z")
        rec["why"] = entry.get("why")
    n_consensus_flag = len(consensus_map)
    n_lone_method = sum(1 for r in consensus_map.values() if r.get("why"))

    stat_outcome_players = stat_outcome_doc.get("players", {})
    situational_players = situational_doc.get("players", {})

    # STALE-STATE GUARD on the situational rest/B2B state: the corrected artifact
    # has ~200 players with a usable B2B bucket; a stale empty-rest state has ~0.
    # If fewer than 150 valid, SKIP the B2B clause everywhere (home/road still
    # render) and report it — never bake a stale empty state into notes.
    n_valid_b2b = sum(
        1 for p in situational_players.values() if (p.get("n_b2b") or 0) >= 10
    )
    render_b2b = n_valid_b2b >= 150

    note_idx = build_player_note_index()
    # clean-name map (H1 titles) — authoritative for partner/duo display names
    name_map = build_clean_name_index()

    # ----- union of all player ids across artifacts -----
    union = (
        set(avail_players)
        | set(pm_players)
        | set(rapm_players)
        | set(onoff_players)
        | set(lineup_players)
        | set(clutch_players)
        | set(consensus_map)
        | set(stat_outcome_players)
        | set(situational_players)
    )

    # coverage counters (players actually folded into a note)
    cov_clutch = 0
    cov_partners = 0
    cov_dossier = 0
    cov_opp_adj = 0
    cov_consensus = 0
    cov_lone_method = 0
    cov_win_lever = 0
    cov_splits = 0
    cov_b2b = 0
    unresolved_artifact_pids: List[str] = []

    n_written = 0
    n_unchanged = 0
    n_no_note = 0
    no_note_pids: List[str] = []

    for pid in sorted(union):
        path = note_idx.get(pid)
        if not path:
            n_no_note += 1
            no_note_pids.append(pid)
            continue
        clutch_p = clutch_players.get(pid)
        lineup_p = lineup_players.get(pid)
        avail_p = avail_players.get(pid)
        # opponent-adjusted margin swing (v2, leak-safe) — only shown when v1 has a swing
        avail_v2_p = avail_v2_players.get(pid)
        avail_adj = avail_v2_p.get("margin_swing_adj") if avail_v2_p else None
        dossier = load_dossier(os.path.join("dossiers", f"player_{pid}.json"))
        dossier_read = dossier.get("outcome_read") if dossier else None
        consensus_p = consensus_map.get(pid)
        stat_p = stat_outcome_players.get(pid)
        situational_p = situational_players.get(pid)
        section = player_section(
            pid,
            avail_p,
            avail_adj,
            pm_players.get(pid),
            rapm_players.get(pid),
            onoff_players.get(pid),
            lineup_p,
            clutch_p,
            closer_rank.get(pid),
            dossier_read,
            name_map,
            consensus_p,
            stat_p,
            situational_p,
            render_b2b,
        )
        # coverage (count what actually folds, ignoring low_n which still renders)
        if clutch_p:
            cov_clutch += 1
        if lineup_p and (lineup_p.get("best_partners") or lineup_p.get("worst_partners")):
            cov_partners += 1
        if dossier_read:
            cov_dossier += 1
        # opp-adj only renders when v1 had an estimable IN/OUT swing (n_out>0)
        if avail_adj is not None and avail_p and avail_p.get("n_out"):
            cov_opp_adj += 1
        # new-signal coverage (what actually renders into a note)
        if _consensus_lines(consensus_p):
            cov_consensus += 1
            if consensus_p and consensus_p.get("why"):
                cov_lone_method += 1
        if _win_lever_line(stat_p):
            cov_win_lever += 1
        splits_ln = _splits_line(situational_p, render_b2b)
        if splits_ln:
            cov_splits += 1
            if "B2B fade" in splits_ln:
                cov_b2b += 1
        block = build_block(section)
        text = read_text(path)
        new, changed = splice_markers(text, block, _insert_at_eof)
        if changed and not args.dry_run:
            write_text(path, new)
        if changed:
            n_written += 1
        else:
            n_unchanged += 1

    # ----- teams -----
    n_team_written = 0
    n_team_unchanged = 0
    n_team_missing = 0
    team_full_blocks = 0  # teams with all 4 new blocks (clutch+gc+duos+dossier)
    cov_fragility = 0
    missing_team_tris: List[str] = []
    all_team_tris = (
        set(team_strength) | set(team_sched) | set(clutch_teams)
        | set(gc_teams) | set(lineup_by_team) | set(injury_teams)
    )
    for tri in sorted(all_team_tris):
        team_note = os.path.join(TEAMS_DIR, f"{tri}.md")
        if not os.path.exists(team_note):
            n_team_missing += 1
            missing_team_tris.append(tri)
            continue
        roster_avail = [
            (pid, p) for pid, p in avail_players.items() if p.get("team") == tri
        ]
        clutch_t = clutch_teams.get(tri)
        gc_t = gc_teams.get(tri)
        lineup_t = lineup_by_team.get(tri)
        injury_t = injury_teams.get(tri)
        dossier = load_dossier(os.path.join("dossiers", f"{tri}.json"))
        dossier_read = dossier.get("outcome_read") if dossier else None
        section = team_section(
            tri,
            team_strength.get(tri),
            league_str,
            team_sched.get(tri),
            league_sched,
            roster_avail,
            onoff_by_team.get(tri, []),
            lineup_t,
            clutch_t,
            gc_t,
            injury_t,
            dossier_read,
            name_map,
        )
        if clutch_t and gc_t and lineup_t and dossier_read:
            team_full_blocks += 1
        if _team_fragility_line(injury_t):
            cov_fragility += 1
        block = build_block(section)
        text = read_text(team_note)
        new, changed = splice_markers(text, block, _insert_team)
        if changed and not args.dry_run:
            write_text(team_note, new)
        if changed:
            n_team_written += 1
        else:
            n_team_unchanged += 1

    # ----- report -----
    mode = "DRY-RUN (no writes)" if args.dry_run else "WROTE"
    print(f"=== fold_outcome_impact :: {mode} ===")
    print(f"union player ids: {len(union)}")
    print(f"  player notes changed:   {n_written}")
    print(f"  player notes unchanged: {n_unchanged}")
    print(f"  player ids with NO note: {n_no_note}")
    print("  --- player new-block coverage (folded into a note) ---")
    print(f"    clutch folded:   {cov_clutch}")
    print(f"    partners folded: {cov_partners}")
    print(f"    dossier folded:  {cov_dossier}")
    print(f"    opp-adj folded:  {cov_opp_adj}")
    print("  --- NEW signals (this wave) ---")
    print(f"    consensus flag folded:   {cov_consensus} (lone-method ⚠️: {cov_lone_method})")
    print(f"    win-lever folded:        {cov_win_lever}")
    print(f"    splits folded:           {cov_splits} (of which w/ B2B: {cov_b2b})")
    print(
        f"    situational stale-guard: n_valid_b2b={n_valid_b2b} "
        f"(threshold 150) -> render_b2b={render_b2b}"
    )
    if not render_b2b:
        print("    !! B2B clause SKIPPED — situational artifact looks empty/stale.")
    print(f"team notes changed:   {n_team_written}")
    print(f"team notes unchanged: {n_team_unchanged}")
    print(f"team notes missing:   {n_team_missing}")
    print(f"team notes with ALL 4 new blocks (clutch+gc+duos+dossier): {team_full_blocks}")
    print(f"team notes with injury-fragility line: {cov_fragility}")
    if missing_team_tris:
        print(f"team tricodes with NO vault note: {', '.join(missing_team_tris)}")
    if no_note_pids:
        # resolve names for reporting
        def nm(p):
            for src in (
                avail_players, pm_players, onoff_players, rapm_players,
                clutch_players, lineup_players,
            ):
                if p in src:
                    v = src[p]
                    return v.get("name") or v.get("player_name") or "?"
            return "?"
        print("player ids with NO vault note:")
        for p in no_note_pids:
            print(f"  {p}  {nm(p)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
