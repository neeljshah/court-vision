"""Neel Shah Resume — CV-focused variant. Same layout as v6, text rewritten for computer vision roles."""
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import simpleSplit

NAVY    = HexColor("#1a2942")
GOLD    = HexColor("#c8a04a")
WHITE   = HexColor("#ffffff")
MUTED   = HexColor("#4e5e78")
LT_BLUE = HexColor("#eef3fa")
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
OUT    = r"C:\Users\neelj\Downloads\NeelShahResume_CV.pdf"

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
spaced(84, iowa_y + 10, "COMPUTER VISION // ML ENGINEERING",
       "Helvetica", 9, NAVY, cs=4.0)

hrule(0, H - HH, W, GOLD, 1.2)

c.setStrokeColor(LT_GRAY); c.setLineWidth(0.8)
c.line(LW, 0, LW, H - HH)

# ── LEFT COLUMN ──────────────────────────────────────────────────────────────
def lsec(title, y):
    spaced(PL, y, title, "Helvetica-Bold", 8.5, NAVY, cs=2.8)
    hrule(PL, y - 5, LW - PL - PR, GOLD, 0.5)
    return y - 17

ly = H - HH - 16

# ── TECHNICAL ────────────────────────────────────────────────────────────────
ly = lsec("TECHNICAL", ly)
skills = ["PYTHON","C++","PYTORCH","TENSORFLOW",
          "OPENCV","CUDA","YOLO","ONNX",
          "NUMPY","TENSORRT","DOCKER","LINUX"]
cw = (LW - PL - PR - 6) / 2
ch, gx, gy = 16, 6, 5
for i, s in enumerate(skills):
    row, col = divmod(i, 2)
    x = PL + col * (cw + gx)
    y = ly - row * (ch + gy) - ch
    c.setFillColor(LT_BLUE)
    c.setStrokeColor(BORDER); c.setLineWidth(0.5)
    c.rect(x, y, cw, ch, fill=1, stroke=1)
    cs_chip = 1.2
    tw = sum(c.stringWidth(ch2, "Helvetica-Bold", 7.5) + cs_chip for ch2 in s) - cs_chip
    spaced(x + (cw - tw) / 2, y + 5, s, "Helvetica-Bold", 7.5, NAVY, cs=cs_chip)
ly -= (len(skills) // 2) * (ch + gy) + SEC_GAP + 4

# ── CORE COMPETENCIES ────────────────────────────────────────────────────────
ly = lsec("CORE COMPETENCIES", ly)
core = ("Real-time multi-object detection and tracking using YOLO architectures, Kalman filtering, "
        "and Hungarian assignment. Building production computer vision pipelines for spatial "
        "analysis, homography estimation, and re-identification across broadcast video.")
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

chip_h = 26
c.setFillColor(LT_BLUE)
c.setStrokeColor(BORDER); c.setLineWidth(0.5)
c.rect(PL, ly - chip_h, LW - PL - PR, chip_h, fill=1, stroke=1)
txt(PL + 7, ly - 9,  "COMPUTER VISION  //  DEEP LEARNING", "Helvetica-Bold", 7.3, NAVY)
txt(PL + 7, ly - 20, "LINEAR ALGEBRA  //  MACHINE LEARNING",   "Helvetica-Bold", 7.3, NAVY)
ly -= chip_h + SEC_GAP

# ── CERTIFICATION ─────────────────────────────────────────────────────────────
ly = lsec("CERTIFICATION", ly)
for name, issuer in [("CDS™","USDSI"),("ML SPECIALIST","KAGGLE"),
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
    "Computer Vision Engineer specializing in real-time detection, tracking, and spatial "
    "analysis from broadcast video. I build end-to-end production pipelines integrating "
    "YOLO detection, SIFT homography, Kalman-Hungarian tracking, and deep re-identification "
    "to extract structured spatial data from raw video at scale. Expert in bridging pixel-level "
    "perception and downstream analytical systems.",
    RW, "Helvetica", 9, 12, NAVY)
ry -= 8

# ── SELECTED RESEARCH & DEVELOPMENT ─────────────────────────────────────────
ry = rsec("SELECTED RESEARCH & DEVELOPMENT", ry)
ry -= 2

c.setFillColor(NAVY); c.setFont("Helvetica-Bold", 18)
c.drawString(RX, ry - 14, "COURT VISION")
badge = "LIVE RESEARCH"
bw = c.stringWidth(badge, "Helvetica-Bold", 8.5) + 14
c.setFillColor(GOLD); c.rect(W - 18 - bw, ry - 13, bw, 14, fill=1, stroke=0)
c.setFillColor(WHITE); c.setFont("Helvetica-Bold", 8.5)
c.drawString(W - 18 - bw + 7, ry - 9, badge)
ry -= 22

spaced(RX, ry, "PRIMARY CV INFRASTRUCTURE", "Helvetica", 8.2, MUTED, cs=2.2)
rtxt(W - 18, ry, "CV-MTCA-V8", "Helvetica-Bold", 8, MUTED)
ry -= 12

box_h = 40
c.setFillColor(LT_BLUE)
c.rect(RX, ry - box_h, RW, box_h, fill=1, stroke=0)
c.setStrokeColor(NAVY); c.setLineWidth(2)
c.line(RX + 1, ry, RX + 1, ry - box_h)
wrap(RX + 10, ry - 11,
     "End-to-End CV Pipeline: Real-time multi-object tracking system processing broadcast "
     "NBA video into structured spatial coordinates via YOLOv8n detection, SIFT homography, "
     "and Kalman-Hungarian association.",
     RW - 14, "Helvetica-Bold", 8.8, 11.5, NAVY)
ry -= box_h + 8

cw2 = (RW - 12) / 2
bl = [
    "Engineered YOLOv8n detection pipeline with ByteTrack identity persistence across occlusions.",
    "Built SIFT keypoint homography for pixel-to-court coordinate mapping at 30+ fps.",
    "Implemented Kalman-Hungarian MOT with OSNet re-identification (512-dim embeddings).",
]
br = [
    "Designed court-line detection and panoramic stitching for broadcast camera calibration.",
    "GPU-optimized inference pipeline processing 80+ fps on RTX 4060 with VRAM management.",
    "EasyOCR jersey number extraction and team classification via HSV color clustering.",
]
yL = yR = ry
for b in bl:
    c.setFillColor(GOLD); c.rect(RX + 2, yL - 3, 3, 3, fill=1, stroke=0)
    yL = wrap(RX + 10, yL, b, cw2 - 12, "Helvetica-Oblique", 8.8, 10.5, NAVY); yL -= 4
for b in br:
    c.setFillColor(GOLD); c.rect(RX + cw2 + 14, yR - 3, 3, 3, fill=1, stroke=0)
    yR = wrap(RX + cw2 + 22, yR, b, cw2 - 12, "Helvetica-Oblique", 8.8, 10.5, NAVY); yR -= 4
ry = min(yL, yR) - 6

# ── 2×2 sub-project boxes ─────────────────────────────────────────────────────
sw = (RW - 10) / 2
sh = 70

def subproj(x, y, w, h, title, body):
    c.setFillColor(GOLD); c.rect(x, y - 2, 26, 2.5, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setStrokeColor(BORDER); c.setLineWidth(0.5)
    c.rect(x, y - h, w, h, fill=1, stroke=1)
    spaced(x + 8, y - 14, title, "Helvetica-Bold", 8.5, NAVY, cs=1.2)
    wrap(x + 8, y - 27, body, w - 16, "Helvetica-Oblique", 8.2, 10.5, NAVY)

subproj(RX,       ry, sw, sh, "MULTI-OBJECT TRACKING",
        "Kalman filter + Hungarian assignment for frame-to-frame association; ByteTrack for "
        "occlusion robustness. OSNet 512-dim re-ID for cross-sequence identity persistence.")
subproj(RX+sw+10, ry, sw, sh, "SPATIAL ANALYSIS",
        "SIFT homography for broadcast-to-court projection. KDE heatmaps and trajectory "
        "clustering. Spatial efficiency metrics (xPPP) via gradient-boosted regressors.")
ry -= sh + 6
subproj(RX,       ry, sw, sh, "VIDEO PROCESSING AT SCALE",
        "GPU-accelerated decoding via NVDEC/Decord. Multi-worker parallel processing with "
        "VRAM management. Scaled to 80+ games on cloud RTX 3090 infrastructure.")
subproj(RX+sw+10, ry, sw, sh, "DEEP LEARNING MODELS",
        "Fine-tuned YOLOv8n for sports-domain detection. Ensemble classifier (97% accuracy) "
        "with CNN features. LSTM temporal model with attention for sequential prediction.")
ry -= sh + 10

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
    return y - 4

ry = role("DATA ANALYST INTERN", "SUNSOLOR  |  TEMPE, AZ", "2025", [
    "Built automated image analysis and visual data pipelines using Python and OpenCV.",
    "Developed real-time detection dashboards reducing manual visual review latency by 30%.",
    "Conducted annotation-quality audits across 5+ image datasets for model training integrity.",
    "Optimized data processing pipelines for high-throughput analysis on 1M+ record datasets.",
], ry)

ry = role("DATA ANNOTATION SPECIALIST", "DATA ANNOTATION TECH  |  REMOTE", "2024 — 2025", [
    "Labeled 10,000+ images and structured samples for production CV model training and fine-tuning.",
    "Authored bounding-box and segmentation guidelines cutting annotation error variance by 20%.",
    "Refined labeling schemas with ML engineers for complex detection and classification tasks.",
], ry)

ry = role("BUSINESS INTELLIGENCE ANALYST", "FORTREX SECURITIES  |  MADISON, WI", "2023 — 2024", [
    "Built real-time visual monitoring dashboards for anomaly detection with 99.9% uptime.",
    "Engineered automated data processing pipelines for high-throughput pattern recognition.",
    "Developed alerting frameworks for real-time anomaly detection in transaction workflows.",
], ry)

c.showPage()
c.save()
print(f"Wrote {OUT}  (bottom y={ry:.0f})")
