"""Deterministic G370 admission exports with CSV fallback."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from scripts.platformkit.tracking.g370_schema import ADMISSION_COLUMNS, canonicalize_row


def sha256_file(path: Path) -> str:
    """Return a streamed digest of an exported artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _csv_value(value: Any) -> Any:
    return json.dumps(value, sort_keys=True, separators=(",", ":")) if isinstance(value, (dict, list)) else value


def write_rows(rows: Iterable[Mapping[str, Any]], out: Path,
               control_bars: Mapping[str, bool] | None = None,
               plant_bars: Mapping[str, bool] | None = None) -> Path:
    """Write rows in a deterministic format, preferring parquet when available."""
    materialized = [canonicalize_row(row, control_bars, plant_bars) for row in rows]
    materialized.sort(key=lambda row: (str(row["game_id"]), str(row["section_id"]),
                                       int(row["frame_index"] or -1), str(row["evaluated_tick_id"])))
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix == ".parquet":
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            out = out.with_suffix(".csv")
        else:
            try:
                table = pa.Table.from_pylist(materialized)
                with pa.OSFile(str(out), "wb") as handle:
                    pq.write_table(table, handle, compression="zstd", use_dictionary=False,
                                   data_page_version="1.0", write_statistics=False)
                return out
            except pa.ArrowException:
                out.unlink(missing_ok=True)
                out = out.with_suffix(".csv")
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ADMISSION_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows([{field: _csv_value(row[field]) for field in ADMISSION_COLUMNS}
                          for row in materialized])
    return out


def write_export_hashes(rows: Iterable[Mapping[str, Any]], out: Path,
                        control_bars: Mapping[str, bool] | None = None,
                        plant_bars: Mapping[str, bool] | None = None) -> dict[str, str]:
    """Export identical rows twice and prove byte identity with digests."""
    first = write_rows(rows, out, control_bars, plant_bars)
    second = write_rows(rows, out.with_name(out.stem + "_repeat" + out.suffix), control_bars, plant_bars)
    hashes = {first.name: sha256_file(first), second.name: sha256_file(second)}
    if len(set(hashes.values())) != 1:
        raise ValueError("identical admission inputs produced different exports")
    report = out.parent / "export_hashes.json"
    report.write_text(json.dumps({"byte_identical": True, "sha256": hashes}, indent=2,
                                 sort_keys=True) + "\n", encoding="utf-8")
    return hashes


def cli() -> int:
    parser = argparse.ArgumentParser(description="G370 deterministic export")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    rows = json.loads(args.input.read_text(encoding="utf-8"))
    hashes = write_export_hashes(rows, args.out)
    print("exports={} byte_identical=1".format(len(hashes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
