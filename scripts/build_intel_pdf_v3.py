"""build_intel_pdf_v3.py — magazine-grade WCF G5 intel brief (v3).

Dark-luxe visual system, denser live in-game playbook, no ops checklist.
Output: data/cache/intel_2026-05-26/reports/WCF_G5_intel_V3.pdf
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, KeepTogether, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)
from reportlab.platypus.flowables import HRFlowable, Flowable

ROOT = Path(__file__).resolve().parent.parent
INTEL = ROOT / "data" / "cache" / "intel_2026-05-26"
OUT = INTEL / "reports" / "WCF_G5_intel_V3.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

# ============================================================
# Dark-luxe color system
# ============================================================
C_INK         = colors.HexColor("#0a1628")
C_INK_DEEP    = colors.HexColor("#060d1a")
C_NAVY        = colors.HexColor("#0c2340")
C_NAVY_MID    = colors.HexColor("#13294b")
C_NAVY_SOFT   = colors.HexColor("#1e3a5f")
C_OKC         = colors.HexColor("#007ac1")
C_OKC_DEEP    = colors.HexColor("#003c70")
C_OKC_ACCENT  = colors.HexColor("#ef6c00")
C_SAS         = colors.HexColor("#2c2c2c")
C_SAS_LIGHT   = colors.HexColor("#7d8085")
C_GOLD        = colors.HexColor("#d4a017")
C_GOLD_DEEP   = colors.HexColor("#a77f0a")
C_GOLD_SOFT   = colors.HexColor("#fff3cd")
C_GREEN       = colors.HexColor("#10b981")
C_GREEN_DEEP  = colors.HexColor("#047857")
C_GREEN_SOFT  = colors.HexColor("#d1fae5")
C_RED         = colors.HexColor("#dc2626")
C_RED_DEEP    = colors.HexColor("#991b1b")
C_RED_SOFT    = colors.HexColor("#fee2e2")
C_LIVE        = colors.HexColor("#ef4444")
C_BLUE        = colors.HexColor("#2563eb")
C_PURPLE      = colors.HexColor("#7c3aed")
C_GRAY_50     = colors.HexColor("#fafbfc")
C_GRAY_100    = colors.HexColor("#f1f5f9")
C_GRAY_200    = colors.HexColor("#e2e8f0")
C_GRAY_300    = colors.HexColor("#cbd5e1")
C_GRAY_400    = colors.HexColor("#94a3b8")
C_GRAY_500    = colors.HexColor("#64748b")
C_GRAY_600    = colors.HexColor("#475569")
C_GRAY_700    = colors.HexColor("#334155")

# Matplotlib color tokens
M_INK    = "#0a1628"
M_NAVY   = "#0c2340"
M_OKC    = "#007ac1"
M_SAS    = "#2c2c2c"
M_GOLD   = "#d4a017"
M_GREEN  = "#10b981"
M_RED    = "#dc2626"
M_GRAY   = "#94a3b8"
M_GRID   = "#e2e8f0"
M_LIVE   = "#ef4444"

# ============================================================
# Load data
# ============================================================
m2 = json.loads((INTEL / "m2_game.json").read_text())
wp = json.loads((INTEL / "win_prob.json").read_text())
mc = json.loads((INTEL / "mc_tonight.json").read_text())
bets = json.loads((INTEL / "tonight_bets_registered.json").read_text())
team_agg = json.loads((INTEL / "wcf_team_series_agg.json").read_text())
player_series = pd.read_csv(INTEL / "wcf_player_series_avg.csv")
steam = pd.read_csv(INTEL / "steam_moves.csv")
def_match = pd.read_csv(INTEL / "wcf_defensive_matchups.csv")
middles = pd.read_csv(INTEL / "valid_middles.csv")

MARKET = {
    "total": 216.5, "total_o_price": -119, "total_u_price": 104,
    "spread_home": -3.5, "spread_home_price": -116,
    "ml_home": -161, "ml_away": 145,
}
BR = 11043.48

# ============================================================
# Styles
# ============================================================
H1_DARK   = ParagraphStyle("H1D", fontName="Helvetica-Bold", fontSize=28, leading=32,
                            textColor="white", spaceAfter=0)
H1_DARK_SM = ParagraphStyle("H1DS", fontName="Helvetica-Bold", fontSize=22, leading=26,
                             textColor="white", spaceAfter=0)
H1        = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=24, leading=28,
                            textColor=C_INK, spaceAfter=2)
H2        = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=14, leading=16,
                            textColor=C_INK, spaceAfter=2)
SUB       = ParagraphStyle("SUB", fontName="Helvetica", fontSize=10, leading=12,
                            textColor=C_GRAY_500, spaceAfter=2)
SUB_WHITE = ParagraphStyle("SUBW", fontName="Helvetica", fontSize=10, leading=12,
                            textColor=C_GRAY_200, spaceAfter=2)
BODY      = ParagraphStyle("BODY", fontName="Helvetica", fontSize=8.5, leading=11,
                            textColor=C_INK)
BODY_SM   = ParagraphStyle("BODYSM", fontName="Helvetica", fontSize=7.8, leading=10,
                            textColor=C_INK)
BODY_WHITE = ParagraphStyle("BODYW", fontName="Helvetica", fontSize=8.5, leading=11,
                             textColor="white")
SMALL     = ParagraphStyle("SMALL", fontName="Helvetica", fontSize=7.2, leading=9,
                            textColor=C_GRAY_500)
SMALL_GOLD = ParagraphStyle("SMALLG", fontName="Helvetica-Bold", fontSize=7.2, leading=9,
                             textColor=C_GOLD)
LABEL     = ParagraphStyle("LBL", fontName="Helvetica-Bold", fontSize=7.5, leading=9,
                            textColor=C_GRAY_500)
LABEL_WHITE = ParagraphStyle("LBLW", fontName="Helvetica-Bold", fontSize=7.5, leading=9,
                              textColor=C_GRAY_200)
BIG_NUM   = ParagraphStyle("BIG", fontName="Helvetica-Bold", fontSize=24, leading=26,
                            textColor=C_INK)
HUGE_NUM  = ParagraphStyle("HUGE", fontName="Helvetica-Bold", fontSize=34, leading=36,
                            textColor="white")
SECTION_GOLD = ParagraphStyle(
    "SG", fontName="Helvetica-Bold", fontSize=10, leading=12,
    textColor=C_GOLD, spaceBefore=4, spaceAfter=2,
)

def section_band(label, *, accent=C_GOLD):
    return Paragraph(
        f"<font color='white'>{label}</font>",
        ParagraphStyle("SB", fontName="Helvetica-Bold", fontSize=11,
                        textColor="white", backColor=C_INK, leftIndent=10,
                        rightIndent=10, spaceBefore=4, spaceAfter=2,
                        borderPadding=(6, 8, 6, 8),
                        borderColor=accent),
    )

def gold_callout(text):
    return Paragraph(
        text,
        ParagraphStyle("GC", fontName="Helvetica", fontSize=8.5, leading=11,
                        textColor=C_INK, backColor=C_GOLD_SOFT,
                        leftIndent=8, rightIndent=8, spaceBefore=2,
                        spaceAfter=2, borderPadding=(5, 8, 5, 8)),
    )

# ============================================================
# Chart helpers
# ============================================================
def _style_ax(ax, *, title=None, ylabel=None, ylim=None, dark=False):
    text_color = "white" if dark else M_INK
    spine_color = "#475569" if dark else "#cbd5e1"
    grid_color = "#1e293b" if dark else M_GRID
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(spine_color)
    ax.spines["bottom"].set_color(spine_color)
    ax.tick_params(colors=text_color, labelsize=8)
    ax.yaxis.grid(True, color=grid_color, linewidth=0.6, alpha=0.6)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, color=text_color, fontsize=10, weight="bold",
                     pad=8, loc="left")
    if ylabel:
        ax.set_ylabel(ylabel, color=text_color, fontsize=8)
    if ylim:
        ax.set_ylim(ylim)


def fig_to_image(fig, *, width_in, height_in=None, facecolor="white"):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=190, bbox_inches="tight",
                facecolor=facecolor, edgecolor="none", pad_inches=0.08)
    plt.close(fig)
    from PIL import Image as PILImage
    buf.seek(0)
    pil_img = PILImage.open(buf)
    aspect = pil_img.height / pil_img.width
    buf.seek(0)
    if height_in is None:
        height_in = width_in * aspect
    return Image(buf, width=width_in * inch, height=height_in * inch)


# ============================================================
# Visual components
# ============================================================
class HeroBanner(Flowable):
    """Dark hero band drawn directly with the canvas."""
    def __init__(self, width, height, title, subtitle, accent=C_GOLD):
        super().__init__()
        self.width = width
        self.height = height
        self.title = title
        self.subtitle = subtitle
        self.accent = accent

    def wrap(self, *args):
        return self.width, self.height

    def draw(self):
        c = self.canv
        # Deep navy band
        c.setFillColor(C_INK_DEEP)
        c.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        # Subtle diagonal accent strip
        c.setFillColor(C_NAVY)
        c.rect(0, 0, self.width, self.height * 0.35, fill=1, stroke=0)
        # Gold accent bar top
        c.setFillColor(self.accent)
        c.rect(0, self.height - 3, self.width, 3, fill=1, stroke=0)
        # OKC + SAS team-color stripes left/right
        c.setFillColor(C_OKC)
        c.rect(0, 0, 6, self.height, fill=1, stroke=0)
        c.setFillColor(C_SAS)
        c.rect(self.width - 6, 0, 6, self.height, fill=1, stroke=0)
        # Title — auto-shrink if too wide. Reserve 190pt for right-side stack.
        right_block_w = max(
            c.stringWidth("COURTVISION AI · INTEL BRIEF", "Helvetica-Bold", 9),
            c.stringWidth("Tue 2026-05-26 · 8:35 PM ET · Paycom Center", "Helvetica", 8),
            c.stringWidth("● SERIES 2-2 · WIN-OR-GO-HOME", "Helvetica-Bold", 8),
        )
        max_title_width = self.width - 20 - 30 - right_block_w  # left pad + gap + right block
        c.setFillColor(colors.white)
        title_font_size = 14
        for size in (28, 24, 22, 20, 18, 16, 14):
            if c.stringWidth(self.title, "Helvetica-Bold", size) <= max_title_width:
                title_font_size = size
                break
        c.setFont("Helvetica-Bold", title_font_size)
        title_y = self.height - 12 - title_font_size
        c.drawString(20, title_y, self.title)
        c.setFillColor(C_GRAY_300)
        c.setFont("Helvetica", 9.5)
        c.drawString(20, title_y - 14, self.subtitle)
        # Live tag right
        c.setFillColor(self.accent)
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(self.width - 20, self.height - 22, "COURTVISION AI · INTEL BRIEF")
        c.setFillColor(C_GRAY_400)
        c.setFont("Helvetica", 8)
        c.drawRightString(self.width - 20, self.height - 36, "Tue 2026-05-26 · 8:35 PM ET · Paycom Center")
        c.setFillColor(C_LIVE)
        c.setFont("Helvetica-Bold", 8)
        c.drawRightString(self.width - 20, self.height - 50, "● SERIES 2-2 · WIN-OR-GO-HOME")


class DarkCard(Flowable):
    """Dark-themed stat card with big number and label."""
    def __init__(self, width, height, label, big, sub_lines, *,
                 accent=C_GOLD, bg=C_INK):
        super().__init__()
        self.width, self.height = width, height
        self.label, self.big, self.sub_lines = label, big, sub_lines
        self.accent, self.bg = accent, bg

    def wrap(self, *args):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(self.bg)
        c.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        # accent top
        c.setFillColor(self.accent)
        c.rect(0, self.height - 3, self.width, 3, fill=1, stroke=0)
        # label
        c.setFillColor(C_GRAY_300)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(10, self.height - 16, self.label.upper())
        # big number
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(10, self.height - 40, self.big)
        # sub lines
        c.setFillColor(C_GRAY_300)
        c.setFont("Helvetica", 8)
        y = self.height - 56
        for line in self.sub_lines:
            c.drawString(10, y, line)
            y -= 10


class LightCard(Flowable):
    """Light card with accent left border."""
    def __init__(self, width, height, content_lines, *, accent=C_OKC, bg=C_GRAY_50):
        super().__init__()
        self.width, self.height = width, height
        self.content_lines = content_lines  # list of (font, size, color, text)
        self.accent, self.bg = accent, bg

    def wrap(self, *args):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(self.bg)
        c.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        c.setFillColor(self.accent)
        c.rect(0, 0, 4, self.height, fill=1, stroke=0)
        y = self.height - 14
        for font, size, color, text in self.content_lines:
            c.setFillColor(color)
            c.setFont(font, size)
            c.drawString(12, y, text)
            y -= size + 3


def team_pill(team_letter, color):
    """Circular colored pill with team letter."""
    return Table([[Paragraph(
        f"<font color='white' size=13><b>{team_letter}</b></font>",
        ParagraphStyle("", alignment=1))]],
        colWidths=[0.32 * inch], rowHeights=[0.32 * inch],
        style=TableStyle([
            ("BACKGROUND", (0,0),(-1,-1), color),
            ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
            ("ALIGN", (0,0),(-1,-1), "CENTER"),
            ("LEFTPADDING", (0,0),(-1,-1), 0),
            ("RIGHTPADDING", (0,0),(-1,-1), 0),
            ("TOPPADDING", (0,0),(-1,-1), 0),
            ("BOTTOMPADDING", (0,0),(-1,-1), 0),
            ("ROUNDEDCORNERS", [16, 16, 16, 16]),
        ]))


# ============================================================
# Page 1 — Executive Brief
# ============================================================
def chart_winprob_gauge(width_in=2.1):
    p = wp["home_win_prob"]
    fig, ax = plt.subplots(figsize=(3.6, 2.3))
    fig.patch.set_facecolor("#0a1628")
    ax.set_facecolor("#0a1628")
    ax.set_aspect("equal")
    theta = np.linspace(180, 0, 360)
    th = np.deg2rad(theta)
    r_out, r_in = 1.0, 0.66
    ax.fill_between(np.cos(th), r_in * np.sin(th), r_out * np.sin(th),
                    color="#1e293b", zorder=1)
    end_deg = 180 - 180 * p
    th_okc = np.deg2rad(np.linspace(180, end_deg, 200))
    ax.fill_between(np.cos(th_okc), r_in * np.sin(th_okc), r_out * np.sin(th_okc),
                    color=M_OKC, zorder=2)
    th_sas = np.deg2rad(np.linspace(end_deg, 0, 200))
    ax.fill_between(np.cos(th_sas), r_in * np.sin(th_sas), r_out * np.sin(th_sas),
                    color="#475569", zorder=2)
    ax.text(0, 0.22, f"{p*100:.1f}%", ha="center", va="center",
            fontsize=26, weight="bold", color="white")
    ax.text(0, 0.03, "OKC WIN", ha="center", va="center",
            fontsize=8.5, weight="bold", color="#94a3b8")
    ax.text(-1.05, -0.05, "SAS", ha="right", fontsize=9,
            color="#94a3b8", weight="bold")
    ax.text(1.05, -0.05, "OKC", ha="left", fontsize=9,
            color=M_OKC, weight="bold")
    pin_imp = abs(MARKET["ml_home"]) / (abs(MARKET["ml_home"]) + 100)
    th_mark = np.deg2rad(180 - 180 * pin_imp)
    ax.plot([0.58 * np.cos(th_mark), 1.08 * np.cos(th_mark)],
            [0.58 * np.sin(th_mark), 1.08 * np.sin(th_mark)],
            color=M_GOLD, lw=2.5)
    ax.text(1.15 * np.cos(th_mark), 1.18 * np.sin(th_mark),
            f"Pin {pin_imp*100:.0f}%", fontsize=7.5, color=M_GOLD,
            ha="center", weight="bold")
    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-0.25, 1.25)
    ax.axis("off")
    return fig_to_image(fig, width_in=width_in, facecolor="#0a1628")


def page1_scorecard_row():
    pred = m2["predictions"]
    h_pts = pred["home_pts"]
    a_pts = pred["away_pts"]
    total_model = h_pts + a_pts
    win_pct = wp["home_win_prob"] * 100
    pin_imp = abs(MARKET["ml_home"]) / (abs(MARKET["ml_home"]) + 100) * 100

    cards = [
        DarkCard(2.0 * inch, 1.05 * inch, "MODEL FINAL",
                  f"OKC {h_pts:.0f} – {a_pts:.0f}",
                  [f"Margin: OKC −{abs(pred['score_diff']):.1f}",
                   f"P(OT): 8.7%   P(home blowout 10+): 15.6%"],
                  accent=C_OKC),
        DarkCard(2.0 * inch, 1.05 * inch, "TOTAL POINTS",
                  f"{total_model:.0f} vs {MARKET['total']:.0f}",
                  [f"M2: {m2['predictions']['total_pts']:.0f}  ·  Series blend: 222",
                   f"Sharp: UNDER  ·  drifting down"],
                  accent=C_GOLD),
        DarkCard(2.0 * inch, 1.05 * inch, "WIN PROB · MODEL vs PIN",
                  f"{win_pct:.1f}% / {pin_imp:.1f}%",
                  [f"Edge: −{pin_imp-win_pct:.1f} pp  ·  no ML bet",
                   f"Home G5 (2-2 series): 62% historical"],
                  accent=C_LIVE),
    ]
    gauge = chart_winprob_gauge(width_in=1.5)
    row = Table([[cards[0], cards[1], cards[2], gauge]],
                colWidths=[2.05*inch, 2.05*inch, 2.05*inch, 1.5*inch],
                style=TableStyle([
                    ("VALIGN", (0,0),(-1,-1), "TOP"),
                    ("LEFTPADDING", (0,0),(-1,-1), 0),
                    ("RIGHTPADDING", (0,0),(-1,-1), 2),
                ]))
    return row


def page1_series_state():
    games = [
        ("G1", "SAS 122-115 (OT)", "Wemby 41/24", C_SAS, C_GRAY_50),
        ("G2", "OKC 122-113", "Home hold", C_OKC, C_GRAY_50),
        ("G3", "OKC 123-108", "OKC eFG .586", C_OKC, C_GRAY_50),
        ("G4", "SAS 103-82", "OKC eFG .363", C_SAS, C_GRAY_50),
        ("G5", "TONIGHT", "OKC −3.5  ·  216.5", C_GOLD, C_GOLD_SOFT),
    ]
    cells = []
    for label, score, note, head, body in games:
        cell = Table([
            [Paragraph(f"<font color='white'><b>{label}</b></font>",
                        ParagraphStyle("", fontSize=11, alignment=1))],
            [Paragraph(f"<b>{score}</b>",
                        ParagraphStyle("", fontSize=8.5, alignment=1, textColor=C_INK))],
            [Paragraph(note,
                        ParagraphStyle("", fontSize=7.5, alignment=1, textColor=C_GRAY_500))],
        ], colWidths=[1.45 * inch])
        cell.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(0,0), head),
            ("BACKGROUND", (0,1),(0,-1), body),
            ("BOX", (0,0),(-1,-1), 0.5, C_GRAY_300),
            ("TOPPADDING", (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ]))
        cells.append(cell)
    return Table([cells], colWidths=[1.5*inch]*5)


def page1_market_table():
    head_p = lambda s: Paragraph(f"<font color='white'><b>{s}</b></font>", BODY)
    rows = [
        [head_p("MARKET (PINNACLE)"), head_p("LINE"), head_p("PRICE"),
         head_p("MOVEMENT / SHARP NOTES")],
        ["Game Total O/U", f"{MARKET['total']}", "−119 / +104",
         Paragraph("Drifted UNDER from 219.5 open. Steam at 217.5. "
                    "<font color='#10b981'><b>NO BET</b></font> — model 211, market 216.", BODY_SM)],
        ["Spread (OKC)", f"OKC −{abs(MARKET['spread_home'])}", "−116",
         Paragraph("Was OKC −4.5 at open. Sharp money on SAS+. "
                    "<font color='#10b981'><b>Buy SAS +4</b></font> if number comes back.", BODY_SM)],
        ["Moneyline", f"OKC {MARKET['ml_home']} / SAS +{MARKET['ml_away']}", "—",
         Paragraph("OKC drifted −174 → −161 in 3 hrs (12 pp drop). Pin 61.7% vs model 59.1%. "
                    "<font color='#dc2626'><b>NO ML EDGE</b></font>.", BODY_SM)],
        ["1st Quarter Total", "53.5", "−108 / −112",
         Paragraph("Both teams open hot in WCF — Q1 avg 56.5 in series. "
                    "<font color='#10b981'><b>Live OVER if Q1 pace > 100</b></font>.", BODY_SM)],
        ["1H Total", "108.5", "−110 / −110",
         Paragraph("Median 1H over G1-G4 = 110. Slight edge OVER (+1.5 pts). "
                    "Watch for live re-pricing in Q2.", BODY_SM)],
    ]
    t = Table(rows, colWidths=[1.5*inch, 0.95*inch, 0.95*inch, 3.85*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,0), C_INK),
        ("FONTSIZE", (0,0),(-1,-1), 8.5),
        ("FONTNAME", (0,1),(2,-1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0,1),(-1,-1), [C_GRAY_50, "white"]),
        ("LEFTPADDING", (0,0),(-1,-1), 6),
        ("RIGHTPADDING", (0,0),(-1,-1), 6),
        ("TOPPADDING", (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("BOX", (0,0),(-1,-1), 0.4, C_GRAY_300),
        ("LINEAFTER", (0,1),(0,-1), 2, C_GOLD),
    ]))
    return t


def page1_intel_bullets():
    bullets = [
        ("MODEL DISAGREES WITH MARKET TOTAL",
         "M2 says 201 pts; market 216.5; series average 222. Truth in the middle — no game-line bet."),
        ("OKC G3→G4 eFG COLLAPSE — REVERSION THESIS",
         "OKC shot .586 in G3, .363 in G4 (22.3-pt swing). Pin partially priced reversion (−4.5 → −3.5). Buying SAS+3.5 is correct asymmetric exposure."),
        ("INJURY-DRIVEN USAGE RESHUFFLE",
         "Jalen Williams (OKC) OUT. Hartenstein, Wallace, Wiggins absorb usage. Hart AST OVER 2.5 is the cleanest 3-way agreement on the slate."),
        ("WEMBY DEFENDER LOTTERY",
         "Series CV data: 37 pts on 5-of-9 from 3 when Hartenstein guards Wemby (90 poss); held to 47% FG / 0-of-1 from 3 when Holmgren switches on. <b>Watch the cross-match the moment Hart picks up his 2nd foul.</b>"),
        ("ROLE-PLAYER MINUTES UNDERPRICED",
         "Pin priced Keldon Johnson PTS at 6.5 (implies &lt;12 min). Series avg 17.6 MPG. Strongest mispricing on board — 58.5% EV."),
    ]
    items = []
    for h, b in bullets:
        items.append(Paragraph(
            f"<font color='#d4a017'>●</font> &nbsp; <b>{h}</b> &nbsp; {b}", BODY))
    return items


# ============================================================
# Page 2 — Game Intelligence
# ============================================================
def chart_series_trajectory():
    okc = team_agg["teams"]["OKC"]["per_game"]
    sas = team_agg["teams"]["SAS"]["per_game"]
    games = ["G1", "G2", "G3", "G4", "G5*"]
    okc_pts = [g["pts"] for g in okc] + [m2["predictions"]["home_pts"]]
    sas_pts = [g["pts"] for g in sas] + [m2["predictions"]["away_pts"]]
    okc_off = [g["off_rtg"] for g in okc]
    sas_off = [g["off_rtg"] for g in sas]
    okc_def = [g["def_rtg"] for g in okc]
    sas_def = [g["def_rtg"] for g in sas]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 3.3))
    x = list(range(5))
    ax1.plot(x[:4], okc_pts[:4], marker="o", lw=2.5, color=M_OKC, label="OKC", markersize=8)
    ax1.plot(x[:4], sas_pts[:4], marker="s", lw=2.5, color=M_SAS, label="SAS", markersize=7)
    ax1.plot([3, 4], [okc_pts[3], okc_pts[4]], "--", color=M_OKC, lw=1.8, alpha=0.55)
    ax1.plot([3, 4], [sas_pts[3], sas_pts[4]], "--", color=M_SAS, lw=1.8, alpha=0.55)
    ax1.scatter([4], [okc_pts[4]], color=M_OKC, s=120, edgecolor=M_GOLD, lw=2.5, zorder=5)
    ax1.scatter([4], [sas_pts[4]], color=M_SAS, s=100, edgecolor=M_GOLD, lw=2.5, zorder=5)
    for i, (o, s) in enumerate(zip(okc_pts, sas_pts)):
        ax1.text(i, o + 3, f"{o:.0f}", ha="center", fontsize=8,
                  color=M_OKC, weight="bold")
        ax1.text(i, s - 6, f"{s:.0f}", ha="center", fontsize=8,
                  color=M_SAS, weight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(games)
    ax1.legend(loc="lower right", frameon=False, fontsize=9)
    _style_ax(ax1, title="POINTS PER GAME · G5 PROJECTED",
              ylim=(70, 135))

    width = 0.35
    pos = np.arange(4)
    ax2.bar(pos - width/2, okc_off, width, color=M_OKC, label="OKC")
    ax2.bar(pos + width/2, sas_off, width, color=M_SAS, label="SAS")
    for i, v in enumerate(okc_off):
        ax2.text(i - width/2, v + 1.5, f"{v:.0f}", ha="center", fontsize=7.5,
                  color=M_OKC, weight="bold")
    for i, v in enumerate(sas_off):
        ax2.text(i + width/2, v + 1.5, f"{v:.0f}", ha="center", fontsize=7.5,
                  color=M_SAS, weight="bold")
    ax2.set_xticks(pos)
    ax2.set_xticklabels(games[:4])
    ax2.legend(loc="upper left", frameon=False, fontsize=9)
    ax2.axhline(115, color=M_GOLD, ls=":", lw=1.2, alpha=0.7)
    _style_ax(ax2, title="OFFENSIVE RATING · note G3→G4 collapse",
              ylim=(95, 135))
    fig.tight_layout()
    return fig_to_image(fig, width_in=7.5)


def chart_efg_variance_pace():
    okc = team_agg["teams"]["OKC"]["per_game"]
    sas = team_agg["teams"]["SAS"]["per_game"]
    games = ["G1", "G2", "G3", "G4"]
    okc_efg = [g["efg_pct"] * 100 for g in okc]
    sas_efg = [g["efg_pct"] * 100 for g in sas]
    okc_pace = [g["pace"] for g in okc]
    sas_pace = [g["pace"] for g in sas]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 2.7))
    ax1.plot(games, okc_efg, marker="o", lw=2.5, color=M_OKC, label="OKC", markersize=9)
    ax1.plot(games, sas_efg, marker="s", lw=2.5, color=M_SAS, label="SAS", markersize=8)
    ax1.fill_between(games, okc_efg, sas_efg, alpha=0.06, color=M_GOLD)
    ax1.annotate("22.3 pt eFG swing", xy=(3, okc_efg[3]),
                  xytext=(1.8, okc_efg[3] - 9), fontsize=8.5, color=M_RED, weight="bold",
                  arrowprops=dict(arrowstyle="->", color=M_RED, lw=1.3))
    for i, v in enumerate(okc_efg):
        ax1.text(i, v + 1.8, f"{v:.1f}", ha="center", fontsize=8,
                  color=M_OKC, weight="bold")
    for i, v in enumerate(sas_efg):
        ax1.text(i, v - 3.3, f"{v:.1f}", ha="center", fontsize=8,
                  color=M_SAS, weight="bold")
    ax1.legend(loc="upper right", frameon=False, fontsize=9)
    _style_ax(ax1, title="eFG% — variance drives reversion edges", ylim=(30, 65))

    width = 0.35
    pos = np.arange(4)
    ax2.bar(pos - width/2, okc_pace, width, color=M_OKC, label="OKC")
    ax2.bar(pos + width/2, sas_pace, width, color=M_SAS, label="SAS")
    avg = (sum(okc_pace) + sum(sas_pace)) / 8
    ax2.axhline(avg, color=M_GOLD, ls="--", lw=1.4)
    ax2.text(3.45, avg + 0.4, f"avg {avg:.1f}", fontsize=8,
              color=M_GOLD, weight="bold", ha="right")
    for i, (a, b) in enumerate(zip(okc_pace, sas_pace)):
        ax2.text(i - width/2, a + 0.6, f"{a:.0f}", ha="center", fontsize=7.5,
                  color=M_OKC, weight="bold")
        ax2.text(i + width/2, b + 0.6, f"{b:.0f}", ha="center", fontsize=7.5,
                  color=M_SAS, weight="bold")
    ax2.set_xticks(pos)
    ax2.set_xticklabels(games)
    ax2.legend(loc="upper left", frameon=False, fontsize=9)
    _style_ax(ax2, title="PACE PER GAME", ylim=(90, 105))
    fig.tight_layout()
    return fig_to_image(fig, width_in=7.5)


def chart_total_distribution():
    fig, ax = plt.subplots(figsize=(11, 2.6))
    mu_model = m2["predictions"]["total_pts"]
    mu_series = (team_agg["teams"]["OKC"]["pts_pg"] + team_agg["teams"]["SAS"]["pts_pg"])
    mu_blend = 0.6 * mu_model + 0.4 * mu_series
    sigma = 13.0
    xs = np.linspace(165, 255, 500)
    ys = (1/(sigma*np.sqrt(2*np.pi))) * np.exp(-0.5*((xs-mu_blend)/sigma)**2)
    ax.fill_between(xs, 0, ys, color=M_OKC, alpha=0.15)
    ax.plot(xs, ys, color=M_OKC, lw=2.5)
    # 80% band shading
    lo80, hi80 = mu_blend - 1.28*sigma, mu_blend + 1.28*sigma
    mask = (xs >= lo80) & (xs <= hi80)
    ax.fill_between(xs[mask], 0, ys[mask], color=M_OKC, alpha=0.22)

    for x_, label, color in [
        (MARKET["total"], f"Pin {MARKET['total']}", M_GOLD),
        (mu_model, f"M2 {mu_model:.0f}", M_RED),
        (mu_series, f"Series {mu_series:.0f}", M_GREEN),
        (mu_blend, f"Blend {mu_blend:.0f}", M_OKC),
    ]:
        ax.axvline(x_, color=color, lw=2 if color in (M_GOLD, M_OKC) else 1.5,
                    ls="--" if color in (M_GOLD,) else "-", alpha=0.9)
        ax.text(x_ + 0.6, ys.max()*0.95, label, fontsize=8.5,
                  color=color, weight="bold")
    ax.set_yticks([])
    ax.set_xlim(165, 255)
    _style_ax(ax, title="GAME TOTAL POINTS — distribution & key landmarks")
    fig.tight_layout()
    return fig_to_image(fig, width_in=7.5)


# ============================================================
# Page 3 — Projected Box Scores
# ============================================================
def projected_box_data():
    OKC = [
        ("Shai Gilgeous-Alexander", 39, 28.4, 3.5, 8.7, 1.1, 0.605),
        ("Chet Holmgren",           33, 15.7, 7.3, 1.4, 0.9, 0.58),
        ("Jared McCain",            22, 10.4, 2.2, 1.2, 1.3, 0.56),
        ("Isaiah Hartenstein",      30,  8.5, 8.1, 3.0, 0.0, 0.62),
        ("Isaiah Joe",              18,  6.9, 1.9, 1.1, 1.4, 0.59),
        ("Cason Wallace",           27,  8.2, 3.8, 2.2, 1.5, 0.58),
        ("Alex Caruso",             26, 10.6, 2.8, 1.9, 2.0, 0.55),
        ("Luguentz Dort",           28,  5.2, 3.2, 1.5, 0.8, 0.53),
        ("Jaylin Williams",         16,  5.9, 3.7, 1.6, 1.4, 0.55),
        ("Kenrich Williams",         9,  5.1, 2.6, 1.1, 0.6, 0.54),
    ]
    SAS = [
        ("Victor Wembanyama", 38, 26.5, 12.5, 3.4, 1.9, 0.62),
        ("De'Aaron Fox",      36, 16.9,  6.1, 5.6, 1.2, 0.56),
        ("Stephon Castle",    33, 17.9,  5.0, 7.1, 1.0, 0.55),
        ("Devin Vassell",     31, 15.2,  4.8, 2.3, 2.8, 0.58),
        ("Keldon Johnson",    24,  9.9,  3.2, 0.7, 1.2, 0.55),
        ("Dylan Harper",      22, 11.4,  4.3, 2.8, 0.7, 0.54),
        ("Julian Champagnie", 18,  9.2,  5.0, 1.5, 1.8, 0.57),
        ("Harrison Barnes",   15,  5.9,  2.3, 0.6, 0.4, 0.54),
        ("Luke Kornet",       14,  4.5,  4.0, 0.8, 0.0, 0.58),
    ]
    return OKC, SAS


def projected_box_table(players, team_color, team_name):
    headers = ["PLAYER", "MIN", "PTS", "REB", "AST", "3PM", "TS%"]
    head_row = [Paragraph(f"<font color='white' size=8><b>{h}</b></font>",
                            ParagraphStyle("", alignment=1 if h != "PLAYER" else 0))
                 for h in headers]
    rows = [head_row]
    for p in players:
        name, mn, pts, reb, ast, three, ts = p
        rows.append([
            Paragraph(f"<b>{name}</b>", BODY_SM),
            Paragraph(f"{mn:.0f}", BODY_SM),
            Paragraph(f"<b>{pts:.1f}</b>", BODY_SM),
            Paragraph(f"{reb:.1f}", BODY_SM),
            Paragraph(f"{ast:.1f}", BODY_SM),
            Paragraph(f"{three:.1f}", BODY_SM),
            Paragraph(f"{ts*100:.0f}", SMALL),
        ])
    t = Table(rows, colWidths=[1.4*inch] + [0.34*inch]*6,
              repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,0), team_color),
        ("FONTSIZE", (0,0),(-1,-1), 7.8),
        ("ROWBACKGROUNDS", (0,1),(-1,-1), [C_GRAY_50, "white"]),
        ("ALIGN", (1,0),(-1,-1), "CENTER"),
        ("ALIGN", (0,0),(0,-1), "LEFT"),
        ("LEFTPADDING", (0,0),(-1,-1), 3),
        ("RIGHTPADDING", (0,0),(-1,-1), 3),
        ("LEFTPADDING", (0,0),(0,-1), 6),
        ("TOPPADDING", (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("BOX", (0,0),(-1,-1), 0.4, C_GRAY_300),
    ]))
    return t


def defensive_matrix_table():
    dm = def_match.head(8).copy()
    head = [Paragraph(f"<font color='white' size=8><b>{h}</b></font>", BODY)
            for h in ["OFF PLAYER", "DEF PLAYER", "MIN", "POSS",
                       "PTS ALL", "FG%", "3P%", "EDGE"]]
    rows = [head]
    for _, r in dm.iterrows():
        fg = r["fg_pct_allowed"] * 100
        three = r["fg3_pct_allowed"] * 100
        if fg > 55: edge_text, edge_hex = "OFF EDGE", "#dc2626"
        elif fg < 38: edge_text, edge_hex = "DEF EDGE", "#10b981"
        else: edge_text, edge_hex = "NEUTRAL", "#64748b"
        rows.append([
            r["off_player_name"], r["def_player_name"],
            f"{r['matchup_min']:.1f}", f"{r['partial_poss']:.0f}",
            f"{r['pts_allowed']:.0f}",
            f"{fg:.0f}%", f"{three:.0f}%",
            Paragraph(f"<font color='{edge_hex}'><b>{edge_text}</b></font>", BODY_SM)
        ])
    t = Table(rows, colWidths=[1.55*inch, 1.55*inch, 0.45*inch, 0.5*inch,
                                  0.6*inch, 0.45*inch, 0.45*inch, 0.7*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,0), C_INK),
        ("FONTSIZE", (0,0),(-1,-1), 8),
        ("ROWBACKGROUNDS", (0,1),(-1,-1), [C_GRAY_50, "white"]),
        ("ALIGN", (2,0),(-1,-1), "CENTER"),
        ("LEFTPADDING", (0,0),(-1,-1), 5),
        ("RIGHTPADDING", (0,0),(-1,-1), 5),
        ("TOPPADDING", (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("BOX", (0,0),(-1,-1), 0.4, C_GRAY_300),
    ]))
    return t


# ============================================================
# Page 4 — Bet Card
# ============================================================
def chart_bankroll():
    risked = sum(b["stake"] for b in bets["bets"])
    free = BR - risked
    fig, ax = plt.subplots(figsize=(11, 0.95))
    ax.barh([0], [risked], color=M_GOLD, height=0.7)
    ax.barh([0], [free], left=[risked], color="#1e293b", height=0.7)
    ax.text(risked/2, 0, f"AT-RISK  ${risked:,.0f}",
             ha="center", va="center", color="white",
             weight="bold", fontsize=11)
    ax.text(risked + free/2, 0, f"RESERVE  ${free:,.0f}",
             ha="center", va="center", color="white",
             weight="bold", fontsize=10)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_xlim(0, BR)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(
        f"BANKROLL ${BR:,.2f}   ·   9 bets × $260 = ${risked:,.0f} "
        f"({risked/BR*100:.1f}% of bankroll at risk)",
        fontsize=9.5, weight="bold", color=M_INK, loc="left", pad=8)
    fig.tight_layout()
    return fig_to_image(fig, width_in=7.5)


def chart_bet_ev_summary():
    df = pd.DataFrame(bets["bets"])
    df["label"] = df.apply(
        lambda r: f"{r['player'].split()[-1]}  ·  {r['stat'].upper()} {r['side']} {r['line']}",
        axis=1)
    df = df.sort_values("ev_pct", ascending=True)
    fig, ax = plt.subplots(figsize=(11, 4.0))
    colors_bar = [M_GREEN if v > 30 else (M_GOLD if v > 18 else M_GRAY)
                   for v in df["ev_pct"]]
    bars = ax.barh(df["label"], df["ev_pct"], color=colors_bar,
                     edgecolor="white", height=0.7)
    for bar, v, kp in zip(bars, df["ev_pct"], df["kelly_adj_pct"]):
        ax.text(v + 0.8, bar.get_y() + bar.get_height()/2,
                  f"  EV {v:.1f}%   Kelly {kp:.1f}%",
                  va="center", fontsize=8.5, color=M_INK)
    ax.set_xlim(0, max(df["ev_pct"]) * 1.45)
    _style_ax(ax, title="9-LEG SLATE · EXPECTED VALUE PER BET")
    ax.set_xlabel("EV % (per $1 staked)", color=M_INK, fontsize=8)
    fig.tight_layout()
    return fig_to_image(fig, width_in=7.5)


def tier_for_ev(ev):
    if ev >= 30: return "S", C_GOLD
    if ev >= 18: return "A", C_GRAY_700
    return "B", colors.HexColor("#b87333")


def make_bet_row(rank, bet, why, kill, p_mc):
    tier, tcol = tier_for_ev(bet["ev_pct"])
    edge_pct = min(100, abs(bet["edge_units"]) / (bet.get("sigma", 1) + 0.01) * 60)
    ev_bar_w = min(100, bet["ev_pct"] * 1.6)
    kelly_bar_w = min(100, bet["kelly_adj_pct"] * 20)
    headline = (
        f"<b>#{rank} {bet['player']} {bet['stat'].upper()} {bet['side']} {bet['line']}</b>"
        f"  <font color='#64748b'>·  Pin {bet['odds']:+d}</font>"
    )
    strip = (
        f"<font color='#64748b'>Model</font> <b>{bet['model_q50']:.2f}</b>  "
        f"<font color='#64748b'>σ</font> {bet.get('sigma',0):.2f}  "
        f"<font color='#64748b'>Edge</font> <b>{bet['edge_units']:+.2f}</b>  "
        f"<font color='#64748b'>MC P</font> <b>{p_mc*100:.1f}%</b>  "
        f"<font color='#10b981'>EV</font> <b>{bet['ev_pct']:.1f}%</b>  "
        f"<font color='#d4a017'>Kelly</font> <b>{bet['kelly_adj_pct']:.1f}%</b>  "
        f"Stake <b>${bet['stake']:.0f}</b>"
    )
    headline_p = Paragraph(headline,
                            ParagraphStyle("", fontName="Helvetica", fontSize=10,
                                            leading=12, textColor=C_INK))
    strip_p = Paragraph(strip, BODY_SM)
    why_p = Paragraph(f"<b>WHY:</b> {why}", BODY_SM)
    kill_p = Paragraph(
        f"<i>KILL:</i> {kill}",
        ParagraphStyle("", fontName="Helvetica-Oblique", fontSize=7.2,
                        leading=9, textColor=C_RED))

    def bar(label, fill_hex, pct, val_str):
        return Table([[
            Paragraph(f"<font size=6.5 color='#64748b'>{label}</font>", BODY_SM),
            Table([[""]], colWidths=[pct/100 * 1.45 * inch], rowHeights=[5],
                   style=TableStyle([("BACKGROUND",(0,0),(-1,-1), fill_hex)])),
            Paragraph(f"<font size=6.8><b>{val_str}</b></font>", BODY_SM)
        ]], colWidths=[0.55*inch, 1.45*inch, 0.55*inch])

    bars_block = Table([
        [bar("EDGE", "#0c2340", edge_pct, f"{bet['edge_units']:+.2f}")],
        [bar("EV",   "#10b981", ev_bar_w, f"{bet['ev_pct']:.1f}%")],
        [bar("KELLY","#d4a017", kelly_bar_w, f"{bet['kelly_adj_pct']:.1f}%")],
    ], colWidths=[2.55*inch], style=TableStyle([
        ("LEFTPADDING",(0,0),(-1,-1), 0),
        ("RIGHTPADDING",(0,0),(-1,-1), 0),
        ("TOPPADDING",(0,0),(-1,-1), 0.5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0.5),
    ]))

    body_col = Table([[headline_p],[strip_p],[why_p],[kill_p]],
                      colWidths=[4.4*inch])
    body_col.setStyle(TableStyle([
        ("LEFTPADDING",(0,0),(-1,-1), 4),
        ("RIGHTPADDING",(0,0),(-1,-1), 4),
        ("TOPPADDING",(0,0),(-1,-1), 1),
        ("BOTTOMPADDING",(0,0),(-1,-1), 1),
    ]))

    tier_cell = Paragraph(
        f"<font size=18 color='white'><b>{tier}</b></font>",
        ParagraphStyle("", alignment=1))

    outer = Table([[tier_cell, body_col, bars_block]],
                   colWidths=[0.4*inch, 4.4*inch, 2.6*inch])
    outer.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(0,0), tcol),
        ("BACKGROUND",(1,0),(-1,-1), C_GRAY_50),
        ("VALIGN",(0,0),(-1,-1), "TOP"),
        ("VALIGN",(0,0),(0,0), "MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1), 4),
        ("RIGHTPADDING",(0,0),(-1,-1), 4),
        ("TOPPADDING",(0,0),(-1,-1), 3),
        ("BOTTOMPADDING",(0,0),(-1,-1), 3),
        ("BOX",(0,0),(-1,-1), 0.4, C_GRAY_300),
    ]))
    return outer


def all_bet_rows():
    bets_sorted = sorted(bets["bets"], key=lambda b: -b["ev_pct"])
    why_kill = {
        ("Keldon Johnson","pts"): ("Pin 6.5 implies &lt;12 min. Series 17.6 MPG. Model 10.91. Softest mispricing on the board.",
                                    "DNP-coach's decision or sub-10 min cameo."),
        ("Luke Kornet","pts"):     ("Pin priced for &lt;12 min. Model 5.14, series 3.5. Wemby foul trouble = Kornet minutes.",
                                    "Pop benches him if SAS goes small."),
        ("Jared McCain","fg3m"):   ("Model 1.22, series 1.50, Pin 2.5 — 3-way structural mismatch. McCain &lt;20 MPG, no green light.",
                                    "Garbage time blowout gives him 8 min and 4 attempts."),
        ("Isaiah Hartenstein","ast"): ("With JaW OUT, Hart inherits the dribble-handoff load. Model 3.06, series 3.00 both above 2.5. +money pricing.",
                                       "Foul trouble caps minutes &lt;22."),
        ("Luke Kornet","reb"):     ("2.5 REB requires single-digit min. Model 4.26, series 3.5. Mirror of Kornet PTS thesis.",
                                    "Kornet plays &lt;8 min."),
        ("Victor Wembanyama","reb"):("Model 11.98, series 13.25 — both below 13.5. Foul fragility (avg 3.0 PF) caps minutes ~32-34.",
                                     "Heavy SAS minutes (35+) almost guarantee 13+ boards."),
        ("De'Aaron Fox","reb"):    ("Fox averaging 8.5 REB in WCF — 5 above line. Crashing offensive glass as SAS adjusts to Wemby drawing help.",
                                    "Reverts to 4.5 season avg if Pop goes small."),
        ("Stephon Castle","pts"):  ("Castle WCF avg 17.25 tracks model 18.26. Pin 16.5 is soft side. ROY usage is real in playoffs.",
                                    "OKC throws Dort or Caruso on him for a stretch."),
        ("Dylan Harper","pts"):    ("Rookie #1 pick — model 10.79, series 12.25, Pin 9.5. Pop trusts him 24+ MPG with clutch reps.",
                                    "Pop tightens to 8-man rotation, Harper drops to 14 min."),
    }
    mc_lookup = {(p["player"], p["stat"]): p for p in mc["props"]}
    rows = []
    for i, b in enumerate(bets_sorted, 1):
        key = (b["player"], b["stat"])
        why, kill = why_kill.get(key, ("—", "—"))
        mp = mc_lookup.get(key, {})
        p_mc = mp.get("p_over_mc", 0.5) if b["side"] == "OVER" else mp.get("p_under_mc", 0.5)
        rows.append(make_bet_row(i, b, why, kill, p_mc))
        rows.append(Spacer(1, 2))
    return rows


def slate_risk_summary():
    bets_list = bets["bets"]
    total_stake = sum(b["stake"] for b in bets_list)
    exp_profit = sum(b["stake"] * b["ev_pct"] / 100 for b in bets_list)
    def payout_for(odds):
        return odds/100 if odds >= 0 else 100/abs(odds)
    best_case = sum(b["stake"] * payout_for(b["odds"]) for b in bets_list)
    worst_case = -total_stake
    avg_ev = sum(b["ev_pct"] for b in bets_list) / len(bets_list)
    avg_kelly = sum(b["kelly_adj_pct"] for b in bets_list) / len(bets_list)
    head = lambda s: Paragraph(f"<font color='white'><b>{s}</b></font>", BODY)
    rows = [
        [head("METRIC"), head("VALUE"), head("INTERPRETATION")],
        ["Total at risk", f"${total_stake:,.0f}",
         f"{total_stake/BR*100:.1f}% of $11,043 bankroll — within 25% slate cap"],
        ["Expected profit", f"${exp_profit:+,.0f}",
         f"Avg leg EV {avg_ev:.1f}% × $260 × 9 — model's +edge claim"],
        ["Best case (all hit)", f"${best_case:+,.0f}",
         "All 9 legs win — multiplicative payoff on 21% bankroll"],
        ["Worst case (all miss)", f"${worst_case:+,.0f}",
         "Single-game contagion is the real tail risk"],
        ["Avg fractional Kelly", f"{avg_kelly:.2f}%",
         "0.25-Kelly × 0.65 playoff mult — half of textbook Kelly"],
        ["Correlated cluster", "3 legs",
         "Kornet PTS+REB + Hart AST share OKC foul-trouble dimension"],
        ["CLV target", "≥ +1.5%",
         "Avg closing-line value > 1.5% = +EV regardless of P&L"],
    ]
    t = Table(rows, colWidths=[1.6*inch, 1.1*inch, 4.7*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), C_INK),
        ("FONTSIZE",(0,0),(-1,-1), 8.5),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [C_GRAY_50, "white"]),
        ("FONTNAME",(0,1),(1,-1), "Helvetica-Bold"),
        ("LEFTPADDING",(0,0),(-1,-1), 6),
        ("RIGHTPADDING",(0,0),(-1,-1), 6),
        ("TOPPADDING",(0,0),(-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ("BOX",(0,0),(-1,-1), 0.4, C_GRAY_300),
        ("TEXTCOLOR",(1,2),(1,2), C_GREEN),
        ("TEXTCOLOR",(1,3),(1,3), C_GREEN),
        ("TEXTCOLOR",(1,4),(1,4), C_RED),
    ]))
    return t


# ============================================================
# PAGE 5 — LIVE: Quarter Scoreline + Game Scripts
# ============================================================
def chart_quarter_scoreline():
    """Quarter-by-quarter projected score with confidence bands."""
    # Series-derived quarter splits
    okc_qtr = [27.6, 28.1, 28.7, 26.5]  # avg in WCF
    sas_qtr = [27.9, 27.7, 28.3, 27.6]
    okc_cum = np.cumsum(okc_qtr)
    sas_cum = np.cumsum(sas_qtr)
    # 80% bands ±5 pts per quarter (cum sigma sqrt(q))
    sigmas = np.array([3.5, 5.0, 6.0, 7.0])
    okc_lo = okc_cum - 1.28 * sigmas
    okc_hi = okc_cum + 1.28 * sigmas
    sas_lo = sas_cum - 1.28 * sigmas
    sas_hi = sas_cum + 1.28 * sigmas

    fig, ax = plt.subplots(figsize=(11, 3.5))
    qs = [1, 2, 3, 4]
    ax.fill_between(qs, okc_lo, okc_hi, color=M_OKC, alpha=0.15,
                     label="OKC 80% band")
    ax.fill_between(qs, sas_lo, sas_hi, color=M_SAS, alpha=0.12,
                     label="SAS 80% band")
    ax.plot(qs, okc_cum, marker="o", lw=3, color=M_OKC, markersize=10,
             label="OKC projected")
    ax.plot(qs, sas_cum, marker="s", lw=3, color=M_SAS, markersize=9,
             label="SAS projected")
    for i, (o, s) in enumerate(zip(okc_cum, sas_cum)):
        ax.text(i+1, o + 2, f"{o:.0f}", ha="center", fontsize=9,
                  color=M_OKC, weight="bold")
        ax.text(i+1, s - 4.5, f"{s:.0f}", ha="center", fontsize=9,
                  color=M_SAS, weight="bold")
    # Halftime divider
    ax.axvline(2, color=M_GOLD, ls=":", lw=1.5, alpha=0.6)
    ax.text(2.05, 5, "HALF", fontsize=8, color=M_GOLD, weight="bold")
    # Pin 1H/total markers
    ax.axhline(108.5, color=M_GOLD, ls="--", lw=1, alpha=0.5)
    ax.text(0.9, 109.5, "Pin 1H 108.5", fontsize=7.5, color=M_GOLD, weight="bold")
    ax.axhline(216.5/2, color=M_GOLD, ls=":", lw=0.6, alpha=0.4)
    ax.set_xticks([1,2,3,4])
    ax.set_xticklabels(["Q1","Q2","Q3","Q4"])
    ax.set_ylabel("Cumulative team points", color=M_INK, fontsize=8.5)
    ax.legend(loc="upper left", frameon=False, fontsize=8.5, ncol=2)
    _style_ax(ax, title="PROJECTED CUMULATIVE SCORE BY QUARTER · with 80% confidence bands")
    fig.tight_layout()
    return fig_to_image(fig, width_in=7.5)


def game_scripts_grid():
    """4 game scripts in a 2x2 grid — each is a styled card."""
    scripts = [
        ("SCRIPT A · OKC TAKES Q1 BY 6+", C_OKC,
         "Crowd energy, OKC pace > 102, Wemby gets only 6 looks",
         ["FIRE: SGA PTS OVER 28.5 (live)",
          "FIRE: Wemby REB UNDER 13.5 (lock current ticket)",
          "FIRE: OKC team total OVER 110.5",
          "HEDGE: SAS team total live UNDER if SAS &lt; 50 at half"]),
        ("SCRIPT B · SAS LEADS BY 6+ AT HALF", C_SAS,
         "Wemby >18 pts in 1H, SAS shooting 50%+",
         ["FIRE: Castle PTS OVER 16.5 (already in)",
          "SELL: Wemby REB UNDER (book moves; lock profit)",
          "FIRE: SAS team total OVER 110.5 live",
          "AVOID: Kornet PTS — Pop tightens rotation against SAS lead"]),
        ("SCRIPT C · TIED ENTERING Q4 (±3)", C_GOLD,
         "Both teams playing tight, clutch lineups in",
         ["FIRE: Game UNDER 216.5 (clutch poss drop 20%)",
          "FIRE: SGA PTS OVER live (clutch usage spike)",
          "FIRE: Wemby BLK OVER (rim attacks)",
          "WATCH: OKC -3.5 → push possibility; consider 1H tease"]),
        ("SCRIPT D · BLOWOUT (15+ either way) BY Q3", C_LIVE,
         "Garbage time, deep bench enters",
         ["FIRE: Kornet PTS+REB OVER (extended minutes)",
          "FIRE: Champagnie / K.Williams 3PM OVER 1.5",
          "AVOID: SGA PTS OVER (gets pulled w/ lead)",
          "HEDGE: Sell McCain UNDER if OKC down 15+ (he chucks)"]),
    ]
    cells = []
    for title, accent, condition, actions in scripts:
        title_p = Paragraph(
            f"<font color='white'><b>{title}</b></font>",
            ParagraphStyle("", fontName="Helvetica-Bold", fontSize=9.5,
                            textColor="white"))
        cond_p = Paragraph(
            f"<i>{condition}</i>",
            ParagraphStyle("", fontName="Helvetica-Oblique", fontSize=7.8,
                            textColor=C_GRAY_500))
        actions_html = "<br/>".join(
            f"<font color='#10b981' size=7.5>▸</font> {a}" if a.startswith("FIRE") else
            f"<font color='#d4a017' size=7.5>▸</font> {a}" if a.startswith("SELL") or a.startswith("HEDGE") else
            f"<font color='#dc2626' size=7.5>▸</font> {a}" if a.startswith("AVOID") else
            f"<font color='#64748b' size=7.5>▸</font> {a}"
            for a in actions)
        actions_p = Paragraph(actions_html, BODY_SM)
        inner = Table([
            [title_p],
            [cond_p],
            [actions_p],
        ], colWidths=[3.55*inch])
        inner.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0), accent),
            ("BACKGROUND",(0,1),(-1,-1), C_GRAY_50),
            ("LEFTPADDING",(0,0),(-1,-1), 8),
            ("RIGHTPADDING",(0,0),(-1,-1), 8),
            ("TOPPADDING",(0,0),(-1,-1), 5),
            ("BOTTOMPADDING",(0,0),(-1,-1), 5),
            ("BOX",(0,0),(-1,-1), 0.5, C_GRAY_300),
        ]))
        cells.append(inner)
    grid = Table([[cells[0], cells[1]], [cells[2], cells[3]]],
                   colWidths=[3.65*inch, 3.65*inch],
                   style=TableStyle([
                       ("VALIGN",(0,0),(-1,-1), "TOP"),
                       ("TOPPADDING",(0,0),(-1,-1), 4),
                       ("BOTTOMPADDING",(0,0),(-1,-1), 4),
                       ("LEFTPADDING",(0,0),(-1,-1), 0),
                       ("RIGHTPADDING",(0,0),(-1,-1), 2),
                   ]))
    return grid


def chart_defender_impact():
    data = [
        ("Hartenstein (primary)",  +6.2,  M_RED),
        ("Holmgren (real solution)", -4.8,  M_GREEN),
        ("Caruso (surprise lever)", -22.6, M_GREEN),
        ("Dort (POA disruptor)",   -8.4,  M_GREEN),
    ]
    fig, ax = plt.subplots(figsize=(11, 2.3))
    labels = [d[0] for d in data]
    vals = [d[1] for d in data]
    cols = [d[2] for d in data]
    bars = ax.barh(labels, vals, color=cols, edgecolor="white", height=0.65)
    for bar, v in zip(bars, vals):
        ax.text(v + (0.7 if v > 0 else -0.7), bar.get_y() + bar.get_height()/2,
                  f"{v:+.1f}%", va="center",
                  ha="left" if v > 0 else "right",
                  fontsize=9, color=M_INK, weight="bold")
    ax.axvline(0, color=M_GRAY, lw=0.8)
    ax.set_xlim(-28, 12)
    _style_ax(ax, title="WEMBY PTS · % Δ vs baseline by primary defender (series CV data)")
    fig.tight_layout()
    return fig_to_image(fig, width_in=7.5)


# ============================================================
# PAGE 6 — LIVE: Triggers, Middles, Hedges, Joint Events
# ============================================================
def live_trigger_matrix():
    triggers = [
        ("Q1 · Hartenstein on Wemby > 6 min",
         "FIRE: Wemby 3PM OVER 1.5 live",
         "Series CV: 5-of-9 from 3 vs Hart (90 poss)",
         C_RED_SOFT),
        ("Q1 · Pace > 100, OKC eFG > .55",
         "FIRE: 1H OVER 108.5",
         "Combines hot-shooting + high pace — Q2 lag",
         C_GREEN_SOFT),
        ("Q2 · Wemby picks up 2nd foul",
         "FIRE: Wemby PTS UNDER 25.5 live · SELL Wemby REB UNDER",
         "Cap on minutes ~28-30; book lags by 60-90 sec",
         C_GREEN_SOFT),
        ("Q2 · OKC down 10+ at any point",
         "FIRE: Hart AST UNDER hedge · sell back",
         "Hart playmaking volume falls in negative scripts",
         C_GOLD_SOFT),
        ("Q3 · Caruso cross-matched on Wemby (any segment)",
         "FIRE: Wemby PTS UNDER 22.5 live",
         "Caruso reduces Wemby PTS by ~22% in priors",
         C_GREEN_SOFT),
        ("Q3 · Holmgren picks up 3rd foul",
         "FIRE: Hart REB OVER 8.5 live · FIRE Kornet 12+ min triggers",
         "Hart absorbs all C minutes",
         C_RED_SOFT),
        ("Q4 · Game tied at 5:00",
         "FIRE: Game UNDER live (clutch poss drops 20%)",
         "Total runs ~ 8 pts/min in clutch vs 9.2 reg",
         C_GREEN_SOFT),
        ("Q4 · Either team up 15+",
         "FIRE: bench-player 3PM OVER · K.Johnson PTS OVER live · stop new SGA bets",
         "Garbage time scripts; SGA gets pulled",
         C_GOLD_SOFT),
        ("Anytime · Wemby on bench 4+ min",
         "FIRE: Kornet PTS+REB OVER live (compressed minutes)",
         "Pop rotates Kornet up; mirror image of REB UNDER",
         C_RED_SOFT),
        ("Anytime · Total in-play > 110 by half",
         "FIRE: Game UNDER 216.5 live (regression to 211 model)",
         "Live total drifts 6-8 pts when 1H runs hot",
         C_GREEN_SOFT),
    ]
    head = lambda s: Paragraph(f"<font color='white'><b>{s}</b></font>", BODY_SM)
    rows = [[head("GAME-STATE TRIGGER"), head("ACTION"), head("WHY")]]
    for cond, act, why, _ in triggers:
        rows.append([
            Paragraph(cond, BODY_SM),
            Paragraph(f"<b>{act}</b>", BODY_SM),
            Paragraph(why, SMALL),
        ])
    t = Table(rows, colWidths=[2.15*inch, 3.0*inch, 2.35*inch])
    bg_styles = [("BACKGROUND",(0,i),(-1,i), triggers[i-1][3])
                  for i in range(1, len(triggers)+1)]
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), C_INK),
        ("FONTSIZE",(0,0),(-1,-1), 8),
        ("VALIGN",(0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",(0,0),(-1,-1), 6),
        ("RIGHTPADDING",(0,0),(-1,-1), 6),
        ("TOPPADDING",(0,0),(-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ("BOX",(0,0),(-1,-1), 0.4, C_GRAY_300),
        ("GRID",(0,1),(-1,-1), 0.3, C_GRAY_200),
    ] + bg_styles))
    return t


def middles_and_hedges_table():
    """Combined: which props have middle setups + when to hedge."""
    head = lambda s: Paragraph(f"<font color='white'><b>{s}</b></font>", BODY_SM)
    rows = [[head("OPPORTUNITY"), head("BOOKS"), head("LIVE TRIGGER")]]
    mid_rows = middles[middles["middle_width"] > 0].head(4)
    for _, r in mid_rows.iterrows():
        rows.append([
            Paragraph(f"<b>{r['player']}</b> {str(r['stat']).upper()} middle "
                       f"{r['over_line']:.1f} / {r['under_line']:.1f}", BODY_SM),
            f"{str(r['over_book']).upper()} OVER {r['over_price']:+.0f} | "
             f"{str(r['under_book']).upper()} UNDER {r['under_price']:+.0f}",
            Paragraph(f"Lock if mid-game total &gt; {r['over_line']}", SMALL),
        ])
    # Add hedge rows
    rows.append([
        Paragraph("<b>Wemby REB UNDER 13.5</b> at -117 — hedge", BODY_SM),
        "Live OVER if &gt; 8 REB by half",
        Paragraph("Lock $50 profit if line moves to 11.5", SMALL),
    ])
    rows.append([
        Paragraph("<b>Kornet PTS OVER 2.5</b> at -115 — hedge", BODY_SM),
        "Live UNDER if 0 pts by Q3",
        Paragraph("Lock $80 profit if line moves to 4.5", SMALL),
    ])
    rows.append([
        Paragraph("<b>K.Johnson PTS OVER 6.5</b> at +105 — hedge", BODY_SM),
        "Live UNDER if &lt; 3 pts by half",
        Paragraph("Net guaranteed +$95 if line moves to 9.5", SMALL),
    ])
    t = Table(rows, colWidths=[3.0*inch, 2.7*inch, 1.8*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), C_INK),
        ("FONTSIZE",(0,0),(-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [C_GRAY_50, "white"]),
        ("VALIGN",(0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",(0,0),(-1,-1), 6),
        ("RIGHTPADDING",(0,0),(-1,-1), 6),
        ("TOPPADDING",(0,0),(-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ("BOX",(0,0),(-1,-1), 0.4, C_GRAY_300),
    ]))
    return t


def chart_joint_events():
    events = [
        ("SGA scores 30+",          0.397, M_OKC),
        ("SGA 30+ AND OKC wins",    0.255, M_OKC),
        ("SGA 30+ | OKC wins",      0.556, M_OKC),
        ("Wemby 25+ PTS",           0.541, M_SAS),
        ("Wemby 4+ BLK",            0.398, M_SAS),
        ("Wemby double-double",     0.798, M_SAS),
        ("Game ends in OT",         0.087, M_GOLD),
        ("Holmgren scoreless Q1",   0.119, M_GRAY),
        ("Both teams 110+ pts",     0.628, M_GREEN),
        ("Wemby triple-double",     0.011, M_GRAY),
        ("OKC wins by 10+",         0.156, M_OKC),
        ("SAS wins by 10+",         0.092, M_SAS),
    ]
    fig, ax = plt.subplots(figsize=(11, 4.0))
    labels = [e[0] for e in events]
    vals = [e[1] * 100 for e in events]
    cols = [e[2] for e in events]
    bars = ax.barh(labels, vals, color=cols, edgecolor="white", height=0.7)
    for bar, v in zip(bars, vals):
        ax.text(v + 1.2, bar.get_y() + bar.get_height()/2,
                  f"{v:.1f}%", va="center", fontsize=8.5,
                  color=M_INK, weight="bold")
    ax.set_xlim(0, 95)
    _style_ax(ax, title="JOINT EVENT PROBABILITIES · Monte Carlo (1000 sims)")
    fig.tight_layout()
    return fig_to_image(fig, width_in=7.5)


def how_we_bet_block():
    items = [
        ("EDGE FROM STRUCTURE, NOT NARRATIVES",
         "3-way agreement (model + series + market) OR a structural mismatch we can name. No stories."),
        ("KELLY × PLAYOFF × CORRELATION",
         "Sized at 0.25-Kelly × 0.65 playoff mult. Correlated legs aggregated into one decision."),
        ("LIVE EDGE > PREGAME EDGE",
         "Defender cross-matches and foul totals produce 2-4x larger edges live. Live playbook is where the EV lives."),
        ("CLV IS THE SCOREBOARD",
         "Win/loss is variance. CLV tells us if we bet smart. +1.5% avg CLV = +EV regardless of nightly P&L."),
    ]
    out = []
    for h, b in items:
        out.append(Paragraph(
            f"<font color='#d4a017'><b>{h}</b></font> &nbsp;{b}",
            ParagraphStyle("", fontName="Helvetica", fontSize=8, leading=10.5,
                            textColor=C_INK, spaceAfter=2)))
    return out


def tonight_watchlist():
    """Specific real-time watch points — what to look at and when."""
    items = [
        ("8:25 PM ET",  "STARTING LINEUPS DROP",
         "Verify J. Williams OUT. Confirm Hartenstein in starting 5. Last-min injury swap = re-price slate."),
        ("8:35 PM ET", "TIP-OFF · WEMBY DEFENDER",
         "Watch Hart vs Holmgren initial assignment. Hart on Wemby → Wemby 3PM OVER 1.5 live. Holmgren → no trigger."),
        ("Q1 :08:00", "PACE READ",
         "If combined poss > 24 by 4-min mark → 1H OVER 108.5 fire. Slow start → game UNDER becomes attractive."),
        ("Q2 :04:00", "FOUL COUNT READ",
         "Wemby PF count + Holmgren PF count. 2+ fouls on either C reshapes Q3 minutes radically."),
        ("HALFTIME",  "LIVE TOTAL & SPREAD RE-PRICE",
         "Books slow to re-price within 45-90 sec of buzzer. Window: bet OPPOSITE side of 1H result for regression edge."),
        ("Q3 :06:00", "LINEUP CROSS-MATCH",
         "Caruso on Wemby for any 2+ min stretch → Wemby PTS UNDER 22.5 live (priors say −22%)."),
        ("Q4 :05:00", "CLUTCH WINDOW",
         "If margin ≤ 5: SGA live PTS OVER + game UNDER. Total drops to 8 pts/min from 9.2 reg-time pace."),
        ("Q4 :02:00", "RUNOUT / GARBAGE TIME",
         "If margin ≥ 12: bench-prop OVERs (Kornet/Champagnie/K.Williams). Stop new SGA bets."),
        ("FINAL :00", "CLOSING LINE LOCK",
         "Capture final Pin numbers for each leg. CLV calc auto-runs at 09:00 ET tomorrow."),
    ]
    head = lambda s: Paragraph(f"<font color='white'><b>{s}</b></font>", BODY_SM)
    rows = [[head("WHEN"), head("WHAT TO WATCH"), head("ACTION")]]
    for when, what, action in items:
        rows.append([
            Paragraph(f"<font color='#d4a017'><b>{when}</b></font>", BODY_SM),
            Paragraph(f"<b>{what}</b>", BODY_SM),
            Paragraph(action, BODY_SM),
        ])
    t = Table(rows, colWidths=[1.0*inch, 2.3*inch, 4.2*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), C_INK),
        ("FONTSIZE",(0,0),(-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [C_GRAY_50, "white"]),
        ("VALIGN",(0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",(0,0),(-1,-1), 6),
        ("RIGHTPADDING",(0,0),(-1,-1), 6),
        ("TOPPADDING",(0,0),(-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
        ("BOX",(0,0),(-1,-1), 0.4, C_GRAY_300),
        ("LINEAFTER",(0,1),(0,-1), 2, C_GOLD),
    ]))
    return t


# ============================================================
# Document builder
# ============================================================
def build():
    doc = BaseDocTemplate(
        str(OUT), pagesize=LETTER,
        leftMargin=0.45 * inch, rightMargin=0.45 * inch,
        topMargin=0.4 * inch, bottomMargin=0.45 * inch,
        title="WCF Game 5 — Intelligence Brief V3",
        author="CourtVision AI",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                   doc.width, doc.height, id="main",
                   leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    def page_footer(canvas, doc_):
        canvas.saveState()
        # subtle bottom rule
        canvas.setStrokeColor(C_GRAY_200)
        canvas.setLineWidth(0.4)
        canvas.line(0.45*inch, 0.36*inch, LETTER[0] - 0.45*inch, 0.36*inch)
        canvas.setFillColor(C_GRAY_500)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(0.45*inch, 0.22*inch,
                           "CourtVision AI  ·  2026-05-26  ·  Bankroll $11,043.48  ·  "
                           "3-way verified (Model + WCF G1–G4 series + Pin sharp)")
        canvas.setFillColor(C_GOLD)
        canvas.setFont("Helvetica-Bold", 7)
        canvas.drawRightString(LETTER[0] - 0.45*inch, 0.22*inch,
                                f"PAGE {doc_.page}")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=page_footer)])

    story = []

    # ===========================================================
    # PAGE 1 — EXECUTIVE BRIEF
    # ===========================================================
    story.append(HeroBanner(7.6*inch, 1.05*inch,
                              "WCF GAME 5 · INTELLIGENCE BRIEF",
                              "San Antonio Spurs @ Oklahoma City Thunder  ·  game_id 0042500315"))
    story.append(Spacer(1, 8))
    story.append(page1_scorecard_row())
    story.append(Spacer(1, 8))
    story.append(section_band("SERIES STATE  ·  TIED 2-2  ·  GAME 5 IN OKC", accent=C_GOLD))
    story.append(Spacer(1, 3))
    story.append(page1_series_state())
    story.append(Spacer(1, 8))
    story.append(section_band("MARKET LINES  ·  SHARP MONEY FLOW", accent=C_GOLD))
    story.append(Spacer(1, 3))
    story.append(page1_market_table())
    story.append(Spacer(1, 8))
    story.append(section_band("FIVE THINGS THAT MATTER TONIGHT", accent=C_GOLD))
    story.append(Spacer(1, 3))
    for b in page1_intel_bullets():
        story.append(b)
        story.append(Spacer(1, 1))

    story.append(PageBreak())

    # ===========================================================
    # PAGE 2 — GAME INTELLIGENCE
    # ===========================================================
    story.append(HeroBanner(7.6*inch, 0.85*inch,
                              "GAME INTELLIGENCE",
                              "Series trajectory  ·  efficiency volatility  ·  market belief"))
    story.append(Spacer(1, 6))
    story.append(section_band("SERIES TRAJECTORY · G1 → G5 (projected)"))
    story.append(Spacer(1, 2))
    story.append(chart_series_trajectory())
    story.append(Spacer(1, 4))
    story.append(section_band("OFFENSIVE VARIANCE · THE REVERSION THESIS"))
    story.append(Spacer(1, 2))
    story.append(chart_efg_variance_pace())
    story.append(Spacer(1, 4))
    story.append(section_band("GAME TOTAL · MODEL vs MARKET BELIEF"))
    story.append(Spacer(1, 2))
    story.append(chart_total_distribution())
    story.append(Spacer(1, 4))
    story.append(gold_callout(
        "<b>READ:</b> Pinnacle 216.5 sits at the right edge of our 80% band — no edge on the game total. "
        "M2 says 211; series blend says 222. The truth is between. Live UNDER becomes a hot trigger if 1H pace stalls "
        "(see page 5). The reversion edge is in the spread, not the total — SAS+3.5 is the asymmetric exposure."))

    story.append(PageBreak())

    # ===========================================================
    # PAGE 3 — PROJECTED BOX SCORES
    # ===========================================================
    story.append(HeroBanner(7.6*inch, 0.85*inch,
                              "PROJECTED BOX SCORES",
                              "Shrunk q50 = 0.6 × model + 0.4 × WCF series  ·  defensive matchup CV data"))
    story.append(Spacer(1, 8))
    okc_list, sas_list = projected_box_data()
    # Team header row
    team_hdr = Table([[
        Table([
            [team_pill("O", C_OKC),
             Paragraph("<font color='#007ac1' size=12><b>OKC THUNDER</b></font> "
                        "<font color='#64748b' size=8>(HOME)</font><br/>"
                        "<font color='#dc2626' size=7.5>OUT: J.Williams · Mitchell · Sorber</font>",
                        BODY_SM)]
        ], colWidths=[0.4*inch, 3.25*inch],
           style=TableStyle([("VALIGN",(0,0),(-1,-1), "MIDDLE")])),
        Table([
            [team_pill("S", C_SAS),
             Paragraph("<font color='#2c2c2c' size=12><b>SAN ANTONIO SPURS</b></font> "
                        "<font color='#64748b' size=8>(AWAY)</font><br/>"
                        "<font color='#10b981' size=7.5>Full strength</font>",
                        BODY_SM)]
        ], colWidths=[0.4*inch, 3.25*inch],
           style=TableStyle([("VALIGN",(0,0),(-1,-1), "MIDDLE")])),
    ]], colWidths=[3.75*inch, 3.75*inch])
    story.append(team_hdr)
    story.append(Spacer(1, 3))
    story.append(Table([[
        projected_box_table(okc_list, C_OKC, "OKC"),
        projected_box_table(sas_list, C_SAS, "SAS"),
    ]], colWidths=[3.75*inch, 3.75*inch],
       style=TableStyle([("VALIGN",(0,0),(-1,-1), "TOP")])))

    story.append(Spacer(1, 12))
    story.append(section_band("DEFENSIVE MATCHUP MATRIX · WCF G1-G4 (top 8 by minutes)"))
    story.append(Spacer(1, 2))
    story.append(defensive_matrix_table())
    story.append(Spacer(1, 4))
    story.append(gold_callout(
        "<b>READ:</b> Wemby drops <b>37 pts on 58% FG / 56% from 3</b> when Hartenstein guards him (90 poss). "
        "When Castle takes SGA, SGA falls to 47% FG and 39 pts in 116 poss — Castle is the matchup OKC needs to break. "
        "<b>Watch the Hart→Wemby cross-match in Q1 — that's where the live 3PM OVER trigger fires.</b>"))

    story.append(PageBreak())

    # ===========================================================
    # PAGE 4 — PRE-GAME BET CARD (overview + bets 1-5)
    # ===========================================================
    story.append(HeroBanner(7.6*inch, 0.95*inch,
                              "PRE-GAME BET CARD",
                              "9 legs  ·  $260 each  ·  21.2% bankroll at risk  ·  all Pinnacle  ·  INTENDED"))
    story.append(Spacer(1, 6))
    story.append(chart_bankroll())
    story.append(Spacer(1, 6))
    story.append(section_band("9-LEG SLATE · RANKED BY EV"))
    story.append(Spacer(1, 3))
    bet_rows_flow = all_bet_rows()
    # First 10 flow items = 5 bets × 2 (bet + spacer)
    for r in bet_rows_flow[:10]:
        story.append(r)

    story.append(PageBreak())

    # ===========================================================
    # PAGE 5 — BETS 6-9 + EV CHART + SLATE RISK
    # ===========================================================
    story.append(HeroBanner(7.6*inch, 0.95*inch,
                              "BET CARD · CONTINUED",
                              "Bets 6-9  ·  expected-value chart  ·  slate risk summary"))
    story.append(Spacer(1, 6))
    for r in bet_rows_flow[10:]:
        story.append(r)
    story.append(Spacer(1, 4))
    story.append(KeepTogether([
        section_band("SLATE RISK SUMMARY"),
        Spacer(1, 2),
        slate_risk_summary(),
    ]))

    story.append(PageBreak())

    # ===========================================================
    # PAGE 6 — LIVE INTEL: QUARTER SCORELINE + GAME SCRIPTS
    # ===========================================================
    story.append(HeroBanner(7.6*inch, 0.95*inch,
                              "LIVE INTEL · WHAT CAN HAPPEN",
                              "Quarter projection  ·  4 game scripts  ·  defender impact",
                              accent=C_LIVE))
    story.append(Spacer(1, 6))
    story.append(section_band("PROJECTED SCORELINE · 80% confidence bands"))
    story.append(Spacer(1, 2))
    story.append(chart_quarter_scoreline())
    story.append(Spacer(1, 4))
    story.append(section_band("FOUR GAME SCRIPTS · pre-mapped actions"))
    story.append(Spacer(1, 2))
    story.append(game_scripts_grid())
    story.append(Spacer(1, 4))
    story.append(section_band("WEMBY DEFENDER IMPACT · series CV priors"))
    story.append(Spacer(1, 2))
    story.append(chart_defender_impact())

    story.append(PageBreak())

    # ===========================================================
    # PAGE 7 — LIVE PLAYBOOK: TRIGGERS + MIDDLES/HEDGES
    # ===========================================================
    story.append(HeroBanner(7.6*inch, 0.95*inch,
                              "LIVE PLAYBOOK · TRIGGERS + HEDGES",
                              "Pre-mapped actions for every game state",
                              accent=C_LIVE))
    story.append(Spacer(1, 6))
    story.append(section_band("LIVE TRIGGER MATRIX · 10 high-confidence game states"))
    story.append(Spacer(1, 2))
    story.append(live_trigger_matrix())
    story.append(Spacer(1, 6))
    story.append(section_band("MIDDLES, HEDGES & PROFIT-LOCKS"))
    story.append(Spacer(1, 2))
    story.append(middles_and_hedges_table())

    story.append(PageBreak())

    # ===========================================================
    # PAGE 8 — JOINT EVENTS + WATCHLIST + HOW WE BET
    # ===========================================================
    story.append(HeroBanner(7.6*inch, 0.95*inch,
                              "TONIGHT'S WATCHLIST · MC PROBABILITIES",
                              "Real-time anchors  ·  joint outcomes  ·  philosophy",
                              accent=C_LIVE))
    story.append(Spacer(1, 6))
    story.append(section_band("WATCHLIST · WHEN TO LOOK AT WHAT"))
    story.append(Spacer(1, 2))
    story.append(tonight_watchlist())
    story.append(Spacer(1, 6))
    story.append(section_band("JOINT EVENT PROBABILITIES · Monte Carlo (1000 sims)"))
    story.append(Spacer(1, 2))
    story.append(chart_joint_events())
    story.append(Spacer(1, 4))
    story.append(section_band("HOW WE BET · the principles"))
    story.append(Spacer(1, 2))
    for b in how_we_bet_block():
        story.append(b)

    doc.build(story)
    print(f"WROTE: {OUT}")
    print(f"SIZE:  {OUT.stat().st_size/1024:.1f} KB")


if __name__ == "__main__":
    build()
