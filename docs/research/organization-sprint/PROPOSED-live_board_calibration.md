# PROPOSED: live_board_ui -> calibration record + pregame->live hero interaction

> **SUPERSEDED (kept as a draft).** The AUTHORITATIVE, contract-verified wiring blueprint
> is [PROPOSED-board-calibration-wiring.md](PROPOSED-board-calibration-wiring.md) -- it cites
> the real, inspected component + `board.ts` field names. Apply that one. This earlier draft
> is retained only for the `Disclaimer.tsx` link snippet it sketches.

> **PROPOSED ONLY -- do NOT apply from this doc.** The live session owns
> `apps/live_board_ui`. This is a reviewable snippet set the live owner can lift in
> deliberately. Nothing here is wired. It is sized to be small and contract-safe.
>
> BINDING: this surface is DECISION-SUPPORT, never a picks / +EV / ROI product. Every
> probability stays badged by SOURCE (`model` / `live-model` / `market` / `live-market`
> / `unavailable`). "MARKET-EFFICIENT HERE -- no edge" is a first-class state. No $ edge,
> ever. The retracted numbers (+18.38 / 0.119 / +54 / 78.11 / 8.94 / 54.57) never appear.

The board already does the honest part well: `SourceBadge.tsx` badges provenance and
`Disclaimer.tsx` / `LegendDialog.tsx` carry the framing. Two things are missing for the
GTM "calibration record" pitch, and they are exactly the gap this proposal fills:

1. a visible link from the board to the public **calibration record** (the proof-of-work
   page, `docs/CALIBRATION_RECORD.md`), so a skeptic reaches the Brier-vs-devigged-close
   evidence from the UI;
2. the **pregame -> in-game hero interaction** ("Pregame 47% | now Q3 +8: 71%"), the one
   measured place the system departs from the close. The current `BoardRow` carries only a
   single CURRENT `win_home` + `source`; it has no pregame anchor to diff against live.

Each proposal below is additive and contract-safe (no existing field renamed; the backend
owns the contract per `src/types/board.ts`).

---

## Proposal A -- a "Calibration record" link in the disclaimer (tiny, no contract change)

Add one honest line + link to `Disclaimer.tsx` (or `LegendDialog.tsx`). Pure presentational.

```tsx
// apps/live_board_ui/src/components/board/Disclaimer.tsx  (append inside the existing copy)
<p className="text-[11px] text-muted">
  Probabilities are calibrated forecasts, not betting advice. We MATCH the devigged
  closing line within noise on team-strength markets (the market is efficient); no $ edge
  is claimed.{" "}
  <a
    href="/calibration"            /* serve docs/CALIBRATION_RECORD.md as a static route */
    className="underline hover:text-txt"
    title="Public calibration record: Brier vs the devigged close, reliability diagrams"
  >
    See the calibration record
  </a>.
</p>
```

The backend can serve `docs/CALIBRATION_RECORD.md` (rendered) at `/calibration`, or link
out to the committed file. No `BoardRow` change required.

---

## Proposal B -- extend the board contract with a PREGAME ANCHOR (backend-owned)

To show "Pregame X% -> now Y%" the row needs the pregame number alongside the live one.
This is a BACKEND contract change (the live session + `apps/live_board/server.py` own it);
shown here so both sides agree on the shape before either edits. Additive only -- all new
fields nullable, so existing consumers are unaffected.

```ts
// PROPOSED additions to src/types/board.ts BoardRow (backend owns the contract):
export interface BoardRow {
  // ... existing fields unchanged ...

  // pregame anchor, captured at tip-off / first pitch (null until known / for pre games):
  win_home_pregame: number | null;   // 0..1, the pregame model or devigged-close anchor
  pregame_source: RowSource | null;  // provenance of the anchor (model vs market)
  // delta is DERIVED on the client (win_home - win_home_pregame); not sent, not a $ figure.
}
```

Honest semantics: `win_home_pregame` is frozen at game start and never re-written, so the
live delta is genuinely "what the realized state added vs the pregame number." Badge the
anchor by its own `pregame_source` -- a market-implied anchor must not be shown as a model
number.

---

## Proposal C -- the hero interaction in GameDetailDialog (presentational, after B)

Once Proposal B ships the anchor, render the pregame -> live transition as the hero of the
detail dialog. Pure presentational; reuses the existing `pct()` formatter + `SourceBadge`.

```tsx
// apps/live_board_ui/src/components/board/PregameLiveHero.tsx  (NEW, proposed)
import type { BoardRow } from "@/types/board";
import { pct } from "@/lib/format";

/** The one measured departure from the close: pregame anchor -> live-conditioned number.
 *  Decision-support only. The delta is conditioning on realized state, NOT a $ edge. */
export function PregameLiveHero({ row }: { row: BoardRow }) {
  const pre = row.win_home_pregame;
  const live = row.win_home;
  if (pre == null || live == null || row.state !== "in") return null;
  const delta = live - pre;
  const arrow = delta >= 0 ? "up" : "down";   // ASCII-safe label, not a glyph
  return (
    <div className="flex items-center gap-2 text-sm" aria-live="polite">
      <span className="text-muted">Pregame</span>
      <span className="tabular-nums font-medium">{pct(pre)}%</span>
      <span className="text-muted">-&gt; now ({row.clock_text ?? "live"})</span>
      <span className="tabular-nums font-semibold">{pct(live)}%</span>
      <span
        className="text-[11px] text-muted"
        title="In-game state conditioning vs the pregame anchor. Calibration, not a $ edge."
      >
        ({arrow} {pct(Math.abs(delta))} pts from realized state)
      </span>
    </div>
  );
}
```

Render it at the top of `GameDetailDialog.tsx` for `state === "in"`. The caption line under
it should restate the framing: *"In-game conditioning is the measured, calibrated gap; the
pregame number matches the devigged close. No $ edge."*

---

## Proposal D -- a one-call data hook for the banner number (optional)

If the UI wants to echo the package's startup calibration context (last OOS Brier + last
recalibration date) in a footer, expose it from the backend via the SAME source the CLI
uses, so the UI never authors its own number:

```py
# backend (apps/live_board/server.py) -- proposed read-only endpoint
from scripts.platformkit.calibration_banner import banner_lines
@app.get("/api/calibration_context")
def calibration_context():
    # banner_lines() reads eval_gate/baselines/*.json; honest, frozen, in-corpus-badged.
    return {"lines": banner_lines(), "edge_claimed": False}
```

The UI renders `lines` verbatim in a muted footer. Single source of truth with the CLI
banner; impossible to drift into a $ claim because the producer never emits one.

---

## Why this is the right gap (and what it deliberately does NOT touch)

- It adds the TWO things the board lacks for the GTM pitch: a path to the proof-of-work
  page, and the pregame->live hero that is the only measured departure from the close.
- It changes NO existing field name and breaks NO current consumer (all additive, nullable).
- It keeps every number badged by source and keeps "market-efficient / no edge" first-class.
- It does not restyle the board, touch the polling/`useBoard` logic, or alter the existing
  `SourceBadge` / `WinProbCell` semantics -- the live session owns those.

Cross-references: `docs/CALIBRATION_RECORD.md`, `docs/SELL-READINESS.md`,
`scripts/platformkit/calibration_banner.py`, `scripts/platformkit/calibration_record.py`,
`docs/JOB_EVIDENCE_PACKET.md` (the do-not-claim truth source).
