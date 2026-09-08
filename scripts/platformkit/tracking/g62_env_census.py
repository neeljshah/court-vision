"""G62 premise census: which committed evidence artifact directories record their environment.

Scope, reading and detection rules are fixed verbatim in
docs/evidence/tracking/g62_prereg_2026-09-08.md section 1 and are not re-decided here. An ARTIFACT
DIRECTORY is every immediate child directory of docs/evidence/tracking/ or docs/evidence/harness/
holding at least one git-tracked file at any depth; every tracked file below it is scanned. Files
sitting directly in a root are counted as their own out-of-scope class. The G62 output directory is
excluded by name so this census stays reproducible after the row lands.
"""
import argparse
import gzip
import json
import re
import subprocess
from pathlib import Path

ROOTS = ("docs/evidence/tracking", "docs/evidence/harness")
EXCLUDE = "docs/evidence/tracking/g62_environment_sidecar_2026-09-08"
BINARY = {".png", ".jpg", ".jpeg", ".mp4", ".pt", ".npy", ".npz", ".parquet", ".zip", ".tar",
          ".ico", ".pdf"}
ENV_KEYS = {"python", "python_version", "py_version", "platform", "hostname", "host", "node",
            "nodename", "torch", "torch_version", "numpy", "numpy_version", "pandas", "cv2",
            "cv2_version", "opencv", "opencv_version", "ultralytics", "scipy", "sklearn", "cuda",
            "cuda_version", "cudnn", "omp_num_threads", "mkl_num_threads", "torch_num_threads",
            "num_threads", "threads", "thread_count", "cpu_count", "environment", "env"}
TEXT_RULES = (
    ("python_version", re.compile(r"python.{0,12}?3\.\d", re.I | re.S)),
    ("numpy_version", re.compile(r"numpy[ _=:v\"',]{0,4}\d+\.\d", re.I)),
    ("torch_version", re.compile(r"torch[ _=:v\"',]{0,4}\d+\.\d", re.I)),
    ("cv2_version", re.compile(r"(cv2|opencv)[ _=:v\"',]{0,4}\d+\.\d", re.I)),
    ("ultralytics_version", re.compile(r"ultralytics[ _=:v\"',]{0,4}\d+\.\d", re.I)),
    ("thread_env_var", re.compile(r"OMP_NUM_THREADS|MKL_NUM_THREADS")),
    ("thread_count", re.compile(r"threads?[ =:]+\d", re.I)),
    ("hostname", re.compile(r"hostname", re.I)),
)
PYTHON_LABELS = {"python_version", "key:python", "key:python_version", "key:py_version"}
NUMPY_LABELS = {"numpy_version", "key:numpy", "key:numpy_version"}
COLUMNS = ("root,directory,files_tracked,files_scanned,files_binary,has_env_record,"
           "has_python_version,has_numpy_version,keys_found")


def pad6(value):
    return "%06d" % int(value)


def _json_keys(node, out):
    if isinstance(node, dict):
        for key, value in node.items():
            out.add(str(key).lower())
            _json_keys(value, out)
    elif isinstance(node, list):
        for value in node:
            _json_keys(value, out)


def scan_file(path):
    """Matched detection labels for one file; None when it is binary or unreadable."""
    if path.suffix.lower() in BINARY:
        return None
    try:
        raw = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    except BaseException:
        return None
    text = raw.decode("utf-8", "replace")
    stem = path.name[:-3] if path.suffix == ".gz" else path.name
    found = set()
    if stem.endswith(".json") or stem.endswith(".jsonl"):
        chunks = [text] if stem.endswith(".json") else text.splitlines()
        for chunk in chunks:
            try:
                document = json.loads(chunk)
            except BaseException:
                continue
            keys = set()
            _json_keys(document, keys)
            found |= {"key:" + key for key in keys & ENV_KEYS}
    for label, pattern in TEXT_RULES:
        if pattern.search(text):
            found.add(label)
    return found


def tracked_files(root):
    out = subprocess.run(["git", "ls-files"] + list(ROOTS), capture_output=True, text=True,
                         check=True, cwd=str(root))
    return [line for line in out.stdout.replace("\r\n", "\n").split("\n") if line.strip()]


def census(root):
    """One row per artifact directory plus the loose-file class, in path order."""
    groups, loose = {}, []
    for name in tracked_files(root):
        parent = name.rsplit("/", 1)[0]
        if parent in ROOTS:
            loose.append(name)
            continue
        head = "/".join(name.split("/")[:4])
        if head == EXCLUDE:
            continue
        groups.setdefault(head, []).append(name)
    rows = []
    for directory in sorted(groups) + ["LOOSE_FILES_DIRECTLY_IN_ROOTS"]:
        names = loose if directory.startswith("LOOSE") else groups[directory]
        labels, scanned, binary = set(), 0, 0
        for name in names:
            found = scan_file(root / name)
            if found is None:
                binary += 1
            else:
                scanned += 1
                labels |= found
        rows.append({
            "root": "both_roots" if directory.startswith("LOOSE") else (
                ROOTS[1] if directory.startswith(ROOTS[1]) else ROOTS[0]),
            "directory": directory, "files_tracked": len(names), "files_scanned": scanned,
            "files_binary": binary, "has_env_record": bool(labels),
            "has_python_version": bool(labels & PYTHON_LABELS),
            "has_numpy_version": bool(labels & NUMPY_LABELS),
            "keys_found": "|".join(sorted(labels)) or "none"})
    return rows


def write_csv(rows, path):
    lines = [COLUMNS]
    for row in rows:
        lines.append(",".join([
            row["root"], row["directory"], pad6(row["files_tracked"]), pad6(row["files_scanned"]),
            pad6(row["files_binary"]), str(row["has_env_record"]).lower(),
            str(row["has_python_version"]).lower(), str(row["has_numpy_version"]).lower(),
            row["keys_found"]]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def summarise(rows):
    dirs = [row for row in rows if not row["directory"].startswith("LOOSE")]
    both = [row for row in dirs if row["has_python_version"] and row["has_numpy_version"]]
    any_record = [row for row in dirs if row["has_env_record"]]
    return {"directories": len(dirs), "with_any_env_record": len(any_record),
            "with_python_and_numpy": len(both),
            "premise_false": len(both) * 2 > len(dirs)}


def main(argv=None):
    parser = argparse.ArgumentParser(description="G62 environment-record premise census")
    parser.add_argument("--root", default=".")
    parser.add_argument("--csv", default="")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    rows = census(root)
    if args.csv:
        write_csv(rows, Path(args.csv))
    totals = summarise(rows)
    print("ARTIFACT_DIRECTORIES n=%s" % pad6(totals["directories"]))
    print("WITH_ANY_ENVIRONMENT_RECORD n=%s" % pad6(totals["with_any_env_record"]))
    print("WITH_PYTHON_AND_NUMPY n=%s" % pad6(totals["with_python_and_numpy"]))
    loose = [row for row in rows if row["directory"].startswith("LOOSE")][0]
    print("LOOSE_FILES_DIRECTLY_IN_ROOTS n=%s has_env_record=%s"
          % (pad6(loose["files_tracked"]), str(loose["has_env_record"]).lower()))
    print("PREMISE %s" % ("FALSE" if totals["premise_false"] else "HOLDS"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
