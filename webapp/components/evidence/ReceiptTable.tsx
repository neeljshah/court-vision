// ReceiptTable.tsx -- a claim page's "claim -> committed artifact" table, one
// ReceiptChip per row. Server-renderable (the chip is a client island, mounted
// here as a child). Dumb renderer: ClaimPage does the build-time artifact join
// and hands resolved rows in. Tokens only, honest empty state.

import { ReceiptChip, type ReceiptChipProps } from "@/components/showcase/ReceiptChip";

export type ReceiptTableRow = {
  /** The guarantee / claim being backed. */
  label: string;
  /** The receipt value (a number or short proof); optional (2-col tables omit it). */
  value?: string;
  /** Raw artifact cell text, shown in mono. */
  artifact: string;
  /** Receipt chip for the artifact, when it resolves to a staged JSON. */
  chip?: ReceiptChipProps;
};

export function ReceiptTable({ rows }: { rows: ReceiptTableRow[] }) {
  if (rows.length === 0) return null;
  const hasValue = rows.some((r) => r.value);
  const hasLabel = rows.some((r) => r.label);

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left">
            {hasLabel && <th className="microlabel px-3 py-1.5">claim</th>}
            {hasValue && <th className="microlabel px-3 py-1.5">receipt</th>}
            <th className="microlabel px-3 py-1.5">committed artifact</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={i}
              className="border-b border-border align-top hover:bg-surface-2"
            >
              {hasLabel && (
                <td className="px-3 py-1.5 leading-relaxed text-foreground">
                  {r.label}
                </td>
              )}
              {hasValue && (
                <td className="px-3 py-1.5 font-data tabular-nums text-foreground">
                  {r.value}
                </td>
              )}
              <td className="px-3 py-1.5 font-data text-[11px] leading-relaxed text-faint">
                {r.artifact}
                {r.chip && <ReceiptChip {...r.chip} />}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
