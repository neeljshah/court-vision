"""Shared state helpers for bot_guards — atomic writes + spend accounting.

Atomicity matters: Path.write_text on Windows is NOT atomic. If the bot crashes
mid-write, live_status.json or spend_*.json gets truncated and the next iteration
dies on JSON parse. write_json_atomic does temp-file + os.replace which IS atomic
on Windows (POSIX too).
"""
from __future__ import annotations
import json, os, tempfile, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".bot_state"
STATE.mkdir(exist_ok=True)


def write_json_atomic(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False,
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp",
    )
    try:
        json.dump(obj, tmp, indent=2)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, path)
    except Exception:
        tmp.close()
        try: os.unlink(tmp.name)
        except OSError: pass
        raise


def read_json_safe(path: Path, default: dict) -> dict:
    if not path.exists():
        return dict(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(default)


def spend_path(date: str | None = None) -> Path:
    return STATE / f"spend_{date or dt.date.today().isoformat()}.json"


def status_path() -> Path:
    return STATE / "live_status.json"


SPEND_DEFAULT = {"usd": 0.0, "input_tokens": 0, "output_tokens": 0, "runs": 0,
                 "last_task": None, "last_update": None}


def add_spend(usd: float = 0.0, in_tok: int = 0, out_tok: int = 0,
              task_slug: str | None = None) -> dict:
    """Increment today's spend file. Safe to call from any hook."""
    p = spend_path()
    s = read_json_safe(p, SPEND_DEFAULT)
    s["usd"] = round(float(s.get("usd", 0.0)) + float(usd), 4)
    s["input_tokens"] = int(s.get("input_tokens", 0)) + int(in_tok)
    s["output_tokens"] = int(s.get("output_tokens", 0)) + int(out_tok)
    s["runs"] = int(s.get("runs", 0)) + 1
    if task_slug: s["last_task"] = task_slug
    s["last_update"] = dt.datetime.now().isoformat(timespec="seconds")
    write_json_atomic(p, s)
    return s


# Per-model pricing ($/M tokens): (input, output). Rough — only feeds the daily cap proxy.
_PRICING = {
    "opus":   (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku":  (0.80, 4.0),
}


def estimate_usd(in_tok: int, out_tok: int, model: str = "opus") -> float:
    """Rough $-equivalent of token usage. model: opus | sonnet | haiku.

    Telemetry only — this is a flat Max subscription: no per-token bill, no spend
    cap. The number just makes 'how hard did the bot run' visible in reports.
    """
    p_in, p_out = _PRICING.get(model, _PRICING["opus"])
    return round((in_tok / 1_000_000) * p_in + (out_tok / 1_000_000) * p_out, 4)


def week_usage(days: int = 7) -> dict:
    """Roll up the last `days` spend files — weekly usage telemetry.

    No cap involved (flat Max plan). Exists so the loop and reports can show how
    much of the week's capacity has actually been put to work.
    """
    today = dt.date.today()
    total = {"usd": 0.0, "input_tokens": 0, "output_tokens": 0, "runs": 0, "days": 0}
    for i in range(days):
        p = spend_path((today - dt.timedelta(days=i)).isoformat())
        if not p.exists():
            continue
        s = read_json_safe(p, SPEND_DEFAULT)
        total["usd"] += float(s.get("usd", 0.0))
        total["input_tokens"] += int(s.get("input_tokens", 0))
        total["output_tokens"] += int(s.get("output_tokens", 0))
        total["runs"] += int(s.get("runs", 0))
        total["days"] += 1
    total["usd"] = round(total["usd"], 2)
    return total
