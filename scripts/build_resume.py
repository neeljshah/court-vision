"""Neel Shah Resume v6 — LT_BLUE header+chips+coursework, even right-col spacing."""
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import simpleSplit

NAVY    = HexColor("#1a2942")
GOLD    = HexColor("#c8a04a")
WHITE   = HexColor("#ffffff")
MUTED   = HexColor("#4e5e78")
LT_BLUE = HexColor("#eef3fa")   # header bg, chips, coursework box
BORDER  = HexColor("#c4ccd8")
LT_GRAY = HexColor("#e2e7ee")

W, H   = letter
LW     = 186
HH     = 92
PL     = 16
PR     = 14
RX     = LW + 18
RW     = W - RX - 18
SEC_GAP = 14
OUT    = r"C:\Users\neelj\Downloads\NeelShahResume_v6.pdf"

c = canvas.Canvas(OUT, pagesize=letter)

def txt(x, y, s, font="Helvetica", size=9, color=NAVY):
    c.setFont(font, size); c.setFillColor(color); c.drawString(x, y, s)

def rtxt(x, y, s, font="Helvetica", size=9, color=NAVY):
    c.setFont(font, size); c.setFillColor(color); c.drawRightString(x, y, s)

def wrap(x, y, s, width, font="Helvetica", size=9, lead=12, color=NAVY):
    c.setFont(font, size); c.setFillColor(color)
    for line in simpleSplit(s, font, size, width):
        c.drawString(x, y, line); y -= lead
    return y

def hrule(x, y, w, color=GOLD, lw=0.7):
    c.setStrokeColor(color); c.setLineWidth(lw); c.line(x, y, x + w, y)

def spaced(x, y, s, font="Helvetica-Bold", size=9, color=NAVY, cs=2.8):
    c.setFont(font, size); c.setFillColor(color)
    for ch in s:
        c.drawString(x, y, ch)
        x += c.stringWidth(ch, font, size) + cs
    return x - cs

# ── HEADER (light blue background) ──────────────────────────────────────────
c.setFillColor(LT_BLUE)
c.rect(0, H - HH, W, HH, fill=1, stroke=0)

iowa_y  = H - HH + 18
email_y = iowa_y + 4 * 14

for label, y in [
    ("neeljshah22@gmail.com",         email_y),
    ("319-230-6152",                  email_y - 14),
    ("github.com/neeljshah",          email_y - 28),
    ("neelshahportfolio.netlify.app", email_y - 42),
    ("Iowa City, IA",                 iowa_y),
]:
    font = "Helvetica-Bold" if "netlify" in label else "Helvetica"
    rtxt(W - 22, y, label, font, 9, NAVY)

c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 30)
c.drawString(26, iowa_y + 36, "NEEL SHAH")
c.setStrokeColor(GOLD); c.setLineWidth(1.5)
c.line(26, iowa_y + 16, 78, iowa_y + 16)
spaced(84, iowa_y + 10, "QUANTITATIVE RESEARCH // ML ENGINEERING",
       "Helvetica", 9, NAVY, cs=4.0)

# Gold rule at bottom of header
hrule(0, H - HH, W, GOLD, 1.2)

# Light gray sidebar separator
c.setStrokeColor(LT_GRAY); c.setLineWidth(0.8)
c.line(LW, 0, LW, H - HH)

# ── LEFT COLUMN ──────────────────────────────────────────────────────────────
def lsec(title, y):
    spaced(PL, y, title, "Helvetica-Bold", 8.5, NAVY, cs=2.8)
    hrule(PL, y - 5, LW - PL - PR, GOLD, 0.5)
    return y - 17

ly = H - HH - 16   # tighter top pad to compensate taller coursework chip

# ── TECHNICAL ────────────────────────────────────────────────────────────────
ly = lsec("TECHNICAL", ly)
skills = ["PYTHON","SQL","PYTORCH","XGBOOST",
          "FASTAPI","OPENCV","PANDAS","NUMPY",
          "STATSMODELS","GCP","DOCKER","TABLEAU"]
cw = (LW - PL - PR - 6) / 2
ch, gx, gy = 16, 6, 5
for i, s in enumerate(skills):
    row, col = divmod(i, 2)
    x = PL + col * (cw + gx)
    y = ly - row * (ch + gy) - ch
    # LT_BLUE chip with navy text — matches header
    c.setFillColor(LT_BLUE)
    c.setStrokeColor(BORDER); c.setLineWidth(0.5)
    c.rect(x, y, cw, ch, fill=1, stroke=1)
    cs_chip = 1.2
    tw = sum(c.stringWidth(ch2, "Helvetica-Bold", 7.5) + cs_chip for ch2 in s) - cs_chip
    spaced(x + (cw - tw) / 2, y + 5, s, "Helvetica-Bold", 7.5, NAVY, cs=cs_chip)
ly -= (len(skills) // 2) * (ch + gy) + SEC_GAP + 4

# ── CORE COMPETENCIES ────────────────────────────────────────────────────────
ly = lsec("CORE COMPETENCIES", ly)
core = ("Probabilistic modeling of high-frequency sports outcomes using Poisson and Monte Carlo "
        "simulations. Building low-latency signal engines for real-time market prediction, "
        "multi-agent execution, and dynamic +EV bankroll management.")
bar_top = ly + 4
ly = wrap(PL + 9, ly, core, LW - PL - PR - 11, "Helvetica", 8.4, 11.5, NAVY)
bar_bot = ly - 2
c.setFillColor(GOLD); c.rect(PL, bar_bot, 4, bar_top - bar_bot, fill=1, stroke=0)
ly -= SEC_GAP

# ── ACADEMIC TRACK ────────────────────────────────────────────────────────────
ly = lsec("ACADEMIC TRACK", ly)
spaced(PL, ly, "B.S. DATA SCIENCE", "Helvetica-Bold", 8.8, NAVY, cs=1.5); ly -= 13
txt(PL, ly, "University of Iowa", "Helvetica-Oblique", 8.8, MUTED); ly -= 11
txt(PL, ly, "2022 — PRESENT", "Helvetica", 8.5, NAVY); ly -= 10
txt(PL, ly, "3 YRS COURSEWORK", "Helvetica", 8.2, NAVY); ly -= 10
txt(PL, ly, "CONTINUING ONLINE", "Helvetica", 8.2, NAVY); ly -= 12

# Coursework chip — LT_BLUE, 2 lines, clear gap from text above
chip_h = 26
c.setFillColor(LT_BLUE)
c.setStrokeColor(BORDER); c.setLineWidth(0.5)
c.rect(PL, ly - chip_h, LW - PL - PR, chip_h, fill=1, stroke=1)
txt(PL + 7, ly - 9,  "MATH STATS  //  FINANCIAL ANALYTICS", "Helvetica-Bold", 7.3, NAVY)
txt(PL + 7, ly - 20, "PROB THEORY  //  MACHINE LEARNING",   "Helvetica-Bold", 7.3, NAVY)
ly -= chip_h + SEC_GAP

# ── CERTIFICATION ─────────────────────────────────────────────────────────────
ly = lsec("CERTIFICATION", ly)
for name, issuer in [("CDS\u2122","USDSI"),("ML SPECIALIST","KAGGLE"),
                     ("DATA VIZ","KAGGLE"),("CBIAP","IABAC")]:
    spaced(PL,        ly, name,   "Helvetica-Bold", 8.5, NAVY, cs=1.2)
    rtxt(LW - PR, ly, issuer, "Helvetica", 8.5, MUTED)
    ly -= 13
ly -= 8

# ── LEADERSHIP ────────────────────────────────────────────────────────────────
ly = lsec("LEADERSHIP", ly)
for title_l, body in [
    ("EAGLE SCOUT — BSA",
     "Directed 20+ service projects and 12-person team; 500+ volunteer hours."),
    ("TENNIS TEAM CAPTAIN",
     "Regional lead; coordinated strategic training, drills, and player development."),
    ("KESEM  /  KIDS FOR CAUSE",
     "Support network for children of cancer patients; tennis-led youth volunteer drives."),
]:
    spaced(PL, ly, title_l, "Helvetica-Bold", 8.5, NAVY, cs=1.2); ly -= 12
    ly = wrap(PL, ly, body, LW - PL - PR, "Helvetica", 8.2, 10.5, MUTED); ly -= 7

# ── RIGHT COLUMN ─────────────────────────────────────────────────────────────
def rsec(title, y):
    end_x = spaced(RX, y, title, "Helvetica-Bold", 9, NAVY, cs=2.2)
    c.setStrokeColor(NAVY); c.setLineWidth(0.6)
    c.line(end_x + 8, y + 3, W - 18, y + 3)
    return y - 14

ry = H - HH - 26

# ── PROFESSIONAL PROFILE ─────────────────────────────────────────────────────
ry = rsec("PROFESSIONAL PROFILE", ry)
ry -= 2
ry = wrap(RX, ry,
    "Quantitative Researcher specializing in high-frequency sports markets with a focus on "
    "statistical arbitrage and predictive modeling. I build end-to-end production architectures "
    "integrating computer vision tracking, Bayesian optimization, and risk-managed simulation "
    "engines to identify +EV market inefficiencies. Expert in bridging raw spatial data and "
    "actionable quantitative insight.",
    RW, "Helvetica", 9, 12, NAVY)
ry -= 12

# ── SELECTED RESEARCH & DEVELOPMENT ─────────────────────────────────────────
ry = rsec("SELECTED RESEARCH & DEVELOPMENT", ry)
ry -= 2   # tightened (was 6)

# Court Vision — tighter so bottom isn't cramped
c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 18)
c.drawString(RX, ry - 14, "COURT VISION")
badge = "LIVE RESEARCH"
bw = c.stringWidth(badge, "Helvetica-Bold", 8.5) + 14
c.setFillColor(GOLD); c.rect(W - 18 - bw, ry - 13, bw, 14, fill=1, stroke=0)
c.setFillColor(WHITE); c.setFont("Helvetica-Bold", 8.5)
c.drawString(W - 18 - bw + 7, ry - 9, badge)
ry -= 22

spaced(RX, ry, "PRIMARY ANALYTICS INFRASTRUCTURE", "Helvetica", 8.2, MUTED, cs=2.2)
rtxt(W - 18, ry, "CV-MTCA-V8", "Helvetica-Bold", 8, MUTED)
ry -= 12   # tightened (was 13)

# Framework callout
box_h = 40
c.setFillColor(LT_BLUE)
c.rect(RX, ry - box_h, RW, box_h, fill=1, stroke=0)
c.setStrokeColor(NAVY); c.setLineWidth(2)
c.line(RX + 1, ry, RX + 1, ry - box_h)
wrap(RX + 10, ry - 11,
     "End-to-End Analytics Framework: Possession-level NBA simulator integrating CV tracking "
     "with 10K Monte Carlo simulations to derive implied distributions vs market lines.",
     RW - 14, "Helvetica-Bold", 8.8, 11.5, NAVY)
ry -= box_h + 12

# Two-column bullets
cw2 = (RW - 12) / 2
bl = [
    "Engineered YOLOv8n detection and ByteTrack identity persistence for player motion.",
    "Architected FastAPI microservices for high-concurrency props prediction.",
    "Bayesian update filters for real-time play-by-play probability shifts.",
]
br = [
    "SIFT-based court homography for 2D spatial coordinate mapping and trajectory analytics.",
    "Scaled spatial intelligence metrics (xPPP) using gradient boosting models.",
    "Kelly Criterion optimization for dynamic bankroll management.",
]
yL = yR = ry
for b in bl:
    c.setFillColor(GOLD); c.rect(RX + 2, yL - 3, 3, 3, fill=1, stroke=0)
    yL = wrap(RX + 10, yL, b, cw2 - 12, "Helvetica-Oblique", 8.8, 10.5, NAVY); yL -= 4
for b in br:
    c.setFillColor(GOLD); c.rect(RX + cw2 + 14, yR - 3, 3, 3, fill=1, stroke=0)
    yR = wrap(RX + cw2 + 22, yR, b, cw2 - 12, "Helvetica-Oblique", 8.8, 10.5, NAVY); yR -= 4
ry = min(yL, yR) - 10

# ── 2×2 sub-project boxes ─────────────────────────────────────────────────────
sw = (RW - 10) / 2
sh = 74

def subproj(x, y, w, h, title, body):
    c.setFillColor(GOLD); c.rect(x, y - 2, 26, 2.5, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setStrokeColor(BORDER); c.setLineWidth(0.5)
    c.rect(x, y - h, w, h, fill=1, stroke=1)
    spaced(x + 8, y - 14, title, "Helvetica-Bold", 8.5, NAVY, cs=1.2)
    wrap(x + 8, y - 27, body, w - 16, "Helvetica-Oblique", 8.2, 10.5, NAVY)

subproj(RX,       ry, sw, sh, "QUANT BETTING FRAMEWORK",
        "Poisson regression for team totals; backtested vs market lines with Sharpe-ratio "
        "optimized Kelly sizing. Multi-source API feeds for real-time liquidity.")
subproj(RX+sw+10, ry, sw, sh, "SPATIAL INTELLIGENCE",
        "KDE shot heatmaps + spatial efficiency engines; K-Means archetyping for rotation "
        "analysis. Homography-driven high-precision court-space projection.")
ry -= sh + 10
subproj(RX,       ry, sw, sh, "REVENUE FORECASTING",
        "Prophet demand forecaster (<8% MAPE) and GPT-4o agent on high-availability GCP. "
        "Automated dbt + BigQuery pipelines for scalable insight delivery.")
subproj(RX+sw+10, ry, sw, sh, "PREDICTIVE SUITE",
        "Ensemble breast-cancer classifier (97%) and housing regression with CNN features + "
        "residual analysis. High-recall focus for clinical and financial risk modeling.")
ry -= sh + 16

# ── PROFESSIONAL EXPERIENCE ──────────────────────────────────────────────────
ry = rsec("PROFESSIONAL EXPERIENCE", ry)
ry -= 4

def role(title, company, when, bullets, y):
    spaced(RX, y, title, "Helvetica-Bold", 11, NAVY, cs=1.5)
    rtxt(W - 18, y, when, "Helvetica-Bold", 9, MUTED)
    y -= 13
    spaced(RX, y, company, "Helvetica-Bold", 8.5, MUTED, cs=1.2)
    y -= 12
    for b in bullets:
        y = wrap(RX + 2, y, b, RW, "Helvetica-Oblique", 8.8, 11, NAVY)
    return y - 7   # slightly more gap between roles

ry = role("DATA ANALYST INTERN", "SUNSOLOR  |  TEMPE, AZ", "2025", [
    "Built live Tableau / Power BI suites reducing manual reporting latency by 30%.",
    "Automated daily market-trend analysis with Python pipelines shaping strategic planning.",
    "Conducted data-quality audits across 5+ datasets to ensure analytical integrity for execs.",
    "Optimized SQL queries for high-performance dashboards on datasets exceeding 1M records.",
], ry)

ry = role("DATA ANNOTATION SPECIALIST", "DATA ANNOTATION TECH  |  REMOTE", "2024 — 2025", [
    "Labeled 10,000+ structured samples for production-tier ML training and LLM fine-tuning.",
    "Authored edge-case documentation cutting pipeline error variance by 20% across teams.",
    "Refined labeling schemas with data scientists for complex sentiment-analysis tasks.",
], ry)

ry = role("BUSINESS INTELLIGENCE ANALYST", "FORTREX SECURITIES  |  MADISON, WI", "2023 — 2024", [
    "Built secure reporting interfaces for executive stakeholders with 99.9% uptime.",
    "Refined backend payment APIs and reporting pipelines for high-throughput billing systems.",
    "Engineered real-time anomaly-detection alerting for transaction-processing workflows.",
], ry)

c.showPage()
c.save()
print(f"Wrote {OUT}  (bottom y={ry:.0f})")
