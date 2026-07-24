// components/lab/CellDetail.tsx -- the selected-cell detail panel for the
// counterfactual explorer. Presentational: renders model/market rows (n, mean
// p, observed freq, calibration error) for one state cell plus an honest
// sentence, with a receipt chip citing the source artifact. No fetch, no state;
// the parent client island (StateCellGrid) owns selection. ASCII only.

import { Panel, PanelHead } from "@/components/ui/terminal";
import { ReceiptChip, type ReceiptChipProps } from "@/components/showcase/ReceiptChip";

export type CellRow = { n: number; meanP: number; meanY: number; calErr: number };
export type Cell = {
  time: string;
  timeLabel: string;
  prob: string;
  model: CellRow | null;
  market: CellRow | null;
};

const comma = (n: number) => n.toLocaleString("en-US");
const d4 = (v: number) => v.toFixed(4);

function Row({ label, tint, row }: { label: string; tint: string; row: CellRow | null }) {
  if (!row) return null;
  return (
    <tr className="border-t border-border">
      <td className={"px-3 py-1.5 font-data " + tint}>{label}</td>
      <td className="px-3 py-1.5 text-right font-data tabular-nums">{comma(row.n)}</td>
      <td className="px-3 py-1.5 text-right font-data tabular-nums">{d4(row.meanP)}</td>
      <td className="px-3 py-1.5 text-right font-data tabular-nums">{d4(row.meanY)}</td>
      <td className="px-3 py-1.5 text-right font-data tabular-nums">{d4(row.calErr)}</td>
    </tr>
  );
}

export function CellDetail({ cell, chip }: { cell: Cell; chip: ReceiptChipProps }) {
  const m = cell.model;
  const k = cell.market;
  const sentence = m
    ? `In this cell the model's mean forecast was ${d4(m.meanP)} and outcomes ` +
      `landed at ${d4(m.meanY)}; calibration error ${d4(m.calErr)}. Lower is ` +
      `better; the market's error here was ${k ? d4(k.calErr) : "n/a"}.`
    : k
      ? `This cell has market cells only in the artifact (no graded model cell). ` +
        `Market calibration error was ${d4(k.calErr)}.`
      : "No graded cell in the artifact for this state.";

  return (
    <Panel>
      <PanelHead
        title={`${cell.timeLabel} x ${cell.prob}`}
        right={<ReceiptChip {...chip} />}
      />
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="text-left">
              <th className="microlabel px-3 py-1.5">source</th>
              <th className="microlabel px-3 py-1.5 text-right">n</th>
              <th className="microlabel px-3 py-1.5 text-right">mean p</th>
              <th className="microlabel px-3 py-1.5 text-right">obs freq</th>
              <th className="microlabel px-3 py-1.5 text-right">cal err</th>
            </tr>
          </thead>
          <tbody>
            <Row label="MODEL" tint="text-s-model" row={m} />
            <Row label="MARKET" tint="text-s-market" row={k} />
          </tbody>
        </table>
      </div>
      <p className="border-t border-border px-3 py-2 text-[13px] leading-relaxed text-faint">
        {sentence}
      </p>
    </Panel>
  );
}
