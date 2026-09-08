"""G327 comparison primitives -- does batching change the production detector's boxes?

Detector-agnostic by design: `run_arm` takes any
`call(list_of_frames) -> [(boxes, scores, classes), ...]`, so every function here is
testable with a synthetic detector and no GPU.

NO ground truth lives here. These functions say whether two passes AGREE; they never
say which pass is right, and nothing here is recall, precision or accuracy.

Rules sealed in `docs/evidence/tracking/g327_prereg_2026-09-08.md`.
Reads and imports src/ ; never edits it.

`g324_arms.py` is NOT on master (its commit was REJECTED), so its helpers cannot be
imported and the three primitives this row needs are re-stated here.
"""

from __future__ import annotations

import time

import numpy as np

IOU_MATCH = 0.5  # sealed; never moved
# B2 ADDITIVE: attempt 1's nine column NAMES and MEANINGS are kept; `slot` and `n_boxes`
# are NEW columns appended at the end. The five float cells carry the SAME quantities in
# a declared EXACT integer form (see `quant`), never a rounded one.
FIELDS = ("frame_index", "arm", "box_index", "x1", "y1", "x2", "y2", "score", "class",
          "slot", "n_boxes")
LEGACY_FIELDS = FIELDS[:9]   # B2: attempt 1's nine columns, still written and read


def cell(v: str) -> float:
    """One numeric cell: attempt-2's EXACT `num/den`, or attempt-1's `repr()` float."""
    return unquant(v) if "/" in v else float(v)


def chunk(seq: list, n: int) -> list[list]:
    """Contiguous chunks of n; the last chunk may be short. Every element kept."""
    if n <= 0:
        raise ValueError("batch size must be positive")
    return [seq[i:i + n] for i in range(0, len(seq), n)]


def run_arm(frames: list, call, bs: int) -> tuple[list, float | None]:
    """One arm over every frame at batch size bs. A zero-box frame keeps its slot and
    its share of the denominator. ms/frame is TOTAL elapsed / frames for every bs, so
    the single-image and batched figures are comparable."""
    rows: list = []
    start = time.perf_counter()
    for part in chunk(frames, bs):
        rows.extend(call(part))
    total = (time.perf_counter() - start) * 1000.0
    if len(rows) != len(frames):
        raise RuntimeError("arm returned %d rows for %d frames" % (len(rows), len(frames)))
    return rows, (total / len(frames)) if frames else None


def canon(row, sort: bool = False) -> np.ndarray:
    """One frame's boxes as float64 (N, 6) = x1, y1, x2, y2, score, class.

    `sort=False` keeps EMISSION ORDER, which is the order the detector's NMS returned
    and the order the ARM NMSORD arm exists to neutralise. `sort=True` orders by
    descending score then by coordinates, so a pure reorder compares equal."""
    boxes, scores, classes = row
    boxes = np.asarray(boxes, dtype=np.float64).reshape(-1, 4)
    scores = np.asarray(scores, dtype=np.float64).reshape(-1)
    classes = np.asarray(classes, dtype=np.float64).reshape(-1)
    out = np.concatenate([boxes, scores[:, None], classes[:, None]], axis=1)
    if sort and len(out):
        keys = (out[:, 3], out[:, 2], out[:, 1], out[:, 0], -out[:, 4])
        out = out[np.lexsort(keys)]
    return out


def bit_identical(left, right, sort: bool = False) -> bool:
    """Equal box count AND every coordinate, score and class equal as float64 with NO
    tolerance, under the arm's own ordering rule. Two zero-box frames ARE identical."""
    a, b = canon(left, sort), canon(right, sort)
    return a.shape == b.shape and bool(np.array_equal(a, b))


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Pairwise IoU of two (N, >=4) and (M, >=4) box sets."""
    if not len(a) or not len(b):
        return np.zeros((len(a), len(b)))
    ax1, ay1, ax2, ay2 = (a[:, i][:, None] for i in range(4))
    bx1, by1, bx2, by2 = (b[:, i][None, :] for i in range(4))
    iw = np.clip(np.minimum(ax2, bx2) - np.maximum(ax1, bx1), 0, None)
    ih = np.clip(np.minimum(ay2, by2) - np.maximum(ay1, by1), 0, None)
    inter = iw * ih
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return np.where(union > 0, inter / np.where(union > 0, union, 1.0), 0.0)


def greedy_pairs(a: np.ndarray, b: np.ndarray, thr: float = IOU_MATCH) -> list:
    """ONE-TO-ONE (i, k) matches at IoU >= thr, greedy by DESCENDING IoU. Stated as
    greedy because a different assignment rule can give a different count."""
    m = iou_matrix(a, b)
    if not m.size:
        return []
    order = np.dstack(np.unravel_index(np.argsort(m, axis=None)[::-1], m.shape))[0]
    used_a, used_b, pairs = set(), set(), []
    for i, k in order:
        if m[i, k] < thr:
            break
        if i not in used_a and k not in used_b:
            used_a.add(int(i))
            used_b.add(int(k))
            pairs.append((int(i), int(k)))
    return pairs


def greedy_match(a: np.ndarray, b: np.ndarray, thr: float = IOU_MATCH) -> int:
    """The COUNT of one-to-one matches; the pairing itself is `greedy_pairs`."""
    return len(greedy_pairs(a, b, thr))


def compare(ref_rows: list, arm_rows: list, sort: bool = False) -> dict:
    """Frame-by-frame verdict of one arm against the single-image reference.

    BIT-IDENTITY and IoU AGREEMENT are reported SEPARATELY: two box sets can agree
    both ways at IoU >= 0.5 and still not be bit-identical, and only bit-identity
    feeds the sealed verdict bars."""
    n = len(ref_rows)
    if len(arm_rows) != n:
        raise ValueError("arm has %d frames, reference has %d" % (len(arm_rows), n))
    ident = [bit_identical(r, a, sort) for r, a in zip(ref_rows, arm_rows)]
    deltas, matched, boxes_ref, boxes_arm, zero_ref, zero_arm = [], 0, 0, 0, 0, 0
    for r, a in zip(ref_rows, arm_rows):
        cr, ca = canon(r), canon(a)
        deltas.append(len(ca) - len(cr))
        matched += greedy_match(cr, ca)
        boxes_ref += len(cr)
        boxes_arm += len(ca)
        zero_ref += int(not len(cr))
        zero_arm += int(not len(ca))
    return {"frames": n, "bit_identical_frames": int(sum(ident)),
            "bit_identical_all": bool(all(ident)),
            "per_frame_bit_identical": [bool(x) for x in ident],
            "per_frame_count_delta": deltas,
            "abs_count_delta_total": int(sum(abs(d) for d in deltas)),
            "boxes_ref": boxes_ref, "boxes_arm": boxes_arm, "matched": matched,
            "agree_ref_in_arm": (matched / boxes_ref) if boxes_ref else None,
            "agree_arm_in_ref": (matched / boxes_arm) if boxes_arm else None,
            "zero_box_frames_ref": zero_ref, "zero_box_frames_arm": zero_arm,
            "ordering": "sorted" if sort else "emission", "iou_match": IOU_MATCH}


def quant(v: float) -> str:
    """A float64 as its EXACT dyadic fraction `num/den`, both zero-padded to 6 digits.

    Every finite double is num / 2**k exactly, so this round-trips with NO tolerance --
    which a rounded `%.6f` would not, and which recomputing bit-identity from the CSV
    alone requires. The form is also PURE DIGITS: a decimal point cannot be reformatted
    out of a decimal, and attempt 1's shortest-round-tripping `repr()` cells carried
    restricted digit sequences on 12 of their committed rows (contract Q6).
    """
    num, den = float(v).as_integer_ratio()
    return "%s%06d/%06d" % ("-" if num < 0 else "", abs(num), den)


def unquant(cell: str) -> float:
    """Inverse of `quant`, exact: the value is representable, so the division is too."""
    num, den = cell.split("/")
    return int(num) / int(den)


def write_arm_csv(path, arm: str, games: list) -> int:
    """ONE raw CSV for ONE arm over `games` = [(slot, frame_indices, rows)], written by
    the arm itself AT RUN TIME.

    EVERY evaluated frame appears. A frame the detector returned no boxes for is an
    EXPLICIT row with `n_boxes` 000000 and empty box fields, so the denominator lives in
    the file instead of being restored from a summary -- the attempt-1 defect. Boxes stay
    in the arm's OWN emission order with their box_index, so a verifier can recompute
    bit-identity, the count deltas and the greedy IoU matching from these cells alone.
    """
    n = 0
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write(",".join(FIELDS) + "\n")
        for slot, idxs, rows in games:
            for i, row in zip(idxs, rows):
                boxes = canon(row)
                if not len(boxes):
                    fh.write(",".join(["%06d" % i, arm] + [""] * 7
                                      + ["%06d" % slot, "%06d" % 0]) + "\n")
                    n += 1
                    continue
                for k, box in enumerate(boxes):
                    fh.write(",".join(["%06d" % i, arm, "%06d" % k]
                                      + [quant(float(v)) for v in box[:5]]
                                      + ["%06d" % int(box[5]), "%06d" % slot,
                                         "%06d" % len(boxes)]) + "\n")
                    n += 1
    return n


def read_arm_csv(path) -> tuple[dict, dict]:
    """Inverse of `write_arm_csv`: `(order, table)` where `order` maps slot -> the frame
    indices IN FILE ORDER, zero-box frames included, and `table` maps slot -> frame ->
    boxes. The scorer builds every reported value from this and from nothing else.

    A MALFORMED ROW RAISES: the arm cell must match the file's arm, box indices must run
    0..n-1 inside a frame, and `n_boxes` must equal the boxes parsed -- a truncated or
    spliced CSV would otherwise reconstruct into a plausible table. Attempt-1's nine
    columns carry no `slot`/`n_boxes`: slot 0, declared-count check skipped."""
    order: dict = {}
    table: dict = {}
    declared: dict = {}
    file_arm = None
    with open(path, encoding="ascii") as fh:
        head = tuple(fh.readline().rstrip("\n").split(","))
        if head not in (FIELDS, LEGACY_FIELDS):
            raise ValueError("unexpected header %r" % (head,))
        legacy = head == LEGACY_FIELDS
        for line in fh:
            if not line.strip():
                continue
            cells = line.rstrip("\n").split(",")
            if len(cells) != len(head):
                raise ValueError("row has %d cells, not %d" % (len(cells), len(head)))
            f, a, k, x1, y1, x2, y2, sc, cl = cells[:9]
            slot = "000000" if legacy else cells[9]
            if file_arm is None:
                file_arm = a
            elif a != file_arm:
                raise ValueError("row arm %r is not the file arm %r" % (a, file_arm))
            s, i = int(slot), int(f)
            seen = order.setdefault(s, [])
            if not seen or seen[-1] != i:
                seen.append(i)
            per = table.setdefault(s, {}).setdefault(i, [])
            if not legacy and declared.setdefault((s, i), int(cells[10])) != int(cells[10]):
                raise ValueError("frame %d declares two different n_boxes" % i)
            if x1 == "":          # the explicit zero-box row: keeps the frame, adds no box
                continue
            if int(k) != len(per):
                raise ValueError("frame %d box_index %s is out of sequence" % (i, k))
            per.append(([cell(x1), cell(y1), cell(x2), cell(y2)], cell(sc), float(int(cl))))
    for (s, i), n in declared.items():
        if n != len(table[s][i]):
            raise ValueError("frame %d declares %d, parsed %d" % (i, n, len(table[s][i])))
    return order, table


def read_boxes_csv(path) -> dict:
    """B2 COMPATIBILITY -- attempt 1's reader, same signature and same return
    `{arm: {frame: [(box, score, class), ...]}}`. Reads either column set."""
    out: dict = {}
    with open(path, encoding="ascii") as fh:
        head = tuple(fh.readline().rstrip("\n").split(","))
        if head not in (FIELDS, LEGACY_FIELDS):
            raise ValueError("unexpected header %r" % (head,))
        for line in fh:
            if not line.strip():
                continue
            f, arm, _k, x1, y1, x2, y2, sc, cl = line.rstrip("\n").split(",")[:9]
            per = out.setdefault(arm, {}).setdefault(int(f), [])
            if x1 != "":
                per.append(([cell(x1), cell(y1), cell(x2), cell(y2)],
                            cell(sc), cell(cl)))
    return out


def write_boxes_csv(path, idxs: list[int], arms: dict) -> int:
    """B2 COMPATIBILITY -- attempt 1's multi-arm writer: same nine columns and `repr()`
    cells. This row writes `write_arm_csv`; this keeps attempt-1 callers alive."""
    n = 0
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write(",".join(LEGACY_FIELDS) + "\n")
        for arm in sorted(arms):
            for i, row in zip(idxs, arms[arm]):
                for k, box in enumerate(canon(row)):
                    fh.write("%d,%s,%d,%s,%d\n"
                             % (i, arm, k,
                                ",".join(repr(float(v)) for v in box[:5]), int(box[5])))
                    n += 1
    return n


def rows_for(table: dict, arm, idxs: list[int] | None = None) -> list:
    """Frames in the DECLARED order with zero-box frames restored as empty box sets.

    B2: attempt 1's `rows_for(table, arm, idxs)` still works; this row calls the
    two-argument form on ONE arm's sub-table."""
    per, idxs = (table, arm) if idxs is None else (table.get(arm, {}), idxs)
    rows = []
    for i in idxs:
        hits = per.get(i, [])
        rows.append((np.asarray([h[0] for h in hits], dtype=np.float64).reshape(-1, 4),
                     np.asarray([h[1] for h in hits], dtype=np.float64),
                     np.asarray([h[2] for h in hits], dtype=np.float64)))
    return rows
