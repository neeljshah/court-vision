"""S29: backup of the FWER audit trail (data/cache/eval_gate/).

`backtest_fwer.jsonl` is what every `deflated_p` in the program is computed against.
It is gitignored, so a volume loss or a bad write makes every past verdict
unreproducible. This copies it (plus the sibling artifacts) OUTSIDE the directory it
protects, into data/backups/eval_gate/<UTC date>/, with a manifest carrying a sha256
per file.

The source is opened READ-ONLY ("rb") and never through `_charge_ledger`; its sha256
is asserted equal before and after every copy. Row-count / k_cumulative regressions
are FLAGGED in the manifest, never blocked -- a backup that refuses to run is worse
than a backup that records a warning (pass strict=True for the raising variant).

No daemon, no loop, no scheduled task: the memo carries the schtasks line for the
orchestrator to arm.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

SRC_DIR = Path("data/cache/eval_gate")
DEST_ROOT = Path("data/backups/eval_gate")
LEDGER = "backtest_fwer.jsonl"
EXTRA = ("hypotheses.sqlite", "gate_manifest.json")
TRIAL_GLOB = "*_trial_*.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:            # read-only, always
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ledger_stats(path: Path) -> dict:
    """Row count, max k_cumulative and within-file monotonicity of a ledger COPY."""
    rows, ks = 0, []
    with open(path, "rb") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows += 1
            k = json.loads(line.decode("ascii")).get("k_cumulative")
            if k is not None:
                ks.append(int(k))
    return {
        "rows": rows,
        "k_cumulative_max": max(ks) if ks else None,
        "k_monotone": all(a <= b for a, b in zip(ks, ks[1:])),
    }


def latest(dest_root: Path = DEST_ROOT, *, before: str | None = None) -> Path | None:
    """Newest dated backup dir (optionally strictly older than `before`)."""
    if not Path(dest_root).is_dir():
        return None
    names = sorted(p.name for p in Path(dest_root).iterdir()
                   if p.is_dir() and not p.name.endswith(".tmp"))
    if before is not None:
        names = [n for n in names if n < before]
    return Path(dest_root) / names[-1] if names else None


def _sources(src_dir: Path) -> list[Path]:
    out = [src_dir / LEDGER]
    out += [src_dir / n for n in EXTRA if (src_dir / n).exists()]
    out += sorted(p for p in src_dir.glob(TRIAL_GLOB) if p.is_file())
    return out


def backup(src_dir: Path = SRC_DIR, dest_root: Path = DEST_ROOT, *,
           now_iso: str | None = None, strict: bool = False) -> dict:
    """Copy the eval_gate cache into dest_root/<UTC date>/ and write manifest.json."""
    src_dir, dest_root = Path(src_dir), Path(dest_root)
    ledger = src_dir / LEDGER
    if not ledger.exists():
        raise FileNotFoundError(f"no ledger at {ledger}")
    if now_iso is None:
        now_iso = datetime.now(timezone.utc).isoformat()
    date = now_iso[:10]

    before = _sha256(ledger)
    tmp = dest_root / (date + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    files = {}
    try:
        for src in _sources(src_dir):
            shutil.copyfile(src, tmp / src.name)     # copyfile reads, never writes src
            files[src.name] = {"sha256": _sha256(tmp / src.name),
                               "bytes": (tmp / src.name).stat().st_size}
        after = _sha256(ledger)
        if after != before:
            raise RuntimeError(f"SOURCE CHANGED during backup: {before} -> {after}")
        if files[LEDGER]["sha256"] != before:
            raise RuntimeError(f"copy sha256 {files[LEDGER]['sha256']} != source {before}")
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    stats = _ledger_stats(tmp / LEDGER)               # assertions run on the COPY
    prior_dir = latest(dest_root, before=date)
    prior = {}
    if prior_dir is not None:
        prior = json.loads((prior_dir / "manifest.json").read_text("ascii")).get("ledger", {})

    warn = []
    if not stats["k_monotone"]:
        warn.append(f"K_NONMONOTONE: k_cumulative decreases inside {LEDGER} on {date}")
    if prior:
        night = f"{prior_dir.name} -> {date}"
        if stats["rows"] < prior.get("rows", 0):
            warn.append(f"ROWS_SHRANK: {prior['rows']} -> {stats['rows']} ({night})")
        pk, k = prior.get("k_cumulative_max"), stats["k_cumulative_max"]
        if pk is not None and k is not None and k < pk:
            warn.append(f"K_REGRESSED: {pk} -> {k} ({night})")
    if warn and strict:
        raise RuntimeError("; ".join(warn))

    manifest = {
        "now_iso": now_iso,
        "date": date,
        "source_dir": str(src_dir),
        "source_sha256_before": before,
        "source_sha256_after": after,
        "files": files,
        "ledger": stats,
        "absent": [n for n in EXTRA if not (src_dir / n).exists()],
        "prior_night": prior_dir.name if prior_dir else None,
        "warn": warn,
    }
    (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2), "ascii")

    dest = dest_root / date
    if dest.exists():                                  # same-day rerun overwrites
        shutil.rmtree(dest)
    tmp.rename(dest)                                   # ponytail: rmtree+rename, not
    manifest["backup_dir"] = str(dest)                 # atomic on Windows; good enough
    return manifest                                    # for a nightly single writer


def verify(backup_dir: Path) -> dict:
    """Recompute every sha256 in the manifest. Reports OK/MISMATCH/MISSING per file."""
    backup_dir = Path(backup_dir)
    manifest = json.loads((backup_dir / "manifest.json").read_text("ascii"))
    files = {}
    for name, rec in manifest["files"].items():
        p = backup_dir / name
        if not p.exists():
            files[name] = "MISSING"
        else:
            files[name] = "OK" if _sha256(p) == rec["sha256"] else "MISMATCH"
    return {"backup_dir": str(backup_dir), "ok": all(v == "OK" for v in files.values()),
            "files": files, "ledger": manifest["ledger"], "warn": manifest["warn"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="FWER-ledger backup (S29)")
    ap.add_argument("--once", action="store_true", help="one nightly pass (default)")
    ap.add_argument("--src-dir", type=Path, default=SRC_DIR)
    ap.add_argument("--out-root", type=Path, default=DEST_ROOT)
    ap.add_argument("--verify", type=Path, metavar="DIR",
                    help="verify a backup dir (omit DIR arg's value to use --out-root latest)")
    a = ap.parse_args(argv)
    if a.verify is not None:
        print(json.dumps(verify(a.verify), indent=2))
        return 0
    print(json.dumps(backup(a.src_dir, a.out_root), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
