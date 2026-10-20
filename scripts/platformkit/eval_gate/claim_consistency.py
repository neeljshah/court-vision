"""scripts.platformkit.eval_gate.claim_consistency -- cross-page figure consistency gate.

Reads docs/evidence/CANONICAL_FIGURES.json and scans every tracked markdown page under its
surface_roots (minus local-only trees and dated harness memos before the cutoff) line by line:

  STALE      a stale-claim pattern (e.g. MLB/soccer "within noise") on a line without
             correction framing (retracted / corrected / superseded / do-not-claim).
  DISAGREE   a figure's anchor (its gap token) followed by a [lo, hi] interval that differs
             from the canonical ci95 at 4 decimals, or by a verdict word (MATCHES_CLOSE /
             TRAILS_CLOSE / BEATS_CLOSE) that differs from the canonical verdict.
  RETRACTED  a retracted figure outside framing: no framing word (or "artifact") within 2 lines,
             and none in the markdown heading above it.
  LANGUAGE   a strict-language surface (the methods pages) carries a forbidden token.
  MISSING    a listed surface does not exist.
  COUNT      on a canonical_counts.count_surfaces page (no framing word on the line): a commit
             count, published-module count, findings count or forward-window end date that
             differs from canonical_counts (a dated historical value passes only on a line that
             matches its `requires` pattern).
  WORDING    a canonical_counts `forbidden` phrase (G6 "zero qualifying weeks"; the record says
             G6 has not started).

Updating a canonical count: re-run the command or read the artifact named in its `source`
(e.g. `git rev-list --count origin/master` in the public clone; module_count in the site
manifest; the findings page count), set `value` and `as_of` to the run date, move the old value
under `historical` with its own as_of and a `requires` regex only if pages may keep citing it
dated, then fix every page this gate flags. `--explain` prints each figure with its source.

Exit 0 when clean, 1 with a counted list. Calibration language only; no figure is computed here.
CLI: python -m scripts.platformkit.eval_gate.claim_consistency --repo-root . [--explain] [extra ...]
Test: python -m pytest scripts/platformkit/eval_gate/test_claim_consistency.py -q
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

FIGURES_REL = "docs/evidence/CANONICAL_FIGURES.json"
VERDICTS = ("MATCHES_CLOSE", "TRAILS_CLOSE", "BEATS_CLOSE")
_NUM = r"[+-]?\d*\.\d+"
_CI = re.compile(r"^[^\[\]|]{0,40}?\[\s*(" + _NUM + r")\s*,\s*(" + _NUM + r")\s*\]")
# ponytail: line-level heuristics, not a parser. A claim wrapped across two markdown lines
# is missed; widen to sentence windows only if a real wrapped hit slips through.
_VERDICT_WINDOW = 160
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def load(repo_root: Path, figures_path: Path | None = None) -> dict:
    path = figures_path or repo_root / FIGURES_REL
    return json.loads(path.read_text(encoding="utf-8"))


def _framed(text: str, words: list[str]) -> bool:
    low = text.lower()
    return any(w in low for w in words)


def _retracted_re(token: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\d.])" + re.escape(token) + r"(?!\d)")


def _check_figure(line: str, fig: dict, anchors: list[re.Pattern[str]]) -> list[str]:
    out = []
    for m in re.finditer(fig["anchor"], line):
        rest = line[m.end():]
        ci = _CI.match(rest)
        want = fig.get("ci95")
        if ci and want:
            got = [round(float(ci.group(1)), 4), round(float(ci.group(2)), 4)]
            ok = [[round(x, 4) for x in c] for c in [want] + fig.get("also_ci95", [])]
            if got not in ok:
                out.append("%s interval %s != canonical %s" % (fig["key"], got, want))
        # verdict window: up to the next other figure's anchor, or a fixed width
        window = rest[:_VERDICT_WINDOW]
        for other in anchors:
            om = other.search(window)
            if om and om.start() > 0:
                window = window[:om.start()]
        found = [v for v in VERDICTS if v in window]
        if found and fig.get("verdict") in VERDICTS and found[0] != fig["verdict"]:
            out.append("%s verdict %s != canonical %s" % (fig["key"], found[0], fig["verdict"]))
    return out


def scan_text(rel: str, text: str, cfg: dict, strict: bool = False) -> list[str]:
    """Return 'KIND rel:line: detail' findings for one surface's text."""
    words = cfg.get("framing_words", [])
    stale = [(s["key"], re.compile(s["pattern"]), re.compile(s.get("unless", "(?!)")))
             for s in cfg.get("stale_claims", [])]
    retracted = [(t, _retracted_re(t)) for t in cfg.get("retracted_tokens", [])]
    forbidden = [re.compile(p) for p in cfg.get("strict_forbidden_patterns", [])] if strict else []
    figs = cfg.get("figures", [])
    anchors = [re.compile(f["anchor"]) for f in figs if f.get("anchor")]
    rwords = words + cfg.get("retraction_window_words", [])
    lines = text.splitlines()
    out: list[str] = []
    heading = ""
    for i, line in enumerate(lines, 1):
        if line.lstrip().startswith("#"):
            heading = line
        where = "%s:%d" % (rel, i)
        framed = _framed(line, words)
        if not framed:
            for key, pat, unless in stale:
                if pat.search(line) and not unless.search(line):
                    out.append("STALE %s: %s" % (where, key))
            for f in figs:
                if f.get("anchor"):
                    out += ["DISAGREE %s: %s" % (where, d) for d in _check_figure(line, f, anchors)]
        near = " ".join(lines[max(0, i - 3):i + 2])  # this line +/- 2 lines
        if not (_framed(near, rwords) or _framed(heading, words)):
            for tok, pat in retracted:
                if pat.search(line):
                    out.append("RETRACTED %s: %s outside retraction framing" % (where, tok))
        for pat in forbidden:
            if pat.search(line):
                out.append("LANGUAGE %s: forbidden token /%s/" % (where, pat.pattern))
    return out


def _count_ok(got: str, fig: dict, line: str) -> bool:
    if isinstance(fig["value"], str):
        return got == fig["value"]
    n = int(got.replace(",", ""))
    return n == fig["value"] or any(n == h["value"] and re.search(h["requires"], line)
                                    for h in fig.get("historical", []))


def scan_counts(rel: str, text: str, cfg: dict) -> list[str]:
    """COUNT / WORDING findings for canonical_counts figures on one count surface."""
    words = cfg.get("framing_words", [])
    figs = cfg.get("canonical_counts", {}).get("figures", [])
    out: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        if _framed(line, words):
            continue
        where = "%s:%d" % (rel, i)
        for f in figs:
            if f.get("unless") and re.search(f["unless"], line):
                continue
            if f.get("forbidden") and re.search(f["forbidden"], line):
                out.append("WORDING %s: %s phrasing /%s/; canonical: %s"
                           % (where, f["key"], f["forbidden"], f["value"]))
            for m in re.finditer(f.get("pattern") or "(?!)", line):
                if not _count_ok(m.group(1), f, line):
                    out.append("COUNT %s: %s %s != canonical %s (as of %s)"
                               % (where, f["key"], m.group(1), f["value"], f["as_of"]))
    return out


def explain(cfg: dict) -> list[str]:
    """One line per canonical figure: key, value, as_of, source (to re-derive it)."""
    out = []
    for f in cfg.get("canonical_counts", {}).get("figures", []):
        out.append("%s = %s (as of %s) <- %s" % (f["key"], f["value"], f["as_of"], f["source"]))
        out += ["  historical %s (as of %s) <- %s" % (h["value"], h["as_of"], h["source"])
                for h in f.get("historical", [])]
    for f in cfg.get("figures", []):
        val = f.get("gap", f.get("ttl_30_fills_credited"))
        out.append("%s = %s %s (as of %s) <- %s"
                   % (f["key"], val, f.get("verdict", ""), f["as_of"], f["source"]))
    return out


def default_surfaces(repo_root: Path, cfg: dict) -> list[str]:
    """Tracked markdown under the configured roots, minus local-only trees and old dated memos."""
    roots = cfg.get("surface_roots", [])
    try:
        listed = subprocess.run(["git", "ls-files", "--", *roots], cwd=repo_root, check=True,
                                capture_output=True, text=True).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        # ponytail: no git (tarball export) -> walk the roots; untracked files would be included
        listed = [p.relative_to(repo_root).as_posix() for r in roots
                  for p in ([repo_root / r] if r.endswith(".md") else (repo_root / r).rglob("*.md"))]
    skip = tuple(cfg.get("exclude_prefixes", []))
    out = []
    for rel in listed:
        if not rel.endswith(".md") or rel.startswith(skip):
            continue
        m = _DATE.search(rel.rsplit("/", 1)[-1])
        if m and any(rel.startswith(o["prefix"]) and m.group(0) < o["before"]
                     for o in cfg.get("exclude_dated_memos", [])):
            continue
        out.append(rel)
    return sorted(set(out) | set(cfg.get("surfaces", [])))


def check(repo_root: Path, extra: list[str] | None = None,
          figures_path: Path | None = None, defaults: bool = True) -> list[str]:
    cfg = load(repo_root, figures_path)
    strict = set(cfg.get("strict_language_surfaces", []))
    counted = set(cfg.get("canonical_counts", {}).get("count_surfaces", []))
    out: list[str] = []
    base = default_surfaces(repo_root, cfg) if defaults else []
    for rel in base + list(extra or []):
        path = Path(rel) if Path(rel).is_absolute() else repo_root / rel
        if not path.is_file():
            out.append("MISSING %s" % rel)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        out += scan_text(rel, text, cfg, strict=rel in strict)
        if rel in counted:
            out += scan_counts(rel, text, cfg)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--figures", default=None, help="alternate figures JSON path")
    ap.add_argument("--explain", action="store_true", help="print each canonical figure + source")
    ap.add_argument("extra", nargs="*", help="extra surface paths (repo-relative or absolute)")
    args = ap.parse_args(argv)
    root = Path(args.repo_root).resolve()
    if args.explain:
        for line in explain(load(root, Path(args.figures) if args.figures else None)):
            print(line.encode("ascii", "replace").decode("ascii"))
        return 0
    findings = check(root, args.extra, Path(args.figures) if args.figures else None)
    for f in findings:
        print(f.encode("ascii", "replace").decode("ascii"))
    print("claim_consistency: %d finding(s)" % len(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
