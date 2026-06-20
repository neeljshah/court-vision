"""scripts.platformkit.props_eval_nba_cli -- CLI entry point for NBA OOF calibration.

Separated from props_eval_nba.py to keep the library module under 300 LOC.

Usage:
  python -m scripts.platformkit.props_eval_nba_cli [--cache] [--data PATH] [--out PATH]

  --data PATH   path to pregame_oof.parquet (default: data/cache/pregame_oof.parquet)
  --cache       write calibration cache JSON after scoring
  --out PATH    output path for cache JSON (default: data/cache/props_eval_nba_calibration.json)
"""
from __future__ import annotations

from typing import Optional, Sequence

from scripts.platformkit.props_eval_nba import (
    INSUFFICIENT_DATA,
    NBA_CALIBRATION_PATH,
    score_nba_oof,
    write_nba_calibration_cache,
)


def _print_readout(res: dict) -> None:
    bar = "-" * 90
    print("=" * 90)
    print("NBA PROPS OOF CALIBRATION READOUT")
    print(bar)
    print(res.get("note", ""))
    print(bar)
    for stat in res.get("stats", []):
        d = res.get("per_stat", {}).get(stat)
        if d == INSUFFICIENT_DATA:
            print("%s INSUFFICIENT_DATA" % stat)
        elif isinstance(d, dict) and d.get("n", 0) > 0:
            print(
                "%-8s n=%6d  brier=%7s  bss=%7s  ece=%7s" % (
                    stat,
                    d["n"],
                    d.get("brier", "--"),
                    d.get("brier_skill_score", "--"),
                    d.get("ece", "--"),
                )
            )
    ov = res.get("overall", {})
    print(bar)
    print(
        "OVERALL  n=%6d  brier=%7s  bss=%7s  ece=%7s" % (
            ov.get("n", 0),
            ov.get("brier", "--"),
            ov.get("brier_skill_score", "--"),
            ov.get("ece", "--"),
        )
    )
    print("=" * 90)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="NBA OOF prop calibration readout.")
    parser.add_argument("--data", default=None, help="pregame_oof.parquet path.")
    parser.add_argument("--cache", action="store_true",
                        help="write calibration cache JSON.")
    parser.add_argument("--out", default=None, help="cache output path.")
    args = parser.parse_args(argv)

    res = score_nba_oof(oof_path=args.data)
    _print_readout(res)

    if args.cache:
        pl = write_nba_calibration_cache(oof_path=args.data, out_path=args.out)
        print("cache written=%s -> %s" % (
            pl.get("written"), args.out or NBA_CALIBRATION_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
