"""Merge the Ask-Scout bucket files into one corpus for AskScout.tsx to search.

Reads webapp/public/data/ask/<bucket>.json (each {"bucket": str, "entries": [...]})
and writes webapp/public/data/ask/corpus.json as {"entries": [...]}: one entry per
question, tagged with its source bucket, deduped by "q" (first occurrence wins).

Run:   python -m scripts.platformkit.analytics_showcase.build_ask_corpus
Check: python -m scripts.platformkit.analytics_showcase.build_ask_corpus --check
--check does no filesystem writes.
"""
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_ASK_DIR = _REPO / "webapp" / "public" / "data" / "ask"
_CORPUS = _ASK_DIR / "corpus.json"


def _iter_bucket_files(ask_dir):
    return sorted(f for f in ask_dir.glob("*.json") if f.name != "corpus.json")


def _merge(ask_dir=_ASK_DIR):
    """Returns (entries, n_files, n_dupes). No filesystem writes."""
    entries = []
    seen = set()
    n_dupes = 0
    files = _iter_bucket_files(ask_dir)
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        bucket = data.get("bucket", f.stem)
        for e in data.get("entries", []):
            q = e.get("q")
            if q in seen:
                n_dupes += 1
                continue
            seen.add(q)
            tagged = dict(e)
            tagged["bucket"] = bucket
            entries.append(tagged)
    return entries, len(files), n_dupes


def _rel(p):
    return str(p.relative_to(_REPO)).replace("\\", "/")


def build():
    entries, n_files, n_dupes = _merge()
    _CORPUS.write_text(
        json.dumps({"entries": entries}, indent=1, ensure_ascii=True), encoding="utf-8")
    print(f"corpus: merged {n_files} bucket files -> {len(entries)} entries "
          f"({n_dupes} duplicate q dropped) -> {_rel(_CORPUS)}")
    return entries


def check():
    """Static, no-write: recompute the merge and assert it's sane."""
    entries, n_files, n_dupes = _merge()
    assert n_files > 0, "no bucket files found"
    assert len(entries) > 0, "no entries merged"
    qs = [e["q"] for e in entries]
    assert len(qs) == len(set(qs)), "duplicate q survived dedupe"
    for e in entries:
        assert "bucket" in e and "q" in e and "a" in e, f"malformed entry: {e.get('q')}"
    print(f"PASS -- {n_files} bucket files, {len(entries)} deduped entries, "
          f"{n_dupes} duplicates dropped (no writes)")


def demo():
    """Self-check on synthetic input: dedupe + bucket-tagging behave."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "a.json").write_text(json.dumps({"bucket": "a", "entries": [
            {"q": "x", "a": {"status": "ok"}}, {"q": "y", "a": {"status": "ok"}}]}))
        (d / "b.json").write_text(json.dumps({"bucket": "b", "entries": [
            {"q": "x", "a": {"status": "ok"}}]}))  # duplicate "q" -- must be dropped
        entries, n_files, n_dupes = _merge(ask_dir=d)
    assert n_files == 2, n_files
    assert n_dupes == 1, n_dupes
    assert len(entries) == 2, entries
    assert entries[0]["bucket"] == "a" and entries[0]["q"] == "x"
    assert entries[1]["bucket"] == "a" and entries[1]["q"] == "y"
    print("demo OK")


def main():
    if "--check" in sys.argv:
        check()
    elif "--demo" in sys.argv:
        demo()
    else:
        build()


if __name__ == "__main__":
    main()
