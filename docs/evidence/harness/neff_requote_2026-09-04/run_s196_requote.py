"""Build the S196 direct n_eff re-quote evidence without modifying source data."""
from __future__ import annotations

import csv
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from scripts.platformkit.eval_gate.s121_requote import clean_tick_ids
from scripts.platformkit.eval_gate.tick_informative import flag_ticks
from scripts.platformkit.foundry.ingame_supply_mlb import joined_ticks, real_game_map
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size


ROOT = Path(__file__).resolve().parents[4]
HOLDING = ROOT / "docs/evidence/harness/neff_requote_2026-09-04"
MANIFEST = HOLDING / "manifest.csv"
INVENTORY = HOLDING / "source_inventory.csv"
DIRECT = HOLDING / "direct_requotes.csv"
COPIES = HOLDING / "direct_sources"
CHUNK = 100_000
TARGET_IDS = {
    "S87b_S80_embargo1_precise", "S87b_S80_embargo0", "S87b_S80_embargo1_rounded",
    "S137_S102", "S137_S82_before", "S137_S82_after", "S137_S87_before", "S137_S87_after",
    "S137_S112_nba_before", "S137_S112_nba_after", "S137_S112_mlb_before", "S137_S112_mlb_after",
    "S137_S114_before", "S137_S114_after", "S137_S116_before", "S137_S116_after",
    "S137_S119_before", "S137_S119_after", "S137_S121_before", "S137_S121_after",
    "S137_S102_recap", "S137_S103", "S137_S115",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path, selector=None) -> tuple[pd.DataFrame, int, list[str]]:
    parts = []
    full_rows = 0
    columns: list[str] = []
    for chunk in pd.read_csv(path, chunksize=CHUNK):
        full_rows += len(chunk)
        columns = list(chunk.columns)
        if selector is not None:
            chunk = selector(chunk)
        if not chunk.empty:
            parts.append(chunk)
    return pd.concat(parts, ignore_index=True), full_rows, columns


def report(rows: pd.DataFrame, game: str, loss: str) -> dict[str, float | int | bool]:
    return effective_sample_size(rows, game, loss)


def brier_difference(rows: pd.DataFrame, candidate: str, baseline: str) -> pd.DataFrame:
    result = rows.copy()
    result["loss_differential"] = (result["y"] - result[candidate]) ** 2 - (result["y"] - result[baseline]) ** 2
    return result


def s80_informative(path: Path) -> tuple[dict[str, float | int | bool], int, list[str]]:
    rows, full_rows, columns = read_csv(path)
    rows = rows.sort_values(["game", "timestamp"], kind="stable")
    duplicate = rows.duplicated(["game", "timestamp"], keep="first")
    rows = rows.loc[~duplicate].copy()
    held_model = rows["p_candidate"].sub(rows.groupby("game")["p_candidate"].shift()).abs().le(1e-9)
    held_market = rows["market_prob"].sub(rows.groupby("game")["market_prob"].shift()).abs().le(1e-9)
    selected = rows.loc[~(held_model & held_market)].copy()
    return report(selected, "game", "loss_differential"), full_rows, columns


def parquet_s102(path: Path) -> tuple[dict[str, float | int | bool], list[str], int]:
    parts = []
    columns = None
    full_rows = 0
    for batch in pq.ParquetFile(path).iter_batches(batch_size=CHUNK):
        frame = batch.to_pandas()
        full_rows += len(frame)
        columns = list(frame.columns)
        parts.append(frame.loc[frame["hypothesis"].eq("margin_over_sqrt_rem|raw")])
    rows = pd.concat(parts, ignore_index=True)
    return report(rows, "game", "d"), columns or [], full_rows


def source_record(path: Path, row_count: int, columns: list[str], copied: bool) -> dict[str, str]:
    relative = path.relative_to(ROOT).as_posix()
    target = ""
    if copied:
        COPIES.mkdir(exist_ok=True)
        target_path = COPIES / path.name
        shutil.copyfile(path, target_path)
        target = target_path.relative_to(HOLDING).as_posix()
        assert sha256(path) == sha256(target_path)
    return {
        "source_path": relative,
        "exists": "true",
        "bytes": str(path.stat().st_size),
        "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
        "sha256": sha256(path),
        "row_count": str(row_count),
        "columns": "|".join(columns),
        "copied_artifact": target,
    }


def s119_quotes(path: Path) -> tuple[dict[str, tuple[dict[str, float | int | bool], str]], int, list[str]]:
    """Re-quote S119/S121 from their named archive and documented cluster rules."""
    rows, full_rows, columns = read_csv(path, lambda frame: frame.loc[frame["feature"].eq("tick_index_in_game")])
    rows = brier_difference(rows, "p_candidate", "p_null")
    rows["legacy_cluster"] = rows["game"].astype(str) + "#" + rows["real_game_seq"].astype(str)

    ticks = joined_ticks()
    states = dict(zip(zip(ticks["game_id"].astype(str), ticks["ts"].astype(str)), ticks["state_summary"]))
    clean = clean_tick_ids(rows, [states.get((str(game), str(stamp))) for game, stamp in zip(rows["game"], rows["timestamp"])])
    current = real_game_map(ticks)
    rows["current_cluster"] = [
        str(game) + "#" + str(current.get((str(game), str(stamp)), 1))
        for game, stamp in zip(rows["game"], rows["timestamp"])
    ]
    flagged, _ = flag_ticks(rows, market_col="market", model_col="p_candidate", loss_col="loss_differential")
    informative = flagged.loc[flagged["is_informative"]]
    partitioned = informative.loc[informative["tick_index"].isin(clean["keep"])]
    assert len(rows) == 15_702 and len(partitioned) == 15_162
    return {
        "S137_S119_before": (report(rows, "legacy_cluster", "loss_differential"), "all ticks; legacy S106 real-game cluster=game#real_game_seq"),
        "S137_S119_after": (report(rows, "current_cluster", "loss_differential"), "all ticks; corrected S131 real-game cluster=game#real_game_seq"),
        "S137_S121_before": (report(informative, "current_cluster", "loss_differential"), "informative ticks; corrected S131 real-game cluster; flag_ticks eps=1e-9, game,timestamp keep-first duplicates"),
        "S137_S121_after": (report(partitioned, "current_cluster", "loss_differential"), "tick-clean partition (15,336 raw ticks, 366 dropped), then informative ticks; corrected S131 real-game cluster; flag_ticks eps=1e-9, game,timestamp keep-first duplicates"),
    }, full_rows, columns


def main() -> None:
    manifest_rows = list(csv.DictReader(MANIFEST.open(newline="", encoding="utf-8")))
    relabelled = [row for row in manifest_rows if row["readout_id"] in TARGET_IDS]
    assert len(manifest_rows) == 45
    assert len(relabelled) == 23

    computed: dict[str, tuple[dict[str, float | int | bool], Path, int, list[str], str]] = {}
    source_rows: dict[str, dict[str, str]] = {}

    def add(ids: list[str], result, path: str, count: int, columns: list[str], rule: str) -> None:
        source = ROOT / path
        for readout_id in ids:
            computed[readout_id] = (result, source, count, columns, rule)
        source_rows[path] = source_record(source, count, columns, source.stat().st_size < 2_000_000)

    path = "data/cache/eval_gate/s80_player_grain_2026-09-03_s83.csv"
    result, full_rows, columns = s80_informative(ROOT / path)
    add(["S87b_S80_embargo1_precise", "S87b_S80_embargo1_rounded"], result, path, full_rows, columns, "informative per-game adjacent p_candidate or market_prob change, eps=1e-9; duplicate game,timestamp keep-first")

    path = "data/cache/eval_gate/s80_player_grain_2026-09-03_embargo0_s83.csv"
    result, full_rows, columns = s80_informative(ROOT / path)
    add(["S87b_S80_embargo0"], result, path, full_rows, columns, "informative per-game adjacent p_candidate or market_prob change, eps=1e-9; duplicate game,timestamp keep-first")

    path = "data/cache/eval_gate/s102_nba_sweep_top10_series.parquet"
    result, columns, full_rows = parquet_s102(ROOT / path)
    add(["S137_S102", "S137_S102_recap"], result, path, full_rows, columns, "all ticks; hypothesis=margin_over_sqrt_rem|raw; cluster=game; loss=d")

    path = "data/cache/eval_gate/s82_ingame_screen_series_2026-09-03.csv"
    rows, full_rows, columns = read_csv(ROOT / path, lambda frame: frame.loc[frame["feature"].eq("tick_index_in_game")])
    rows = brier_difference(rows, "p_candidate", "p_null")
    result = report(rows, "game", "loss_differential")
    add(["S137_S82_before", "S137_S82_after"], result, path, full_rows, columns, "all ticks; feature=tick_index_in_game; cluster=game; loss=(y-p_candidate)^2-(y-p_null)^2")

    path = "data/cache/eval_gate/s119_real_game_series_2026-09-03.csv"
    s119, full_rows, columns = s119_quotes(ROOT / path)
    for readout_id, (result, rule) in s119.items():
        add([readout_id], result, path, full_rows, columns, rule)

    path = "data/cache/eval_gate/s58_trialA_clamp_family_series_2026-09-03.csv"
    rows, full_rows, columns = read_csv(ROOT / path)
    rows = brier_difference(rows, "candidate", "incumbent_e4_gd")
    result = report(rows, "game", "loss_differential")
    add(["S137_S87_before", "S137_S87_after"], result, path, full_rows, columns, "all ticks; cluster=game; loss=(y-candidate)^2-(y-incumbent_e4_gd)^2")

    for sport, state, ids in [
        ("nba", "pre_s132", ["S137_S112_nba_before"]),
        ("nba", "current", ["S137_S112_nba_after"]),
        ("mlb", "pre_s132", ["S137_S112_mlb_before"]),
        ("mlb", "current", ["S137_S112_mlb_after"]),
    ]:
        suffix = "_pre_s132" if state == "pre_s132" else ""
        path = "data/cache/eval_gate/s112_rescore_2026-09-03_%s_fullmodel%s.csv" % (sport, suffix)
        rows, full_rows, columns = read_csv(ROOT / path)
        rows["loss_differential"] = rows["loss_close"] - rows["loss_elo"]
        result = report(rows, "cluster_id", "loss_differential")
        add(ids, result, path, full_rows, columns, "all ticks; cluster=cluster_id; loss=loss_close-loss_elo")

    path = "data/cache/eval_gate/s114_ingame_ensemble_series.csv"
    rows, full_rows, columns = read_csv(ROOT / path)
    rows = brier_difference(rows, "p_k5", "market")
    result = report(rows, "game", "loss_differential")
    add(["S137_S114_before", "S137_S114_after"], result, path, full_rows, columns, "all ticks; cluster=game; loss=(y-p_k5)^2-(y-market)^2")

    for name, ids in [
        ("s116_pooled_ingame_2026-09-03.csv", ["S137_S116_before"]),
        ("s116_pooled_ingame_2026-09-03_rerun.csv", ["S137_S116_after"]),
    ]:
        path = "data/cache/eval_gate/" + name
        rows, full_rows, columns = read_csv(ROOT / path, lambda frame: frame.loc[frame["sport"].eq("mlb")])
        result = report(rows, "cluster", "d_partial_vs_line")
        add(ids, result, path, full_rows, columns, "all ticks; sport=mlb; cluster=cluster; loss=d_partial_vs_line")

    path = "data/cache/eval_gate/s103_nba_sigma_2026-09-03.csv"
    rows, full_rows, columns = read_csv(ROOT / path)
    result = report(rows, "game", "d_wide_vs_market")
    add(["S137_S103"], result, path, full_rows, columns, "all ticks; cluster=game; loss=d_wide_vs_market")

    path = "data/cache/eval_gate/s115_ingame_models_2026-09-03.csv"
    rows, full_rows, columns = read_csv(ROOT / path)
    result = report(rows, "game", "d_mlp_vs_market")
    add(["S137_S115"], result, path, full_rows, columns, "all ticks; cluster=game; loss=d_mlp_vs_market")

    assert set(row["readout_id"] for row in relabelled) == set(computed)
    direct_rows = []
    for row in manifest_rows:
        if row["readout_id"] not in TARGET_IDS:
            continue
        result, source, row_count, columns, rule = computed[row["readout_id"]]
        quoted = float(result["n_eff"])
        published = float(row["n_eff_published"])
        identical = quoted == published
        row.update({
            "source_path": source.relative_to(ROOT).as_posix(),
            "exists": "true",
            "bytes": str(source.stat().st_size),
            "sha256": sha256(source),
            "n_ticks": str(result["n_ticks"]),
            "n_games": str(result["n_games"]),
            "rho": repr(float(result["rho"])),
            "n_eff_requoted": repr(quoted),
            "byte_identical": str(identical).lower(),
            "status": "RE-QUOTED",
            "selection_rule": rule,
            "artifact_path": "direct_sources/" + source.name if source.stat().st_size < 2_000_000 else "direct_requotes.csv",
            "note": "S196 direct helper re-quote; delta=%+.15g." % (quoted - published),
        })
        direct_rows.append({
            "readout_id": row["readout_id"],
            "source_path": row["source_path"],
            "source_sha256": row["sha256"],
            "source_bytes": row["bytes"],
            "source_row_count": row_count,
            "source_file_rows": row_count,
            "source_columns": "|".join(columns),
            "selection_rule": rule,
            "n_ticks": result["n_ticks"],
            "n_games": result["n_games"],
            "rho": repr(float(result["rho"])),
            "n_eff_published": row["n_eff_published"],
            "n_eff_direct": repr(quoted),
            "delta_direct_minus_published": repr(quoted - published),
            "byte_identical": str(identical).lower(),
        })

    with MANIFEST.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(manifest_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest_rows)
    with DIRECT.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(direct_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(direct_rows)

    inventory_rows = list(csv.DictReader(INVENTORY.open(newline="", encoding="utf-8")))
    fields = list(inventory_rows[0])
    for field in ("row_count", "columns", "copied_artifact"):
        if field not in fields:
            fields.append(field)
    for source in source_rows.values():
        existing = next((row for row in inventory_rows if row["source_path"] == source["source_path"]), None)
        if existing is None:
            inventory_rows.append({field: source.get(field, "") for field in fields})
        else:
            existing.update({field: source.get(field, existing.get(field, "")) for field in fields})
    with INVENTORY.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(inventory_rows)

    print("converted=%d" % len(direct_rows))
    print("manifest_rows=%d" % len(manifest_rows))
    print("inventory_rows=%d" % len(inventory_rows))


if __name__ == "__main__":
    main()
