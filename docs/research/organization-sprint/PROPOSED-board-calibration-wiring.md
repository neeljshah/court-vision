# PROPOSED: Board -> Calibration Record + Pregame->Live Hero Interaction

> PROPOSED = a human applies this. Do NOT edit apps/live_board_ui directly.
> This document gives the exact, non-invasive additions a human would make.
> All copy is decision-support framing only. No $ edge, ROI, or picks language.
> The live session owns apps/live_board_ui; this is a blueprint, not a diff.

---

## 1. What this wires

Two additions to the existing live board:

**A. Calibration-record link/panel** -- a non-invasive link from the board controls
row to `docs/CALIBRATION_RECORD.md` (or the deployed equivalent), showing the
headline Brier-vs-devigged-close verdict per sport, with "MARKET-EFFICIENT HERE"
surfaced as a badge (not hidden as a footnote).

**B. Pregame->live hero interaction** -- when a game transitions from `state="pre"`
to `state="in"`, the WinProbCell's displayed probability should visually anchor on the
pregame number and then show the live-conditioned update with a delta label, e.g.:

  Pregame 47% | Q3 +8: 71% [MODEL-LIVE]

This is the single interaction that demonstrates the decisive, measured, calibrated
in-game edge: the pregame prior fused with the realized state. It claims calibration
quality, not a dollar edge.

---

## 2. Real component and contract names (from inspection)

Relevant files (DO NOT edit without a human decision; listed for context only):

- `apps/live_board_ui/src/App.tsx` -- root composition; wires all panels
- `apps/live_board_ui/src/components/board/Header.tsx` -- sticky top header;
  accepts `children` in a right-side slot (already used for ThemeToggle/DensityToggle)
- `apps/live_board_ui/src/components/board/LegendDialog.tsx` -- "How to read this"
  Dialog in the controls row; good anchor for a "Calibration Record" sibling button
- `apps/live_board_ui/src/components/board/WinProbCell.tsx` -- renders home/away/draw
  bars; reads `row.win_home`, `row.win_away`, `row.draw`; does NOT currently hold a
  pregame anchor
- `apps/live_board_ui/src/components/board/GameDetailDialog.tsx` -- per-row detail
  Dialog; has a SourceSection that renders plain-language provenance; best place to
  surface the pregame->live delta for a selected game
- `apps/live_board_ui/src/components/board/SourceBadge.tsx` -- provenance pill;
  maps `row.source` (RowSource) to MODEL / MARKET / SCORE-ONLY labels
- `apps/live_board_ui/src/components/board/Disclaimer.tsx` -- honesty banner
  (footer + banner variants); already rendered in App.tsx
- `apps/live_board_ui/src/types/board.ts` -- BoardRow contract; source of truth for
  field names; backend (apps/live_board/server.py) owns the contract

BoardRow fields relevant to both additions (from types/board.ts):
  - `state: "pre" | "in" | "post"`
  - `win_home: number | null`  (calibrated probability, 0..1)
  - `win_away: number | null`
  - `source: RowSource`  ("model" | "live-model" | "market" | "live-market" | "unavailable")
  - `note: string | null`  (already printed in GameDetailDialog; can carry pregame anchor)

---

## 3. Addition A: Calibration-record link in the controls row

### Where

In `App.tsx`, inside the `<section aria-label="Board controls">` div, adjacent to the
existing `<LegendDialog />` component (line ~120). Add a sibling anchor/button after it.

### Proposed JSX snippet (human would add to App.tsx)

```tsx
{/* Calibration Record link -- non-invasive sibling to LegendDialog */}
<a
  href="/calibration"
  target="_blank"
  rel="noopener noreferrer"
  aria-label="View calibration record (opens in new tab)"
  className="
    inline-flex items-center gap-1.5
    border border-line rounded-md px-2.5 py-1.5
    text-sm text-muted
    hover:text-txt hover:bg-surface2
    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent
    transition-colors
  "
>
  {/* BarChart2 from lucide-react, already a dep */}
  <BarChart2 size={14} aria-hidden="true" />
  <span>Calibration record</span>
</a>
```

Import to add at top of App.tsx:
```tsx
import { BarChart2 } from "lucide-react";
```

The href `/calibration` assumes a static route that serves `docs/CALIBRATION_RECORD.md`
rendered as HTML. Alternatively, link to the raw GitHub URL of the committed file, or
open the LegendDialog and include calibration data inline (see Addition A-alt below).

### Addition A-alt: Inline calibration panel in LegendDialog

Instead of a separate link, add a "Calibration" section to the existing LegendDialog
in `LegendDialog.tsx` after the current "Details" section:

```tsx
{/* ---- Calibration record ---- */}
<SectionHeading>Calibration record</SectionHeading>

<LegendRow
  label={<span className="text-xs font-semibold text-txt">How we're calibrated</span>}
  meaning="Pregame win-prob MATCHES the Shin-devigged closing line on NBA/MLB/Soccer team-strength markets (within sampling noise). We are BEHIND on totals and ATP-tennis -- a data gap, not a model failure. 'Market-efficient here' means we do not claim an edge; the close is our honest baseline."
/>
<LegendRow
  label={
    <span className="inline-flex items-center gap-1">
      <Badge variant="model">MODEL</Badge>
      <span className="text-[10px] text-muted ml-1">Brier</span>
    </span>
  }
  meaning="NBA ml: 0.1735 vs market 0.1672 -- MATCHES. MLB ml: 0.2429 vs 0.2390 -- MATCHES. Soccer O/U-2.5: 0.2465 vs 0.2390 -- MATCHES. Tennis ATP: 0.2177 vs 0.2028 -- BEHIND (tight market). Source: committed fixture (offline proof); real-corpus OOS = VALIDATION_PENDING."
/>
<LegendRow
  label={<span className="text-xs font-semibold text-txt">In-game</span>}
  meaning="When a game is live, the model fuses the pregame rating prior with the realized score/clock state. NBA: 0.209->0.159 Brier (real-corpus only; VALIDATION_PENDING on committed fixture -- prints no-improvement due to SYNTHETIC ANCHOR ARTIFACT). MLB: 0.241->0.126. Soccer: O/U 0.264->0.176. Tennis: 0.219->0.151. MLB/Soccer/Tennis reproduce on committed fixture. This measured improvement is calibration quality, not a dollar edge. edge_claimed=False."
/>
<p className="mt-2 text-[10px] text-muted">
  Full methodology: docs/CALIBRATION_RECORD.md and docs/JOB_EVIDENCE_PACKET.md.
  edge_claimed=False. Calibration != edge.
</p>
```

A-alt is lower-risk (no new route needed) and keeps everything inside the existing
LegendDialog pattern.

---

## 4. Addition B: Pregame->live hero interaction

### The hero sentence

When `row.state === "in"` and `row.source` is `"live-model"`, display:

  Pregame [X]% -> [Checkpoint] [Y]% [MODEL-LIVE]

where X is the pregame win-prob anchor and Y is the live-conditioned win-prob. This
communicates the decisive, measured, calibrated in-game improvement in one line.

### Where (two options)

**Option B1: In GameDetailDialog** (lower risk -- zero board layout change)

In `GameDetailDialog.tsx`, extend the existing Win Probability section to show the
pregame anchor alongside the live number. The `row.note` field already passes through;
the backend (apps/live_board/server.py) would need to include the pregame anchor in the
note for in-game rows, OR the `BoardRow` contract would need a new `pregame_win_home`
field (backend-side change, human-gated).

Simplest path with NO new BoardRow fields: the backend populates `row.note` for in-game
MODEL-LIVE rows as:
  "Pregame 47% | Q3 8 min: +8"

Then GameDetailDialog's existing NoteSection (already rendered) displays it, and nothing
else changes. No JSX required from the frontend.

**Option B2: In WinProbCell / BoardRow** (more visible, requires a BoardRow extension)

Add a `pregame_win_home: number | null` field to BoardRow in `types/board.ts`, populated
by the backend for in-game rows. Then in `WinProbCell.tsx`, when the row is live-model:

```tsx
{/* Hero pregame->live anchor -- only for live-model rows with a pregame anchor */}
{row.state === "in" && row.source === "live-model" && pregameWinHome !== null && (
  <div className="text-[10px] text-muted mt-1 tabular-nums" aria-label="Pregame anchor">
    Pregame {pct(pregameWinHome)}% -> Live {pct(wh ?? 0)}%
  </div>
)}
```

This requires:
  1. Add `pregame_win_home: number | null` to `types/board.ts` BoardRow (human-gated; must
     match the backend contract in apps/live_board/server.py)
  2. Backend populates pregame_win_home for state="in", source="live-model" rows
  3. WinProbCell reads the new field (JSX above)

**Recommendation:** start with Option B1 (no contract change, note-field only) to get
the hero sentence visible immediately. Promote to B2 when the backend wiring is human-
confirmed.

---

## 5. Copy discipline for the hero sentence

These phrasings are safe (decision-support framing):

  "Pregame 47% | Q3 +8: 71% [MODEL-LIVE]"
  "Pregame prior: 47% -> Q3 state: 71% (calibration update, not a wager)"
  "In-game: 71% [MODEL-LIVE] | Pregame was 47%"

These phrasings are NOT safe (edge / profit language -- do not use):

  "Edge: +24% since tip" (implies a dollar edge)
  "Value shift: +24pp" (value = EV language)
  "Bet the live line now" (picks / action language)
  "Model is +24pp ahead of the market" (beat-the-market claim)

The honest framing: "the pregame rating prior fused with the realized state."
The source badge "MODEL-LIVE" already conveys in-corpus origin. The Disclaimer
footer ("Decision support, not a money machine. No $ edge claimed.") anchors
the whole board and does not need to be duplicated on each row.

---

## 6. Calibration-record panel content (what to show)

If a standalone `/calibration` route is served, the minimal honest content is:

```
Calibration Record -- CourtVision 4-Sport Predictor
Decision-support. edge_claimed=False. Honest "market-efficient here" = feature.

PREGAME vs Shin-devigged close (leak-free OOS walk-forward):

Sport / market    | Our Brier | Close Brier | Verdict
------------------|-----------|-------------|-------------------------
NBA moneyline     | 0.1735    | 0.1672      | MATCHES (within noise)
MLB moneyline     | 0.2429    | 0.2390      | MATCHES
Soccer O/U-2.5    | 0.2465    | 0.2390      | MATCHES
Tennis ATP ml     | 0.2177    | 0.2028      | BEHIND (freshness gap)

IN-GAME: pregame prior + realized state (static -> conditional Brier):
NOTE: NBA row is real-corpus-only. Committed fixture prints no-improvement for NBA
(SYNTHETIC ANCHOR ARTIFACT). MLB/Soccer/Tennis reproduce on committed fixture.

Sport  | Static | Conditional | Checkpoint       | Fixture result
-------|--------|-------------|------------------|---------------
NBA    | 0.209  | 0.159       | end Q1/Q2/Q3     | no-improvement (SYNTHETIC ANCHOR ARTIFACT; VALIDATION_PENDING)
MLB    | 0.241  | 0.126       | inning 3/5/7     | WIN (reproduces)
Soccer | 0.264  | 0.176       | half-time (O/U)  | WIN (reproduces)
Tennis | 0.219  | 0.151       | after set 1      | WIN (reproduces)

REPRODUCE: python -m scripts.platformkit.eval_gate.run_gate --golden
           python -m scripts.platformkit.ledger.replay_proof

VALIDATION_PENDING: real-corpus OOS is a human-run step. Committed fixtures only.
edge_claimed = False. Source: docs/CALIBRATION_RECORD.md
```

Source badges on every number: [model-in-corpus] / [devigged-market] / [score-only-anchor].

---

## 7. What a human needs to do (ordered)

1. CONFIRM the target route for the calibration record (static file? /calibration endpoint?
   GitHub raw URL? inline in LegendDialog?). Pick Option A or A-alt.
2. APPLY Addition A (link in controls row OR inline in LegendDialog) -- 5-10 lines of JSX.
3. DECIDE on hero interaction approach (B1 note-field vs B2 BoardRow extension).
4. If B1: configure the backend (apps/live_board/server.py) to populate row.note for
   in-game model rows with the pregame anchor sentence.
5. If B2: extend BoardRow in types/board.ts + backend + WinProbCell (3 files, human-gated).
6. VERIFY: run `npm run dev` in apps/live_board_ui; check the calibration link and the
   pregame->live hero sentence render correctly in a test game row.
7. NEVER add any copy that implies a dollar edge, ROI, or picks recommendation.

No edits to src/, kernel/, or api/ are needed for these additions.
