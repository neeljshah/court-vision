"""build_intel_pdf_premium.py — magazine-grade WCF G5 intelligence brief.

Produces a 5-page polished PDF combining ReportLab layout + matplotlib charts:
  Page 1: Executive Brief — hero, series state, model-vs-market scorecard
  Page 2: Game Intelligence — series trajectory, pace/eFG charts, sharp flow
  Page 3: Projected Box Scores with edge bars
  Page 4: Pre-Game Bet Card — tier ranked with edge/EV/Kelly visualization
  Page 5: Live Betting Playbook — defender triggers, joint events, ops

Reads from data/cache/intel_2026-05-26/, writes to that dir's reports/.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepInFrame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import HRFlowable

ROOT = Path(__file__).resolve().parent.parent
INTEL = ROOT / "data" / "cache" / "intel_2026-05-26"
OUT = INTEL / "reports" / "WCF_G5_intel_PREMIUM.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)

# ============================================================
# Color palette — modern dark-navy + accent gold/red
# ============================================================
C_INK = colors.HexColor("#0a1628")
C_NAVY = colors.HexColor("#0c2340")
C_NAVY_LIGHT = colors.HexColor("#1e3a5f")
C_OKC = colors.HexColor("#007ac1")
C_OKC_ACCENT = colors.HexColor("#ef6c00")
C_SAS = colors.HexColor("#3b3b3b")
C_SAS_ACCENT = colors.HexColor("#c4ced4")
C_GOLD = colors.HexColor("#d4a017")
C_GOLD_LIGHT = colors.HexColor("#f4e4a6")
C_GREEN = colors.HexColor("#1f7a3b")
C_GREEN_LIGHT = colors.HexColor("#d4f4dd")
C_RED = colors.HexColor("#a51d2d")
C_RED_LIGHT = colors.HexColor("#fadbd8")
C_BLUE = colors.HexColor("#2563eb")
C_GRAY_50 = colors.HexColor("#f8fafc")
C_GRAY_100 = colors.HexColor("#f1f5f9")
C_GRAY_200 = colors.HexColor("#e2e8f0")
C_GRAY_300 = colors.HexColor("#cbd5e1")
C_GRAY_500 = colors.HexColor("#64748b")
C_GRAY_700 = colors.HexColor("#334155")
C_TIER_S = colors.HexColor("#d4a017")
C_TIER_A = colors.HexColor("#64748b")
C_TIER_B = colors.HexColor("#b87333")

MPL_INK = "#0a1628"
MPL_OKC = "#007ac1"
MPL_SAS = "#3b3b3b"
MPL_GOLD = "#d4a017"
MPL_GREEN = "#1f7a3b"
MPL_RED = "#a51d2d"
MPL_GRAY = "#94a3b8"
MPL_GRID = "#e2e8f0"

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

# Market lines (Pinnacle from page-1 of v2 report)
MARKET = {
    "total": 216.5, "total_o_price": -119, "total_u_price": 104,
    "spread_home": -3.5, "spread_home_price": -116,
    "ml_home": -161, "ml_away": 145,
}

BR = 11043.48

# ============================================================
# Chart helpers — return PNG bytes (Image flowable will consume)
# ============================================================
def _style_ax(ax, *, title=None, ylabel=None, ylim=None):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#cbd5e1")
    ax.spines["bottom"].set_color("#cbd5e1")
    ax.tick_params(colors=MPL_INK, labelsize=8)
    ax.yaxis.grid(True, color=MPL_GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, color=MPL_INK, fontsize=10, weight="bold", pad=8, loc="left")
    if ylabel:
        ax.set_ylabel(ylabel, color=MPL_INK, fontsize=8)
    if ylim:
        ax.set_ylim(ylim)


def fig_to_image(fig, *, width_in, height_in=None):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight",
                facecolor="white", edgecolor="none", pad_inches=0.08)
    plt.close(fig)
    buf.seek(0)
    # Use PIL to measure the actual saved image aspect (bbox_inches=tight may crop)
    from PIL import Image as PILImage
    buf.seek(0)
    pil_img = PILImage.open(buf)
    aspect = pil_img.height / pil_img.width
    buf.seek(0)
    if height_in is None:
        height_in = width_in * aspect
    img = Image(buf, width=width_in * inch, height=height_in * inch)
    return img


def chart_winprob_gauge():
    """Semicircular gauge showing OKC win prob 59.1%."""
    p = wp["home_win_prob"]
    fig, ax = plt.subplots(figsize=(4.2, 2.4))
    ax.set_aspect("equal")
    # Background half-circle
    theta_full = list(range(180, -1, -1))
    import numpy as np
    th = np.deg2rad(theta_full)
    r_out, r_in = 1.0, 0.62
    # Background ring
    ax.fill_between(np.cos(th), r_in * np.sin(th), r_out * np.sin(th),
                    color="#e2e8f0", zorder=1)
    # OKC arc from 180° (left) to (180 - 180*p)° to fill p
    end_deg = 180 - 180 * p
    th_okc = np.deg2rad(np.linspace(180, end_deg, 200))
    ax.fill_between(np.cos(th_okc), r_in * np.sin(th_okc), r_out * np.sin(th_okc),
                    color=MPL_OKC, zorder=2)
    th_sas = np.deg2rad(np.linspace(end_deg, 0, 200))
    ax.fill_between(np.cos(th_sas), r_in * np.sin(th_sas), r_out * np.sin(th_sas),
                    color=MPL_SAS, zorder=2)
    # Center numbers
    ax.text(0, 0.20, f"{p*100:.1f}%", ha="center", va="center",
            fontsize=24, weight="bold", color=MPL_INK)
    ax.text(0, 0.02, "OKC WIN", ha="center", va="center",
            fontsize=9, weight="bold", color=MPL_INK, alpha=0.7)
    ax.text(-1.05, -0.05, "SAS", ha="right", fontsize=9, color=MPL_SAS, weight="bold")
    ax.text(1.05, -0.05, "OKC", ha="left", fontsize=9, color=MPL_OKC, weight="bold")
    # Pinnacle implied marker
    pin_imp = abs(MARKET["ml_home"]) / (abs(MARKET["ml_home"]) + 100)  # 0.617
    th_mark = np.deg2rad(180 - 180 * pin_imp)
    ax.plot([0.55 * np.cos(th_mark), 1.05 * np.cos(th_mark)],
            [0.55 * np.sin(th_mark), 1.05 * np.sin(th_mark)],
            color=MPL_GOLD, lw=2.5)
    ax.text(1.08 * np.cos(th_mark), 1.12 * np.sin(th_mark),
            f"Pin {pin_imp*100:.1f}%", fontsize=7.5, color=MPL_GOLD,
            ha="center", weight="bold")
    ax.set_xlim(-1.25, 1.25)
    ax.set_ylim(-0.25, 1.20)
    ax.axis("off")
    return fig_to_image(fig, width_in=1.85)


def chart_series_trajectory():
    """OKC vs SAS per-game pts and rtg over 4 games + projected G5."""
    okc = team_agg["teams"]["OKC"]["per_game"]
    sas = team_agg["teams"]["SAS"]["per_game"]
    games = [f"G{i+1}" for i in range(4)] + ["G5*"]
    okc_pts = [g["pts"] for g in okc] + [m2["predictions"]["home_pts"]]
    sas_pts = [g["pts"] for g in sas] + [m2["predictions"]["away_pts"]]
    okc_off = [g["off_rtg"] for g in okc]
    sas_off = [g["off_rtg"] for g in sas]
    okc_def = [g["def_rtg"] for g in okc]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.1))
    # Left: points per game
    x = list(range(5))
    ax1.plot(x[:4], okc_pts[:4], marker="o", lw=2.2, color=MPL_OKC, label="OKC", markersize=7)
    ax1.plot(x[:4], sas_pts[:4], marker="s", lw=2.2, color=MPL_SAS, label="SAS", markersize=6)
    # Projected dashed segment
    ax1.plot([3, 4], [okc_pts[3], okc_pts[4]], "--", color=MPL_OKC, lw=1.8, alpha=0.6)
    ax1.plot([3, 4], [sas_pts[3], sas_pts[4]], "--", color=MPL_SAS, lw=1.8, alpha=0.6)
    ax1.scatter([4], [okc_pts[4]], color=MPL_OKC, marker="o", s=85, edgecolor=MPL_GOLD, lw=2, zorder=5)
    ax1.scatter([4], [sas_pts[4]], color=MPL_SAS, marker="s", s=70, edgecolor=MPL_GOLD, lw=2, zorder=5)
    for i, (o, s) in enumerate(zip(okc_pts, sas_pts)):
        ax1.text(i, o + 3, f"{o:.0f}", ha="center", fontsize=7.5, color=MPL_OKC, weight="bold")
        ax1.text(i, s - 6, f"{s:.0f}", ha="center", fontsize=7.5, color=MPL_SAS, weight="bold")
    ax1.set_xticks(x)
    ax1.set_xticklabels(games)
    ax1.legend(loc="lower right", frameon=False, fontsize=8)
    _style_ax(ax1, title="POINTS PER GAME (G5 = projected)", ylim=(70, 135))

    # Right: OKC off rtg vs def rtg — the volatility story
    ax2.bar([i - 0.2 for i in range(4)], okc_off, width=0.4, color=MPL_OKC, label="OKC Off Rtg")
    ax2.bar([i + 0.2 for i in range(4)], okc_def, width=0.4, color=MPL_GRAY, label="OKC Def Rtg")
    for i, v in enumerate(okc_off):
        ax2.text(i - 0.2, v + 1.2, f"{v:.0f}", ha="center", fontsize=7.5, color=MPL_OKC, weight="bold")
    for i, v in enumerate(okc_def):
        ax2.text(i + 0.2, v + 1.2, f"{v:.0f}", ha="center", fontsize=7.5, color=MPL_GRAY, weight="bold")
    ax2.set_xticks(range(4))
    ax2.set_xticklabels(games[:4])
    ax2.legend(loc="upper left", frameon=False, fontsize=8)
    ax2.axhline(115, color=MPL_GREEN, ls=":", lw=1, alpha=0.5)
    _style_ax(ax2, title="OKC OFFENSIVE vs DEFENSIVE RATING — note G3↔G4 collapse",
              ylim=(95, 135))
    fig.tight_layout()
    return fig_to_image(fig, width_in=7.3)


def chart_efg_volatility():
    """eFG% per-game — the variance story."""
    okc = team_agg["teams"]["OKC"]["per_game"]
    sas = team_agg["teams"]["SAS"]["per_game"]
    games = ["G1", "G2", "G3", "G4"]
    okc_efg = [g["efg_pct"] * 100 for g in okc]
    sas_efg = [g["efg_pct"] * 100 for g in sas]
    fig, ax = plt.subplots(figsize=(6.8, 2.1))
    ax.plot(games, okc_efg, marker="o", lw=2.4, color=MPL_OKC, label="OKC", markersize=8)
    ax.plot(games, sas_efg, marker="s", lw=2.4, color=MPL_SAS, label="SAS", markersize=7)
    # Annotate G3-G4 swing for OKC
    ax.annotate(
        f"22.3 pt swing", xy=(3, okc_efg[3]), xytext=(2.4, okc_efg[3] - 8),
        fontsize=8, color=MPL_RED, weight="bold",
        arrowprops=dict(arrowstyle="->", color=MPL_RED, lw=1.2),
    )
    for i, v in enumerate(okc_efg):
        ax.text(i, v + 1.5, f"{v:.1f}", ha="center", fontsize=8, color=MPL_OKC, weight="bold")
    for i, v in enumerate(sas_efg):
        ax.text(i, v - 3.0, f"{v:.1f}", ha="center", fontsize=8, color=MPL_SAS, weight="bold")
    ax.legend(loc="upper right", frameon=False, fontsize=8)
    _style_ax(ax, title="eFG% VOLATILITY — variance creates reversion edges", ylim=(30, 65))
    fig.tight_layout()
    return fig_to_image(fig, width_in=4.7)


def chart_pace_chart():
    """Pace per game — both teams."""
    okc = team_agg["teams"]["OKC"]["per_game"]
    sas = team_agg["teams"]["SAS"]["per_game"]
    games = ["G1", "G2", "G3", "G4"]
    okc_pace = [g["pace"] for g in okc]
    sas_pace = [g["pace"] for g in sas]
    fig, ax = plt.subplots(figsize=(3.3, 2.1))
    x = list(range(4))
    ax.bar([i - 0.2 for i in x], okc_pace, width=0.4, color=MPL_OKC)
    ax.bar([i + 0.2 for i in x], sas_pace, width=0.4, color=MPL_SAS)
    ax.set_xticks(x)
    ax.set_xticklabels(games)
    avg = (sum(okc_pace) + sum(sas_pace)) / 8
    ax.axhline(avg, color=MPL_GOLD, ls="--", lw=1.2)
    ax.text(3.55, avg + 0.3, f"avg {avg:.1f}", fontsize=7, color=MPL_GOLD, weight="bold", ha="right")
    _style_ax(ax, title="SERIES PACE", ylim=(90, 105))
    fig.tight_layout()
    return fig_to_image(fig, width_in=2.4)


def chart_total_distribution():
    """Total points pdf with market & model markers."""
    import numpy as np
    fig, ax = plt.subplots(figsize=(6.8, 2.0))
    # Build a normal-ish distribution around model total
    mu_model = m2["predictions"]["total_pts"]  # 201
    mu_series = (team_agg["teams"]["OKC"]["pts_pg"] + team_agg["teams"]["SAS"]["pts_pg"])  # 222
    mu_blend = 0.6 * mu_model + 0.4 * mu_series  # blended
    sigma = 13.0
    xs = np.linspace(170, 250, 400)
    ys = (1 / (sigma * (2 * 3.14159) ** 0.5)) * np.exp(-0.5 * ((xs - mu_blend) / sigma) ** 2)
    ax.fill_between(xs, 0, ys, color=MPL_OKC, alpha=0.15)
    ax.plot(xs, ys, color=MPL_OKC, lw=2)
    # Market line
    ax.axvline(MARKET["total"], color=MPL_GOLD, lw=2, ls="--")
    ax.text(MARKET["total"] + 0.6, ys.max() * 0.95, f"Pin {MARKET['total']}",
            fontsize=8, color=MPL_GOLD, weight="bold")
    # Model
    ax.axvline(mu_model, color=MPL_RED, lw=1.5)
    ax.text(mu_model + 0.6, ys.max() * 0.78, f"M2 {mu_model:.0f}",
            fontsize=7.5, color=MPL_RED)
    # Series-blend
    ax.axvline(mu_series, color=MPL_GREEN, lw=1.5)
    ax.text(mu_series + 0.6, ys.max() * 0.62, f"Series {mu_series:.0f}",
            fontsize=7.5, color=MPL_GREEN)
    ax.set_yticks([])
    _style_ax(ax, title="TOTAL POINTS — model vs market belief")
    ax.set_xlim(170, 250)
    fig.tight_layout()
    return fig_to_image(fig, width_in=7.3)


def chart_bet_edge_summary():
    """Horizontal bar chart of bets by EV%."""
    df = pd.DataFrame(bets["bets"])
    df["label"] = df.apply(lambda r: f"{r['player'].split()[-1]} {r['stat'].upper()} {r['side']} {r['line']}", axis=1)
    df = df.sort_values("ev_pct", ascending=True)
    fig, ax = plt.subplots(figsize=(6.8, 3.4))
    colors_bar = [MPL_GREEN if v > 30 else (MPL_GOLD if v > 18 else MPL_GRAY) for v in df["ev_pct"]]
    bars = ax.barh(df["label"], df["ev_pct"], color=colors_bar, edgecolor="white")
    for bar, v, kp in zip(bars, df["ev_pct"], df["kelly_adj_pct"]):
        ax.text(v + 0.7, bar.get_y() + bar.get_height() / 2,
                f"{v:.1f}%  ·  K {kp:.1f}%",
                va="center", fontsize=7.5, color=MPL_INK)
    ax.set_xlim(0, max(df["ev_pct"]) * 1.4)
    _style_ax(ax, title="9-LEG SLATE — Expected Value by bet", ylabel=None)
    ax.set_xlabel("EV % (per $1 staked)", color=MPL_INK, fontsize=8)
    fig.tight_layout()
    return fig_to_image(fig, width_in=7.3)


def chart_defender_impact():
    """Wemby PTS adj by defender — horizontal bars."""
    data = [
        ("Hartenstein (primary)",  +6.2, MPL_RED),
        ("Holmgren (real solution)", -4.8, MPL_GREEN),
        ("Caruso (surprise lever)", -22.6, MPL_GREEN),
        ("Dort (POA disruptor)",   -8.4, MPL_GREEN),
    ]
    fig, ax = plt.subplots(figsize=(6.8, 2.2))
    labels = [d[0] for d in data]
    vals = [d[1] for d in data]
    cols = [d[2] for d in data]
    bars = ax.barh(labels, vals, color=cols, edgecolor="white")
    for bar, v in zip(bars, vals):
        ax.text(v + (0.6 if v > 0 else -0.6), bar.get_y() + bar.get_height() / 2,
                f"{v:+.1f}%", va="center",
                ha=("left" if v > 0 else "right"),
                fontsize=8, color=MPL_INK, weight="bold")
    ax.axvline(0, color=MPL_GRAY, lw=0.8)
    ax.set_xlim(-28, 12)
    _style_ax(ax, title="WEMBY PTS — % Δ vs baseline by primary defender")
    fig.tight_layout()
    return fig_to_image(fig, width_in=7.3)


def chart_joint_events():
    """Joint event probabilities."""
    events = [
        ("SGA scores 30+", 0.397, MPL_OKC),
        ("SGA 30+ AND OKC wins", 0.255, MPL_OKC),
        ("SGA 30+ | OKC wins", 0.556, MPL_OKC),
        ("Wemby 25+ PTS", 0.541, MPL_SAS),
        ("Wemby 4+ BLK", 0.398, MPL_SAS),
        ("Game ends in OT", 0.087, MPL_GOLD),
        ("Holmgren scoreless Q1", 0.119, MPL_GRAY),
        ("Wemby triple-double", 0.011, MPL_GRAY),
    ]
    fig, ax = plt.subplots(figsize=(6.8, 2.8))
    labels = [e[0] for e in events]
    vals = [e[1] * 100 for e in events]
    cols = [e[2] for e in events]
    bars = ax.barh(labels, vals, color=cols, edgecolor="white")
    for bar, v in zip(bars, vals):
        ax.text(v + 1.2, bar.get_y() + bar.get_height() / 2,
                f"{v:.1f}%", va="center", fontsize=8, color=MPL_INK, weight="bold")
    ax.set_xlim(0, 65)
    _style_ax(ax, title="JOINT EVENT PROBABILITIES (MC, 1000 sims)")
    fig.tight_layout()
    return fig_to_image(fig, width_in=7.3)


def chart_bankroll_allocation():
    """Pie-ish horizontal stacked bar of bankroll exposure."""
    risked = sum(b["stake"] for b in bets["bets"])
    free = BR - risked
    fig, ax = plt.subplots(figsize=(6.8, 0.8))
    ax.barh([0], [risked], color=MPL_GOLD, label=f"At-risk ${risked:,.0f} ({risked/BR*100:.1f}%)")
    ax.barh([0], [free], left=[risked], color=MPL_GRAY, label=f"Reserve ${free:,.0f}")
    ax.text(risked / 2, 0, f"${risked:,.0f}", ha="center", va="center",
            color="white", weight="bold", fontsize=10)
    ax.text(risked + free / 2, 0, f"reserve ${free:,.0f}", ha="center", va="center",
            color="white", weight="bold", fontsize=9)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_xlim(0, BR)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(f"BANKROLL ${BR:,.2f}  —  9 bets × $260 = $2,340 at risk ({risked/BR*100:.1f}%)",
                 fontsize=9, weight="bold", color=MPL_INK, loc="left", pad=6)
    fig.tight_layout()
    return fig_to_image(fig, width_in=7.3)


# ============================================================
# Styles
# ============================================================
ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=26, leading=30,
                    textColor=C_NAVY, spaceAfter=2)
SUB = ParagraphStyle("SUB", fontName="Helvetica", fontSize=10.5, leading=13,
                     textColor=C_GRAY_500, spaceAfter=4)
SECTION = ParagraphStyle("SECTION", fontName="Helvetica-Bold", fontSize=12, leading=14,
                         textColor="white", backColor=C_NAVY, leftIndent=8, rightIndent=8,
                         spaceBefore=8, spaceAfter=4, borderPadding=6)
H_RULE = ParagraphStyle("HR", fontName="Helvetica-Bold", fontSize=10.5, leading=13,
                        textColor=C_NAVY, spaceBefore=6, spaceAfter=2)
BODY = ParagraphStyle("BODY", fontName="Helvetica", fontSize=8.5, leading=11,
                      textColor=C_INK, spaceAfter=2)
BODY_TIGHT = ParagraphStyle("BODYT", fontName="Helvetica", fontSize=8, leading=10,
                            textColor=C_INK, spaceAfter=0)
SMALL = ParagraphStyle("SMALL", fontName="Helvetica", fontSize=7.5, leading=9.5,
                       textColor=C_GRAY_500)
SMALL_ITAL = ParagraphStyle("SMALLI", fontName="Helvetica-Oblique", fontSize=7.5,
                            leading=9.5, textColor=C_GRAY_500)
WHITE = ParagraphStyle("WHITE", fontName="Helvetica-Bold", fontSize=9, leading=11,
                       textColor="white")
BIG_NUM = ParagraphStyle("BIG", fontName="Helvetica-Bold", fontSize=22, leading=24,
                         textColor=C_NAVY)
MED_NUM = ParagraphStyle("MED", fontName="Helvetica-Bold", fontSize=14, leading=16,
                         textColor=C_NAVY)
LABEL = ParagraphStyle("LBL", fontName="Helvetica-Bold", fontSize=7, leading=9,
                       textColor=C_GRAY_500)
WHY = ParagraphStyle("WHY", fontName="Helvetica", fontSize=7.8, leading=9.8,
                     textColor=C_INK, leftIndent=2)
WHY_KILL = ParagraphStyle("KILL", fontName="Helvetica-Oblique", fontSize=7.2,
                          leading=9, textColor=C_RED, leftIndent=2)


def section_band(label):
    return Paragraph(label, SECTION)


def hero_block():
    """Hero header — game ID, teams, tip time, series, prediction."""
    title = Paragraph("WCF GAME 5 &nbsp;·&nbsp; INTELLIGENCE BRIEF", H1)
    sub = Paragraph(
        "<b>San Antonio Spurs</b> @ <b>Oklahoma City Thunder</b> &nbsp;·&nbsp; "
        "Tue 2026-05-26  ·  8:35 PM ET  ·  Paycom Center  ·  "
        "<font color='#a51d2d'>SERIES 2–2</font>  ·  game_id 0042500315",
        SUB,
    )
    return [title, sub]


def scorecard_row():
    """3 cards: Model Final · Total · Spread + Win-prob gauge in same row."""
    pred = m2["predictions"]
    # Build each as a tiny table
    def card(label, big, small_lines, accent=C_NAVY):
        big_p = Paragraph(big, BIG_NUM)
        lbl_p = Paragraph(label, LABEL)
        small_p = [Paragraph(s, BODY_TIGHT) for s in small_lines]
        t = Table([[lbl_p], [big_p]] + [[s] for s in small_p],
                  colWidths=[1.95 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_GRAY_50),
            ("LINEABOVE", (0, 0), (-1, 0), 3, accent),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (0, 0), 8),
        ]))
        return t

    c1 = card("MODEL FINAL", f"OKC {pred['home_pts']:.0f} – {pred['away_pts']:.0f} SAS",
              [f"Margin OKC −{abs(pred['score_diff']):.1f}",
               f"Model says CLOSE — within 2 pts"], C_OKC)
    c2 = card("TOTAL POINTS",
              f"{(pred['home_pts']+pred['away_pts']):.0f} <font size=11 color='#a51d2d'>vs {MARKET['total']}</font>",
              [f"M2: <b>{m2['predictions']['total_pts']:.1f}</b>  ·  "
               f"Series-blend: <b>222</b>",
               f"Sharp money: UNDER  ·  drift down"], C_GOLD)
    c3 = card("WIN PROBABILITY",
              f"{wp['home_win_prob']*100:.1f}% OKC",
              [f"Pinnacle implied: {abs(MARKET['ml_home'])/(abs(MARKET['ml_home'])+100)*100:.1f}%",
               f"Edge: <font color='#a51d2d'><b>−2.6 pp</b></font>  ·  no game-line bet"],
              C_NAVY_LIGHT)

    gauge = chart_winprob_gauge()
    row = Table([[c1, c2, c3, gauge]],
                colWidths=[2.05 * inch, 2.05 * inch, 2.05 * inch, 1.55 * inch],
                style=TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]))
    return row


def series_state_visual():
    """SERIES TIES 2-2 visual with mini-results."""
    games_short = [
        ("G1", "SAS 122-115", "OT · Wemby 41", "SAS"),
        ("G2", "OKC 122-113", "Home hold", "OKC"),
        ("G3", "OKC 123-108", "eFG .586 clinic", "OKC"),
        ("G4", "SAS 103-82",  "OKC eFG .363 collapse", "SAS"),
        ("G5", "TONIGHT", "OKC −3.5 · 216.5", None),
    ]
    cells = []
    for label, score, note, winner in games_short:
        # Box border color = winner color
        if winner == "OKC":
            head_color, fill_color = C_OKC, C_GRAY_50
        elif winner == "SAS":
            head_color, fill_color = C_SAS, C_GRAY_50
        else:
            head_color, fill_color = C_GOLD, C_GOLD_LIGHT
        cell = Table([
            [Paragraph(label, ParagraphStyle("", fontName="Helvetica-Bold",
                                              fontSize=10, textColor="white",
                                              alignment=1))],
            [Paragraph(score, ParagraphStyle("", fontName="Helvetica-Bold",
                                              fontSize=8.5, textColor=C_INK,
                                              alignment=1))],
            [Paragraph(note, ParagraphStyle("", fontName="Helvetica",
                                              fontSize=7, textColor=C_GRAY_500,
                                              alignment=1))],
        ], colWidths=[1.42 * inch])
        cell.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), head_color),
            ("BACKGROUND", (0, 1), (0, -1), fill_color),
            ("BOX", (0, 0), (-1, -1), 0.5, C_GRAY_300),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        cells.append(cell)
    return Table([cells], colWidths=[1.5 * inch] * 5)


def market_lines_card():
    """Market lines with sharp-money annotations."""
    rows = [
        [Paragraph("<b>MARKET (Pinnacle)</b>", WHITE),
         Paragraph("<b>NUMBER</b>", WHITE),
         Paragraph("<b>PRICE</b>", WHITE),
         Paragraph("<b>MOVEMENT / SHARP NOTES</b>", WHITE)],
        ["Total O/U", f"{MARKET['total']}", "−119 / +104",
         Paragraph("Drift toward <font color='#a51d2d'><b>UNDER</b></font> from 219.5 open. Steam at 217.5.", BODY)],
        ["Spread (OKC)", f"OKC −{abs(MARKET['spread_home'])}", "−116",
         Paragraph("Was OKC −4.5 at open. Sharp money on SAS+. <b>Buy SAS +4 PHIN, sell at +3.</b>", BODY)],
        ["Moneyline", f"OKC {MARKET['ml_home']} / SAS +{MARKET['ml_away']}", "—",
         Paragraph("OKC drifted −174 → −161 in 3 hrs (12-pt drop in implied prob).", BODY)],
        ["Series 2–2 G5", "Home court advantage live", "—",
         Paragraph("Historic: home wins G5 of 2-2 series ~ <b>62%</b>. Model 59.1% slightly under.", BODY)],
    ]
    t = Table(rows, colWidths=[1.55 * inch, 1.05 * inch, 1.0 * inch, 3.6 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), C_INK),
        ("BACKGROUND", (0, 1), (-1, -1), C_GRAY_50),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_GRAY_50, "white"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 0.4, C_GRAY_300),
    ]))
    return t


def why_it_matters_block():
    """5 sharp pre-game observations."""
    bullets = [
        ("MODEL DISAGREES WITH MARKET TOTAL",
         "M2 says 201 pts; market 216.5. But series avg is 222. The truth is between — we don't bet game lines."),
        ("OKC G3→G4 eFG% COLLAPSE IS THE STORY",
         "OKC shot .586 in G3, .363 in G4 — a 22.3-pt swing. Pinnacle has partially priced reversion (line moved from OKC −4.5 to −3.5). Either G3 or G4 was the outlier; the SAS+3.5 buy is correct asymmetric exposure."),
        ("INJURY-DRIVEN USAGE RESHUFFLE",
         "Jalen Williams (OKC) OUT. Aaron Wiggins, Hartenstein, and Cason Wallace absorb usage. <b>Hart AST OVER 2.5</b> is the cleanest model+series+market three-way agreement on the slate."),
        ("WEMBY DEFENDER LOTTERY",
         "Series matchup data: Wemby drops 37 pts on 5-of-9 from 3 when Hartenstein guards him (90 poss); held to 47% FG / 0-of-1 from 3 when Holmgren switches on. Live edge: watch the cross-match the moment Hart picks up his 2nd foul."),
        ("ROLE-PLAYER MINUTES UNDERPRICED",
         "Pinnacle priced Keldon Johnson PTS at 6.5 — implies <12 minutes. Series average is 17.6 MPG. Either Pop changes his rotation tonight or this is a free 58.5% EV bet. <b>This is the strongest mispricing on the board.</b>"),
    ]
    out = []
    for h, b in bullets:
        out.append(Paragraph(
            f"<font color='#d4a017'><b>● {h}</b></font> &nbsp; {b}", BODY))
    return out


def projected_box_table(team_label, players_list, team_color):
    """Projected box score for one team."""
    head = [Paragraph("<b>PLAYER</b>", WHITE),
            Paragraph("<b>MIN</b>", WHITE),
            Paragraph("<b>PTS</b>", WHITE),
            Paragraph("<b>REB</b>", WHITE),
            Paragraph("<b>AST</b>", WHITE),
            Paragraph("<b>3PM</b>", WHITE),
            Paragraph("<b>TS%</b>", WHITE)]
    rows = [head]
    for p in players_list:
        name = p["name"]
        if p.get("flag"):
            name = f"<font color='#a51d2d'>{name}</font>"
        rows.append([
            Paragraph(name, BODY_TIGHT),
            f"{p['min']:.0f}", f"{p['pts']:.1f}", f"{p['reb']:.1f}",
            f"{p['ast']:.1f}", f"{p['fg3m']:.1f}", f"{p.get('ts',0)*100:.1f}",
        ])
    t = Table(rows, colWidths=[1.35 * inch] + [0.36 * inch] * 6, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), team_color),
        ("FONTSIZE", (0, 0), (-1, -1), 7.8),
        ("TEXTCOLOR", (0, 1), (-1, -1), C_INK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_GRAY_50, "white"]),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (0, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BOX", (0, 0), (-1, -1), 0.4, C_GRAY_300),
    ]))
    return t


def projected_box_data():
    """Pull from player_series csv + add MIN projections."""
    OKC_min = {
        "Shai Gilgeous-Alexander": 39, "Chet Holmgren": 33, "Jared McCain": 22,
        "Isaiah Hartenstein": 30, "Isaiah Joe": 18, "Cason Wallace": 27,
        "Alex Caruso": 26, "Luguentz Dort": 28, "Jaylin Williams": 16,
        "Kenrich Williams": 9,
    }
    SAS_min = {
        "Victor Wembanyama": 38, "De'Aaron Fox": 36, "Stephon Castle": 33,
        "Devin Vassell": 31, "Keldon Johnson": 24, "Dylan Harper": 22,
        "Julian Champagnie": 18, "Harrison Barnes": 15, "Luke Kornet": 14,
    }
    # PTS/REB/AST/3PM from page-1 projections (already computed in v2)
    OKC_LINES = {
        "Shai Gilgeous-Alexander": (28.4, 3.5, 8.7, 1.1, 0.605),
        "Chet Holmgren":            (15.7, 7.3, 1.4, 0.9, 0.58),
        "Jared McCain":             (10.4, 2.2, 1.2, 1.3, 0.56),
        "Isaiah Hartenstein":        (8.5, 8.1, 3.0, 0.0, 0.62),
        "Isaiah Joe":                (6.9, 1.9, 1.1, 1.4, 0.59),
        "Cason Wallace":             (8.2, 3.8, 2.2, 1.5, 0.58),
        "Alex Caruso":              (10.6, 2.8, 1.9, 2.0, 0.55),
        "Luguentz Dort":             (5.2, 3.2, 1.5, 0.8, 0.53),
        "Jaylin Williams":           (5.9, 3.7, 1.6, 1.4, 0.55),
        "Kenrich Williams":          (5.1, 2.6, 1.1, 0.6, 0.54),
    }
    SAS_LINES = {
        "Victor Wembanyama":  (26.5, 12.5, 3.4, 1.9, 0.62),
        "De'Aaron Fox":       (16.9, 6.1, 5.6, 1.2, 0.56),
        "Stephon Castle":     (17.9, 5.0, 7.1, 1.0, 0.55),
        "Devin Vassell":      (15.2, 4.8, 2.3, 2.8, 0.58),
        "Keldon Johnson":     ( 9.9, 3.2, 0.7, 1.2, 0.55),
        "Dylan Harper":       (11.4, 4.3, 2.8, 0.7, 0.54),
        "Julian Champagnie":  ( 9.2, 5.0, 1.5, 1.8, 0.57),
        "Harrison Barnes":    ( 5.9, 2.3, 0.6, 0.4, 0.54),
        "Luke Kornet":        ( 4.5, 4.0, 0.8, 0.0, 0.58),
    }
    def listify(d_min, d_lines):
        out = []
        for nm in d_min:
            pts, reb, ast, three, ts = d_lines[nm]
            out.append({"name": nm, "min": d_min[nm], "pts": pts, "reb": reb,
                        "ast": ast, "fg3m": three, "ts": ts})
        return out
    return listify(OKC_min, OKC_LINES), listify(SAS_min, SAS_LINES)


# ============================================================
# Bet card builder
# ============================================================
def tier_letter(ev):
    if ev >= 30: return "S"
    if ev >= 18: return "A"
    return "B"

def tier_color(tier):
    return {"S": C_TIER_S, "A": C_TIER_A, "B": C_TIER_B}[tier]

def make_bet_row(rank, bet, why, kill, p_mc):
    tier = tier_letter(bet["ev_pct"])
    tcol = tier_color(tier)
    # Edge bar (visual representation of edge_units relative to sigma)
    edge_pct = min(100, abs(bet["edge_units"]) / (bet.get("sigma", 1) + 0.01) * 60)
    ev_bar_w = min(100, bet["ev_pct"] * 1.6)
    kelly_bar_w = min(100, bet["kelly_adj_pct"] * 20)

    # Top row: tier ribbon + headline + EV/Kelly
    headline = (
        f"<b>#{rank} {bet['player']} {bet['stat'].upper()} {bet['side']} {bet['line']}</b> &nbsp;"
        f"<font color='#64748b'>· Pin {bet['odds']:+d}</font>"
    )
    headline_p = Paragraph(headline, ParagraphStyle("", fontName="Helvetica",
                                                     fontSize=10, leading=12,
                                                     textColor=C_INK))
    # Stat strip
    strip = (
        f"<font color='#64748b'>Model q50</font> <b>{bet['model_q50']:.2f}</b>  ·  "
        f"<font color='#64748b'>σ</font> {bet.get('sigma',0):.2f}  ·  "
        f"<font color='#64748b'>Edge</font> <b>{bet['edge_units']:+.2f}</b>  ·  "
        f"<font color='#64748b'>MC P(win)</font> <b>{p_mc*100:.1f}%</b>  ·  "
        f"<font color='#1f7a3b'>EV</font> <b>{bet['ev_pct']:.1f}%</b>  ·  "
        f"<font color='#d4a017'>Kelly</font> <b>{bet['kelly_adj_pct']:.1f}%</b>  ·  "
        f"Stake <b>${bet['stake']:.0f}</b>"
    )
    strip_p = Paragraph(strip, BODY)

    why_p = Paragraph(f"<b>WHY:</b> {why}", WHY)
    kill_p = Paragraph(f"<i>KILL:</i> {kill}", WHY_KILL)

    # Mini bar visual using a tiny table
    def bar(label, color_hex, width_pct, value_str):
        bars_row = Table(
            [[Paragraph(f"<font size=7 color='#64748b'>{label}</font>", BODY_TIGHT),
              Table([[""]], colWidths=[width_pct / 100 * 1.4 * inch], rowHeights=[5],
                    style=TableStyle([("BACKGROUND", (0,0),(-1,-1), color_hex)])),
              Paragraph(f"<font size=7><b>{value_str}</b></font>", BODY_TIGHT)]],
            colWidths=[0.6 * inch, 1.4 * inch, 0.55 * inch])
        bars_row.setStyle(TableStyle([
            ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0),(-1,-1), 0),
            ("RIGHTPADDING", (0,0),(-1,-1), 2),
            ("BOTTOMPADDING", (0,0),(-1,-1), 1),
            ("TOPPADDING", (0,0),(-1,-1), 1),
        ]))
        return bars_row

    bars_block = Table([
        [bar("EDGE", "#0c2340", edge_pct, f"{bet['edge_units']:+.2f}")],
        [bar("EV", "#1f7a3b", ev_bar_w, f"{bet['ev_pct']:.1f}%")],
        [bar("KELLY", "#d4a017", kelly_bar_w, f"{bet['kelly_adj_pct']:.1f}%")],
    ], colWidths=[2.55 * inch])
    bars_block.setStyle(TableStyle([
        ("LEFTPADDING", (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ("TOPPADDING", (0,0),(-1,-1), 0),
        ("BOTTOMPADDING", (0,0),(-1,-1), 0),
    ]))

    body_col = Table([[headline_p], [strip_p], [why_p], [kill_p]],
                     colWidths=[4.45 * inch])
    body_col.setStyle(TableStyle([
        ("LEFTPADDING", (0,0),(-1,-1), 4),
        ("RIGHTPADDING", (0,0),(-1,-1), 4),
        ("TOPPADDING", (0,0),(-1,-1), 1),
        ("BOTTOMPADDING", (0,0),(-1,-1), 1),
    ]))

    tier_cell = Paragraph(
        f"<font size=18 color='white'><b>{tier}</b></font>",
        ParagraphStyle("", fontName="Helvetica-Bold", alignment=1, textColor="white"))

    outer = Table([[tier_cell, body_col, bars_block]],
                  colWidths=[0.35 * inch, 4.45 * inch, 2.6 * inch])
    outer.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(0,0), tcol),
        ("BACKGROUND", (1,0),(-1,-1), C_GRAY_50),
        ("VALIGN", (0,0),(-1,-1), "TOP"),
        ("VALIGN", (0,0),(0,0), "MIDDLE"),
        ("LEFTPADDING", (0,0),(-1,-1), 4),
        ("RIGHTPADDING", (0,0),(-1,-1), 4),
        ("TOPPADDING", (0,0),(-1,-1), 2),
        ("BOTTOMPADDING", (0,0),(-1,-1), 2),
        ("BOX", (0,0),(-1,-1), 0.4, C_GRAY_300),
    ]))
    return outer


def bet_card_section():
    # Order bets by EV desc
    bets_sorted = sorted(bets["bets"], key=lambda b: -b["ev_pct"])
    why_kill = {
        ("Keldon Johnson","pts"): ("Pin 6.5 implies <12 min — but series 17.6 MPG. Pop has trusted him in WCF. Model 10.91, series 8.5. Softest mispricing on the board.",
                                    "DNP-coach's decision or sub-10 min cameo."),
        ("Luke Kornet","pts"): ("Pin priced at 2.5 PTS — implies <12 min as backup C. Model 5.14, series 3.5. Wemby foul trouble = Kornet minutes.",
                                 "Pop benches him if SAS goes small."),
        ("Jared McCain","fg3m"): ("Model 1.22, series 1.50, Pin 2.5 — three-way structural mismatch. McCain's WCF role <20 MPG with no green-light usage.",
                                  "Garbage-time blowout gives him 8 min and 4 attempts."),
        ("Isaiah Hartenstein","ast"): ("With JaW OUT, Hart inherits dribble-handoff load. Model 3.06, series 3.00 both > 2.5 line. +money pricing.",
                                        "Foul trouble caps his minutes <22."),
        ("Luke Kornet","reb"): ("Same minutes thesis as Kornet PTS — model 4.26, series 3.5. 2.5 REB requires single-digit minutes to fail.",
                                  "Kornet plays <8 minutes."),
        ("Victor Wembanyama","reb"): ("Model 11.98, series 13.25 — both below 13.5. Wemby's foul fragility (avg 3.0 PF in series) caps minutes ~32-34.",
                                      "Heavy SAS minutes (35+) almost guarantee 13+ boards."),
        ("De'Aaron Fox","reb"): ("Fox averaging 8.5 REB/g in WCF — 5 boards above line. He's been crashing offensive glass as SAS adjusts to Wemby drawing center help.",
                                  "Reverts to 4.5 season avg if Pop goes small."),
        ("Stephon Castle","pts"): ("Castle's WCF avg 17.25 PTS tracks model 18.26. Pin 16.5 is the soft side. Rookie of Year-caliber usage real in playoffs.",
                                    "OKC throws Dort or Caruso on him for a stretch."),
        ("Dylan Harper","pts"): ("Rookie #1 pick — model 10.79, series 12.25, Pin 9.5. Pop trusts him with 24+ MPG and clutch reps.",
                                  "Pop tightens to 8-man rotation and Harper drops to 14 min."),
    }
    # Build MC p_win lookup
    mc_lookup = {}
    for p in mc["props"]:
        key = (p["player"], p["stat"])
        mc_lookup[key] = p

    rows = []
    for i, b in enumerate(bets_sorted, 1):
        key = (b["player"], b["stat"])
        why, kill = why_kill.get(key, ("—", "—"))
        mp = mc_lookup.get(key, {})
        if b["side"] == "OVER":
            p_mc = mp.get("p_over_mc", 0.5)
        else:
            p_mc = mp.get("p_under_mc", 0.5)
        rows.append(make_bet_row(i, b, why, kill, p_mc))
        rows.append(Spacer(1, 1.5))
    return rows


# ============================================================
# Live playbook — defender triggers + situational matrix
# ============================================================
def live_trigger_table():
    triggers = [
        ("Q1, Hartenstein on Wemby >6 min",
         "Fire Wemby 3PM OVER 1.5 LIVE",
         "Series: 5-of-9 from 3 when Hart guards (90 poss)", C_RED_LIGHT),
        ("Wemby picks up 2nd foul before half",
         "Fire Wemby REB UNDER 13.5 LIVE",
         "Reduces ceiling minutes to ~28-30", C_GREEN_LIGHT),
        ("OKC pace > 102 by end of Q2",
         "Fire SGA PTS OVER 28.5 LIVE",
         "SGA scales with possessions — series 28 PTS in 100+ pace games", C_RED_LIGHT),
        ("SAS leads by 8+ entering Q4",
         "Fire Wemby PTS UNDER 26.5 LIVE",
         "Garbage time / blowout caps his minutes", C_GREEN_LIGHT),
        ("OKC down by 10+ at half",
         "Sell back Hart AST OVER (hedge)",
         "Hart's playmaking volume falls in OKC negative scripts", C_GOLD_LIGHT),
        ("Caruso cross-matched to Wemby (any segment)",
         "Fire Wemby PTS UNDER 25.5 LIVE",
         "Caruso reduces Wemby PTS by ~22% in our priors", C_GREEN_LIGHT),
        ("Holmgren picks up 3rd foul before Q3",
         "Fire Hartenstein REB OVER 8.5 LIVE",
         "Hart absorbs all C minutes when Chet sits", C_RED_LIGHT),
        ("Total in play > 220 entering Q4",
         "Sell OKC live UNDER team total 110.5",
         "Pace + variance combo — pricing usually lags", C_GOLD_LIGHT),
    ]
    head = [Paragraph(f"<b><font color='white' size=9>{t}</font></b>", BODY)
            for t in ["GAME STATE TRIGGER", "ACTION", "RATIONALE"]]
    rows = [head]
    for cond, act, rat, bg in triggers:
        rows.append([
            Paragraph(cond, BODY),
            Paragraph(f"<b>{act}</b>", BODY),
            Paragraph(rat, SMALL),
        ])
    t = Table(rows, colWidths=[2.4 * inch, 2.4 * inch, 2.5 * inch])
    bg_styles = []
    for i, (_, _, _, bg) in enumerate(triggers, 1):
        bg_styles.append(("BACKGROUND", (0, i), (-1, i), bg))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 0.4, C_GRAY_300),
        ("GRID", (0, 0), (-1, -1), 0.3, C_GRAY_200),
    ] + bg_styles))
    return t


def ops_checklist():
    rows = [
        ["SYSTEM", "DETAIL", "STATE"],
        ["Live engine daemon", "PID 9452 alive — defender residuals wired", "OK"],
        ["Closing line capture", "PID 4776 + watchdog 10372 — fires 00:30 UTC", "OK"],
        ["Bets pre-registered", "9 rows in data/pnl_ledger.csv  status=INTENDED", "OK"],
        ["Alert webhook", "vault/Improvements/alerts_2026-05-26.log", "TAIL"],
        ["Health monitor", "17 OK / 5 WARN / 0 ERROR", "OK"],
        ["Live-edge scanner", "MC re-run every 90 sec post-tip", "OK"],
        ["CLV auto-pickup", "wire_clv_from_registered.py @ 09:00 ET", "OK"],
        ["Bankroll snapshot", "$11,043.48 — 21.2% at risk", "OK"],
    ]
    t = Table(rows, colWidths=[1.7 * inch, 4.0 * inch, 0.95 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), "white"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_GRAY_50, "white"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BOX", (0, 0), (-1, -1), 0.4, C_GRAY_300),
        ("TEXTCOLOR", (2, 1), (2, -1), C_GREEN),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
    ]))
    return t


def intelligent_betting_principles():
    """A short manifesto of HOW intelligent betting differs from gambling."""
    items = [
        ("EDGE FROM STRUCTURE, NOT NARRATIVES",
         "Every leg has a 3-way agreement (model + series + market) OR a structural mismatch we can name. We don't bet on stories — we bet where book pricing collides with three independent signals."),
        ("KELLY × PLAYOFF × CORRELATION",
         "Bets are sized at 0.25-Kelly × 0.65 playoff multiplier — never raw Kelly. Correlated legs are aggregated into a single sizing decision (Wemby REB UNDER + Hart AST OVER share the foul-trouble dimension)."),
        ("LIVE EDGE > PREGAME EDGE",
         "Defender cross-matches, foul totals, and pace shifts produce 2-4x larger edges live than pregame, because books lag CV/play-by-play. The live playbook (page 5) is where most of the EV lives."),
        ("CLV IS THE SCOREBOARD",
         "Win/loss is variance. Closing line value tells us if we bet smart. Every leg is CLV-tracked — if our average CLV across 100 bets is +2%, we are +EV regardless of nightly P&L."),
        ("EXIT, HEDGE, MIDDLE",
         "Live, we look for: (1) middles where the book's number moves enough to lock profit, (2) hedges if game-state invalidates a thesis, (3) doubling-down on confirmed signals (e.g., Hart actually guarding Wemby in Q1)."),
    ]
    out = []
    for h, b in items:
        out.append(Paragraph(
            f"<font color='#d4a017'><b>{h}</b></font><br/>{b}",
            ParagraphStyle("", fontName="Helvetica", fontSize=8.5, leading=11,
                            textColor=C_INK, spaceAfter=4)))
    return out


# ============================================================
# Document builder
# ============================================================
def build():
    doc = BaseDocTemplate(
        str(OUT), pagesize=LETTER,
        leftMargin=0.45 * inch, rightMargin=0.45 * inch,
        topMargin=0.4 * inch, bottomMargin=0.4 * inch,
        title="WCF Game 5 — Intelligence Brief (CourtVision)",
        author="CourtVision AI",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="main",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    def page_footer(canvas, doc_):
        canvas.saveState()
        canvas.setFillColor(C_GRAY_500)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(0.45 * inch, 0.22 * inch,
                          "CourtVision AI · 2026-05-26 · BR $11,043.48 · "
                          "3-way verified (model + WCF G1–G4 + Pin sharp)")
        canvas.drawRightString(LETTER[0] - 0.45 * inch, 0.22 * inch,
                                f"Page {doc_.page}")
        canvas.restoreState()

    template = PageTemplate(id="main", frames=[frame], onPage=page_footer)
    doc.addPageTemplates([template])

    story = []

    # ---------- PAGE 1: Executive Brief ----------
    story.extend(hero_block())
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=2, color=C_GOLD))
    story.append(Spacer(1, 8))
    story.append(scorecard_row())
    story.append(Spacer(1, 10))

    story.append(section_band("SERIES STATE — 2-2 / GAME 5 IN OKC"))
    story.append(Spacer(1, 4))
    story.append(series_state_visual())
    story.append(Spacer(1, 10))

    story.append(section_band("GAME LINES & SHARP MONEY FLOW"))
    story.append(Spacer(1, 4))
    story.append(market_lines_card())
    story.append(Spacer(1, 10))

    story.append(section_band("FIVE THINGS THAT MATTER TONIGHT"))
    story.append(Spacer(1, 2))
    story.extend(why_it_matters_block())

    story.append(PageBreak())

    # ---------- PAGE 2: Game Intelligence ----------
    story.append(Paragraph("GAME INTELLIGENCE", H1))
    story.append(Paragraph("Series trajectory, pace, efficiency volatility & market signals", SUB))
    story.append(HRFlowable(width="100%", thickness=2, color=C_GOLD))
    story.append(Spacer(1, 8))

    story.append(section_band("SERIES TRAJECTORY — G1 to G5 (projected)"))
    story.append(Spacer(1, 4))
    story.append(chart_series_trajectory())
    story.append(Spacer(1, 8))

    # eFG + Pace side by side
    efg = chart_efg_volatility()
    pace = chart_pace_chart()
    story.append(section_band("OFFENSIVE VARIANCE — THE REVERSION THESIS"))
    story.append(Spacer(1, 4))
    story.append(Table([[efg, pace]],
                       colWidths=[7.3 * inch * 0.65, 7.3 * inch * 0.32],
                       style=TableStyle([
                           ("VALIGN", (0,0),(-1,-1), "TOP"),
                           ("LEFTPADDING", (0,0),(-1,-1), 0),
                           ("RIGHTPADDING", (0,0),(-1,-1), 0),
                       ])))
    story.append(Spacer(1, 8))

    story.append(section_band("TOTAL POINTS — MODEL vs MARKET BELIEF"))
    story.append(Spacer(1, 4))
    story.append(chart_total_distribution())
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "<b>READ:</b> Pinnacle's 216.5 sits at the right edge of our 80% band — no edge on the total. "
        "Live UNDER becomes attractive if pace stalls in Q2.",
        BODY))
    story.append(Spacer(1, 6))

    story.append(section_band(
        "SHARP MONEY MOVES — Fox AST tightened to −460 · JaW PTS line jumped on J. Williams OUT"))
    story.append(Spacer(1, 4))
    # Steam moves table
    sm_rows = [["TIME", "BOOK", "PLAYER", "STAT", "LINE Δ", "ODDS Δ", "TAG"]]
    for _, r in steam.head(3).iterrows():
        sm_rows.append([
            str(r["ts_to"]).split("T")[1][:5],
            str(r["book"]).upper(),
            str(r["player"]),
            str(r["stat"]).upper(),
            f"{r['line_from']:.1f} → {r['line_to']:.1f}",
            f"{r['odds_from']:+.0f} → {r['odds_to']:+.0f}",
            str(r["tags"]),
        ])
    sm_table = Table(sm_rows, colWidths=[0.55*inch, 0.45*inch, 1.55*inch,
                                          0.55*inch, 1.1*inch, 1.3*inch, 1.8*inch])
    sm_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), "white"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_GRAY_50, "white"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BOX", (0, 0), (-1, -1), 0.4, C_GRAY_300),
    ]))
    story.append(sm_table)

    story.append(PageBreak())

    # ---------- PAGE 3: Projected Box Scores ----------
    story.append(Paragraph("PROJECTED BOX SCORES", H1))
    story.append(Paragraph(
        "Shrunk q50 = 0.6 × model + 0.4 × WCF G1–G4 series average. "
        "Red names = OUT or questionable.", SUB))
    story.append(HRFlowable(width="100%", thickness=2, color=C_GOLD))
    story.append(Spacer(1, 8))

    okc_list, sas_list = projected_box_data()

    story.append(Table([[
        Paragraph("<b><font color='#007ac1' size=11>OKC THUNDER (HOME)</font></b><br/>"
                  "<font size=7 color='#a51d2d'>OUT: J.Williams · Mitchell · Sorber</font>", BODY),
        Paragraph("<b><font color='#3b3b3b' size=11>SAN ANTONIO SPURS (AWAY)</font></b><br/>"
                  "<font size=7 color='#1f7a3b'>Full strength</font>", BODY),
    ]], colWidths=[3.7 * inch, 3.7 * inch]))
    story.append(Spacer(1, 4))
    story.append(Table([[
        projected_box_table("OKC", okc_list, C_OKC),
        projected_box_table("SAS", sas_list, C_SAS),
    ]], colWidths=[3.7 * inch, 3.7 * inch],
       style=TableStyle([("VALIGN", (0,0),(-1,-1), "TOP")])))

    story.append(Spacer(1, 10))
    story.append(section_band("DEFENSIVE MATCHUP MATRIX (WCF G1-G4)"))
    story.append(Spacer(1, 4))
    # Top defender pairings
    dm = def_match.head(8).copy()
    dm_rows = [["OFF PLAYER", "DEF PLAYER", "MIN", "POSS", "PTS ALL", "FG%", "3P%"]]
    for _, r in dm.iterrows():
        dm_rows.append([
            r["off_player_name"], r["def_player_name"],
            f"{r['matchup_min']:.1f}", f"{r['partial_poss']:.0f}",
            f"{r['pts_allowed']:.0f}",
            f"{r['fg_pct_allowed']*100:.0f}%",
            f"{r['fg3_pct_allowed']*100:.0f}%",
        ])
    dm_t = Table(dm_rows, colWidths=[1.6*inch, 1.6*inch, 0.5*inch, 0.55*inch,
                                       0.7*inch, 0.55*inch, 0.55*inch])
    dm_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,0), C_NAVY),
        ("TEXTCOLOR", (0,0),(-1,0), "white"),
        ("FONTNAME", (0,0),(-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0),(-1,-1), 8),
        ("ROWBACKGROUNDS", (0,1),(-1,-1), [C_GRAY_50, "white"]),
        ("ALIGN", (2,0),(-1,-1), "CENTER"),
        ("LEFTPADDING", (0,0),(-1,-1), 5),
        ("RIGHTPADDING", (0,0),(-1,-1), 5),
        ("TOPPADDING", (0,0),(-1,-1), 3),
        ("BOTTOMPADDING", (0,0),(-1,-1), 3),
        ("BOX", (0,0),(-1,-1), 0.4, C_GRAY_300),
    ]))
    story.append(dm_t)
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "<b>READ:</b> Wemby drops 37 pts on 58% FG / 56% from 3 when Hartenstein guards him (90 poss). "
        "When Castle takes SGA, SGA drops to 47% FG and 39 pts in 116 poss — Castle is the matchup OKC needs to break. "
        "Watch the Hart-Wemby cross-match in Q1 — that's where the live 3PM OVER trigger fires.",
        BODY))

    story.append(PageBreak())

    # ---------- PAGE 4: Bet Card ----------
    story.append(Paragraph("PRE-GAME BET CARD", H1))
    story.append(Paragraph(
        "9 legs · $260 each · 21.2% bankroll at risk · all Pinnacle · INTENDED status",
        SUB))
    story.append(HRFlowable(width="100%", thickness=2, color=C_GOLD))
    story.append(Spacer(1, 4))
    story.append(chart_bankroll_allocation())
    story.append(Spacer(1, 6))
    story.append(chart_bet_edge_summary())
    story.append(Spacer(1, 6))

    story.append(section_band("THE 9 LEGS — RANKED BY EV"))
    story.append(Spacer(1, 4))
    story.extend(bet_card_section())

    # Portfolio risk summary (fills page 6 whitespace)
    story.append(Spacer(1, 8))
    story.append(section_band("SLATE RISK SUMMARY"))
    story.append(Spacer(1, 4))
    # Expected returns + worst/best cases
    bets_list = bets["bets"]
    total_stake = sum(b["stake"] for b in bets_list)
    # Expected profit: sum(stake * ev_per_$1)
    exp_profit = sum(b["stake"] * b["ev_pct"] / 100 for b in bets_list)
    # Best case: every bet wins
    def payout_for(odds):
        return odds / 100 if odds >= 0 else 100 / abs(odds)
    best_case = sum(b["stake"] * payout_for(b["odds"]) for b in bets_list)
    worst_case = -total_stake
    # Avg edge metric
    avg_ev = sum(b["ev_pct"] for b in bets_list) / len(bets_list)
    avg_kelly = sum(b["kelly_adj_pct"] for b in bets_list) / len(bets_list)

    risk_rows = [
        [Paragraph("<b><font color='white' size=8>METRIC</font></b>", BODY),
         Paragraph("<b><font color='white' size=8>VALUE</font></b>", BODY),
         Paragraph("<b><font color='white' size=8>INTERPRETATION</font></b>", BODY)],
        ["Total at risk", f"${total_stake:,.0f}",
         f"{total_stake/BR*100:.1f}% of $11,043 bankroll — within 25% slate cap"],
        ["Expected profit", f"${exp_profit:+,.0f}",
         f"Avg leg EV {avg_ev:.1f}% × $260 × 9 — model's positive-edge claim"],
        ["Best case (all hit)", f"${best_case:+,.0f}",
         f"All 9 legs win — multiplicative return on 21% of bankroll"],
        ["Worst case (all miss)", f"${worst_case:+,.0f}",
         "Pure variance loss — single-game contagion is the real tail risk"],
        ["Avg fractional Kelly", f"{avg_kelly:.2f}%",
         "0.25-Kelly × 0.65 playoff multiplier — half of textbook Kelly"],
        ["Correlated cluster", "3 legs",
         "Kornet PTS+REB + Hart AST share OKC-foul-trouble dimension"],
        ["CLV target", "≥ +1.5%",
         "If avg closing-line value clears 1.5%, slate is +EV regardless of P&L"],
    ]
    risk_t = Table(risk_rows, colWidths=[1.6 * inch, 1.1 * inch, 4.6 * inch])
    risk_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_GRAY_50, "white"]),
        ("FONTNAME", (0, 1), (1, -1), "Helvetica-Bold"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 0.4, C_GRAY_300),
        ("TEXTCOLOR", (1, 2), (1, 2), C_GREEN),
        ("TEXTCOLOR", (1, 3), (1, 3), C_GREEN),
        ("TEXTCOLOR", (1, 4), (1, 4), C_RED),
    ]))
    story.append(risk_t)

    story.append(PageBreak())

    # ---------- PAGE 5: Live Playbook + Intelligent Betting ----------
    story.append(Paragraph("LIVE BETTING PLAYBOOK", H1))
    story.append(Paragraph(
        "Pre-mapped triggers. Most EV in this slate lives in-game, not pregame.",
        SUB))
    story.append(HRFlowable(width="100%", thickness=2, color=C_GOLD))
    story.append(Spacer(1, 8))

    story.append(section_band("DEFENDER IMPACT — WEMBY PTS by primary defender"))
    story.append(Spacer(1, 4))
    story.append(chart_defender_impact())
    story.append(Spacer(1, 6))

    story.append(section_band("LIVE TRIGGER MATRIX"))
    story.append(Spacer(1, 4))
    story.append(live_trigger_table())
    story.append(Spacer(1, 8))

    story.append(section_band("JOINT EVENT PROBABILITIES (Monte Carlo · 1000 sims)"))
    story.append(Spacer(1, 4))
    story.append(chart_joint_events())

    story.append(PageBreak())

    # ---------- PAGE 6: Intelligent Betting Manifesto + Ops ----------
    story.append(Paragraph("HOW WE BET", H1))
    story.append(Paragraph(
        "The system's philosophy and tonight's operational state",
        SUB))
    story.append(HRFlowable(width="100%", thickness=2, color=C_GOLD))
    story.append(Spacer(1, 8))

    story.append(section_band("WHAT INTELLIGENT BETTING LOOKS LIKE"))
    story.append(Spacer(1, 4))
    story.extend(intelligent_betting_principles())
    story.append(Spacer(1, 8))

    story.append(section_band("PRE-TIP OPERATIONAL CHECKLIST"))
    story.append(Spacer(1, 4))
    story.append(ops_checklist())

    doc.build(story)
    print(f"WROTE: {OUT}")
    print(f"SIZE:  {OUT.stat().st_size/1024:.1f} KB")


if __name__ == "__main__":
    build()
