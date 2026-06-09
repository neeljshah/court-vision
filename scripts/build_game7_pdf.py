"""build_game7_pdf.py — styled 3-page PDF for the WCF Game 7 intel report.

Pure matplotlib (PdfPages) so it needs no extra deps. Reads the intel_game7
artifacts + curated narrative, writes reports/WCF_G7_intel.pdf.
"""
from __future__ import annotations
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd

D = Path(r"C:\Users\neelj\nba-ai-system\data\cache\intel_game7")
OUT = D / "reports"
OUT.mkdir(exist_ok=True)
PDF = OUT / "WCF_G7_intel.pdf"

# palette
BG = "#0d1b2a"; CARD = "#16263a"; INK = "#eaf2fb"; SUB = "#9fb3c8"
GOLD = "#e0a82e"; TEAL = "#3ad0c9"; RED = "#ef5b5b"; GREEN = "#4cd07d"; OKCB = "#1d80c8"

game = json.load(open(D / "game_forecast.json"))
joints = json.load(open(D / "joint_events.json"))
fz = pd.read_csv(D / "pts_fusion.csv").sort_values("fused_mu", ascending=False)
ev = pd.read_csv(D / "prop_ev_best.csv")
cred = ev[(ev.odds >= -250) & (ev.odds <= 160) & (ev.p_win >= 0.55) & (ev.p_win <= 0.93)
          & (ev.ev_pct >= 5)].sort_values("ev_pct", ascending=False).head(8)


def newpage(pdf):
    fig = plt.figure(figsize=(8.5, 11), facecolor=BG)
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_facecolor(BG)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    return fig, ax


def band(ax, y, h, color=CARD):
    ax.add_patch(plt.Rectangle((0.06, y), 0.88, h, color=color, zorder=0, lw=0))


def T(ax, x, y, s, size=10, color=INK, weight="normal", ha="left", style="normal", font="DejaVu Sans"):
    ax.text(x, y, s, fontsize=size, color=color, weight=weight, ha=ha, va="top",
            style=style, family=font, transform=ax.transAxes)


def table(ax, x, y, rows, widths, header, rh=0.026, fs=8.2, hl=None):
    """rows: list of lists. widths: fractional col widths summing ~width. y=top."""
    band(ax, y - rh + 0.004, rh, "#1f3350")
    cx = x
    for j, (cell, w) in enumerate(zip(header, widths)):
        T(ax, cx + 0.004, y, cell, size=fs, color=GOLD, weight="bold")
        cx += w
    yy = y - rh
    for i, row in enumerate(rows):
        if i % 2 == 0:
            band(ax, yy - rh + 0.004, rh, "#13243a")
        cx = x
        for j, (cell, w) in enumerate(zip(row, widths)):
            col = INK
            if hl and hl(i, j, row):
                col = hl(i, j, row)
            T(ax, cx + 0.004, yy, str(cell), size=fs, color=col)
            cx += w
        yy -= rh
    return yy


# ============================================================ PAGE 1
pdf = PdfPages(PDF)
fig, ax = newpage(pdf)
band(ax, 0.905, 0.075, GOLD)
T(ax, 0.085, 0.965, "WESTERN CONFERENCE FINALS  ·  GAME 7", 13, BG, "bold")
T(ax, 0.085, 0.94, "SAN ANTONIO  @  OKLAHOMA CITY", 19, BG, "bold")
T(ax, 0.92, 0.95, "Sat May 30 · 8:00 ET", 9.5, BG, "bold", ha="right")
T(ax, 0.92, 0.928, "NBC / Peacock", 9.5, BG, ha="right")

T(ax, 0.085, 0.885, "Series 3–3 · winner advances to the NBA Finals", 11, TEAL, "bold")
T(ax, 0.085, 0.866, "Pregame intelligence — fused model + 6-game series + CV tracking + live 7-book market.",
  8.6, SUB)

# --- forecast cards
band(ax, 0.74, 0.10)
T(ax, 0.085, 0.823, "GAME FORECAST", 11, GOLD, "bold")
T(ax, 0.09, 0.80, "MARKET (FD/DK)", 8, SUB, "bold")
T(ax, 0.09, 0.782, "OKC −155 ML", 15, INK, "bold")
T(ax, 0.09, 0.758, "~61% win  ·  OKC −4", 9, OKCB, "bold")
T(ax, 0.40, 0.80, "TOTAL", 8, SUB, "bold")
T(ax, 0.40, 0.782, "212.5 / 213.5", 15, INK, "bold")
T(ax, 0.40, 0.758, f"sim ~{game['proj_total']:.0f}  ·  lean under", 9, SUB)
T(ax, 0.70, 0.80, "PROJECTED SCORE", 8, SUB, "bold")
T(ax, 0.70, 0.782, f"OKC {game['proj_okc_pts']:.0f} – {game['proj_sas_pts']:.0f} SAS", 14, INK, "bold")
T(ax, 0.70, 0.758, "home edge is the tell", 9, SUB, style="italic")

# --- series results
T(ax, 0.085, 0.715, "THE SERIES SO FAR", 11, GOLD, "bold")
rows = [
    ["1", "5/18", "@OKC", "SAS 122–115", "road win"],
    ["2", "5/20", "@OKC", "OKC 122–113", ""],
    ["3", "5/22", "@SAS", "OKC 123–108", "road win"],
    ["4", "5/24", "@SAS", "SAS 103–082", ""],
    ["5", "5/26", "@OKC", "OKC 127–114", "SGA 32/9 · McCain 20 · Wemby 20 (4-15)"],
    ["6", "5/28", "@SAS", "SAS 118–91", "Wemby 28/10/3b · SGA 15 (6-18)"],
]
def hl_series(i, j, row):
    if j == 3:
        return GREEN if row[3].startswith("OKC") else RED
    return None
y = table(ax, 0.085, 0.69, rows, [0.04, 0.07, 0.08, 0.17, 0.50], ["G", "DATE", "SITE", "RESULT", "NOTE"],
          hl=hl_series)

# --- key reads
band(ax, 0.30, 0.205)
T(ax, 0.085, 0.485, "WHY OKC IS FAVORED IN GAME 7", 11, GOLD, "bold")
bullets = [
    ("Home teams are 4–0 since Game 1", "(G2/G4/G5/G6) — the strongest signal on the board."),
    ("Reigning champs + MVP at home", "OKC took G5 here 127–114; SGA dropped 32."),
    ("Scoring rule", "OKC is 3–0 when SGA ≥ Wemby in points; SAS 3–0 when Wemby wins the duel."),
    ("First CF Game 7 between two top-3 MVP finishers", "since Bird–Erving, 1982."),
]
yy = 0.458
for head, body in bullets:
    T(ax, 0.095, yy, "▸", 9, GOLD, "bold")
    T(ax, 0.12, yy, head, 9.4, INK, "bold")
    T(ax, 0.12, yy - 0.018, body, 8.4, SUB)
    yy -= 0.045

# --- rotation watch
band(ax, 0.075, 0.205)
T(ax, 0.085, 0.275, "ROTATION WATCH", 11, GOLD, "bold")
rot = [
    (RED, "Jalen Williams (OKC) — hamstring", "OUT G5, 10 min in G6. Game-time decision = #1 swing factor."),
    (GREEN, "Jared McCain (OKC) — now starting", "20 pts G5, 13/6a G6. Role way up."),
    (TEAL, "Dylan Harper (SAS) — emerging", "18 pts in G6 off the bench."),
    ("#7fa8d0", "De'Aaron Fox (SAS) — ice cold", "9 then 5 pts (1-9 in G6); now a passer, not scorer."),
]
yy = 0.248
for c, head, body in rot:
    T(ax, 0.095, yy, "●", 8, c, "bold")
    T(ax, 0.12, yy, head, 9.2, INK, "bold")
    T(ax, 0.12, yy - 0.0175, body, 8.3, SUB)
    yy -= 0.042
T(ax, 0.085, 0.045, "CourtVision · 10K-sim Monte Carlo · tracking matchup overlay (CV) · page 1 / 3", 7.5, SUB)
pdf.savefig(fig, facecolor=BG); fig.savefig(OUT / "_pg1.png", facecolor=BG, dpi=110); plt.close(fig)

# ============================================================ PAGE 2
fig, ax = newpage(pdf)
band(ax, 0.93, 0.05, GOLD)
T(ax, 0.085, 0.972, "HOW TRACKING MOVES THE PROJECTIONS", 14, BG, "bold")

T(ax, 0.085, 0.90, "Fusion = (0.45·model + 0.55·6-game series) × CV matchup multiplier (FG% allowed by this", 8.6, SUB)
T(ax, 0.085, 0.884, "opponent's defenders, bounded ±10%).  The overlay bumps Wemby and haircuts SGA.", 8.6, SUB)

# chart: model vs series vs fused for top scorers
top = fz.head(8).iloc[::-1]
axc = fig.add_axes([0.10, 0.55, 0.82, 0.27]); axc.set_facecolor(BG)
yb = np.arange(len(top)); h = 0.26
axc.barh(yb + h, top["model_q50"], h, color="#3a5a7a", label="model q50")
axc.barh(yb, top["series_avg"], h, color=TEAL, label="6-game series")
axc.barh(yb - h, top["fused_mu"], h, color=GOLD, label="fused (used)")
for s in axc.spines.values():
    s.set_color(SUB)
axc.set_yticks(yb); axc.set_yticklabels(top["player"], color=INK, fontsize=8)
axc.tick_params(colors=SUB, labelsize=7)
axc.set_xlabel("projected points", color=SUB, fontsize=8)
axc.legend(facecolor=CARD, edgecolor=SUB, labelcolor=INK, fontsize=7.5, loc="lower right")
axc.set_title("", color=INK)

# matchup multiplier table
T(ax, 0.085, 0.50, "MATCHUP MULTIPLIERS (CV defender efficiency, Games 1–4)", 10.5, GOLD, "bold")
mr = []
for _, r in fz.head(10).iterrows():
    arrow = "↑" if r["track_mult"] > 1.0 else ("↓" if r["track_mult"] < 1.0 else "·")
    mr.append([r["player"], r["primary_def"], f"{r['fg%_allowed']:.0%}", f"{r['track_mult']:.3f} {arrow}",
               f"{r['fused_mu']:.1f}"])
def hl_mult(i, j, row):
    if j == 3:
        return GREEN if "↑" in row[3] else (RED if "↓" in row[3] else INK)
    return None
table(ax, 0.085, 0.475, mr, [0.27, 0.27, 0.12, 0.16, 0.10],
      ["PLAYER", "PRIMARY DEFENDER", "FG% ALL", "MULT", "PTS"], hl=hl_mult)

band(ax, 0.085, 0.10)
T(ax, 0.085, 0.175, "THE MATCHUP THAT DECIDES IT", 11, GOLD, "bold")
T(ax, 0.095, 0.150, "Hartenstein vs Wembanyama is OKC's biggest leak — Wemby shot 56% FG / 56% from three", 8.7, INK)
T(ax, 0.095, 0.133, "against him over 18 head-to-head minutes. Holmgren defends it far better (3 blocks on Wemby,", 8.7, INK)
T(ax, 0.095, 0.116, "37% FG). Watch OKC's opening assignment: if Holmgren draws Wemby, the Wemby unders", 8.7, INK)
T(ax, 0.095, 0.099, "strengthen and OKC's win probability climbs.", 8.7, INK)
T(ax, 0.085, 0.045, "CourtVision · tracking layer G1–4 (G5/G6 video not yet processed) · page 2 / 3", 7.5, SUB)
pdf.savefig(fig, facecolor=BG); fig.savefig(OUT / "_pg2.png", facecolor=BG, dpi=110); plt.close(fig)

# ============================================================ PAGE 3
fig, ax = newpage(pdf)
band(ax, 0.93, 0.05, GOLD)
T(ax, 0.085, 0.972, "BET CARD  ·  vs LIVE GAME-7 LINES", 14, BG, "bold")

# EV bar chart
cc = cred.iloc[::-1]
labels = [f"{r.player.split()[-1]} {r.stat.upper()} {r.side[:1]}{r.line:g}" for _, r in cc.iterrows()]
axc = fig.add_axes([0.30, 0.60, 0.62, 0.30]); axc.set_facecolor(BG)
yb = np.arange(len(cc))
axc.barh(yb, cc["ev_pct"], color=[GREEN if v >= 30 else GOLD for v in cc["ev_pct"]])
for i, (_, r) in enumerate(cc.iterrows()):
    axc.text(r["ev_pct"] + 1, i, f"{r['ev_pct']:.0f}%", color=INK, fontsize=7.5, va="center")
axc.set_yticks(yb); axc.set_yticklabels(labels, color=INK, fontsize=8)
axc.tick_params(colors=SUB, labelsize=7)
for s in axc.spines.values():
    s.set_color(SUB)
axc.set_xlabel("model edge (EV %)", color=SUB, fontsize=8)
T(ax, 0.085, 0.895, "TOP EDGES", 10.5, GOLD, "bold")
T(ax, 0.085, 0.86, "Monte-Carlo\np(win) vs the\nposted price.\n\nFused model,\nreal 7-book\nGame-7 lines.\n\nGreen = 30%+\nedge.", 8.2, SUB)

# bet table
br = []
for _, r in cred.iterrows():
    br.append([r["player"], f"{r['stat'].upper()} {r['side']} {r['line']:g}", f"{r['fused_mu']:.1f}",
               f"{r['p_win']:.0%}", f"{int(r['odds']):+d}", f"+{r['ev_pct']:.0f}%", r["book"]])
T(ax, 0.085, 0.55, "RANKED BET CARD", 10.5, GOLD, "bold")
def hl_bet(i, j, row):
    return GREEN if j == 5 else None
table(ax, 0.085, 0.525, br, [0.24, 0.22, 0.08, 0.08, 0.09, 0.10, 0.12],
      ["PLAYER", "PROP", "PROJ", "P(W)", "ODDS", "EV", "BOOK"], hl=hl_bet)

# joints + bottom line
band(ax, 0.085, 0.165)
T(ax, 0.085, 0.238, "JOINT / PARLAY (10K sim)", 10, GOLD, "bold")
jl = [("Wemby double-double", joints.get("P(Wemby double-double)")),
      ("Wemby 30+ pts", joints.get("P(Wemby 30+ pts)")),
      ("SGA 25+ & 6+ ast", joints.get("P(SGA 25+ pts & 6+ ast)")),
      ("SGA 30+ pts", joints.get("P(SGA 30+ pts)"))]
yy = 0.214
for name, v in jl:
    if v is None:
        continue
    T(ax, 0.095, yy, name, 8.6, INK)
    T(ax, 0.40, yy, f"{v:.0%}", 8.6, TEAL, "bold")
    yy -= 0.022

T(ax, 0.52, 0.238, "BOTTOM LINE", 10, GOLD, "bold")
bl = ["Side: OKC −4 / ~61% at home.",
      "Total: sim ~215 vs 213 — lean under / pass.",
      "Best: Wemby REB u13.5 · BLK u3.5 ·",
      "        Holmgren REB u8.5 · Fox PTS u15.5.",
      "Hinge: SGA-vs-Wemby duel + OKC's",
      "        opening defender on Wemby.",
      "Swing: Jalen Williams hamstring (confirm)."]
yy = 0.214
for s in bl:
    T(ax, 0.53, yy, s, 8.3, INK)
    yy -= 0.021

T(ax, 0.085, 0.045, "CourtVision · provisional vs current G7 market · confirm game-time injuries · page 3 / 3", 7.5, SUB)
pdf.savefig(fig, facecolor=BG); fig.savefig(OUT / "_pg3.png", facecolor=BG, dpi=110); plt.close(fig)
pdf.close()
print(f"Wrote {PDF}  ({PDF.stat().st_size//1024} KB)")
