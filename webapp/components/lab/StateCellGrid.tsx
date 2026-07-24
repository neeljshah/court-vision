"use client";

// components/lab/StateCellGrid.tsx -- the one client island of the
// counterfactual explorer. A CSS-grid heatmap (probability band rows x
// game-time columns) tinted by MODEL calibration error; clicking a cell holds
// it in state and fills the CellDetail panel beside the grid. Cells arrive
// pre-computed from the server page (state_conditioned_calibration.json read at
// build) -- no fetch, no sim. Tint uses the --danger token only, so it reads in
// both themes. ASCII only.

import * as React from "react";
import { CellDetail, type Cell } from "@/components/lab/CellDetail";
import type { ReceiptChipProps } from "@/components/showcase/ReceiptChip";

const comma = (n: number) => n.toLocaleString("en-US");

// Sequential single-hue ramp on --danger: alpha grows with error, capped so a
// well-calibrated cell stays legible. ce ~0.18 saturates near the cap.
const tint = (ce: number | null) =>
  ce == null
    ? "hsl(var(--surface-2))"
    : `hsl(var(--danger) / ${Math.min(ce / 0.18, 0.62).toFixed(3)})`;

const cellKey = (time: string, prob: string) => `${time}|${prob}`;

export function StateCellGrid({
  times,
  timeLabels,
  probs,
  cells,
  initialSelected,
  chip,
}: {
  times: string[];
  timeLabels: string[];
  probs: string[];
  cells: Cell[];
  initialSelected: string; // "time|prob"
  chip: ReceiptChipProps;
}) {
  const byKey = React.useMemo(() => {
    const m = new Map<string, Cell>();
    for (const c of cells) m.set(cellKey(c.time, c.prob), c);
    return m;
  }, [cells]);

  const [sel, setSel] = React.useState(initialSelected);
  const selected =
    byKey.get(sel) ??
    byKey.get(initialSelected) ??
    cells[0];

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
      <div>
        <div
          className="grid gap-px border border-border bg-border"
          style={{ gridTemplateColumns: `auto repeat(${times.length}, 1fr)` }}
        >
          <div className="microlabel bg-card px-2.5 py-2 text-center" />
          {timeLabels.map((t) => (
            <div key={t} className="microlabel bg-card px-2.5 py-2 text-center">
              {t}
            </div>
          ))}
          {probs.map((p) => (
            <React.Fragment key={p}>
              <div className="flex items-center bg-card px-2.5 py-2.5 font-data text-xs text-faint">
                {p}
              </div>
              {times.map((t) => {
                const key = cellKey(t, p);
                const c = byKey.get(key);
                const m = c?.model ?? null;
                const isSel = key === sel;
                if (!m) {
                  return (
                    <div
                      key={key}
                      className={
                        "bg-card px-2.5 py-3 text-center text-faint " +
                        (c ? "cursor-pointer" : "")
                      }
                      onClick={c ? () => setSel(key) : undefined}
                      style={isSel ? { outline: "2px solid hsl(var(--primary))", outlineOffset: -2 } : undefined}
                    >
                      <div className="font-data text-[15px]">{c ? "-" : "."}</div>
                      {c && <div className="mt-0.5 font-data text-[9.5px] text-faint">market only</div>}
                    </div>
                  );
                }
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setSel(key)}
                    className="bg-card px-2.5 py-3 text-center transition hover:brightness-125 focus:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    style={{
                      background: tint(m.calErr),
                      ...(isSel ? { outline: "2px solid hsl(var(--primary))", outlineOffset: -2 } : {}),
                    }}
                    aria-pressed={isSel}
                  >
                    <div className="font-data text-[15px] tabular-nums">{m.calErr.toFixed(4)}</div>
                    <div className="mt-0.5 font-data text-[9.5px] text-faint">n {comma(m.n)}</div>
                  </button>
                );
              })}
            </React.Fragment>
          ))}
        </div>
        <div className="mt-2 flex items-center gap-2 font-data text-[11px] text-faint">
          <span>well-calibrated</span>
          <span className="flex">
            {[0.05, 0.18, 0.31, 0.44, 0.6].map((a) => (
              <span
                key={a}
                className="inline-block h-3 w-5"
                style={{ background: `hsl(var(--danger) / ${a})` }}
              />
            ))}
          </span>
          <span>high error</span>
          <span className="ml-auto">tint = model calibration error</span>
        </div>
      </div>

      {selected && <CellDetail cell={selected} chip={chip} />}
    </div>
  );
}
