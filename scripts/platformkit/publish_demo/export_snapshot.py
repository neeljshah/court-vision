"""export_snapshot.py -- bake the running P5/boards services into static JSON
for the GitHub Pages demo build (webapp/public/demo-data/*.json).

READ-ONLY against the RUNNING services (:8099 P5, :8098 boards) -- never
reads data/ or vault/ directly. Filenames are produced by the SAME slug the
client's fetchHonest.snapshotPath() uses (webapp/lib/fetchHonest.ts), so a
snapshot-mode client fetch of an URL resolves to exactly the file this script
wrote for that URL.

Endpoint list: derived by grepping webapp/lib/p5api.ts + app/**/*.tsx call
sites (2026-07-15) for every `api.<method>(...)` in use. Best-effort, not an
AST-verified source of truth -- see the ENDPOINTS registry below.
ponytail: paginated/limit-varying endpoints (paper trail, paper predictions)
only bake the ONE (sport, limit/offset) combo actually hit on first paint of
the page that uses them; other combos degrade to the honest Unavailable
sentinel in the demo. Upgrade to multi-variant baking if a demo page needs it.

Usage: python scripts/platformkit/publish_demo/export_snapshot.py
  [--p5 http://127.0.0.1:8099] [--boards http://127.0.0.1:8098]
  [--out webapp/public/demo-data]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT = REPO_ROOT / "webapp" / "public" / "demo-data"

SPORTS = ["nba", "mlb", "soccer", "soccer_intl", "tennis"]

# Secrets that must never appear in a baked demo file. Checked against the
# full JSON text (key names AND values) -- fail closed, refuse the file.
SECRET_PATTERN = re.compile(r"(api_key|secret|token|password)", re.IGNORECASE)

# Row-array keys that get capped to the most-recent N rows (bounds payload
# size / limits exposure of the full paper history in a public demo).
TRAIL_KEYS = ("trail", "predictions", "rows")
TRAIL_CAP = 300


def slug(path: str) -> str:
    """MUST match webapp/lib/fetchHonest.ts:snapshotPath() exactly."""
    s = re.sub(r"^/+", "", path)
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s)
    return f"{s}.json"


def to_bet_id(row: dict[str, Any]) -> str:
    """MUST mirror components/paper_pm/PmTradeRow.tsx:toBetId() exactly -- the
    /paper/[betId] route matches on this same encoding."""
    parts = [
        row.get("sport") or "unknown",
        row.get("game_id") or "unknown",
        row.get("market_type") or "moneyline",
        row.get("side") or "home",
        row.get("taken_book") or "paper",
    ]
    return quote("|".join(parts), safe="")


def cap_trail_rows(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    for key in TRAIL_KEYS:
        rows = payload.get(key)
        if isinstance(rows, list) and len(rows) > TRAIL_CAP:
            payload[key] = rows[-TRAIL_CAP:]
    return payload


def _find_secret_key(obj: Any) -> str | None:
    """Recursively walk JSON KEYS (not values -- an honest reasons string like
    'no signing secret: set GOVERNANCE_REALMONEY_SECRET' is not a leak) for a
    key name matching SECRET_PATTERN."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and SECRET_PATTERN.search(k):
                return k
            found = _find_secret_key(v)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_secret_key(item)
            if found:
                return found
    return None


def privacy_gate(payload: Any, path: str) -> None:
    """HARD GATE -- refuse (raise) if any JSON KEY in the payload looks like a
    secret/credential field. Never fixes it up quietly; the export must stop
    and be looked at. Takes the parsed object, not the serialized text, so an
    honest string VALUE that happens to mention "secret" (e.g. a governance
    reason quoting an env var name) is not a false-positive leak."""
    found = _find_secret_key(payload)
    if found:
        raise RuntimeError(
            f"privacy gate: refusing to write snapshot for {path!r} -- "
            f"payload has a secret-like key {found!r}"
        )


class Exporter:
    def __init__(self, p5: str, boards: str, out_dir: Path):
        self.p5 = p5.rstrip("/")
        self.boards = boards.rstrip("/")
        self.out_dir = out_dir
        self.written: list[str] = []
        self.skipped: list[tuple[str, str]] = []
        self.games: list[dict[str, str]] = []  # {sport, game_id}
        self.bet_ids: list[str] = []

    def fetch(self, base: str, path: str) -> Any | None:
        url = f"{base}{path}"
        try:
            r = requests.get(url, timeout=10)
        except requests.RequestException as e:
            self.skipped.append((path, f"unreachable: {e}"))
            return None
        if r.status_code >= 500:
            self.skipped.append((path, f"HTTP {r.status_code}"))
            return None
        try:
            body = r.json()
        except ValueError:
            self.skipped.append((path, "non-JSON response"))
            return None
        return body

    def write(self, path: str, payload: Any) -> None:
        payload = cap_trail_rows(payload)
        privacy_gate(payload, path)
        text = json.dumps(payload, ensure_ascii=True)
        fname = slug(path)
        (self.out_dir / fname).write_text(text, encoding="utf-8")
        self.written.append(path)

    def export_p5(self, path: str) -> Any | None:
        body = self.fetch(self.p5, path)
        if body is None:
            return None
        self.write(path, body)
        return body

    def run(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)

        # -- static / no-param -------------------------------------------
        for path in [
            "/api/catalog",
            "/api/gate/status",
            "/api/improve/ledger",
            "/api/improve/status",
            "/api/improve/timeline",
            "/api/ingame/gates",
            "/api/ops/autonomy",
            "/api/ops/status",
            "/api/paper/bankroll",
            "/api/paper/clv",
            "/api/paper/open",
            "/api/paper/pnl/series",
            "/api/parity",
            "/api/quant/clv",
            "/api/quant/risk",
            "/api/status.all_honest",
            "/api/paper/clv/series",
            "/api/paper/predictions?limit=500",
            "/api/improve/clv-corpus?limit=50",
        ]:
            self.export_p5(path)

        paper_trail = self.export_p5("/api/paper/trail?limit=2000")
        bet_ids: list[str] = []
        for row in ((paper_trail or {}).get("trail") or [])[:20]:
            bet_ids.append(to_bet_id(row))
        self.bet_ids = bet_ids

        # -- per-sport ----------------------------------------------------
        best_boards: dict[str, Any] = {}
        for sport in SPORTS:
            for path in [
                f"/api/report/{sport}",
                f"/api/v1/bestbets/{sport}",
                f"/api/predict/{sport}",
                f"/api/lines/{sport}",
                f"/api/predict/props/{sport}",
                f"/api/produce/status?sport={sport}",
                f"/api/quant/{sport}/validate",
                f"/api/results/{sport}",
                f"/api/bestbets/board?sport={sport}",
            ]:
                body = self.export_p5(path)
                if path.startswith("/api/bestbets/board"):
                    best_boards[sport] = body

            # boards service (:8098) -- board.ts fetchSlate query shape.
            slate = self.fetch(self.boards, f"/api/slate?sport={sport}")
            if slate is not None:
                self.write(f"/api/board/slate?sport={sport}", slate)

        # -- per-game (discovered from the bestbets board cards) -----------
        MAX_GAMES_PER_SPORT = 3
        for sport, board in best_boards.items():
            cards = (board or {}).get("cards") or []
            seen: set[str] = set()
            for card in cards:
                gid = card.get("game_id")
                if not gid or gid in seen:
                    continue
                seen.add(gid)
                self.games.append({"sport": sport, "game_id": gid})
                if len(seen) >= MAX_GAMES_PER_SPORT:
                    break
            for gid in seen:
                for path in [
                    f"/api/report/{sport}/{gid}",
                    f"/api/v1/bestbets/{sport}/{gid}",
                    f"/api/predict/{sport}/{gid}",
                    f"/api/ingame/{sport}/{gid}",
                    f"/api/ingame/{sport}/{gid}/full",
                    f"/api/boxscore/{sport}/{gid}",
                    f"/api/lines/{sport}/{gid}/matrix",
                    f"/api/results/{sport}?game_id={gid}",
                ]:
                    self.export_p5(path)

        # -- manifest (drives generateStaticParams for the static export) --
        manifest = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "sports": SPORTS,
            "games": self.games,
            "bet_ids": self.bet_ids,
        }
        privacy_gate(manifest, "manifest.json")
        manifest_text = json.dumps(manifest, ensure_ascii=True)
        (self.out_dir / "manifest.json").write_text(manifest_text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p5", default="http://127.0.0.1:8099")
    ap.add_argument("--boards", default="http://127.0.0.1:8098")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    ex = Exporter(args.p5, args.boards, Path(args.out))
    ex.run()

    print(f"wrote {len(ex.written)} snapshot files to {args.out}")
    for path in ex.written:
        print(f"  ok   {path}")
    for path, reason in ex.skipped:
        print(f"  skip {path} -- {reason}", file=sys.stderr)
    print(f"manifest: {len(ex.games)} games across {len(SPORTS)} sports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
