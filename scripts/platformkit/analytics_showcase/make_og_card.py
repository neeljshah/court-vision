"""Generate the 1200x630 social share card for CourtVision Analytics.

Fixes the documented gap in webapp/app/(analytics)/layout.tsx: with no purpose-
built 1200x630 image the Twitter card was downgraded to `summary` (a square
thumbnail). This draws one editorial card -- ivory paper, the nav lockup, the
"every number wears its receipt" headline, the honest-rail line -- so shared
analytics links render a proper large landscape card carrying the brand.

Typographic (not a logo composite) so the layout is fully controlled and
reproducible. Uses Georgia (a system serif) as a stand-in for the Fraunces
display face; the shapes and hierarchy match the site nav.

Usage:
    python -m scripts.platformkit.analytics_showcase.make_og_card
    python -m scripts.platformkit.analytics_showcase.make_og_card --check
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BRAND = os.path.join(ROOT, "webapp", "public", "brand")
OUT_PNG = os.path.join(BRAND, "og-analytics.png")

# Per-findings share cards: (route slug, two-line headline). The flagship findings
# pages are the most-shared content, so each gets a card carrying its own headline
# instead of the generic default -- a distinct, compelling embed per shared link.
FINDINGS = [
    ("retraction", ["The six numbers", "we took back."]),
    ("effective-sample-size", ["How independent", "is our data, really?"]),
    ("verdict-flips", ["When we", "changed our mind."]),
    ("mlb-leaderboards", ["Leaderboards, with", "the nulls attached."]),
    ("tennis", ["Tennis: where", "momentum has a limit."]),
    ("nba-momentum", ["NBA momentum,", "tested honestly."]),
    ("q4-shift", ["The fourth-quarter", "shift, un-refused."]),
    ("shrinkage", ["When the leaderboard", "regresses to the mean."]),
    ("reliability", ["Are our", "probabilities honest?"]),
    ("forecast-life", ["The life", "of a forecast."]),
    ("soccer-home-advantage", ["Home advantage,", "and why it grew."]),
    ("bookmaker-accuracy", ["We graded", "the bookmakers."]),
]

W, H = 1200, 630
PAPER = (250, 246, 238)   # --paper  #FAF6EE
INK = (26, 23, 20)        # --ink    #1A1714
INK2 = (74, 66, 59)       # --ink-2  #4A423B
INK3 = (110, 102, 95)     # --ink-3  #6E665F
ACCENT = (29, 92, 122)    # --accent #1D5C7A
RULE = (223, 214, 200)

_FONTS = "C:/Windows/Fonts"


def _font(name, size):
    return ImageFont.truetype(os.path.join(_FONTS, name), size)


def _tracked(draw, xy, text, font, fill, spacing):
    """Draw letter-spaced text (PIL has no native tracking)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + spacing
    return x


def _card(head_lines, tag_lines, kicker):
    """Draw one 1200x630 card. kicker sits beside the lockup (e.g. 'FINDINGS')."""
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    # thin accent frame -- the "receipt" edge
    d.rectangle([12, 12, W - 13, H - 13], outline=RULE, width=2)
    d.rectangle([12, 12, W - 13, 18], fill=ACCENT)  # top accent bar

    m = 72
    # --- lockup row: filled triangle mark + CourtVision + ANALYTICS (+ kicker) ---
    ty = 70
    d.polygon([(m, ty + 30), (m + 30, ty + 30), (m + 15, ty)], fill=ACCENT)
    name_f = _font("georgiab.ttf", 40)
    x = m + 48
    d.text((x, ty - 6), "CourtVision", font=name_f, fill=INK)
    x += d.textlength("CourtVision", font=name_f) + 16
    kick_f = _font("georgia.ttf", 22)
    x = _tracked(d, (x, ty + 6), "ANALYTICS", kick_f, INK3, 3)
    if kicker:
        x += 14
        d.text((x, ty + 6), "/", font=kick_f, fill=RULE)
        _tracked(d, (x + 16, ty + 6), kicker, kick_f, ACCENT, 3)

    # --- headline (two lines) ---
    head_f = _font("georgiab.ttf", 72)
    d.text((m, 214), head_lines[0], font=head_f, fill=INK)
    d.text((m, 298), head_lines[1] if len(head_lines) > 1 else "", font=head_f, fill=INK)

    # accent rule under the headline
    d.rectangle([m, 410, m + 120, 414], fill=ACCENT)

    # --- tagline (two lines) ---
    tag_f = _font("georgia.ttf", 30)
    d.text((m, 442), tag_lines[0], font=tag_f, fill=INK2)
    if len(tag_lines) > 1:
        d.text((m, 483), tag_lines[1], font=tag_f, fill=INK2)

    # --- footer: url + honest rail ---
    foot_f = _font("georgia.ttf", 23)
    d.text((m, 552), "neeljshah.github.io/court-vision/analytics", font=foot_f, fill=INK3)
    rail = "No dollar edge is claimed."
    rw = d.textlength(rail, font=foot_f)
    d.text((W - m - rw, 552), rail, font=foot_f, fill=INK3)
    return img


def build():
    os.makedirs(BRAND, exist_ok=True)
    default = _card(
        ["Every number", "wears its receipt."],
        ["Honestly-measured sports analytics across", "basketball, baseball, soccer, and tennis."],
        "",
    )
    default.save(OUT_PNG, "PNG")
    print("wrote %s (%dx%d)" % (OUT_PNG, W, H))
    for slug, head in FINDINGS:
        card = _card(head, ["A CourtVision Analytics finding -- measured, receipted,", "and published with its confounds and nulls in plain sight."], "FINDINGS")
        p = os.path.join(BRAND, "og-finding-%s.png" % slug)
        card.save(p, "PNG")
        print("wrote %s" % os.path.basename(p))


def check():
    paths = [OUT_PNG] + [os.path.join(BRAND, "og-finding-%s.png" % s) for s, _ in FINDINGS]
    for p in paths:
        assert os.path.exists(p), "%s not built" % os.path.basename(p)
        im = Image.open(p)
        assert im.size == (W, H), "%s: expected 1200x630, got %s" % (os.path.basename(p), im.size)
        assert im.mode == "RGB"
        px = im.getpixel((40, 300))
        assert abs(px[0] - PAPER[0]) < 20, "%s: background not paper: %s" % (os.path.basename(p), px)
    assert len(paths) == 1 + len(FINDINGS), "expected 1 default + %d findings cards" % len(FINDINGS)
    print("OK (%d cards)" % len(paths))


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        build()
