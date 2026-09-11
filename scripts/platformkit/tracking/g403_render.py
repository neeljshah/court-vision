"""Deterministic G403 renders: CONSTRUCT control cards, audit sheets, binding strip."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Sequence

from PIL import Image, ImageDraw

from scripts.platformkit.tracking.g403_controls import ControlCase

FLOOR = (196, 158, 110)
LINE = (238, 238, 238)
BALL = (214, 104, 38)
SEAM = (70, 40, 20)
HARDWARE = (222, 86, 42)
BOARD = (236, 236, 240)
JERSEY = (36, 64, 148)
PATCH = (214, 104, 38)
MASK = (96, 96, 96)
BENCH = (72, 78, 88)
SILHOUETTE = (34, 37, 43)


def _ball(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    """Draw a seamed ball inside an exact native-pixel bounding box."""
    left, top, right, bottom = box
    draw.ellipse([left, top, right - 1, bottom - 1], fill=BALL, outline=SEAM)
    draw.line([left, (top + bottom) // 2, right - 1, (top + bottom) // 2], fill=SEAM)
    draw.line([(left + right) // 2, top, (left + right) // 2, bottom - 1], fill=SEAM)


def _court(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    draw.rectangle([0, 0, width - 1, height - 1], fill=FLOOR)
    draw.line([0, int(height * 0.82), width - 1, int(height * 0.82)], fill=LINE, width=3)
    draw.arc([int(width * 0.25), int(height * 0.10), int(width * 0.75), int(height * 0.74)],
             200, 340, fill=LINE, width=3)


def _bench_context(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    """Draw an off-court bench band so the spare ball is visibly non-playing."""
    sideline = height // 4
    draw.rectangle([0, 0, width - 1, sideline - 1], fill=BENCH)
    draw.line([0, sideline, width - 1, sideline], fill=LINE, width=4)
    seat_top, seat_bottom = height // 16, height // 6
    for cx in range(width // 12, width, max(1, width // 6)):
        draw.ellipse([cx - height // 64, height // 32, cx + height // 64, height // 16], fill=SILHOUETTE)
        draw.rectangle([cx - height // 48, seat_top, cx + height // 48, seat_bottom], fill=SILHOUETTE)


def render_control(case: ControlCase, out_dir: Path) -> Path:
    """Render one construct control card at native scale; identical bytes every run."""
    image = Image.new("RGB", (case.width, case.height))
    draw = ImageDraw.Draw(image)
    _court(draw, case.width, case.height)
    if case.scene == "ACTIVE_PLUS_BENCH_BALL":
        _bench_context(draw, case.width, case.height)
    for index, box in enumerate(case.distractor_boxes):
        if case.scene == "BALL_BESIDE_RIM_HARDWARE":
            draw.rectangle(list(box), fill=HARDWARE)
            draw.rectangle([box[0] - 6, box[1] - 10, box[2] + 6, box[1]], fill=BOARD)
        elif case.scene == "ACTIVE_PLUS_BENCH_BALL":
            _ball(draw, box)
        elif case.scene == "DISTRACTORS_WITHOUT_BALL":
            # No ball may appear on an ABSENT card: hardware block and a kit patch only.
            draw.rectangle(list(box), fill=HARDWARE if index == 0 else JERSEY)
        elif case.scene == "BALL_BESIDE_JERSEY_PATCH":
            draw.rectangle(list(box), fill=JERSEY)
            mid = ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)
            draw.ellipse([mid[0] - 8, mid[1] - 8, mid[0] + 8, mid[1] + 8], fill=PATCH)
        else:
            draw.rectangle(list(box), fill=MASK)
    if case.ball_bbox is not None:
        _ball(draw, case.ball_bbox)
    if case.expected_state == "UNKNOWN":
        draw.rectangle(list(case.occlusion_mask), fill=MASK)
    path = out_dir / ("control_%s.png" % case.case_id.replace("G403-", ""))
    image.save(path, "PNG", optimize=False, compress_level=6)
    return path


def render_controls(cases: Sequence[ControlCase], out_dir: Path) -> list[Path]:
    """Render every control card in catalogue order."""
    out_dir.mkdir(parents=True, exist_ok=True)
    return [render_control(case, out_dir) for case in cases]


def render_audit_sheets(cards: Sequence[Mapping[str, object]], sheets_dir: Path, out_dir: Path,
                        per_sheet: int = 6, prefix: str = "shot_audit_sheet") -> list[Path]:
    """Tile native sheets in a fixed 3-column grid so a card set is inspectable by eye."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tile_w, tile_h = 640, 360
    rows = (per_sheet + 2) // 3
    paths: list[Path] = []
    for start in range(0, len(cards), per_sheet):
        block = cards[start:start + per_sheet]
        grid = Image.new("RGB", (tile_w * 3, tile_h * rows), (0, 0, 0))
        draw = ImageDraw.Draw(grid)
        for offset, card in enumerate(block):
            source = sheets_dir / (str(card["frame_key"])[:12] + ".jpg")
            tile = Image.open(source).convert("RGB").resize((tile_w, tile_h), Image.BILINEAR)
            x, y = (offset % 3) * tile_w, (offset // 3) * tile_h
            grid.paste(tile, (x, y))
            draw.rectangle([x, y, x + 132, y + 22], fill=(0, 0, 0))
            draw.text((x + 4, y + 6), "g%03d r%s p%s" % (card["global_index"], card["round"], card["position"]),
                      fill=(255, 232, 0))
        path = out_dir / ("%s_%d.jpg" % (prefix, start // per_sheet + 1))
        grid.save(path, "JPEG", quality=88, optimize=False)
        paths.append(path)
    return paths


def render_binding_strip(pairs: Sequence[Mapping[str, object]], sheets_dir: Path, out_path: Path,
                         crop: int = 200) -> Path:
    """Crop each round-8 terra centre from its own card and from the next card.

    A one-card binding slip shows as: no ball at that pixel on the own card, the ball
    at that pixel on the next card.
    """
    strip = Image.new("RGB", (2 * crop, max(1, len(pairs)) * crop), (0, 0, 0))
    draw = ImageDraw.Draw(strip)
    for row, pair in enumerate(pairs):
        cx, cy = int(float(pair["terra_cx"])), int(float(pair["terra_cy"]))
        for column, key in enumerate((pair["own_key"], pair["next_key"])):
            source = sheets_dir / (str(key)[:12] + ".jpg")
            tile = Image.open(source).convert("RGB").crop(
                (cx - crop // 2, cy - crop // 2, cx + crop // 2, cy + crop // 2))
            strip.paste(tile, (column * crop, row * crop))
            centre = (column * crop + crop // 2, row * crop + crop // 2)
            draw.rectangle([centre[0] - 3, centre[1] - 3, centre[0] + 3, centre[1] + 3], outline=(255, 0, 0))
            draw.text((column * crop + 4, row * crop + 4),
                      "p%s %s" % (pair["position"] if column == 0 else int(pair["position"]) + 1,
                                  "own" if column == 0 else "next"), fill=(255, 232, 0))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    strip.save(out_path, "JPEG", quality=90, optimize=False)
    return out_path


def sheets_available(sheets_dir: Path) -> bool:
    """The receiver sheet store is local-only; renders that need it are skipped without it."""
    return sheets_dir.is_dir() and any(sheets_dir.glob("*.jpg")) and os.access(sheets_dir, os.R_OK)
