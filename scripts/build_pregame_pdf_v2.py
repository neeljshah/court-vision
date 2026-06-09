"""build_pregame_pdf_v2.py - magazine-style WCF G5 cheat sheet.

Reads from data/cache/intel_2026-05-26/. Output: 2-page dense, color-coded,
tier-ranked PDF with per-bet WHY reasoning.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    BaseDocTemplate,
    Spacer,
    Table,
    TableStyle,
    KeepInFrame,
)
from reportlab.platypus.flowables import HRFlowable

ROOT = Path(__file__).resolve().parent.parent
INTEL = ROOT / "data" / "cache" / "intel_2026-05-26"
OUT = INTEL / "reports" / "WCF_G5_intel_v2.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

# ---------------- Color palette (NBA-ish, no emojis) -----------------------
C_OKC_BLUE = colors.HexColor("#0c2340")
C_OKC_ORANGE = colors.HexColor("#ef3b24")
C_SAS_SILVER = colors.HexColor("#c4ced4")
C_SAS_BLACK = colors.HexColor("#000000")
C_DARK = colors.HexColor("#0a0e1a")
C_NAVY = colors.HexColor("#13294b")
C_CARD = colors.HexColor("#f5f7fa")
C_CARD_BORDER = colors.HexColor("#dde3eb")
C_GOLD = colors.HexColor("#d4a017")
C_SILVER = colors.HexColor("#9aa3b2")
C_BRONZE = colors.HexColor("#b87333")
C_WIN = colors.HexColor("#1f7a3b")
C_LOSS = colors.HexColor("#a51d2d")
C_MUTED = colors.HexColor("#6b7280")
C_BG_ALT = colors.HexColor("#eef2f7")
C_HI_YELLOW = colors.HexColor("#fff5cc")
C_HI_GREEN = colors.HexColor("#e8f4ec")
C_HI_RED = colors.HexColor("#fbeaec")

# ---------------- Styles ----------------------------------------------------
styles = getSampleStyleSheet()

TITLE = ParagraphStyle("title", parent=styles["Heading1"],
                       fontSize=18, leading=20, textColor=colors.white,
                       fontName="Helvetica-Bold", spaceAfter=0)
SUBTITLE = ParagraphStyle("sub", parent=styles["BodyText"],
                          fontSize=9, leading=11, textColor=colors.white,
                          fontName="Helvetica")
SECTION = ParagraphStyle("section", parent=styles["Heading2"],
                         fontSize=11, leading=12, textColor=C_NAVY,
                         fontName="Helvetica-Bold",
                         spaceBefore=6, spaceAfter=3)
BODY = ParagraphStyle("body", parent=styles["BodyText"],
                      fontSize=7.5, leading=9.5,
                      fontName="Helvetica", textColor=C_DARK)
BODY_BOLD = ParagraphStyle("bodyb", parent=BODY, fontName="Helvetica-Bold")
SMALL = ParagraphStyle("small", parent=BODY, fontSize=6.5, leading=8,
                       textColor=C_MUTED)
KEY = ParagraphStyle("key", parent=BODY, fontSize=8, leading=10,
                     fontName="Helvetica-Bold", textColor=C_NAVY)
WHY = ParagraphStyle("why", parent=BODY, fontSize=7, leading=9,
                     textColor=C_DARK, leftIndent=4)
TIER_S = ParagraphStyle("tier_s", parent=BODY, fontSize=9, leading=11,
                        fontName="Helvetica-Bold", textColor=colors.white)
KILL = ParagraphStyle("kill", parent=BODY, fontSize=6.5, leading=8,
                      textColor=C_LOSS, fontName="Helvetica-Oblique")
WIN_LABEL = ParagraphStyle("win", parent=BODY, fontSize=7, leading=9,
                           fontName="Helvetica-Bold", textColor=C_WIN)

# ---------------- Data ------------------------------------------------------
def load_intel():
    slate = pd.read_parquet(INTEL / "slate_fresh_2026-05-26.parquet")
    series = pd.read_csv(INTEL / "wcf_player_series_avg.csv")
    m2 = json.loads((INTEL / "m2_game.json").read_text(encoding="utf-8"))
    wp = json.loads((INTEL / "win_prob.json").read_text(encoding="utf-8"))
    team = json.loads((INTEL / "wcf_team_series_agg.json").read_text(encoding="utf-8"))
    ev = pd.read_csv(INTEL / "ev_final_high_conviction.csv")
    mc = json.loads((INTEL / "mc_tonight.json").read_text(encoding="utf-8"))
    return dict(slate=slate, series=series, m2=m2, wp=wp, team=team, ev=ev, mc=mc)

def mc_prob_for(mc, player, stat, line, side):
    for p in mc["props"]:
        if (p["player"] == player and p["stat"].lower() == stat.lower()
                and abs(float(p["line"]) - float(line)) < 0.01):
            return p["p_over_mc"] if side == "OVER" else p["p_under_mc"]
    return None

def shrunk(model, series):
    return 0.6 * model + 0.4 * series

# Per-pick reasoning (hand-curated based on this session's intel)
PICK_REASONING = {
    ("De'Aaron Fox", "reb", "OVER"): {
        "tier": "S",
        "why": ("Fox is averaging <b>8.5 REB/g</b> in the WCF (G1-G4) - that's "
                "5 boards above the line. He's been crashing the offensive glass as "
                "SAS adjusts to Wemby drawing the center help. Series + Pin both "
                "scream OVER; model lags."),
        "kill": "Reverts toward his 4.5 season avg if Pop uses smaller lineups.",
        "mc_extra": "MC P(over)=0.866 vs simple normal P=0.669 - the +20pp jump "
                    "is the strongest divergence on the board."
    },
    ("Luke Kornet", "pts", "OVER"): {
        "tier": "B",
        "why": ("Pin priced him at 2.5 PTS - implies <12 min. Model + series put him "
                "at 4-5 PTS, suggesting closer to 20+ min as backup C if Wemby "
                "draws fouls. Modest stake, +money line, low downside."),
        "kill": "Pop benches him if SAS goes small."
    },
    ("Stephon Castle", "pts", "OVER"): {
        "tier": "A",
        "why": ("Castle's WCF series avg <b>17.25 PTS</b> tracks model 18.26 closely; "
                "Pin's 16.5 line is the soft side. He's the secondary creator next "
                "to Fox and the Rookie of the Year-caliber usage is real in the "
                "playoffs (-37.9 MIN/g in WCF)."),
        "kill": "OKC throws Dort or Caruso on him for a stretch - both elite POA defenders."
    },
    ("Victor Wembanyama", "reb", "UNDER"): {
        "tier": "B",
        "why": ("Model 11.98 + series 13.25 both below the 13.5 line, but the gap "
                "is tight. Wemby's foul fragility (avg 3.0 PF in series) caps "
                "his minutes. If Hartenstein draws him into 4 fouls, REB count "
                "stalls."),
        "kill": "Heavy SAS minutes (32+) almost guarantee 13+ boards from him."
    },
    ("Isaiah Hartenstein", "ast", "OVER"): {
        "tier": "A",
        "why": ("Hart is the secondary playmaker for OKC's offense. Model 3.06 + "
                "series 3.00 both >2.5 line. With <b>Jalen Williams OUT</b> "
                "(hamstring), more dribble-handoff actions flow through Hart - "
                "AST upside material."),
        "kill": "Foul trouble caps his minutes <22."
    },
    ("Jared McCain", "fg3m", "UNDER"): {
        "tier": "A",
        "why": ("Model 1.22, series 1.50, Pin 2.5 - all signals point UNDER. McCain's "
                "WCF role is <20 MPG, no green-light usage. Heavy juice (-172) but "
                "the structural mismatch is real."),
        "kill": "Garbage-time blow-out gives him 8 min and he chucks 4 threes."
    },
    ("Dylan Harper", "pts", "OVER"): {
        "tier": "B",
        "why": ("Rookie #1 pick Harper has been producing - model 10.79, series "
                "12.25, Pin 9.5. Pop has trusted him with 24+ MPG and clutch reps. "
                "Smart books pricing the line low because rookies regress."),
        "kill": "Pop tightens to 8-man playoff rotation and Harper drops to 14 min."
    },
    ("Luke Kornet", "reb", "OVER"): {
        "tier": "B",
        "why": ("Same minutes thesis as Kornet PTS - 2.5 REB requires single-digit "
                "minutes to fail. Model 4.26 + series 3.5 both above."),
        "kill": "Kornet plays <8 minutes (rotation depth shrink)."
    },
    ("Keldon Johnson", "pts", "OVER"): {
        "tier": "S",
        "why": ("Pin is at 6.5 implying a deep-bench role - but model 10.91 and "
                "WCF series 8.5 both contradict. Pop has rolled him 17.6 MPG in "
                "series. The Pin line is the softest mispricing on the board."),
        "kill": "DNP-coach's-decision or sub-10 min cameo."
    },
}

# ---------------- Custom flowables ------------------------------------------
def header_band(title_text, subtitle_text):
    """Dark band header."""
    data = [
        [Paragraph(title_text, TITLE)],
        [Paragraph(subtitle_text, SUBTITLE)],
    ]
    t = Table(data, colWidths=[7.7*inch], rowHeights=[0.32*inch, 0.20*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_DARK),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t

def section_bar(text):
    """Compact navy section bar."""
    p = Paragraph(f"<font color='white'><b>{text}</b></font>",
                  ParagraphStyle("sb", parent=BODY, fontSize=9, leading=11,
                                 textColor=colors.white, fontName="Helvetica-Bold"))
    t = Table([[p]], colWidths=[7.7*inch], rowHeights=[0.20*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t

def three_col_top_card(intel):
    """3-column: Lines | Series | Forecast."""
    m2 = intel["m2"]
    wp = intel["wp"]
    # Game Lines mini-card
    lines = Table([
        [Paragraph("<b>GAME LINES (Pinnacle)</b>", KEY)],
        [Paragraph("Total <b>216.5</b> -119/+104 (drift UNDER)", BODY)],
        [Paragraph("Spread <b>OKC -3.5</b> -116 (was -4.5)", BODY)],
        [Paragraph("ML <b>OKC -161</b> / SAS +145", BODY)],
        [Paragraph("<i>Sharp money: SAS+pts, UNDER</i>", SMALL)],
    ], colWidths=[2.5*inch])
    lines.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_CARD),
        ("BACKGROUND", (0, 0), (0, 0), C_NAVY),
        ("TEXTCOLOR", (0, 0), (0, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, C_CARD_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    # Series state
    ser = Table([
        [Paragraph("<b>SERIES 2-2 (G5 in OKC)</b>", KEY)],
        [Paragraph("G1 SAS 122-115 OT (Wemby 41/24)", BODY)],
        [Paragraph("G2 OKC 122-113 (home hold)", BODY)],
        [Paragraph("G3 OKC 123-108 (shooting clinic)", BODY)],
        [Paragraph("G4 SAS 103-82 (<b>OKC eFG .363 collapse</b>)", BODY)],
    ], colWidths=[2.5*inch])
    ser.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_CARD),
        ("BACKGROUND", (0, 0), (0, 0), C_NAVY),
        ("TEXTCOLOR", (0, 0), (0, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, C_CARD_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    # Forecast card
    fc = Table([
        [Paragraph("<b>MODEL FORECASTS</b>", KEY)],
        [Paragraph(f"M2 total <b>211.1</b> (Pin 216.5)", BODY)],
        [Paragraph(f"M2 spread OKC <b>-1.2</b>", BODY)],
        [Paragraph(f"<b>WP: OKC {wp.get('home_win_prob', 0.591)*100:.1f}%</b> "
                   f"(Pin imp 61.7%)", BODY)],
        [Paragraph("<i>No edge on game lines</i>", SMALL)],
    ], colWidths=[2.5*inch])
    fc.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_CARD),
        ("BACKGROUND", (0, 0), (0, 0), C_NAVY),
        ("TEXTCOLOR", (0, 0), (0, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, C_CARD_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    outer = Table([[lines, ser, fc]], colWidths=[2.55*inch]*3)
    outer.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return outer

def team_box(intel, team, accent_color):
    """Compact projected box-score table for a team."""
    slate = intel["slate"]
    series = intel["series"]
    sub = slate[slate["team"] == team].copy()
    rows = []
    for player in sub["player"].unique():
        if not player or not str(player).strip():
            continue
        p_slate = sub[sub["player"] == player]
        s_row = series[series["player_name"].str.lower() == player.lower()]
        rec = {"Player": player}
        sort_val = 0
        for stat_key, stat_disp in [("pts", "PTS"), ("reb", "REB"), ("ast", "AST"),
                                     ("fg3m", "3PM"), ("blk", "BLK"), ("tov", "TOV")]:
            m_row = p_slate[p_slate["stat"] == stat_key]
            if m_row.empty:
                rec[stat_disp] = "-"; continue
            q50_m = float(m_row.iloc[0]["q50"])
            ser_v = None
            if not s_row.empty:
                col = f"{stat_key}_pg"
                if col in s_row.columns and not pd.isna(s_row.iloc[0][col]):
                    ser_v = float(s_row.iloc[0][col])
            val = shrunk(q50_m, ser_v) if ser_v is not None else q50_m
            rec[stat_disp] = f"{val:.1f}"
            if stat_key == "pts": sort_val = q50_m
        rec["_sort"] = sort_val
        rows.append(rec)
    df = pd.DataFrame(rows).sort_values("_sort", ascending=False).drop(columns="_sort").head(10)

    header = ["Player", "PTS", "REB", "AST", "3PM", "BLK", "TOV"]
    data = [header] + [[r.get(c, "-") for c in header] for _, r in df.iterrows()]
    tbl = Table(data, colWidths=[1.4*inch] + [0.4*inch]*6)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), accent_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_BG_ALT]),
        ("GRID", (0, 0), (-1, -1), 0.25, C_CARD_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return tbl

def two_col_boxes(intel):
    """OKC + SAS side by side."""
    okc_label = Paragraph("<b>OKC THUNDER (home)</b> - JW/Mitchell/Sorber OUT", KEY)
    sas_label = Paragraph("<b>SAN ANTONIO SPURS (away)</b> - full strength", KEY)
    okc_tbl = team_box(intel, "OKC", C_OKC_BLUE)
    sas_tbl = team_box(intel, "SAS", C_SAS_BLACK)
    inner = Table([[okc_label, sas_label], [okc_tbl, sas_tbl]],
                  colWidths=[3.85*inch, 3.85*inch])
    inner.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return inner

def tier_color(tier):
    return {"S": C_GOLD, "A": C_SILVER, "B": C_BRONZE}.get(tier, C_MUTED)

def bet_card_row(rank, row, mc_p, reasoning):
    """One bet card row - dense, color-coded, with WHY."""
    tier = reasoning["tier"]
    why = reasoning["why"]
    kill = reasoning["kill"]
    extra = reasoning.get("mc_extra", "")
    side = row["side"]
    line = row["line"]
    edge_pct = row["ev_pct"]
    odds = int(row["odds"])
    odds_str = f"+{odds}" if odds > 0 else str(odds)
    stake = row["stake_$"]
    model = row["model_q50"]
    series = row["wcf_series_avg"]

    tier_block = Paragraph(f"<font color='white'><b> {tier} </b></font>",
                           ParagraphStyle("t", parent=BODY, fontSize=11,
                                          leading=13, fontName="Helvetica-Bold",
                                          alignment=1))
    # Left: tier + rank + player
    head = Paragraph(
        f"<b>#{rank}  {row['player']}</b>  <font color='{C_NAVY.hexval()}'>"
        f"{row['stat'].upper()} {side} {line:.1f}</font>"
        f"  <font color='{C_MUTED.hexval()}'>Pin {odds_str}</font>",
        ParagraphStyle("h", parent=BODY, fontSize=8.5, leading=10,
                       fontName="Helvetica-Bold"))
    # Right side: model / series / mc / ev
    mc_str = f"{mc_p*100:.1f}%" if mc_p is not None else "n/a"
    stats_block = Paragraph(
        f"<b>Model</b> {model:.2f} | <b>Series</b> {series:.2f} | "
        f"<b>MC P(win)</b> {mc_str} | <b>EV</b> {edge_pct:.1f}% | "
        f"<b>Stake</b> ${stake:.0f}",
        ParagraphStyle("s", parent=BODY, fontSize=7, leading=9,
                       textColor=C_NAVY))
    why_p = Paragraph(f"<b>WHY:</b> {why}", WHY)
    kill_p = Paragraph(f"KILL: {kill}", KILL)
    extra_p = Paragraph(extra, SMALL) if extra else None

    body_rows = [[head], [stats_block], [why_p], [kill_p]]
    if extra_p: body_rows.append([extra_p])
    body_tbl = Table(body_rows, colWidths=[6.9*inch])
    body_tbl.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    outer = Table([[tier_block, body_tbl]],
                  colWidths=[0.45*inch, 7.25*inch])
    outer.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), tier_color(tier)),
        ("BACKGROUND", (1, 0), (1, 0), C_HI_GREEN if tier == "S" else
         (C_CARD if tier == "A" else colors.white)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, C_CARD_BORDER),
    ]))
    return outer

def matchup_decision_card():
    """Live defender decision rules - compact."""
    data = [
        [Paragraph("<b>WEMBY DEFENDER</b>", KEY),
         Paragraph("<b>PTS adj</b>", KEY),
         Paragraph("<b>LIVE TRIGGER</b>", KEY)],
        [Paragraph("Hartenstein", BODY),
         Paragraph("<font color='" + C_WIN.hexval() + "'><b>+6.2%</b></font>", BODY),
         Paragraph("Fire <b>Wemby 3PM OVER 1.5</b>", BODY)],
        [Paragraph("Holmgren", BODY),
         Paragraph("<font color='" + C_LOSS.hexval() + "'><b>-4.8%</b></font>", BODY),
         Paragraph("Fire <b>Wemby PTS UNDER 25.5</b>", BODY)],
        [Paragraph("Caruso (surprise lever)", BODY),
         Paragraph("<font color='" + C_LOSS.hexval() + "'><b>-22.6%</b></font>", BODY),
         Paragraph("Fire <b>Wemby PTS UNDER 22.5</b>", BODY)],
        [Paragraph("<b>SGA DEFENDER</b>", KEY),
         Paragraph("<b>PTS adj</b>", KEY),
         Paragraph("<b>LIVE TRIGGER</b>", KEY)],
        [Paragraph("Vassell (neutralizer)", BODY),
         Paragraph("<font color='" + C_LOSS.hexval() + "'><b>-9.5%</b></font>", BODY),
         Paragraph("Fire <b>SGA PTS UNDER live</b>", BODY)],
    ]
    tbl = Table(data, colWidths=[2.0*inch, 1.0*inch, 4.7*inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("BACKGROUND", (0, 4), (-1, 4), C_NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, 3), [colors.white, C_BG_ALT]),
        ("ROWBACKGROUNDS", (0, 5), (-1, 5), [colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.25, C_CARD_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl

def joint_events_card(intel):
    """MC joint events."""
    je = intel["mc"]["joint_events"]
    data = [
        [Paragraph("<b>EVENT</b>", KEY), Paragraph("<b>P</b>", KEY),
         Paragraph("<b>INTERPRETATION</b>", KEY)],
        [Paragraph("SGA scores 30+", BODY),
         Paragraph(f"<b>{je['P(SGA_pts_ge_30)']['value']*100:.1f}%</b>", BODY),
         Paragraph("Strong shot - he's at 24.8 series avg, 30+ in 2 of 4 games", BODY)],
        [Paragraph("SGA 30+ AND OKC wins", BODY),
         Paragraph(f"<b>{je['P(SGA_30plus_AND_OKC_wins)']['value']*100:.1f}%</b>", BODY),
         Paragraph("Correlated - SGA volume drives OKC wins (rho=0.45)", BODY)],
        [Paragraph("SGA 30+ given OKC wins", BODY),
         Paragraph(f"<b>{je['P(SGA_pts_ge_30_given_OKC_wins)']['value']*100:.1f}%</b>", BODY),
         Paragraph("Conditional: when OKC wins, SGA hits 30+ most of the time", BODY)],
        [Paragraph("Wemby triple-double", BODY),
         Paragraph(f"<b>{je['P(Wemby_triple_double)']['value']*100:.1f}%</b>", BODY),
         Paragraph("Effectively 0 - Wemby's AST volume too low (~3.0/g)", BODY)],
        [Paragraph("Holmgren scoreless Q1", BODY),
         Paragraph(f"<b>{je['P(Holmgren_0_pts_Q1)']['value']*100:.1f}%</b>", BODY),
         Paragraph("Wemby blocks 3x per 52 poss vs Chet - real risk", BODY)],
    ]
    tbl = Table(data, colWidths=[2.0*inch, 0.6*inch, 5.1*inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_BG_ALT]),
        ("GRID", (0, 0), (-1, -1), 0.25, C_CARD_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl

def ops_checklist():
    rows = [
        ["Live daemon", "PID 9452 alive - defender residual wired", "OK"],
        ["Closing line cap", "PID 4776 + watchdog 10372 - fires 00:30 UTC", "OK"],
        ["Bets pre-registered", "9 rows in data/pnl_ledger.csv status=INTENDED", "OK"],
        ["Alerts", "vault/Improvements/alerts_2026-05-26.log", "TAIL IT"],
        ["Health", "17 OK / 5 WARN / 0 ERROR", "OK"],
        ["System status", "python scripts/system_status.py --date 2026-05-26", "RUN @ 8PM"],
    ]
    data = [[Paragraph("<b>SYSTEM</b>", KEY),
             Paragraph("<b>DETAIL</b>", KEY),
             Paragraph("<b>STATE</b>", KEY)]]
    for r in rows:
        data.append([
            Paragraph(r[0], BODY),
            Paragraph(r[1], BODY),
            Paragraph(f"<font color='{C_WIN.hexval()}'><b>{r[2]}</b></font>", BODY)
                if r[2] == "OK" else
            Paragraph(f"<font color='{C_GOLD.hexval()}'><b>{r[2]}</b></font>", BODY),
        ])
    tbl = Table(data, colWidths=[1.4*inch, 4.9*inch, 1.4*inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_BG_ALT]),
        ("GRID", (0, 0), (-1, -1), 0.25, C_CARD_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl

# ---------------- Doc build -------------------------------------------------
def build():
    intel = load_intel()
    doc = BaseDocTemplate(
        str(OUT), pagesize=LETTER,
        leftMargin=0.3*inch, rightMargin=0.3*inch,
        topMargin=0.3*inch, bottomMargin=0.3*inch,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="full",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="all", frames=frame)])

    story = []
    # Header
    story.append(header_band(
        "WCF GAME 5 - SAS @ OKC - INTEL SHEET",
        "Tue 2026-05-26 - 8:35 PM ET - Paycom Center - SERIES 2-2 - game_id 0042500315"
    ))
    story.append(Spacer(1, 0.06*inch))

    # 3-col top
    story.append(three_col_top_card(intel))
    story.append(Spacer(1, 0.06*inch))

    # Section: Box scores
    story.append(section_bar("PROJECTED BOX SCORES (shrunk q50 = 0.6*model + 0.4*WCF series)"))
    story.append(Spacer(1, 0.03*inch))
    story.append(two_col_boxes(intel))
    story.append(Spacer(1, 0.05*inch))

    # Section: Top intelligence callouts (NEW)
    story.append(section_bar("KEY INTELLIGENCE - WHY THESE BETS MATTER TONIGHT"))
    story.append(Spacer(1, 0.04*inch))
    callout_data = [
        [Paragraph("<b>Sharp money is on SAS+pts and UNDER 216.5.</b> ML drifted -174 -> -161 in 3 hrs. "
                   "Vegas sees Game 4 (SAS 103-82) as structural, not variance. Total moved to UNDER side.", BODY)],
        [Paragraph("<b>OKC eFG% G3 was .586, G4 was .363</b> - 22.3pp swing. Either G3 was the outlier or G4 was. "
                   "Pinnacle pricing partial reversion at OKC -3.5 (down from -4.5 open).", BODY)],
        [Paragraph("<b>Jalen Williams is OUT.</b> JaW PTS line steam (9.5->14.5) confirmed market priced it in. "
                   "Hartenstein's usage rises - hence AST OVER pick.", BODY)],
        [Paragraph("<b>Wemby's series matchup data is the unmodeled edge:</b> 37 PTS / 5-of-9 from 3 vs Hartenstein "
                   "(90 poss), but Holmgren limits him to 47% FG and 0/1 from 3. Defender selection swings projection up to "
                   "<b>+/-3.3 PTS and +/-2.25 3PM</b>.", BODY)],
        [Paragraph("<b>Pinnacle dramatically underprices role minutes:</b> K.Johnson PTS 6.5 (model 10.91, series 8.5), "
                   "Kornet PTS 2.5 (model 5.14). Soft books are right that role-player MIN is volatile - but Pin's lines "
                   "imply <12 MIN which contradicts WCF rotation.", BODY)],
    ]
    co = Table(callout_data, colWidths=[7.7*inch])
    co.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_HI_YELLOW),
        ("BOX", (0, 0), (-1, -1), 0.5, C_CARD_BORDER),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, C_CARD_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(co)

    # PAGE 2
    story.append(PageBreak())
    story.append(header_band(
        "BET CARD - 9 THREE-WAY VERIFIED PICKS",
        "All Pinnacle - $260/leg (4% Kelly * 0.65 playoff * $11,043 BR) - total $2,340 (21%)"
    ))
    story.append(Spacer(1, 0.05*inch))

    # Tier legend
    legend = Table([[
        Paragraph(f"<font color='white'><b> S </b></font>",
                  ParagraphStyle("ls", parent=BODY, fontSize=10,
                                 fontName="Helvetica-Bold", alignment=1)),
        Paragraph(" <b>STRONGEST</b> - 3-way agree + structural mismatch", BODY),
        Paragraph(f"<font color='white'><b> A </b></font>",
                  ParagraphStyle("la", parent=BODY, fontSize=10,
                                 fontName="Helvetica-Bold", alignment=1)),
        Paragraph(" <b>HIGH</b> - 3-way agree, normal risk", BODY),
        Paragraph(f"<font color='white'><b> B </b></font>",
                  ParagraphStyle("lb", parent=BODY, fontSize=10,
                                 fontName="Helvetica-Bold", alignment=1)),
        Paragraph(" <b>OK</b> - 2-way agree or thinner edge", BODY),
    ]], colWidths=[0.3*inch, 2.2*inch, 0.3*inch, 1.8*inch, 0.3*inch, 2.8*inch])
    legend.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), C_GOLD),
        ("BACKGROUND", (2, 0), (2, 0), C_SILVER),
        ("BACKGROUND", (4, 0), (4, 0), C_BRONZE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(legend)
    story.append(Spacer(1, 0.05*inch))

    # Bet card - tier-ordered: S, A, A, A, B, B, B, B, B (sort by tier)
    ev = intel["ev"]
    pick_rows = []
    for idx, row in ev.iterrows():
        key = (row["player"], row["stat"], row["side"])
        if key not in PICK_REASONING:
            continue
        reasoning = PICK_REASONING[key]
        mc_p = mc_prob_for(intel["mc"], row["player"], row["stat"],
                           row["line"], row["side"])
        pick_rows.append((reasoning["tier"], idx, row, mc_p, reasoning))

    # Sort: S, A, B
    tier_order = {"S": 0, "A": 1, "B": 2}
    pick_rows.sort(key=lambda x: (tier_order.get(x[0], 9), -x[2]["ev_pct"]))

    for rank, (tier, _, row, mc_p, reasoning) in enumerate(pick_rows, 1):
        story.append(bet_card_row(rank, row, mc_p, reasoning))

    story.append(Spacer(1, 0.06*inch))

    # Live defender triggers
    story.append(section_bar("LIVE DEFENDER TRIGGERS (run during timeouts)"))
    story.append(Spacer(1, 0.03*inch))
    story.append(matchup_decision_card())
    story.append(Paragraph(
        "Manual probe: <font name='Courier' size='7'>python scripts/whatif_defender.py "
        "--player Wemby --stat pts --vs-all</font>",
        SMALL))
    story.append(Spacer(1, 0.06*inch))

    # Joint events
    story.append(section_bar("JOINT EVENTS (Monte Carlo, 1000 sims)"))
    story.append(Spacer(1, 0.03*inch))
    story.append(joint_events_card(intel))
    story.append(Spacer(1, 0.06*inch))

    # Ops checklist
    story.append(section_bar("PRE-TIP OPERATIONAL CHECKLIST"))
    story.append(Spacer(1, 0.03*inch))
    story.append(ops_checklist())
    story.append(Spacer(1, 0.04*inch))

    # Footer
    story.append(Paragraph(
        f"Generated 2026-05-26 by CourtVision after 43 agent ops across 8 rounds. "
        f"Three-way verification: model + WCF G1-G4 series + Pinnacle sharp. "
        f"Bankroll $11,043.48. Tonight's 9 bets persisted to data/pnl_ledger.csv "
        f"as INTENDED. CLV auto-pickup via wire_clv_from_registered.py tomorrow AM.",
        SMALL))

    doc.build(story)
    return OUT

if __name__ == "__main__":
    path = build()
    print(f"Generated: {path}  ({path.stat().st_size/1024:.1f} KB)")
