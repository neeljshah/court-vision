"""
Synthesize rich offensive + defensive playstyle narratives from the stat tables
that already live in vault/Intelligence/Teams/*.md and vault/Intelligence/Players/*.md.

For each team and player note, parses the bullet/table values present in the file,
then writes two prose paragraphs (Offense, Defense) into an idempotent block:

    <!-- PLAYSTYLE-NARRATIVE START -->
    ### Offensive Playstyle
    ...
    ### Defensive Playstyle
    ...
    <!-- PLAYSTYLE-NARRATIVE END -->

Re-runs replace the block in place. Deterministic, no LLM, no external data.

Player narratives draw on: archetype, usage, scoring shot-distribution, drives,
self-creation, catch-and-shoot, playmaking (passes/ast/A:TO), rebounding rates,
defense (FG%/3PT% allowed, blocks, FTA generation), best/worst scheme TS,
CV behavioral (defender distance, paint time, off-ball distance, jump freq),
and the ranked strengths/weaknesses percentile table.

Team narratives draw on: scheme atlas tags, scheme axis z-scores, paint defense
(opp paint%/3pt%/mid%, rim FG%), perimeter pressure, halfcourt/transition mix,
play-type PPP, ball movement, rebounding identity, turnover forcing, FT/foul env.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TEAMS_DIR = ROOT / "vault" / "Intelligence" / "Teams"
PLAYERS_DIR = ROOT / "vault" / "Intelligence" / "Players"

NARR_START = "<!-- PLAYSTYLE-NARRATIVE START -->"
NARR_END = "<!-- PLAYSTYLE-NARRATIVE END -->"


# --------------------------------------------------------------------- parsing helpers

NUM_RE = r"[-+]?\d*\.?\d+%?"


def _grab(text: str, label_pattern: str, value_pattern: str = NUM_RE):
    """Return the first match of value_pattern after a bullet/cell labelled label_pattern.
    Handles both '- **Label:** val', '| Label | val |', '**Label:** val' and 'Label: val'.
    Returns float when numeric, else the raw string. None if not found."""
    # Allow any prefix text (e.g. "Shot distribution — ") inside the bold span before the
    # target label, so "**Shot distribution — Pts paint share:**" matches `Pts paint share`.
    patterns = [
        rf"[-*]\s+\*\*(?:[^*\n]*?\s)?{label_pattern}\s*:?\s*\*\*\s*({value_pattern})",
        rf"\*\*(?:[^*\n]*?\s)?{label_pattern}\s*:?\s*\*\*\s*({value_pattern})",
        rf"\|\s*{label_pattern}\s*\|\s*({value_pattern})\s*\|",
        rf"(?:^|\n){label_pattern}\s*:\s*({value_pattern})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            v = m.group(1).strip()
            cleaned = v.rstrip("%").replace(",", "")
            try:
                f = float(cleaned)
                if v.endswith("%"):
                    return f / 100.0
                return f
            except (TypeError, ValueError):
                return v
    return None


def _grab_str(text: str, label_pattern: str):
    patterns = [
        rf"[-*]\s+\*\*(?:[^*\n]*?\s)?{label_pattern}\s*:?\s*\*\*\s*([^\n|]+?)\s*(?:\||\n|$)",
        rf"\*\*(?:[^*\n]*?\s)?{label_pattern}\s*:?\s*\*\*\s*([^\n|]+?)\s*(?:\||\n|$)",
        rf"\|\s*{label_pattern}\s*\|\s*([^\n|]+?)\s*\|",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _pct(v):
    """Coerce a 0–1 or 0–100 numeric to '%' string. None passes through."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if 0 <= f <= 1.0:
        f *= 100
    return f"{f:.1f}%"


def _f(v, nd=1):
    if v is None:
        return None
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------- player parser

def parse_player(text: str) -> dict:
    d = {}
    # header
    m = re.search(r"^#\s+(.+?)\s*$", text, re.M)
    d["name"] = m.group(1).strip() if m else "Player"
    m = re.search(r"\*\*Archetype:\*\*\s*([^·\n]+)", text)
    d["archetype"] = (m.group(1).strip() if m else "Role Player")
    m = re.search(r"\*\(secondary:\s*([^\)]+)\)\*", text)
    d["secondary"] = m.group(1).strip() if m else None
    m = re.search(r"Tags:\s*(.+)$", text, re.M)
    d["tags"] = re.findall(r"`([^`]+)`", m.group(1)) if m else []

    # role
    d["position"] = _grab_str(text, r"Position")
    d["usage_rate"] = _grab(text, r"Usage rate")
    d["usage_tier"] = _grab_str(text, r"Usage tier")
    d["minutes"] = _grab(text, r"Minutes per game")
    d["ast_pct"] = _grab(text, r"AST %")
    d["pie"] = _grab(text, r"Pie mean")
    d["on_off"] = _grab(text, r"On off net diff")
    d["creator_role"] = _grab_str(text, r"Creator role")
    d["usage_rank"] = _grab(text, r"Usage % rank")
    d["ast_rank"] = _grab(text, r"AST % rank")
    d["impact_rank"] = _grab(text, r"Impact % rank")

    # scheme freq
    d["pnr_handler"] = _grab(text, r"Pick and roll — Handler freq")
    d["pnr_roll"] = _grab(text, r"Pick and roll — Roll man freq")
    d["post_freq"] = _grab(text, r"Post up — Freq %")
    d["post_ppp"] = _grab(text, r"Post up — PPP")
    d["iso_freq"] = _grab(text, r"Isolation — Freq %")
    d["iso_ppp"] = _grab(text, r"Isolation — PPP")
    d["spot_freq"] = _grab(text, r"Spot up — Freq %")
    d["spot_ppp"] = _grab(text, r"Spot up — PPP")
    d["transition_freq"] = _grab(text, r"Transition — Freq %")
    d["off_screen_freq"] = _grab(text, r"Off screen — Freq %")
    d["handoff_freq"] = _grab(text, r"Handoff — Freq %")

    # scoring
    d["paint_share"] = _grab(text, r"Pts paint share")
    d["three_share"] = _grab(text, r"Pts 3pt share")
    d["mid_share"] = _grab(text, r"Pts midrange share")
    d["ft_share"] = _grab(text, r"Pts FT share")
    d["unassist_2"] = _grab(text, r"Unassisted share 2PM")
    d["unassist_3"] = _grab(text, r"Unassisted share 3PM")
    d["drives"] = _grab(text, r"Drives per game")
    d["catch_efg"] = _grab(text, r"Catch shoot eFG")
    d["self_create_rank"] = _grab(text, r"Self creation % rank")
    d["catch_rank"] = _grab(text, r"Catch shoot % rank")
    d["trans_pts_share"] = _grab(text, r"Transition pts share")

    # playmaking
    d["passes"] = _grab(text, r"Passes made")
    d["pot_ast"] = _grab(text, r"Potential AST")
    d["ast_pts"] = _grab(text, r"AST pts created")
    d["ato"] = _grab(text, r"AST to TOV")
    d["sec_ast"] = _grab(text, r"Secondary AST")

    # rebounding
    d["treb"] = _grab(text, r"Total reb rate(?! rank)")
    d["oreb"] = _grab(text, r"OREB rate(?! rank)")
    d["dreb"] = _grab(text, r"DREB rate(?! rank)")
    d["boxouts"] = _grab(text, r"Box outs per game")

    # defense
    d["fg_allow"] = _grab(text, r"FG % allowed")
    d["three_allow"] = _grab(text, r"3PT % allowed")
    d["blk_match"] = _grab(text, r"Blocks matchup")
    d["fta_pg"] = _grab(text, r"Fta per game")
    d["fta_36"] = _grab(text, r"Fta per 36")
    d["and1_pg"] = _grab(text, r"And-1 per game")

    # situational form / vs scheme
    d["best_scheme"] = _grab_str(text, r"Best scheme")
    d["worst_scheme"] = _grab_str(text, r"Worst scheme")
    d["scheme_ts_spread"] = _grab(text, r"Scheme TS spread")
    d["form_score"] = _grab(text, r"Form summary — Form score")
    d["form_pts"] = _grab(text, r"Monthly form — Pts per game")
    d["form_reb"] = _grab(text, r"Monthly form — Reb per game")
    d["form_ast"] = _grab(text, r"Monthly form — AST per game")
    d["form_stl"] = _grab(text, r"Monthly form — STL per game")
    d["form_blk"] = _grab(text, r"Monthly form — BLK per game")
    d["form_tov"] = _grab(text, r"Monthly form — TOV per game")
    d["q4_ratio"] = _grab(text, r"Q4 vs early ratio")
    d["clutch_pts"] = _grab(text, r"Clutch pts per game")
    d["gravity"] = _grab(text, r"Gravity score")
    d["gravity_rank"] = _grab(text, r"Gravity % rank")
    d["age"] = _grab(text, r"Age years")
    d["seasons"] = _grab(text, r"Seasons in league")
    d["high_min_rate"] = _grab(text, r"High minutes game rate")

    # CV behavioral
    d["cv_def_dist"] = _grab(text, r"Avg defender distance")
    d["cv_spacing"] = _grab(text, r"Avg spacing")
    d["cv_offball"] = _grab(text, r"Off-ball distance")
    d["cv_velocity"] = _grab(text, r"Avg velocity")
    d["cv_paint_time"] = _grab(text, r"Paint-time %")
    d["cv_near_basket"] = _grab(text, r"Near-basket %")
    d["cv_jump_freq"] = _grab(text, r"Jump frequency")
    d["cv_dist_basket"] = _grab(text, r"Avg distance to basket")

    # strengths/weaknesses table
    sw = []
    for m in re.finditer(r"\|\s*([^|]+?)\s*\|\s*(\d+)(?:th|st|nd|rd)?\s*\|\s*([^|]+?)\s*\|", text):
        metric = m.group(1).strip()
        if metric.lower() in ("metric", "---"):
            continue
        try:
            pct = int(m.group(2))
        except ValueError:
            continue
        sw.append((metric, pct, m.group(3).strip()))
    d["sw"] = sw
    return d


# --------------------------------------------------------------------- player prose

def _list_join(parts):
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _cap(s: str) -> str:
    """Capitalize first letter of a string without touching the rest."""
    if not s:
        return s
    return s[0].upper() + s[1:]


def _append_sentence(s: str, fragment: str) -> str:
    """Append `fragment` as its own sentence (capitalize, period)."""
    f = fragment.strip()
    if not f:
        return s
    if not f.endswith("."):
        f += "."
    return s + " " + _cap(f) if s else _cap(f)


def _strengths(d, prefer):
    """Return up to N strength labels from sw list whose metric matches prefer-substrings."""
    out = []
    for label, pct, _ in d["sw"]:
        if pct >= 70 and any(p in label.lower() for p in prefer):
            out.append(f"{label.lower()} ({pct}th pct)")
    return out


def _weaknesses(d, prefer):
    out = []
    for label, pct, _ in d["sw"]:
        if pct <= 30 and any(p in label.lower() for p in prefer):
            out.append(f"{label.lower()} ({pct}th pct)")
    return out


def player_offense(d) -> str:
    name = d["name"]
    first = name.split()[0]
    arch = d["archetype"].lower()
    sec = f" with a {d['secondary'].lower()} secondary lean" if d.get("secondary") else ""

    # volume
    usage_tier = (d.get("usage_tier") or "").lower()
    usage_rank = d.get("usage_rank")
    min_v = _f(d.get("minutes"))
    usage_v = _pct(d.get("usage_rate"))
    if usage_rank is not None and usage_rank >= 85:
        vol = f"He carries elite offensive load (usage {usage_v}, {int(usage_rank)}th pct)"
    elif usage_rank is not None and usage_rank >= 65:
        vol = f"He sees above-average touches (usage {usage_v}, {int(usage_rank)}th pct)"
    elif usage_rank is not None and usage_rank >= 35:
        vol = f"He runs a moderate share of the offense (usage {usage_v})"
    elif usage_rank is not None:
        vol = f"He is a low-usage finisher rather than initiator (usage {usage_v}, {int(usage_rank)}th pct)"
    else:
        vol = f"He plays {min_v or '?'} mpg with usage {usage_v or 'n/a'}"

    # shot diet
    diet_bits = []
    p3, pp, pm, pft = d.get("three_share"), d.get("paint_share"), d.get("mid_share"), d.get("ft_share")
    if p3 is not None and p3 >= 0.45:
        diet_bits.append(f"perimeter-heavy diet ({_pct(p3)} of points from three)")
    elif pp is not None and pp >= 0.45:
        diet_bits.append(f"rim-pressure diet ({_pct(pp)} of points in the paint)")
    elif pft is not None and pft >= 0.22:
        diet_bits.append(f"foul-drawing profile ({_pct(pft)} of points from the FT line)")
    elif p3 is not None and pp is not None:
        diet_bits.append(f"balanced shot profile (paint {_pct(pp)} / three {_pct(p3)} / mid {_pct(pm) if pm else '—'} / FT {_pct(pft) if pft else '—'})")

    # creation
    u3 = d.get("unassist_3")
    u2 = d.get("unassist_2")
    drives = d.get("drives")
    create = []
    if u3 is not None and u3 >= 0.5:
        create.append(f"creates the majority of his threes off the bounce ({_pct(u3)} unassisted)")
    elif u3 is not None and u3 <= 0.2:
        create.append(f"functions as a kick-out target on threes ({_pct(u3)} unassisted — {_pct(1-u3)} are catch-and-shoot)")
    if u2 is not None and u2 >= 0.6:
        create.append("generates most twos as a self-creator")
    elif u2 is not None and u2 <= 0.3:
        create.append("relies on teammates to set up paint scores")
    if drives is not None:
        if drives >= 12:
            create.append(f"a high-volume driver at {_f(drives)}/g")
        elif drives >= 7:
            create.append(f"drives the ball regularly ({_f(drives)}/g)")
        elif drives <= 2:
            create.append(f"rarely puts the ball on the floor ({_f(drives)} drives/g)")

    # catch & shoot
    cs_eFG = d.get("catch_efg")
    cs_rank = d.get("catch_rank")
    if cs_eFG is not None:
        if cs_eFG >= 0.58:
            create.append(f"elite catch-and-shoot finisher ({_pct(cs_eFG)} eFG)")
        elif cs_eFG <= 0.45 and cs_rank is not None and cs_rank <= 30:
            create.append(f"below-average catch-and-shoot ({_pct(cs_eFG)} eFG, {int(cs_rank)}th pct)")

    # playmaking
    pm_bits = []
    ato = d.get("ato"); ast_pts = d.get("ast_pts"); pot = d.get("pot_ast"); passes = d.get("passes")
    if ast_pts is not None and ast_pts >= 12:
        pm_bits.append(f"high-level playmaker (creates {_f(ast_pts)} pts/g via assists, {_f(pot,1) or '?'} potential ast)")
    elif ast_pts is not None and ast_pts >= 6:
        pm_bits.append(f"capable secondary creator ({_f(ast_pts)} ast-pts/g)")
    elif ast_pts is not None and ast_pts <= 2:
        pm_bits.append("not a creator for others")
    if ato is not None:
        if ato >= 2.4:
            pm_bits.append(f"protects the ball at an elite rate (A/TO {_f(ato,2)})")
        elif ato <= 1.0 and ast_pts is not None and ast_pts >= 4:
            pm_bits.append(f"turnover-prone for his role (A/TO {_f(ato,2)})")

    # scheme usage
    sch_bits = []
    if d.get("pnr_handler") is not None and d["pnr_handler"] >= 0.25:
        sch_bits.append(f"runs PnR as the handler on {_pct(d['pnr_handler'])} of his plays")
    elif d.get("pnr_roll") is not None and d["pnr_roll"] >= 0.20:
        sch_bits.append(f"finishes as the roll/pop man ({_pct(d['pnr_roll'])} of plays)")
    if d.get("post_freq") is not None and d["post_freq"] >= 0.10:
        ppp = d.get("post_ppp")
        sch_bits.append(f"posts up on {_pct(d['post_freq'])} of plays" + (f" at {_f(ppp,2)} PPP" if ppp else ""))
    if d.get("spot_freq") is not None and d["spot_freq"] >= 0.30:
        sch_bits.append(f"lives off spot-ups ({_pct(d['spot_freq'])} of plays)")

    # vs scheme
    vs = []
    if d.get("best_scheme") and d.get("worst_scheme") and d.get("scheme_ts_spread") and d["scheme_ts_spread"] >= 0.04:
        vs.append(f"thrives against {d['best_scheme']} and struggles versus {d['worst_scheme']} (TS spread {_pct(d['scheme_ts_spread'])})")

    # CV behavioral
    cv = []
    if d.get("cv_def_dist") is not None:
        try:
            cd = float(d["cv_def_dist"])
            if cd >= 70:
                cv.append("CV tracking shows he gets clean separation from defenders")
            elif cd <= 45:
                cv.append("CV shows he plays through tight on-ball pressure")
        except (TypeError, ValueError):
            pass
    if d.get("cv_paint_time") is not None and d["cv_paint_time"] >= 0.15:
        cv.append(f"high paint occupancy ({_pct(d['cv_paint_time'])})")

    # gravity
    grav_bits = []
    gr = d.get("gravity_rank")
    if gr is not None:
        if gr >= 75:
            grav_bits.append(f"strong off-ball gravity ({int(gr)}th pct)")
        elif gr <= 25:
            grav_bits.append(f"limited off-ball gravity ({int(gr)}th pct)")

    # on/off
    onoff = d.get("on_off")
    onoff_bit = ""
    if onoff is not None and abs(onoff) >= 4:
        onoff_bit = f" His team is {'+' if onoff>0 else ''}{_f(onoff,1)} net-rating with him on the floor."

    # strengths
    o_strengths = _strengths(d, [
        "usage", "self-creation", "scoring", "three-point", "catch", "playmaking", "passing",
        "ball security", "transition", "off-ball", "gravity", "post", "impact", "consist",
    ])
    o_weaknesses = _weaknesses(d, [
        "catch", "self-creation", "three-point", "post", "transition", "gravity", "playmaking",
    ])

    s = f"{name} profiles as a {arch}{sec}. " + _cap(vol)
    if min_v:
        s += f" over {min_v} mpg"
    s += "."
    if diet_bits:
        s = _append_sentence(s, "His scoring lives on a " + diet_bits[0])
    if create:
        s = _append_sentence(s, _list_join(create[:3]))
    if sch_bits:
        s = _append_sentence(s, "Scheme-wise, he " + _list_join(sch_bits[:3]))
    if pm_bits:
        s = _append_sentence(s, _list_join(pm_bits[:2]))
    if grav_bits:
        s = _append_sentence(s, _list_join(grav_bits))
    if vs:
        s = _append_sentence(s, _list_join(vs))
    if cv:
        s = _append_sentence(s, _list_join(cv))
    if o_strengths:
        s = _append_sentence(s, "Offensive strengths: " + ", ".join(o_strengths[:4]))
    if o_weaknesses:
        s = _append_sentence(s, "Offensive gaps: " + ", ".join(o_weaknesses[:3]))
    if onoff_bit:
        s += onoff_bit
    return s.strip()


def player_defense(d) -> str:
    name = d["name"]
    bits = []

    # FG% allowed
    fga = d.get("fg_allow"); ta = d.get("three_allow")
    if fga is not None:
        if fga <= 0.43:
            bits.append(f"holds matchups to {_pct(fga)} FG (stingy on-ball)")
        elif fga >= 0.49:
            bits.append(f"gives up {_pct(fga)} FG when targeted (gets attacked)")
        else:
            bits.append(f"average on-ball FG suppression ({_pct(fga)} allowed)")
    if ta is not None:
        if ta <= 0.33:
            bits.append(f"runs shooters off the line ({_pct(ta)} 3PT allowed)")
        elif ta >= 0.38:
            bits.append(f"slow closeouts ({_pct(ta)} 3PT allowed)")

    # rim protection from blocks/CV
    blk = d.get("blk_match")
    form_blk = d.get("form_blk")
    if form_blk is not None:
        if form_blk >= 1.3:
            bits.append(f"plus rim protector ({_f(form_blk,1)} BLK/g)")
        elif form_blk >= 0.6:
            bits.append(f"useful weakside swatter ({_f(form_blk,1)} BLK/g)")

    # steal/playmaking on defense
    form_stl = d.get("form_stl")
    if form_stl is not None:
        if form_stl >= 1.4:
            bits.append(f"active hands disruption ({_f(form_stl,1)} STL/g)")
        elif form_stl <= 0.5 and d.get("position") and "guard" in (d.get("position") or "").lower():
            bits.append(f"low event-creation defender ({_f(form_stl,1)} STL/g)")

    # rebound role (rough role tag for def boards)
    dreb = d.get("dreb")
    if dreb is not None:
        if dreb >= 0.20:
            bits.append(f"strong defensive-board finisher (DREB% {_pct(dreb)})")
        elif dreb <= 0.08:
            bits.append(f"limited defensive rebounder (DREB% {_pct(dreb)})")

    # box outs / paint role
    if d.get("boxouts") is not None and d["boxouts"] >= 1.5:
        bits.append(f"physical box-out finisher ({_f(d['boxouts'],1)}/g)")

    # CV behavioral on defense side
    if d.get("cv_paint_time") is not None and d["cv_paint_time"] >= 0.20:
        bits.append("CV shows heavy paint occupancy — drops/anchors near the rim")
    elif d.get("cv_paint_time") is not None and d["cv_paint_time"] <= 0.05 and d.get("position") and "guard" in (d.get("position") or "").lower():
        bits.append("CV shows perimeter-anchored coverage")
    if d.get("cv_velocity") is not None:
        try:
            vv = float(d["cv_velocity"])
            if vv >= 13.0:
                bits.append(f"high movement intensity ({_f(vv,1)} avg velocity)")
            elif vv <= 9.0:
                bits.append(f"low movement intensity ({_f(vv,1)} avg velocity)")
        except (TypeError, ValueError):
            pass

    # fouling profile (and-1 against, foul-prone proxy)
    if d.get("and1_pg") is not None:
        a1 = d["and1_pg"]
        if a1 >= 0.4:
            bits.append(f"prone to and-1s ({_f(a1,2)}/g)")

    # form/durability
    if d.get("high_min_rate") is not None and d["high_min_rate"] >= 0.75:
        bits.append(f"heavy-minute role ({_pct(d['high_min_rate'])} high-minute games — late-game fatigue risk)")

    # role / archetype context
    arch = (d.get("archetype") or "").lower()
    intro = f"{name} "
    if "two-way" in arch or "lockdown" in arch or "stopper" in arch:
        intro += "is a known stopper archetype — "
    elif "spacing" in arch or "shooter" in arch or "spec" in arch:
        intro += "is asked to chase shooters / stay attached on closeouts — "
    elif "big" in arch or "anchor" in arch or "rim" in arch or "post" in arch:
        intro += "anchors paint coverage — "
    elif "playmak" in arch or "primary" in arch or "lead" in arch:
        intro += "defends from a high-usage offensive role (preserve fouls/legs) — "
    else:
        intro += "fits a complementary defensive role — "

    if not bits:
        return intro + "no clear defensive separator in the current sample; treat as scheme-neutral."

    s = intro + _list_join(bits[:5]) + "."

    d_strengths = _strengths(d, ["defen", "block", "steal", "rebound"])
    d_weak = _weaknesses(d, ["defen", "block", "steal", "rebound"])
    if d_strengths:
        s = _append_sentence(s, "Defensive strengths: " + ", ".join(d_strengths[:3]))
    if d_weak:
        s = _append_sentence(s, "Defensive gaps: " + ", ".join(d_weak[:3]))
    return s


def player_narrative(d) -> str:
    o = player_offense(d)
    de = player_defense(d)
    return (
        "### Offensive Playstyle\n\n" + o + "\n\n"
        "### Defensive Playstyle\n\n" + de + "\n"
    )


# --------------------------------------------------------------------- team parser

def parse_team(text: str) -> dict:
    d = {}
    m = re.search(r"^#\s+([A-Z]{3})\b", text, re.M)
    d["abbr"] = m.group(1) if m else "TEAM"

    # scheme tags
    m = re.search(r"\*\*Primary coverage:\*\*\s*([^\n]+)", text)
    d["primary_cov"] = m.group(1).strip() if m else None
    m = re.search(r"\*\*All tags:\*\*\s*([^\n]+)", text)
    if m:
        raw = m.group(1)
        d["all_tags"] = [t.strip() for t in re.split(r"[|,]", raw) if t.strip()]
    else:
        d["all_tags"] = []
    m = re.search(r"\*\*Dominant tag:\*\*\s*([^\n]+)", text)
    d["dominant"] = m.group(1).strip() if m else d.get("primary_cov")
    m = re.search(r"\*\*Pace identity:\*\*\s*([A-Z]+)", text)
    d["pace_label"] = m.group(1).strip() if m else _grab_str(text, r"Pace label")
    m = re.search(r"\*\*Rebounding identity:\*\*\s*([a-zA-Z]+)", text)
    d["reb_identity"] = m.group(1).strip() if m else None
    m = re.search(r"\*\*Profile:\*\*\s*([^\n]+)", text)
    d["tempo_profile"] = m.group(1).strip() if m else None

    # axis scores
    for k, lbl in [("drop_switch", r"Drop vs Switch"), ("paint_prot", r"Paint Protection"),
                   ("perim_denial", r"Perimeter Denial"), ("pace_ctrl", r"Pace Control"),
                   ("iso_force", r"Iso Force"), ("closeout", r"Closeout Intensity")]:
        d[k] = _grab(text, lbl)

    # ratings
    d["offrtg"] = _grab(text, r"OffRtg(?! L10)")
    d["defrtg"] = _grab(text, r"DefRtg(?! L10| trend)")
    d["defrtg_l10"] = _grab(text, r"DefRtg L10")
    d["defrtg_trend"] = _grab(text, r"DefRtg trend")
    d["pace"] = _grab(text, r"Pace(?!\s*(?:label|identity))")
    d["efg"] = _grab(text, r"eFG%")
    d["ts"] = _grab(text, r"TS%")
    d["tov_ratio"] = _grab(text, r"TOV ratio")
    d["ast_pct"] = _grab(text, r"Ast%")
    d["oreb_pct"] = _grab(text, r"OReb%(?! season| L10| rank)")
    d["dreb_pct"] = _grab(text, r"DReb%(?! season| L10| rank)")
    d["pnr_ppp"] = _grab(text, r"PNR PPP")

    # opp shot mix
    d["opp_paint_z"] = _grab(text, r"Opp paint% z")
    d["opp_3_z"] = _grab(text, r"Opp 3pt% z")
    d["opp_mid_z"] = _grab(text, r"Opp mid% z")
    d["paint_dwell_z"] = _grab(text, r"Paint dwell% z")
    d["opp_3p_pct"] = _grab(text, r"Opp 3P%")
    d["opp_3pa_g"] = _grab(text, r"3PA/g")
    d["opp_3pa_rate"] = _grab(text, r"3PA rate")

    # rim def
    d["rim_fg_allow"] = _grab(text, r"Rim FG% allowed")
    d["rim_freq"] = _grab(text, r"Rim freq faced")
    d["rim_vs_normal"] = _grab(text, r"Rim FG% vs normal")
    d["paint_fg_allow"] = _grab(text, r"Paint FG% allowed")

    # perimeter pressure z's
    d["contest_z"] = _grab(text, r"Contested shot rate z")
    d["def_dist_z"] = _grab(text, r"Avg defender distance z")
    d["pace_imposed_z"] = _grab(text, r"Pace imposed z")

    # tempo z
    d["tempo_z"] = _grab(text, r"Tempo z(?! score)")
    d["trans_share_z"] = _grab(text, r"Transition share z")
    d["spacing_z"] = _grab(text, r"Avg spacing z")

    # turnover / transition
    d["opp_tov"] = _grab(text, r"Opp TOV% \(season\)")
    d["own_tov"] = _grab(text, r"Own TOV ratio")
    d["deflect_g"] = _grab(text, r"Deflections/g")
    d["opp_trans_g"] = _grab(text, r"Opp transition possessions/g")

    # FT env
    d["pf_g"] = _grab(text, r"PF/g")
    d["fta_g"] = _grab(text, r"FTA drawn/g")
    d["opp_fta_g"] = _grab(text, r"Opp FTA allowed/g")
    d["net_fta"] = _grab(text, r"Net FTA differential")

    # ball movement / drives
    d["passes_g"] = _grab(text, r"Passes made/g")
    d["drives_g"] = _grab(text, r"Drives/g")
    d["drive_fg"] = _grab(text, r"Drive FG%")

    # play type freq + ppp
    # capture "| play | val |" pairs in the freq + PPP tables
    def _table_dict(section_header_re, label_col=1):
        # Stop at the next bold-header / heading / HTML comment so adjacent tables don't bleed.
        sec = re.search(section_header_re + r"(.*?)(?:\n\s*\*\*[^*\n]+:\*\*|\n##|\n###|\n<!--|\Z)",
                        text, re.S)
        if not sec:
            return {}
        out = {}
        for m in re.finditer(r"\|\s*([A-Za-z][^|]*?)\s*\|\s*([\d.]+)\s*\|", sec.group(1)):
            k = m.group(1).strip()
            if k in ("Play type", "Metric"):
                continue
            try:
                out[k.lower()] = float(m.group(2))
            except ValueError:
                pass
        return out
    d["pt_freq"] = _table_dict(r"\*\*Play type mix \(frequency\):\*\*")
    d["pt_ppp"] = _table_dict(r"\*\*PPP by play type:\*\*")

    return d


def _z_descriptor(z, high_word, low_word, neutral="balanced"):
    if z is None:
        return None
    try:
        zf = float(z)
    except (TypeError, ValueError):
        return None
    if zf >= 0.6:
        return f"{high_word} (z=+{zf:.2f})"
    if zf <= -0.6:
        return f"{low_word} (z={zf:.2f})"
    return None


def team_offense(d) -> str:
    abbr = d["abbr"]
    bits = []
    pace = d.get("pace_label") or ("fast" if (d.get("pace") or 0) >= 100 else "slow")
    if d.get("pace") is not None:
        bits.append(f"plays at a {pace.lower()} tempo (pace {_f(d['pace'])})")

    if d.get("tempo_profile"):
        bits.append(d["tempo_profile"].lower())

    # tempo & spacing z
    t = _z_descriptor(d.get("tempo_z"), "above-league tempo", "below-league tempo")
    sp = _z_descriptor(d.get("spacing_z"), "wide-spacing offense", "tight-spacing offense")
    trz = _z_descriptor(d.get("trans_share_z"), "transition-heavy", "halfcourt-grind")
    if t: bits.append(t)
    if sp: bits.append(sp)
    if trz: bits.append(trz)

    # efficiency
    if d.get("offrtg") is not None:
        bits.append(f"OffRtg {_f(d['offrtg'])} on {_pct(d['efg']) or '?'} eFG, {_pct(d['ts']) or '?'} TS")
    if d.get("tov_ratio") is not None:
        ttext = f"TOV ratio {_f(d['tov_ratio'])}"
        bits.append(ttext)
    if d.get("ast_pct") is not None:
        bits.append(f"assist rate {_pct(d['ast_pct'])}")

    # PnR
    if d.get("pnr_ppp") is not None:
        bits.append(f"PnR PPP {_f(d['pnr_ppp'],2)}")

    # play type lean
    pt = d.get("pt_freq") or {}
    pt_ppp = d.get("pt_ppp") or {}
    leans = []
    for k in ("spot-up", "pnr", "iso", "cut", "post", "handoff", "off screen", "pnr roll"):
        v = pt.get(k)
        if v is not None and v >= 0.18:
            leans.append(f"{k} {_pct(v)}")
    if leans:
        bits.append("play-type lean " + " · ".join(leans[:3]))

    # most efficient play type
    if pt_ppp:
        top = max([(v, k) for k, v in pt_ppp.items() if k != "halfcourt (overall)"], default=(None, None))
        if top[1] is not None and top[0] >= 1.05:
            bits.append(f"most efficient action: {top[1]} ({_f(top[0],2)} PPP)")
        # weakest action
        if len(pt_ppp) >= 3:
            bot = min([(v, k) for k, v in pt_ppp.items() if k != "halfcourt (overall)" and (pt.get(k) or 0) >= 0.05])
            if bot[1] is not None and bot[0] <= 0.95:
                bits.append(f"struggles in: {bot[1]} ({_f(bot[0],2)} PPP)")

    # ball movement
    if d.get("passes_g") is not None and d["passes_g"] >= 25:
        bits.append(f"ball-movement offense ({_f(d['passes_g'])} passes/g)")
    elif d.get("passes_g") is not None and d["passes_g"] <= 20:
        bits.append(f"low-pass offense ({_f(d['passes_g'])} passes/g)")
    if d.get("drives_g") is not None:
        if d["drives_g"] >= 4.5:
            bits.append(f"drive-heavy ({_f(d['drives_g'])} drives/g, {_pct(d['drive_fg']) or '?'} FG)")
        elif d["drives_g"] <= 2.5:
            bits.append(f"low-drive volume ({_f(d['drives_g'])} drives/g)")

    # rebounding
    if d.get("oreb_pct") is not None:
        if d["oreb_pct"] >= 0.30:
            bits.append(f"strong offensive-glass crash (OReb% {_pct(d['oreb_pct'])})")
        elif d["oreb_pct"] <= 0.23:
            bits.append(f"avoids offensive-glass crash (OReb% {_pct(d['oreb_pct'])})")

    # Break into 2-3 sentences for readability: pace+efficiency / play-type / movement+reb.
    out = []
    if bits:
        out.append(f"{abbr} " + _list_join(bits[:5]) + ".")
    if len(bits) > 5:
        out.append(_cap(_list_join(bits[5:10]) + "."))
    if len(bits) > 10:
        out.append(_cap(_list_join(bits[10:]) + "."))
    return " ".join(out)


def team_defense(d) -> str:
    abbr = d["abbr"]
    bits = []

    # scheme label
    if d.get("dominant") or d.get("primary_cov"):
        tag = (d.get("dominant") or d["primary_cov"]).lower()
        bits.append(f"runs primarily {tag}")
    other_tags = [t for t in (d.get("all_tags") or []) if t and t.lower() != (d.get("dominant") or "").lower()]
    if other_tags:
        bits.append("with secondary looks: " + ", ".join(other_tags[:4]).lower())

    # axis description
    axis_bits = []
    drop = d.get("drop_switch"); pp = d.get("paint_prot"); pd_ = d.get("perim_denial")
    pc = d.get("pace_ctrl"); iso = d.get("iso_force"); co = d.get("closeout")
    if drop is not None:
        axis_bits.append(("drop-coverage tilt" if drop > 0.1 else "switch-tilt") + f" (z={_f(drop,2)})" if abs(drop) > 0.1 else None)
    if pd_ is not None and abs(pd_) > 0.1:
        axis_bits.append(("aggressive perimeter denial" if pd_ > 0 else "soft perimeter coverage") + f" (z={_f(pd_,2)})")
    if pp is not None and abs(pp) > 0.1:
        axis_bits.append(("paint-first protection" if pp > 0 else "light paint pressure") + f" (z={_f(pp,2)})")
    if pc is not None and abs(pc) > 0.1:
        axis_bits.append(("dictates pace" if pc > 0 else "lets opponents push pace") + f" (z={_f(pc,2)})")
    if iso is not None and abs(iso) > 0.1:
        axis_bits.append(("forces opponents into iso" if iso > 0 else "avoids iso forcing") + f" (z={_f(iso,2)})")
    if co is not None and abs(co) > 0.15:
        axis_bits.append(("hot closeouts" if co > 0 else "slow closeouts") + f" (z={_f(co,2)})")
    axis_bits = [a for a in axis_bits if a]
    if axis_bits:
        bits.append(_list_join(axis_bits))

    # opp shot mix
    mix = []
    if d.get("opp_paint_z") is not None and abs(d["opp_paint_z"]) > 0.5:
        mix.append(("concedes paint" if d["opp_paint_z"] > 0 else "denies paint") + f" (z={_f(d['opp_paint_z'],2)})")
    if d.get("opp_3_z") is not None and abs(d["opp_3_z"]) > 0.5:
        mix.append(("gives up threes" if d["opp_3_z"] > 0 else "limits threes") + f" (z={_f(d['opp_3_z'],2)})")
    if d.get("opp_mid_z") is not None and abs(d["opp_mid_z"]) > 0.5:
        mix.append(("funnels to mid-range" if d["opp_mid_z"] > 0 else "denies mid-range") + f" (z={_f(d['opp_mid_z'],2)})")
    if mix:
        bits.append("shot-mix: " + _list_join(mix))

    # rim def
    if d.get("rim_fg_allow") is not None:
        rim = d["rim_fg_allow"]
        if rim <= 0.60:
            bits.append(f"strong rim defense ({_pct(rim)} rim FG allowed)")
        elif rim >= 0.66:
            bits.append(f"leaky rim defense ({_pct(rim)} rim FG allowed)")
    if d.get("rim_vs_normal") is not None:
        rvn = d["rim_vs_normal"]
        if rvn <= -0.02:
            bits.append(f"rim FG% below expected by {_f(abs(rvn)*100,1)}pp")
        elif rvn >= 0.02:
            bits.append(f"rim FG% above expected by {_f(rvn*100,1)}pp")

    # perimeter pressure
    perim = []
    if d.get("contest_z") is not None:
        if d["contest_z"] >= 0.6:
            perim.append(f"elite contest rate (z=+{_f(d['contest_z'],2)})")
        elif d["contest_z"] <= -0.6:
            perim.append(f"low contest rate (z={_f(d['contest_z'],2)})")
    if d.get("def_dist_z") is not None and abs(d["def_dist_z"]) > 0.6:
        perim.append(("loose closeouts" if d["def_dist_z"] > 0 else "tight closeouts") + f" (z={_f(d['def_dist_z'],2)})")
    if perim:
        bits.append(_list_join(perim))

    # defensive efficiency
    if d.get("defrtg") is not None:
        rg = f"DefRtg {_f(d['defrtg'])}"
        if d.get("defrtg_trend") is not None and abs(d["defrtg_trend"]) >= 1.5:
            rg += f" ({'improving' if d['defrtg_trend']<0 else 'sliding'}, L10 trend {_f(d['defrtg_trend'],1)})"
        bits.append(rg)

    # turnover forcing & transition allowed
    if d.get("opp_tov") is not None:
        if d["opp_tov"] >= 0.155:
            bits.append(f"forces turnovers at high rate (opp TOV% {_pct(d['opp_tov'])})")
        elif d["opp_tov"] <= 0.125:
            bits.append(f"low turnover-forcing (opp TOV% {_pct(d['opp_tov'])})")
    if d.get("deflect_g") is not None and d["deflect_g"] >= 1.5:
        bits.append(f"active hands ({_f(d['deflect_g'],1)} deflections/g)")
    if d.get("opp_trans_g") is not None and d["opp_trans_g"] >= 18:
        bits.append(f"vulnerable in transition ({_f(d['opp_trans_g'],1)} opp trans poss/g)")

    # defensive rebounding
    if d.get("dreb_pct") is not None:
        if d["dreb_pct"] >= 0.74:
            bits.append(f"locks the defensive glass (DReb% {_pct(d['dreb_pct'])})")
        elif d["dreb_pct"] <= 0.70:
            bits.append(f"leaks second chances (DReb% {_pct(d['dreb_pct'])})")

    # FT / fouls
    if d.get("pf_g") is not None and d["pf_g"] >= 23:
        bits.append(f"high foul team ({_f(d['pf_g'],1)} PF/g, sends opp to line {_f(d.get('opp_fta_g') or 0,1)}/g)")
    if d.get("net_fta") is not None and d["net_fta"] <= -3:
        bits.append(f"loses the FT battle (net FTA {_f(d['net_fta'],1)})")
    elif d.get("net_fta") is not None and d["net_fta"] >= 3:
        bits.append(f"wins the FT battle (net FTA +{_f(d['net_fta'],1)})")

    # opponent 3 efficiency
    if d.get("opp_3p_pct") is not None:
        bits.append(f"opp 3P% {_pct(d['opp_3p_pct'])} on {_f(d.get('opp_3pa_g') or 0)} 3PA/g")

    out = []
    if bits:
        out.append(f"{abbr} " + _list_join(bits[:4]) + ".")
    if len(bits) > 4:
        out.append(_cap(_list_join(bits[4:8]) + "."))
    if len(bits) > 8:
        out.append(_cap(_list_join(bits[8:12]) + "."))
    if len(bits) > 12:
        out.append(_cap(_list_join(bits[12:]) + "."))
    return " ".join(out)


def team_narrative(d) -> str:
    o = team_offense(d)
    de = team_defense(d)
    return (
        "### Offensive Playstyle\n\n" + o + "\n\n"
        "### Defensive Playstyle\n\n" + de + "\n"
    )


# --------------------------------------------------------------------- writer

def upsert_block(text: str, block_md: str, after_header_re: str | None = None) -> str:
    """Replace existing PLAYSTYLE-NARRATIVE block, or insert one in a sensible spot."""
    block = f"\n## Playstyle Narrative\n\n{NARR_START}\n\n{block_md}\n{NARR_END}\n"
    if NARR_START in text and NARR_END in text:
        return re.sub(
            r"\n## Playstyle Narrative\s*\n\s*" + re.escape(NARR_START) + r".*?" + re.escape(NARR_END) + r"\n?",
            block, text, flags=re.S,
        )
    # Insert after the heading if given, else append before any trailing AUTO blocks
    if after_header_re:
        m = re.search(after_header_re, text)
        if m:
            idx = m.end()
            # advance to end of that section (next ## heading or EOF)
            nxt = re.search(r"\n## ", text[idx:])
            insert_at = idx + (nxt.start() if nxt else (len(text) - idx))
            return text[:insert_at] + block + text[insert_at:]
    # default: insert before SCHEME-AUTO START if present, else append
    m = re.search(r"\n<!-- SCHEME-AUTO START -->", text)
    if m:
        return text[:m.start()] + block + text[m.start():]
    m = re.search(r"\n<!-- ROSTER-AUTO START -->", text)
    if m:
        return text[:m.start()] + block + text[m.start():]
    return text.rstrip() + "\n" + block


def process_team(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    d = parse_team(text)
    block = team_narrative(d)
    new = upsert_block(text, block, after_header_re=r"^# [A-Z]{3}.*$")
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def process_player(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "<!-- PLAYSTYLE-EXPORT v1 -->" not in text:
        return False
    d = parse_player(text)
    block = player_narrative(d)
    # insert after the existing "## How X plays" section if present, else after Strengths
    new = upsert_block(text, block, after_header_re=r"^## How [^\n]+$")
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    t_done = p_done = 0
    if only in ("all", "teams"):
        for f in sorted(TEAMS_DIR.glob("*.md")):
            try:
                if process_team(f):
                    t_done += 1
            except Exception as e:
                print(f"[team-fail] {f.name}: {e}", file=sys.stderr)
    if only in ("all", "players"):
        for f in sorted(PLAYERS_DIR.glob("*.md")):
            try:
                if process_player(f):
                    p_done += 1
            except Exception as e:
                print(f"[player-fail] {f.name}: {e}", file=sys.stderr)
    print(f"teams updated: {t_done}/30")
    print(f"players updated: {p_done}/{len(list(PLAYERS_DIR.glob('*.md')))}")


if __name__ == "__main__":
    main()
