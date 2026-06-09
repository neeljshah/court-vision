"""
Build per-team Game Plan pages for vault/Intelligence/GamePlans/<TRI>.md.

For each of 30 teams, generates an opposing-GM scouting report:
  - YAML frontmatter
  - Offensive identity prose (3-5 sentences)
  - How to defend them (5 tactical bullets)
  - Defensive identity prose (3-5 sentences)
  - How to attack them (5 tactical bullets)
  - Personnel to target (stars + anchors + shooters)
  - Statistical X-ray table

Also writes GamePlans_Index.md and inserts a "Game plan:" link at the top of each team note.

Idempotent: uses <!-- GAMEPLAN START/END --> markers.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parent.parent.parent
TEAMS_DIR  = ROOT / "vault" / "Intelligence" / "Teams"
PLANS_DIR  = ROOT / "vault" / "Intelligence" / "GamePlans"
INDEX_PATH = ROOT / "vault" / "Intelligence" / "GamePlans_Index.md"

GP_START = "<!-- GAMEPLAN START -->"
GP_END   = "<!-- GAMEPLAN END -->"

AS_OF = str(date.today())

# ─────────────────────────────── regex / parse helpers ───────────────────────

NUM_RE = r"[-+]?\d*\.?\d+%?"


def _grab(text: str, label_pattern: str, value_pattern: str = NUM_RE):
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
                return f / 100.0 if v.endswith("%") else f
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


def _pct(v, nd=1):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if 0 <= f <= 1.0:
        f *= 100
    return f"{f:.{nd}f}%"


def _f(v, nd=1):
    if v is None:
        return None
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return None


# ─────────────────────────────── team parser ─────────────────────────────────

def _table_dict(text: str, section_header_re: str):
    sec = re.search(
        section_header_re + r"(.*?)(?:\n\s*\*\*[^*\n]+:\*\*|\n##|\n###|\n<!--|\Z)",
        text, re.S
    )
    if not sec:
        return {}
    out = {}
    for m in re.finditer(r"\|\s*([A-Za-z][^|]*?)\s*\|\s*([\d.]+)\s*\|", sec.group(1)):
        k = m.group(1).strip()
        if k.lower() in ("play type", "metric"):
            continue
        try:
            out[k.lower()] = float(m.group(2))
        except ValueError:
            pass
    return out


def parse_team(text: str) -> dict:
    d: dict = {}

    m = re.search(r"^#\s+([A-Z]{3})\b", text, re.M)
    d["abbr"] = m.group(1) if m else "TEAM"

    # YAML frontmatter n_games
    m = re.search(r"n_cv_games:\s*(\d+)", text)
    d["n_games"] = int(m.group(1)) if m else None

    # scheme tags
    m = re.search(r"\*\*Dominant tag:\*\*\s*([^\n]+)", text)
    d["dominant"] = m.group(1).strip() if m else None
    m = re.search(r"\*\*Primary coverage:\*\*\s*([^\n]+)", text)
    d["primary_cov"] = m.group(1).strip() if m else None
    m = re.search(r"\*\*All tags:\*\*\s*([^\n]+)", text)
    if m:
        d["all_tags"] = [t.strip() for t in re.split(r"[|,]", m.group(1)) if t.strip()]
    else:
        d["all_tags"] = []
    m = re.search(r"\*\*Pace identity:\*\*\s*([A-Z]+)", text)
    d["pace_label"] = m.group(1).strip() if m else _grab_str(text, r"Pace label")
    m = re.search(r"\*\*Rebounding identity:\*\*\s*([a-zA-Z_]+)", text)
    d["reb_identity"] = (m.group(1).replace("_", " ") if m else None)

    # axis scores
    for k, lbl in [
        ("drop_switch",  r"Drop vs Switch"),
        ("paint_prot",   r"Paint Protection"),
        ("perim_denial", r"Perimeter Denial"),
        ("pace_ctrl",    r"Pace Control"),
        ("iso_force",    r"Iso Force"),
        ("closeout",     r"Closeout Intensity"),
    ]:
        d[k] = _grab(text, lbl)

    # ratings
    d["offrtg"]      = _grab(text, r"OffRtg(?! L10)")
    d["defrtg"]      = _grab(text, r"DefRtg(?! L10| trend)")
    d["defrtg_l10"]  = _grab(text, r"DefRtg L10")
    d["defrtg_trend"]= _grab(text, r"DefRtg trend")
    d["pace"]        = _grab(text, r"Pace(?!\s*(?:label|identity|context))")
    d["efg"]         = _grab(text, r"eFG%")
    d["ts"]          = _grab(text, r"TS%")
    d["tov_ratio"]   = _grab(text, r"TOV ratio")
    d["ast_pct"]     = _grab(text, r"Ast%")
    d["oreb_pct"]    = _grab(text, r"OReb%(?! season| L10| rank)")
    d["dreb_pct"]    = _grab(text, r"DReb%(?! season| L10| rank)")
    d["pnr_ppp"]     = _grab(text, r"PNR PPP")

    # opp shot mix z-scores
    d["opp_paint_z"] = _grab(text, r"Opp paint% z")
    d["opp_3_z"]     = _grab(text, r"Opp 3pt% z")
    d["opp_mid_z"]   = _grab(text, r"Opp mid% z")

    # rim defense
    d["rim_fg_allow"]  = _grab(text, r"Rim FG% allowed")
    d["rim_fg_normal"] = _grab(text, r"Rim FG% normal")
    d["rim_vs_normal"] = _grab(text, r"Rim FG% vs normal")
    d["rim_freq"]      = _grab(text, r"Rim freq faced")
    d["paint_fg_allow"]= _grab(text, r"Paint FG% allowed")

    # perimeter pressure z
    d["contest_z"]   = _grab(text, r"Contested shot rate z")
    d["def_dist_z"]  = _grab(text, r"Avg defender distance z")
    d["pace_imposed_z"] = _grab(text, r"Pace imposed z")

    # tempo z
    d["tempo_z"]       = _grab(text, r"Tempo z(?! score)")
    d["trans_share_z"] = _grab(text, r"Transition share z")
    d["spacing_z"]     = _grab(text, r"Avg spacing z")

    # turnover / transition
    d["opp_tov"]    = _grab(text, r"Opp TOV% \(season\)")
    d["own_tov"]    = _grab(text, r"Own TOV ratio")
    d["deflect_g"]  = _grab(text, r"Deflections/g")
    d["opp_trans_g"]= _grab(text, r"Opp transition possessions/g")

    # FT env
    d["pf_g"]       = _grab(text, r"PF/g")
    d["fta_g"]      = _grab(text, r"FTA drawn/g")
    d["opp_fta_g"]  = _grab(text, r"Opp FTA allowed/g")
    d["net_fta"]    = _grab(text, r"Net FTA differential")

    # ball movement / drives
    d["passes_g"]   = _grab(text, r"Passes made/g")
    d["drives_g"]   = _grab(text, r"Drives/g")
    d["drive_fg"]   = _grab(text, r"Drive FG%")

    # 3-pt defense
    d["opp_3p_pct"] = _grab(text, r"Opp 3P%")
    d["opp_3pa_g"]  = _grab(text, r"3PA/g")

    # play type tables
    d["pt_freq"] = _table_dict(text, r"\*\*Play type mix \(frequency\):\*\*")
    d["pt_ppp"]  = _table_dict(text, r"\*\*PPP by play type:\*\*")

    # roster (wikilinks)
    roster = []
    for m in re.finditer(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]\s*—\s*_([^_]+)_", text):
        slug = m.group(1).strip()
        arch = m.group(2).strip()
        name_part = re.sub(r"^\d+_", "", slug).replace("_", " ").title()
        roster.append({"slug": slug, "name": name_part, "arch": arch})
    d["roster"] = roster

    return d


# ─────────────────────────────── league rank helper ──────────────────────────

# Pre-computed approximate league ranks from the 30-team dataset for key metrics.
# Rank is bucket: "top-5 / top-10 / middle / bottom-10 / bottom-5"
def _rank_bucket(val, league_vals: list[float], higher_is_better: bool) -> str:
    """Return top-5 / top-10 / middle / bottom-10 / bottom-5 bucket."""
    if val is None:
        return "—"
    vals_sorted = sorted([v for v in league_vals if v is not None], reverse=higher_is_better)
    try:
        rank = vals_sorted.index(val) + 1
    except ValueError:
        # find closest
        diffs = [(abs(v - val), i) for i, v in enumerate(vals_sorted)]
        rank = min(diffs)[1] + 1
    n = len(vals_sorted)
    if rank <= 5:
        return "top-5"
    if rank <= 10:
        return "top-10"
    if rank >= n - 4:
        return "bottom-5"
    if rank >= n - 9:
        return "bottom-10"
    return "middle"


# ─────────────────────────────── narrative builders ──────────────────────────

def _z_word(z, high, low):
    if z is None:
        return None
    try:
        z = float(z)
    except (TypeError, ValueError):
        return None
    if z >= 0.6:
        return high
    if z <= -0.6:
        return low
    return None


def _best_ppp(pt_ppp: dict, pt_freq: dict, exclude_keys=("halfcourt (overall)",)):
    candidates = [(v, k) for k, v in pt_ppp.items() if k not in exclude_keys]
    # filter to plays with meaningful frequency
    candidates = [(v, k) for v, k in candidates if (pt_freq.get(k) or 0) >= 0.03]
    if not candidates:
        return None, None
    v, k = max(candidates)
    return k, v


def _worst_ppp(pt_ppp: dict, pt_freq: dict, exclude_keys=("halfcourt (overall)",)):
    candidates = [(v, k) for k, v in pt_ppp.items() if k not in exclude_keys]
    candidates = [(v, k) for v, k in candidates if (pt_freq.get(k) or 0) >= 0.05]
    if not candidates:
        return None, None
    v, k = min(candidates)
    return k, v


def _top_freq_plays(pt_freq: dict, n=3):
    items = sorted(pt_freq.items(), key=lambda x: x[1], reverse=True)
    return items[:n]


def _cap(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


# ─────────────────────────────── offense section ─────────────────────────────

def offense_prose(d: dict) -> str:
    abbr = d["abbr"]
    bits = []

    # Pace identity
    pace = d.get("pace_label") or ("fast" if (d.get("pace") or 0) >= 100 else "slow")
    pace_v = _f(d.get("pace"))
    tempo_z = d.get("tempo_z")
    trans_z = d.get("trans_share_z")

    pace_desc = pace.lower()
    if tempo_z is not None:
        try:
            tz = float(tempo_z)
            if tz >= 1.0:
                pace_desc = "one of the fastest"
            elif tz >= 0.6:
                pace_desc = "above-league"
            elif tz <= -1.0:
                pace_desc = "one of the slowest"
            elif tz <= -0.6:
                pace_desc = "below-league"
        except (TypeError, ValueError):
            pass

    s = f"{abbr} plays a {pace_desc}-tempo game (pace {pace_v or '?'}"
    if trans_z is not None:
        try:
            tz2 = float(trans_z)
            if tz2 >= 0.7:
                s += ", transition-heavy"
            elif tz2 <= -0.7:
                s += ", halfcourt-grind"
        except (TypeError, ValueError):
            pass
    s += ")."

    # Spacing
    sp_z = d.get("spacing_z")
    sp_word = _z_word(sp_z, "wide-spacing / stretch-floor look", "tight-spacing / paint-first look")
    if sp_word:
        s += f" Their floor alignment is {sp_word} (spacing z={_f(sp_z, 2)})."

    # Play type primary actions
    pt_freq = d.get("pt_freq") or {}
    pt_ppp  = d.get("pt_ppp") or {}
    top_plays = _top_freq_plays(pt_freq, 3)
    if top_plays:
        play_str = ", ".join(f"{k} ({_pct(v)})" for k, v in top_plays)
        s += f" Primary actions by frequency: {play_str}."

    # Best and worst PPP
    best_k, best_v = _best_ppp(pt_ppp, pt_freq)
    worst_k, worst_v = _worst_ppp(pt_ppp, pt_freq)
    if best_k and best_v:
        s += f" Their most efficient action is {best_k} ({_f(best_v, 2)} PPP)"
        if worst_k and worst_v and worst_k != best_k:
            s += f"; least efficient is {worst_k} ({_f(worst_v, 2)} PPP)."
        else:
            s += "."

    # Ball movement vs iso
    passes = d.get("passes_g")
    ast_pct = d.get("ast_pct")
    tov = d.get("tov_ratio")
    if passes is not None and ast_pct is not None:
        move = "ball-movement" if passes >= 24 else ("low-movement" if passes <= 21 else "moderate-movement")
        s += f" {_cap(move)} offense: {_f(passes)} passes/g, {_pct(ast_pct)} assist rate"
        if tov:
            s += f", TOV ratio {_f(tov)}."
        else:
            s += "."

    # Drive-heavy vs jump-shot heavy
    drives = d.get("drives_g")
    drive_fg = d.get("drive_fg")
    if drives is not None:
        if drives >= 4.5:
            s += f" Drive-heavy attack: {_f(drives)} drives/g at {_pct(drive_fg) or '?'} FG."
        elif drives <= 2.5:
            s += f" Jump-shot oriented: only {_f(drives)} drives/g."

    # Efficiency summary
    off = _f(d.get("offrtg"))
    efg = _pct(d.get("efg"))
    ts  = _pct(d.get("ts"))
    if off:
        s += f" Season OffRtg {off} ({efg or '?'} eFG / {ts or '?'} TS)."

    # OReb
    oreb = d.get("oreb_pct")
    if oreb is not None:
        if oreb >= 0.30:
            s += f" Strong offensive-glass team (OReb% {_pct(oreb)}) — extra possessions are a key pillar."
        elif oreb <= 0.23:
            s += f" Get-back team: de-emphasizes offensive glass (OReb% {_pct(oreb)})."

    return s


# ─────────────────────────────── how-to-defend bullets ───────────────────────

def defend_bullets(d: dict) -> list[str]:
    pt_freq = d.get("pt_freq") or {}
    pt_ppp  = d.get("pt_ppp") or {}
    bullets = []

    # 1. Play-type redirection
    best_k, best_v = _best_ppp(pt_ppp, pt_freq)
    worst_k, worst_v = _worst_ppp(pt_ppp, pt_freq)
    if best_k and best_v and worst_k and worst_v and best_k != worst_k:
        bullets.append(
            f"Force them out of **{best_k}** ({_f(best_v, 2)} PPP) into **{worst_k}** "
            f"({_f(worst_v, 2)} PPP) — biggest efficiency gap in their halfcourt menu."
        )
    elif best_k and best_v:
        bullets.append(
            f"Take away **{best_k}** — their sharpest play at {_f(best_v, 2)} PPP; "
            "accept the second option."
        )

    # 2. 3-point / PnR coverage
    spacing_z = d.get("spacing_z")
    pnr_ppp   = d.get("pnr_ppp")
    if spacing_z is not None:
        try:
            sz = float(spacing_z)
            if sz >= 0.6:
                coverage = "stay attached and contest every spot-up — they space the floor well (spacing z={:.2f})".format(sz)
            elif sz <= -0.6:
                coverage = "sagging off the shooter is viable; they are not a spacing team (spacing z={:.2f})".format(sz)
            else:
                coverage = "stay connected on shooters (neutral spacing team)"
        except (TypeError, ValueError):
            coverage = "standard 3-point coverage"
    else:
        coverage = "standard 3-point coverage"

    pnr_note = ""
    if pnr_ppp is not None:
        try:
            pv = float(pnr_ppp)
            if pv >= 1.00:
                pnr_note = f"; PnR is dangerous at {_f(pv, 2)} PPP — show hard or switch"
            elif pv <= 0.85:
                pnr_note = f"; PnR is weak ({_f(pv, 2)} PPP) — drop is viable"
        except (TypeError, ValueError):
            pass
    bullets.append(f"Perimeter coverage: {coverage}{pnr_note}.")

    # 3. Pace
    tempo_z = d.get("tempo_z")
    trans_z = d.get("trans_share_z")
    if trans_z is not None:
        try:
            tz = float(trans_z)
            if tz >= 0.8:
                bullets.append(
                    f"Slow the game down — they thrive in transition (trans share z=+{_f(tz, 2)}). "
                    "Crack-back the rim, get set early, force halfcourt sets."
                )
            elif tz <= -0.8:
                bullets.append(
                    f"Push pace — they are a grind team (trans share z={_f(tz, 2)}). "
                    "Attack off misses before they set up and make them defend in chaos."
                )
            else:
                bullets.append(
                    "Pace is neutral; focus energy on halfcourt scheme disruption rather than speed of play."
                )
        except (TypeError, ValueError):
            bullets.append("Match or control pace to neutralize tempo advantage.")
    else:
        bullets.append("Match pace; neutralize any transition edge by getting numbers back.")

    # 4. Offensive rebounding
    oreb = d.get("oreb_pct")
    if oreb is not None:
        try:
            ov = float(oreb)
            if ov >= 0.30:
                bullets.append(
                    f"Send 2+ defenders to box out after every shot — they crash hard (OReb% {_pct(oreb)}). "
                    "Surrendering second-chance points is a known way to lose to this team."
                )
            elif ov <= 0.23:
                bullets.append(
                    f"One defender can tag the offensive glass — they get back (OReb% {_pct(oreb)}). "
                    "Release your guards into transition offense early."
                )
            else:
                bullets.append(
                    f"Standard box-out discipline — average offensive-glass aggression (OReb% {_pct(oreb)})."
                )
        except (TypeError, ValueError):
            bullets.append("Standard box-out discipline.")
    else:
        bullets.append("Standard box-out discipline.")

    # 5. Foul-bait / FT environment
    pf = d.get("pf_g")
    fta_drawn = d.get("fta_g")
    if fta_drawn is not None:
        try:
            fv = float(fta_drawn)
            if fv >= 28:
                bullets.append(
                    f"Stay disciplined and vertical — they draw fouls at a high rate "
                    f"({_f(fv)} FTA/g). Avoid body contact, especially in the paint."
                )
            elif fv <= 22:
                bullets.append(
                    f"Be physical — they rarely get to the line ({_f(fv)} FTA/g). "
                    "Bump cutters, crowd the driver; they won't manufacture easy FTs."
                )
            else:
                bullets.append(
                    f"Average FT rate ({_f(fv)} FTA/g) — standard foul-discipline applies."
                )
        except (TypeError, ValueError):
            bullets.append("Average foul environment — standard discipline.")
    else:
        bullets.append("Average foul environment — standard discipline.")

    return bullets[:5]


# ─────────────────────────────── defense section ─────────────────────────────

def defense_prose(d: dict) -> str:
    abbr = d["abbr"]
    bits = []

    # Scheme identity
    scheme = d.get("dominant") or d.get("primary_cov") or "undetermined scheme"
    other  = [t for t in (d.get("all_tags") or []) if t and t.lower() != scheme.lower()]
    bits.append(
        f"{abbr} employs a **{scheme.upper()}** primary scheme"
        + (f" with {', '.join(o.lower() for o in other[:3])} elements" if other else "")
        + "."
    )

    # Drop vs switch axis
    ds = d.get("drop_switch")
    if ds is not None:
        try:
            dsv = float(ds)
            if dsv >= 0.3:
                bits.append(f"They lean heavily into drop coverage on PnR (axis z=+{_f(dsv, 2)}), yielding mid-range pull-ups.")
            elif dsv <= -0.3:
                bits.append(f"They prefer switching assignments (drop/switch axis z={_f(dsv, 2)}), creating mismatch hunt opportunities.")
        except (TypeError, ValueError):
            pass

    # Rim vs perimeter tradeoff
    rim = d.get("rim_fg_allow")
    opp3 = d.get("opp_3p_pct")
    rim_vs = d.get("rim_vs_normal")
    if rim is not None:
        try:
            rv = float(rim)
            verdict = "strong rim protectors" if rv <= 0.60 else ("leaky at the rim" if rv >= 0.65 else "average rim defense")
            s_rim = f"Rim defense is {verdict} ({_pct(rim)} rim FG allowed"
            if rim_vs is not None:
                diff = float(rim_vs)
                s_rim += f", {'+' if diff >= 0 else ''}{_f(diff * 100, 1)}pp vs expected"
            s_rim += ")."
        except (TypeError, ValueError):
            s_rim = None
    else:
        s_rim = None
    if opp3 is not None and s_rim:
        bits.append(s_rim + f" Opponents shoot {_pct(opp3)} from three ({_f(d.get('opp_3pa_g') or 0)} 3PA/g).")
    elif s_rim:
        bits.append(s_rim)

    # Turnover forcing rate
    opp_tov = d.get("opp_tov")
    deflect = d.get("deflect_g")
    if opp_tov is not None:
        try:
            tv = float(opp_tov)
            if tv >= 0.155:
                bits.append(f"Aggressive turnover-forcing defense: {_pct(tv)} opp TOV rate"
                            + (f" / {_f(deflect)} deflections/g" if deflect else "") + ".")
            elif tv <= 0.125:
                bits.append(f"Passive turnover-forcing: {_pct(tv)} opp TOV rate — they stay home and prevent rather than gamble.")
            else:
                bits.append(f"Average turnover-forcing rate ({_pct(tv)} opp TOV%).")
        except (TypeError, ValueError):
            pass

    # Closeout discipline / contest rate
    cont_z = d.get("contest_z")
    dist_z = d.get("def_dist_z")
    closeout_bits = []
    if cont_z is not None:
        try:
            cv = float(cont_z)
            if cv >= 0.6:
                closeout_bits.append(f"elite contest rate (z=+{_f(cv, 2)})")
            elif cv <= -0.6:
                closeout_bits.append(f"low contest rate (z={_f(cv, 2)})")
        except (TypeError, ValueError):
            pass
    if dist_z is not None:
        try:
            dv = float(dist_z)
            if dv >= 0.6:
                closeout_bits.append(f"defenders play off shooters (dist z=+{_f(dv, 2)})")
            elif dv <= -0.6:
                closeout_bits.append(f"tight on-ball pressure (dist z={_f(dv, 2)})")
        except (TypeError, ValueError):
            pass
    if closeout_bits:
        bits.append("Closeout discipline: " + ", ".join(closeout_bits) + ".")

    # DefRtg + trend
    defrtg = d.get("defrtg")
    trend  = d.get("defrtg_trend")
    if defrtg is not None:
        dr_s = f"Season DefRtg {_f(defrtg)}"
        if trend is not None:
            try:
                tv2 = float(trend)
                if tv2 <= -1.5:
                    dr_s += f" (improving, L10 trend {_f(tv2, 1)})"
                elif tv2 >= 1.5:
                    dr_s += f" (sliding, L10 trend +{_f(tv2, 1)})"
            except (TypeError, ValueError):
                pass
        bits.append(dr_s + ".")

    # Transition defense
    trans_g = d.get("opp_trans_g")
    if trans_g is not None:
        try:
            tgv = float(trans_g)
            if tgv >= 18:
                bits.append(f"Transition vulnerability: opponents get {_f(tgv)} transition poss/g — attack off misses.")
            elif tgv <= 14:
                bits.append(f"Solid transition defense: only {_f(tgv)} opp transition poss/g.")
        except (TypeError, ValueError):
            pass

    return " ".join(bits)


# ─────────────────────────────── how-to-attack bullets ───────────────────────

def attack_bullets(d: dict) -> list[str]:
    bullets = []

    # 1. Weakest shot zone they concede
    opp_paint_z = d.get("opp_paint_z")
    opp_3_z     = d.get("opp_3_z")
    opp_mid_z   = d.get("opp_mid_z")

    zones = []
    if opp_paint_z is not None:
        try:
            zones.append(("paint", float(opp_paint_z)))
        except (TypeError, ValueError):
            pass
    if opp_3_z is not None:
        try:
            zones.append(("three-point line", float(opp_3_z)))
        except (TypeError, ValueError):
            pass
    if opp_mid_z is not None:
        try:
            zones.append(("mid-range", float(opp_mid_z)))
        except (TypeError, ValueError):
            pass

    if zones:
        best_zone = max(zones, key=lambda x: x[1])
        zone_name, zone_z = best_zone
        if zone_z >= 0.5:
            bullets.append(
                f"Attack the **{zone_name}** — they concede that zone above league average "
                f"(z=+{_f(zone_z, 2)}). That's the structural crack in their shot-mix defense."
            )
        else:
            worst_zone = min(zones, key=lambda x: x[1])
            wz_name, wz_z = worst_zone
            if wz_z <= -0.5:
                bullets.append(
                    f"Avoid the **{wz_name}** (they suppress it at z={_f(wz_z, 2)}). "
                    f"Shift volume toward {'paint' if wz_name != 'paint' else 'three-point'} attempts."
                )
            else:
                bullets.append(
                    "Shot-mix defense is balanced — attack based on personnel mismatches, not zone."
                )
    else:
        bullets.append("No clear zone concession — attack personnel mismatches.")

    # 2. Drop/switch exploitation
    ds = d.get("drop_switch")
    if ds is not None:
        try:
            dsv = float(ds)
            if dsv >= 0.25:
                bullets.append(
                    f"They drop the big on PnR (drop axis z=+{_f(dsv, 2)}): "
                    "pull the screener to the mid-range and let him pop; attack the early-return big with pick-and-pop."
                )
            elif dsv <= -0.25:
                bullets.append(
                    f"They switch across (drop axis z={_f(dsv, 2)}): "
                    "hunt size mismatches — put a guard on the big and post/hunt at the rim, "
                    "or isolate slow-footed bigs in space."
                )
            else:
                bullets.append(
                    "Coverage is mixed drop/switch — read the action and hit the open option on the second side."
                )
        except (TypeError, ValueError):
            bullets.append("Read their coverage assignment and attack the mismatch player.")
    else:
        bullets.append("Standard PnR execution; read coverage and attack the open side.")

    # 3. Foul rate exploitation
    pf = d.get("pf_g")
    opp_fta = d.get("opp_fta_g")
    if opp_fta is not None:
        try:
            fv = float(opp_fta)
            if fv >= 27:
                bullets.append(
                    f"Drive into contact aggressively — they foul at a high rate "
                    f"({_f(fv)} opp FTA allowed/g). Straight-line drives and post-ups put them in foul trouble."
                )
            elif fv <= 23:
                bullets.append(
                    f"They seldom foul ({_f(fv)} opp FTA allowed/g). "
                    "Earn your points inside on clean finishes; drawing free throws will be limited."
                )
            else:
                bullets.append(
                    f"Average foul rate ({_f(fv)} opp FTA/g) — standard contact strategy applies."
                )
        except (TypeError, ValueError):
            bullets.append("Average foul environment on defense.")
    else:
        bullets.append("Average foul environment on defense.")

    # 4. Defensive rebounding leak
    dreb = d.get("dreb_pct")
    if dreb is not None:
        try:
            dv = float(dreb)
            if dv <= 0.71:
                bullets.append(
                    f"Send offensive rebounders — they leak second chances (DReb% {_pct(dreb)}). "
                    "Crashing two is profitable; expect live-ball turnovers and tip-ins."
                )
            elif dv >= 0.75:
                bullets.append(
                    f"Get back on D after misses — they lock the defensive glass (DReb% {_pct(dreb)}). "
                    "Offensive rebounding is a losing bet; prioritize fast-break transition instead."
                )
            else:
                bullets.append(
                    f"Average defensive-glass lock (DReb% {_pct(dreb)}) — one crash attacker is fine."
                )
        except (TypeError, ValueError):
            bullets.append("Average defensive rebounding — standard crash discipline.")
    else:
        bullets.append("Average defensive rebounding — standard crash discipline.")

    # 5. Transition offense opportunity
    trans_g = d.get("opp_trans_g")
    if trans_g is not None:
        try:
            tgv = float(trans_g)
            if tgv >= 18:
                bullets.append(
                    f"Push in transition every chance you get — opponents average {_f(tgv)} "
                    "transition poss/g vs this defense. Get out early off every defensive rebound and turnover."
                )
            elif tgv <= 14:
                bullets.append(
                    f"This team gets back well ({_f(tgv)} opp trans poss/g) — "
                    "set up your halfcourt game; fast breaks will be scarce."
                )
            else:
                bullets.append(
                    f"Moderate transition opportunity ({_f(tgv)} opp trans poss/g) — "
                    "push selectively when numbers are clearly there."
                )
        except (TypeError, ValueError):
            bullets.append("Moderate transition opportunity — push selectively.")
    else:
        bullets.append("Moderate transition opportunity — push selectively.")

    return bullets[:5]


# ─────────────────────────────── personnel section ───────────────────────────

def personnel_section(d: dict) -> str:
    roster = d.get("roster") or []
    if not roster:
        return "_No roster data available._"

    # Classify by archetype
    star_archs = {"primary initiator", "lead guard", "high-usage scorer", "dominant two-way big",
                  "playmaking big", "high-usage shot creator", "playmaking guard"}
    anchor_archs = {"dominant two-way big", "playmaking big", "rim protector", "big", "anchor"}
    shooter_archs = {"movement shooter", "3&d wing", "spot-up shooter", "spacing forward"}

    stars    = [p for p in roster if any(a in p["arch"].lower() for a in star_archs)]
    anchors  = [p for p in roster if any(a in p["arch"].lower() for a in anchor_archs)
                and p not in stars]
    shooters = [p for p in roster if any(a in p["arch"].lower() for a in shooter_archs)]

    lines = []

    # Top offensive threats
    lines.append("**Offensive threats to slow:**")
    for p in stars[:3]:
        lines.append(f"- [[{p['slug']}|{p['name']}]] — _{p['arch']}_ — primary scoring load; game-plan around his action first")
    if not stars:
        lines.append("- _(no high-usage scorers tagged — check player dossiers)_")

    # Defensive anchor
    lines.append("\n**Defensive anchor(s):**")
    for p in anchors[:2]:
        lines.append(f"- [[{p['slug']}|{p['name']}]] — _{p['arch']}_ — rim/paint anchor; draw him away from the paint to open lanes")
    if not anchors:
        lines.append("- _(no dedicated anchor tagged)_")

    # Shooters to respect
    lines.append("\n**Shooters to respect off the ball:**")
    for p in shooters[:4]:
        lines.append(f"- [[{p['slug']}|{p['name']}]] — _{p['arch']}_ — leave open at your peril; one skip pass = open look")
    if not shooters:
        lines.append("- _(no dedicated spacing shooters tagged)_")

    return "\n".join(lines)


# ─────────────────────────────── x-ray table ─────────────────────────────────

def xray_table(d: dict, all_teams: list[dict]) -> str:
    def _collect(key):
        return [t.get(key) for t in all_teams if t.get(key) is not None]

    rows = []

    def _row(label, key, val, higher_is_better, fmt_fn, unit=""):
        league_vals = _collect(key)
        bucket = _rank_bucket(val, league_vals, higher_is_better) if (val is not None and league_vals) else "—"
        display = (fmt_fn(val) + unit) if val is not None else "—"
        read = {
            "top-5":    "elite" if higher_is_better else "liability",
            "top-10":   "above avg" if higher_is_better else "below avg",
            "middle":   "avg",
            "bottom-10":"below avg" if higher_is_better else "above avg",
            "bottom-5": "liability" if higher_is_better else "elite",
            "—":        "—",
        }.get(bucket, "—")
        rows.append(f"| {label} | {display} | {bucket} | {read} |")

    _row("OffRtg",           "offrtg",     d.get("offrtg"),     True,  lambda v: _f(v, 1))
    _row("DefRtg",           "defrtg",     d.get("defrtg"),     False, lambda v: _f(v, 1))
    _row("Pace",             "pace",       d.get("pace"),       True,  lambda v: _f(v, 2))
    _row("eFG%",             "efg",        d.get("efg"),        True,  lambda v: _pct(v))
    _row("OReb%",            "oreb_pct",   d.get("oreb_pct"),   True,  lambda v: _pct(v))
    _row("DReb%",            "dreb_pct",   d.get("dreb_pct"),   True,  lambda v: _pct(v))
    _row("TOV ratio",        "tov_ratio",  d.get("tov_ratio"),  False, lambda v: _f(v, 1))
    _row("Opp 3P%",          "opp_3p_pct", d.get("opp_3p_pct"), False, lambda v: _pct(v))
    _row("Rim FG% allowed",  "rim_fg_allow",d.get("rim_fg_allow"),False,lambda v: _pct(v))
    _row("Net FTA diff",     "net_fta",    d.get("net_fta"),    True,  lambda v: (f"+{_f(v,1)}" if (v or 0) >= 0 else _f(v, 1)))

    header = ("| Metric | Value | League tier | Read |\n"
              "|--------|-------|-------------|------|\n")
    return header + "\n".join(rows)


# ─────────────────────────────── one-line index summary ──────────────────────

def index_summary(d: dict) -> str:
    abbr = d["abbr"]
    pace = (d.get("pace_label") or "").upper() or "?"
    spacing = None
    sp_z = d.get("spacing_z")
    if sp_z is not None:
        try:
            spacing = "wide-spacing" if float(sp_z) >= 0.5 else ("tight-spacing" if float(sp_z) <= -0.5 else "neutral-spacing")
        except (TypeError, ValueError):
            pass
    scheme = (d.get("dominant") or d.get("primary_cov") or "?").upper()
    off = _f(d.get("offrtg"), 0)
    def_ = _f(d.get("defrtg"), 0)
    parts = [pace, spacing or "neutral-spacing", scheme.lower()]
    if off:
        parts.append(f"OffRtg {off}")
    if def_:
        parts.append(f"DefRtg {def_}")
    return f"**[[GamePlans/{abbr}|{abbr}]]** — " + " / ".join(p for p in parts if p)


# ─────────────────────────────── full page builder ───────────────────────────

def build_page(d: dict, all_teams: list[dict]) -> str:
    abbr    = d["abbr"]
    n_games = d.get("n_games") or "n/a"

    front = (
        f"---\n"
        f"team_abbr: {abbr}\n"
        f"as_of: {AS_OF}\n"
        f"n_games: {n_games}\n"
        f"---\n\n"
        f"# {abbr} — Game Plan\n\n"
        f"> Opposing-GM scouting report. Auto-generated from vault team stats — do not edit between GAMEPLAN markers.\n\n"
        f"← Back to [[Teams/{abbr}|{abbr} Team Card]] | [[GamePlans_Index|All Game Plans]]\n\n"
    )

    off_prose  = offense_prose(d)
    def_prose  = defense_prose(d)
    def_buls   = defend_bullets(d)
    atk_buls   = attack_bullets(d)
    personnel  = personnel_section(d)
    xray       = xray_table(d, all_teams)

    body = (
        f"## What {abbr} Wants to Do on Offense\n\n"
        f"{off_prose}\n\n"
        f"## How to Defend {abbr} — Tactical Bullets\n\n"
        + "\n".join(f"- {b}" for b in def_buls)
        + f"\n\n## What {abbr} Does on Defense\n\n"
        f"{def_prose}\n\n"
        f"## How to Attack {abbr} — Tactical Bullets\n\n"
        + "\n".join(f"- {b}" for b in atk_buls)
        + f"\n\n## Personnel to Target\n\n"
        f"{personnel}\n\n"
        f"## Statistical X-Ray\n\n"
        f"{xray}\n"
    )

    return front + GP_START + "\n\n" + body + "\n" + GP_END + "\n"


# ─────────────────────────────── idempotent upsert ───────────────────────────

def upsert_page(path: Path, content: str) -> bool:
    if path.exists():
        old = path.read_text(encoding="utf-8")
        # Replace block between markers (keep frontmatter outside)
        if GP_START in old and GP_END in old:
            new = re.sub(
                re.escape(GP_START) + r".*?" + re.escape(GP_END),
                GP_START + "\n\n" + _extract_body(content) + "\n" + GP_END,
                old, flags=re.S
            )
        else:
            new = content
        if new == old:
            return False
        path.write_text(new, encoding="utf-8")
        return True
    path.write_text(content, encoding="utf-8")
    return True


def _extract_body(full_page: str) -> str:
    m = re.search(re.escape(GP_START) + r"\n\n(.*?)\n" + re.escape(GP_END), full_page, re.S)
    return m.group(1).strip() if m else full_page


# ─────────────────────────────── team-note backlink ──────────────────────────

GAMEPLAN_LINK_RE = re.compile(r"^\*\*Game plan:\*\*.*\n?", re.M)


def inject_team_backlink(team_path: Path, abbr: str) -> bool:
    text = team_path.read_text(encoding="utf-8")
    link_line = f"**Game plan:** [[GamePlans/{abbr}]]\n"

    if GAMEPLAN_LINK_RE.search(text):
        new = GAMEPLAN_LINK_RE.sub(link_line, text, count=1)
    else:
        # Insert after the YAML front-matter block (end of ---) before the first heading
        m = re.search(r"^---\n.*?^---\n", text, re.M | re.S)
        if m:
            insert_at = m.end()
            new = text[:insert_at] + "\n" + link_line + text[insert_at:]
        else:
            # Just after the first # heading line
            m2 = re.search(r"^# .+\n", text, re.M)
            if m2:
                insert_at = m2.end()
                new = text[:insert_at] + "\n" + link_line + "\n" + text[insert_at:]
            else:
                new = link_line + text

    if new == text:
        return False
    team_path.write_text(new, encoding="utf-8")
    return True


# ─────────────────────────────── main ────────────────────────────────────────

def main():
    PLANS_DIR.mkdir(parents=True, exist_ok=True)

    # Parse all teams
    team_files = sorted(TEAMS_DIR.glob("*.md"))
    all_data = []
    for f in team_files:
        try:
            text = f.read_text(encoding="utf-8")
            all_data.append(parse_team(text))
        except Exception as e:
            print(f"[parse-fail] {f.name}: {e}", file=sys.stderr)

    if not all_data:
        print("ERROR: no team files parsed", file=sys.stderr)
        sys.exit(1)

    # Build game plans
    written = skipped = 0
    index_rows = []
    sample_strong = sample_weak = None
    best_offrtg = worst_offrtg = None

    for d in all_data:
        abbr = d["abbr"]
        try:
            content = build_page(d, all_data)
            out_path = PLANS_DIR / f"{abbr}.md"
            changed = upsert_page(out_path, content)
            if changed:
                written += 1
            else:
                skipped += 1

            # Backlink in team note
            team_path = TEAMS_DIR / f"{abbr}.md"
            if team_path.exists():
                inject_team_backlink(team_path, abbr)

            index_rows.append(index_summary(d))

            # Track sample pages
            offrtg = d.get("offrtg")
            if offrtg is not None:
                if best_offrtg is None or offrtg > best_offrtg[0]:
                    best_offrtg = (offrtg, content, abbr)
                if worst_offrtg is None or offrtg < worst_offrtg[0]:
                    worst_offrtg = (offrtg, content, abbr)
        except Exception as e:
            print(f"[build-fail] {abbr}: {e}", file=sys.stderr)
            import traceback; traceback.print_exc(file=sys.stderr)

    # Write index
    index_md = (
        "# NBA Game Plans Index\n\n"
        "_Auto-generated by build_game_plans.py — one scouting summary per team._\n\n"
        f"_Last updated: {AS_OF}_\n\n"
        "| Team | Profile |\n"
        "|------|---------|\n"
    )
    for row in sorted(index_rows):
        # row already has [[GamePlans/TRI|TRI]] format
        # Reformat as table row: strip leading **
        m = re.match(r"\*\*(\[\[.*?\]\])\*\* — (.+)", row)
        if m:
            index_md += f"| {m.group(1)} | {m.group(2)} |\n"
        else:
            index_md += f"| {row} |\n"

    INDEX_PATH.write_text(index_md, encoding="utf-8")

    print(f"game plans written/updated: {written} | skipped (no change): {skipped}")
    print(f"index: {INDEX_PATH}")

    # Dump 2 sample pages
    for label, sample in [("STRONG TEAM", best_offrtg), ("WEAK TEAM", worst_offrtg)]:
        if sample:
            _, content, abbr = sample
            print(f"\n{'='*60}")
            print(f"SAMPLE — {label}: {abbr}")
            print("=" * 60)
            # Print only the body between markers (≤80 lines)
            lines = content.split("\n")
            in_block = False
            count = 0
            for line in lines:
                if GP_START in line:
                    in_block = True
                    continue
                if GP_END in line:
                    break
                if in_block:
                    print(line)
                    count += 1
                    if count >= 80:
                        print("... (truncated)")
                        break


if __name__ == "__main__":
    main()
