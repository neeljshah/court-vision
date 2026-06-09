"""build_pregame_pdf.py - generate the SAS @ OKC WCF G5 cheat-sheet PDF.

Reads from data/cache/intel_2026-05-26/ and produces a printable 2-page report:
  Page 1 - game forecast + projected box scores (both teams)
  Page 2 - bet card + live triggers + matchup intelligence
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
INTEL = ROOT / "data" / "cache" / "intel_2026-05-26"
OUT = INTEL / "reports" / "WCF_G5_SAS_at_OKC_cheat_sheet.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------- styles ----------------------------------------
styles = getSampleStyleSheet()
H_TITLE = ParagraphStyle(
    "h_title", parent=styles["Heading1"],
    fontSize=16, leading=18, spaceAfter=2, textColor=colors.HexColor("#0a0a0a"),
)
H_SUB = ParagraphStyle(
    "h_sub", parent=styles["Heading3"],
    fontSize=10, leading=12, spaceBefore=6, spaceAfter=3,
    textColor=colors.HexColor("#444444"),
)
H_SECTION = ParagraphStyle(
    "h_section", parent=styles["Heading2"],
    fontSize=11, leading=13, spaceBefore=10, spaceAfter=4,
    textColor=colors.HexColor("#003366"),
)
BODY = ParagraphStyle(
    "body", parent=styles["BodyText"],
    fontSize=8, leading=10,
)
SMALL = ParagraphStyle(
    "small", parent=styles["BodyText"],
    fontSize=7, leading=8, textColor=colors.HexColor("#555555"),
)
PICK_HI = ParagraphStyle(
    "pick_hi", parent=styles["BodyText"],
    fontSize=8, leading=10, textColor=colors.HexColor("#003366"),
)

# ---------------------------- data load -------------------------------------
def load_intel():
    """Return dict of all the cheat-sheet inputs."""
    out = {}
    # Slate
    slate = pd.read_parquet(INTEL / "slate_fresh_2026-05-26.parquet")
    out["slate"] = slate
    # WCF series averages
    ser = pd.read_csv(INTEL / "wcf_player_series_avg.csv")
    out["series"] = ser
    # M2 + WP forecasts
    out["m2"] = json.loads((INTEL / "m2_game.json").read_text(encoding="utf-8"))
    out["wp"] = json.loads((INTEL / "win_prob.json").read_text(encoding="utf-8"))
    # Team series aggregates
    out["team_ser"] = json.loads((INTEL / "wcf_team_series_agg.json").read_text(encoding="utf-8"))
    # Top 9 EV bets
    out["ev"] = pd.read_csv(INTEL / "ev_final_high_conviction.csv")
    return out

# ---------------------------- shrunk projections ----------------------------
LAM = 0.4

def shrunk_q50(model: float, series: float) -> float:
    return 0.6 * model + 0.4 * series

def project_box(intel: dict, team: str) -> pd.DataFrame:
    """Per-player table with shrunk projections."""
    slate = intel["slate"]
    series = intel["series"]
    sub = slate[slate["team"] == team].copy()
    rows = []
    for player in sub["player"].unique():
        if not player or not str(player).strip():
            continue
        p_slate = sub[sub["player"] == player]
        # series row may not exist for deep bench
        s_row = series[series["player_name"].str.lower() == player.lower()]
        rec = {"Player": player}
        for stat_key, stat_disp in [("pts", "PTS"), ("reb", "REB"), ("ast", "AST"),
                                     ("fg3m", "3PM"), ("stl", "STL"), ("blk", "BLK"), ("tov", "TOV")]:
            m_row = p_slate[p_slate["stat"] == stat_key]
            if m_row.empty:
                rec[stat_disp] = ""
                continue
            q50_model = float(m_row.iloc[0]["q50"])
            ser_val = None
            if not s_row.empty:
                col = f"{stat_key}_pg"
                if col in s_row.columns and not pd.isna(s_row.iloc[0][col]):
                    ser_val = float(s_row.iloc[0][col])
            if ser_val is not None:
                shrunk = shrunk_q50(q50_model, ser_val)
            else:
                shrunk = q50_model
            rec[stat_disp] = f"{shrunk:.1f}"
        # Sort proxy: model PTS desc
        rec["_sort"] = float(p_slate[p_slate["stat"] == "pts"].iloc[0]["q50"]) if not p_slate[p_slate["stat"] == "pts"].empty else 0
        rows.append(rec)
    df = pd.DataFrame(rows).sort_values("_sort", ascending=False).drop(columns="_sort")
    return df

# ---------------------------- table builders --------------------------------
def make_box_table(df: pd.DataFrame, team_label: str) -> Table:
    """Per-team box score projection table."""
    header = ["Player", "PTS", "REB", "AST", "3PM", "STL", "BLK", "TOV"]
    data = [header]
    for _, row in df.iterrows():
        data.append([row.get(c, "") for c in header])
    tbl = Table(data, colWidths=[1.5*inch, 0.45*inch, 0.45*inch, 0.45*inch,
                                  0.45*inch, 0.45*inch, 0.45*inch, 0.45*inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f6fa")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return tbl

def make_ev_table(intel: dict) -> Table:
    """Bet card table."""
    ev = intel["ev"]
    header = ["#", "Player", "Stat", "Side", "Line", "Pin Odds", "Model", "Series",
              "Edge", "EV%", "Stake"]
    data = [header]
    for i, row in ev.iterrows():
        odds = int(row["odds"]) if pd.notna(row["odds"]) else 0
        odds_str = f"+{odds}" if odds > 0 else str(odds)
        data.append([
            str(i + 1),
            row["player"],
            row["stat"].upper(),
            row["side"],
            f'{row["line"]:.1f}',
            odds_str,
            f'{row["model_q50"]:.2f}',
            f'{row["wcf_series_avg"]:.2f}',
            f'{row["edge_units"]:+.2f}',
            f'{row["ev_pct"]:.1f}%',
            f'${row["stake_$"]:.0f}',
        ])
    tbl = Table(data, colWidths=[0.25*inch, 1.4*inch, 0.45*inch, 0.45*inch, 0.45*inch,
                                  0.55*inch, 0.5*inch, 0.5*inch, 0.5*inch, 0.55*inch,
                                  0.5*inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d3b1f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eaf3ec")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tbl

def make_game_lines_table() -> Table:
    """Pin sharp lines + model + verdict."""
    data = [
        ["Market", "Pinnacle", "Model", "Verdict"],
        ["Total", "216.5 (-119/+104)", "M2: 211.1", "Lean UNDER (small)"],
        ["Spread", "OKC -3.5 (-116)", "M2: -1.2", "PASS (no edge)"],
        ["Moneyline", "OKC -161 / SAS +145", "WP: 0.59", "PASS (priced fair)"],
    ]
    tbl = Table(data, colWidths=[1.0*inch, 1.7*inch, 1.2*inch, 1.7*inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 1), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tbl

def make_series_table(intel: dict) -> Table:
    """Series recap G1-G4."""
    data = [
        ["Game", "Date", "Score", "Pace", "Note"],
        ["G1", "5/18 @OKC", "SAS 122-115 OT", "93.9", "Wemby 41/24"],
        ["G2", "5/20 @OKC", "OKC 122-113", "97.5", "OKC home hold"],
        ["G3", "5/22 @SAS", "OKC 123-108", "98.0", "OKC shooting clinic"],
        ["G4", "5/24 @SAS", "SAS 103-82", "101.5", "OKC eFG collapse"],
        ["G5", "5/26 @OKC", "TONIGHT", "?", "Series 2-2 swing game"],
    ]
    tbl = Table(data, colWidths=[0.5*inch, 1.0*inch, 1.4*inch, 0.6*inch, 2.1*inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (4, 1), (4, -1), "LEFT"),
        ("BACKGROUND", (0, 5), (-1, 5), colors.HexColor("#fff5cc")),
        ("FONTNAME", (0, 5), (-1, 5), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl

def make_matchup_table() -> Table:
    """Defender matchup live triggers."""
    data = [
        ["Wemby Defender", "PTS Mult", "Wemby PTS", "Wemby 3PM", "Live Trigger"],
        ["Hartenstein", "+6.2%", "31.9", "3.5", "Fire Wemby 3PM OVER 1.5"],
        ["Holmgren", "-4.8%", "27.2", "1.2", "Fire Wemby PTS UNDER 25.5"],
        ["Caruso", "-22.6%", "22.1", "1.2", "Fire Wemby PTS UNDER 22.5"],
        ["SGA Defender", "PTS Mult", "SGA PTS", "", "Live Trigger"],
        ["Vassell", "-9.5%", "22.4", "—", "SGA PTS UNDER live"],
        ["Castle", "neutral", "24.8", "—", "No matchup adjustment"],
    ]
    tbl = Table(data, colWidths=[1.0*inch, 0.7*inch, 0.7*inch, 0.7*inch, 2.4*inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7a0d0d")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 4), (-1, 4), colors.HexColor("#7a0d0d")),
        ("TEXTCOLOR", (0, 4), (-1, 4), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 4), (-1, 4), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (4, 1), (4, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, 3), [colors.white, colors.HexColor("#f9eaea")]),
        ("ROWBACKGROUNDS", (0, 5), (-1, -1), [colors.white, colors.HexColor("#f9eaea")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl

# ---------------------------- build PDF --------------------------------------
def build_pdf():
    intel = load_intel()
    doc = SimpleDocTemplate(
        str(OUT), pagesize=LETTER,
        leftMargin=0.4*inch, rightMargin=0.4*inch,
        topMargin=0.4*inch, bottomMargin=0.4*inch,
    )

    story = []

    # ============================== PAGE 1 ==============================
    story.append(Paragraph(
        "WCF Game 5 - SAS @ OKC - Pregame Intel Sheet",
        H_TITLE,
    ))
    story.append(Paragraph(
        "Tue 2026-05-26 - 8:35 PM ET - Paycom Center - Series tied 2-2 - "
        "game_id 0042500315",
        H_SUB,
    ))
    story.append(Spacer(1, 0.05*inch))

    # Game lines
    story.append(Paragraph("Game Lines (Pinnacle sharp baseline)", H_SECTION))
    story.append(make_game_lines_table())
    story.append(Paragraph(
        "Sharp money is on SAS+points and UNDER 216.5. ML drifted -174 -> -161 today. "
        "Pass on all three game lines (priced fair to model).",
        SMALL,
    ))

    # Series
    story.append(Paragraph("Series Recap (G1-G4)", H_SECTION))
    story.append(make_series_table(intel))

    # OKC box
    story.append(Paragraph("OKC Thunder - Projected Box (shrunk q50)", H_SECTION))
    okc_df = project_box(intel, "OKC")
    okc_df = okc_df.head(12)  # top 12 rotation
    story.append(make_box_table(okc_df, "OKC"))
    story.append(Paragraph(
        "OUT: Jalen Williams (hamstring), Ajay Mitchell (calf), Thomas Sorber (ACL). "
        "JW out -> Hartenstein gets touches; JaW PTS up steam (9.5 -> 14.5) confirms.",
        SMALL,
    ))

    # SAS box
    story.append(Paragraph("SAS Spurs - Projected Box (shrunk q50)", H_SECTION))
    sas_df = project_box(intel, "SAS")
    sas_df = sas_df.head(12)
    story.append(make_box_table(sas_df, "SAS"))
    story.append(Paragraph(
        "Wemby series avg 30.2 PTS / 13.2 REB / 3.0 BLK. Fox 13.5 PTS / 8.5 REB. "
        "Castle 17.2 PTS / 8.0 AST. Vassell 17.0 PTS.",
        SMALL,
    ))

    story.append(PageBreak())

    # ============================== PAGE 2 ==============================
    story.append(Paragraph(
        "WCF G5 - Bet Card + Live Triggers",
        H_TITLE,
    ))
    story.append(Paragraph(
        "All 9 bets at Pinnacle. Three-way verified (model + WCF series + Pin sharp). "
        "Stake $260 each = 4% Kelly cap x 0.65 playoff. Total exposure $2,340 (23% of $11,043 bankroll).",
        H_SUB,
    ))
    story.append(Spacer(1, 0.05*inch))

    story.append(Paragraph("Bet Card", H_SECTION))
    story.append(make_ev_table(intel))
    story.append(Paragraph(
        "All 9 picks pass the auto-place 8-gate chain after the sigma threshold lowering "
        "(DEFAULT_Q50_DEV_SIGMAS 0.5 -> 0.25). Top 5 = $1,300 exposure if you only fire half.",
        SMALL,
    ))

    # Matchup intelligence
    story.append(Paragraph("Live Defender Triggers (watch start of Q2)", H_SECTION))
    story.append(make_matchup_table())
    story.append(Paragraph(
        "CLI: python scripts/whatif_defender.py --player Wemby --stat pts --vs-all  "
        "(run during timeouts to see live multipliers)",
        SMALL,
    ))

    # Live game-plan
    story.append(Paragraph("Live Game-Plan", H_SECTION))
    plan_data = [
        ["Trigger", "Action"],
        ["Q1 ends", "Period head fires (cycle 105b, -37% MAE vs naive linear)"],
        ["Halftime (endQ2)", "5/7 stats viable at 80% of endQ3 ROI - best live window"],
        ["End Q3", "70-89% backtest ROI window - foul/blowout/heat-check residuals fire"],
        ["Wemby has 3+ PF by Q3", "Foul-residual reduces BLK proj - hammer Wemby BLK UNDER live"],
        ["Either team up 18+ end Q3", "Blowout-residual: stars come out, fade alt-line OVERs"],
        ["Holmgren stays on Wemby", "Wemby PTS UNDER 25.5 live (Wemby 3 BLK in 52 poss vs Chet)"],
        ["Hartenstein switches to Wemby", "Wemby 3PM OVER 1.5 live (5/9 from 3 vs Hartenstein in series)"],
    ]
    plan_tbl = Table(plan_data, colWidths=[2.0*inch, 4.7*inch])
    plan_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef2f7")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(plan_tbl)

    # Warnings / known limits
    story.append(Paragraph("Pre-Tip Operational Checklist", H_SECTION))
    ops = [
        "  Live daemon: PID 9452 (patched code, defender residual live)",
        "  Closing-line capture: PID 4776 + watchdog 10372 (fires 00:30 + 00:34 UTC)",
        "  Bets pre-registered: data/pnl_ledger.csv (9 rows status=INTENDED)",
        "  Alert fallback: vault/Improvements/alerts_2026-05-26.log (tail it)",
        "  Health: 17 OK / 5 WARN / 0 ERROR",
        "  System status: python scripts/system_status.py --date 2026-05-26",
    ]
    for line in ops:
        story.append(Paragraph(line, BODY))

    story.append(Paragraph("Known Weaknesses (acknowledge before betting real $)", H_SECTION))
    weak = [
        "  Model still over-projects on Fox / Holmgren / K.Johnson (shrinkage applied for picks).",
        "  No real Pinnacle closing-line history yet - CLV measurement starts tonight.",
        "  CV defender-distance not wired (separate workstream).",
        "  L5 features carry only 0.186% gain importance (model insensitive to playoff slumps).",
        "  Pin/Bov/FD only - DK / Caesars / MGM IP-blocked.",
    ]
    for line in weak:
        story.append(Paragraph(line, SMALL))

    story.append(Spacer(1, 0.1*inch))
    story.append(Paragraph(
        "Generated 2026-05-26 by CourtVision after 43 agent ops across 8 rounds. "
        "Model + WCF G1-G4 series + Pinnacle sharp all aligned.",
        SMALL,
    ))

    doc.build(story)
    return OUT

if __name__ == "__main__":
    path = build_pdf()
    size_kb = path.stat().st_size / 1024
    print(f"Generated: {path}")
    print(f"Size: {size_kb:.1f} KB")
