"""HYGIENE GUARDS for unattended running (MASTER_SYSTEM_BUILD section 6B).

  - DISK: require >= 20 GB free before any large write, else STOP.
  - FEED-STALE: any feed (odds/PBP/injury) stale-or-erroring -> mark STALE, skip dependent levers,
    record the gap. NEVER fabricate / extrapolate a value into a prediction.
  - POWERSHELL: any .ps1 the loop writes MUST be UTF-8 WITH BOM and ASCII-only. PS 5.1 (Windows default)
    reads a non-BOM file as Windows-1252; an em-dash byte becomes a smart-quote that 5.1 treats as a
    string delimiter -> parse-abort that froze the live stack for days. Board check asserts EF BB BF + ASCII.
"""
from __future__ import annotations
import glob
import os
import shutil
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_BOM = b"\xef\xbb\xbf"


# --------------------------------------------------------------------------- disk
def free_gb(path: str = ROOT) -> float:
    return shutil.disk_usage(path).free / 1e9


def disk_ok(min_gb: float = 20.0, path: str = ROOT) -> bool:
    return free_gb(path) >= min_gb


def require_disk(min_gb: float = 20.0, path: str = ROOT) -> None:
    g = free_gb(path)
    if g < min_gb:
        raise RuntimeError(f"DISK GUARD: only {g:.1f} GB free (< {min_gb} GB). STOP before large write (6B).")


# --------------------------------------------------------------------------- feed staleness
def feed_age_hours(path: str) -> float:
    if not os.path.exists(path):
        return float("inf")
    return (time.time() - os.path.getmtime(path)) / 3600.0


def check_feed(path: str, max_age_hours: float, name: str = "") -> dict:
    """Returns {name, exists, age_h, stale}. A stale/missing feed must SKIP dependent levers + be recorded
    -- the live path falls back to last-known-good and logs the gap; it never fabricates a value."""
    name = name or os.path.basename(path)
    exists = os.path.exists(path)
    age = feed_age_hours(path)
    return dict(name=name, exists=exists, age_h=round(age, 2) if exists else None,
                stale=(not exists) or age > max_age_hours, max_age_hours=max_age_hours)


# --------------------------------------------------------------------------- PowerShell BOM/ASCII
def ps1_ok(path: str) -> tuple[bool, list]:
    """A .ps1 is loop-safe iff it starts with a UTF-8 BOM and is ASCII-only after the BOM."""
    reasons = []
    with open(path, "rb") as f:
        raw = f.read()
    if not raw.startswith(_BOM):
        reasons.append("missing UTF-8 BOM (EF BB BF)")
        body = raw
    else:
        body = raw[len(_BOM):]
    nonascii = [i for i, b in enumerate(body) if b > 0x7F]
    if nonascii:
        reasons.append(f"{len(nonascii)} non-ASCII byte(s) (first at offset {nonascii[0]})")
    return (not reasons), reasons


def write_ps1(path: str, content: str) -> None:
    """Write a .ps1 with a UTF-8 BOM, refusing any non-ASCII content (em-dash/smart-quote -> 5.1 abort)."""
    if any(ord(c) > 0x7F for c in content):
        bad = next(c for c in content if ord(c) > 0x7F)
        raise ValueError(f"refusing non-ASCII char {bad!r} (U+{ord(bad):04X}) in a .ps1 -- "
                         f"PS 5.1 parse-abort risk (6B). Replace it with ASCII.")
    with open(path, "wb") as f:
        f.write(_BOM + content.encode("ascii"))


def lint_ps1_tree(root: str = ROOT) -> dict:
    """Scan all *.ps1 under root; return {ok, total, bad:[(path,reasons)]}. The board uses this."""
    bad = []
    files = glob.glob(os.path.join(root, "**", "*.ps1"), recursive=True)
    for fp in files:
        ok, reasons = ps1_ok(fp)
        if not ok:
            bad.append((os.path.relpath(fp, root), reasons))
    return dict(ok=(len(bad) == 0), total=len(files), bad=bad)


if __name__ == "__main__":
    import sys
    print(f"free disk: {free_gb():.1f} GB  (>=20 ok: {disk_ok()})")
    rep = lint_ps1_tree()
    print(f"ps1 lint: {rep['total']} files, {'CLEAN' if rep['ok'] else 'PROBLEMS'}")
    for p, why in rep["bad"][:20]:
        print(f"  BAD {p}: {'; '.join(why)}")
    if "--feeds" in sys.argv:
        for f in ["data/cache/odds_snapshot.parquet", "data/cache/injuries.parquet"]:
            print(check_feed(os.path.join(ROOT, f), 6.0))
