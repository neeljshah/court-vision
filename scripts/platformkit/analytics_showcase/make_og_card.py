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
OUT_PNG = os.path.join(ROOT, "webapp", "public", "brand", "og-analytics.png")

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


def build():
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    # thin accent frame -- the "receipt" edge
    d.rectangle([12, 12, W - 13, H - 13], outline=RULE, width=2)
    d.rectangle([12, 12, W - 13, 18], fill=ACCENT)  # top accent bar

    m = 72
    # --- lockup row: filled triangle mark + CourtVision + ANALYTICS ---
    ty = 70
    tri = [(m, ty + 30), (m + 30, ty + 30), (m + 15, ty)]
    d.polygon(tri, fill=ACCENT)
    name_f = _font("georgiab.ttf", 40)
    x = m + 48
    d.text((x, ty - 6), "CourtVision", font=name_f, fill=INK)
    x += d.textlength("CourtVision", font=name_f) + 16
    kick_f = _font("georgia.ttf", 22)
    _tracked(d, (x, ty + 6), "ANALYTICS", kick_f, INK3, 3)

    # --- headline ---
    head_f = _font("georgiab.ttf", 78)
    d.text((m, 210), "Every number", font=head_f, fill=INK)
    d.text((m, 300), "wears its receipt.", font=head_f, fill=INK)

    # accent rule under the headline
    d.rectangle([m, 415, m + 120, 419], fill=ACCENT)

    # --- tagline (two lines) ---
    tag_f = _font("georgia.ttf", 30)
    d.text((m, 445), "Honestly-measured sports analytics across", font=tag_f, fill=INK2)
    d.text((m, 486), "basketball, baseball, soccer, and tennis.", font=tag_f, fill=INK2)

    # --- footer: url + honest rail ---
    foot_f = _font("georgia.ttf", 23)
    d.text((m, 552), "neeljshah.github.io/court-vision/analytics", font=foot_f, fill=INK3)
    rail = "No dollar edge is claimed."
    rw = d.textlength(rail, font=foot_f)
    d.text((W - m - rw, 552), rail, font=foot_f, fill=INK3)

    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    img.save(OUT_PNG, "PNG")
    print("wrote %s (%dx%d)" % (OUT_PNG, W, H))


def check():
    assert os.path.exists(OUT_PNG), "og-analytics.png not built"
    im = Image.open(OUT_PNG)
    assert im.size == (W, H), "expected 1200x630, got %s" % (im.size,)
    assert im.mode == "RGB"
    # top-left should be paper-ish (inside the frame), not black -> card actually drew
    px = im.getpixel((40, 300))
    assert abs(px[0] - PAPER[0]) < 20, "background not paper-colored: %s" % (px,)
    print("OK")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        build()
