// OddsCell -- renders market odds string and optional provider label for a board row.
// Shows "--" in muted style when odds are unavailable.

import type { BoardRow } from "@/types/board";

interface OddsCellProps {
  row: BoardRow;
}

export function OddsCell({ row }: OddsCellProps) {
  if (!row.market_odds) {
    return (
      <span className="text-muted tabular-nums whitespace-nowrap" aria-label="Odds unavailable">
        --
      </span>
    );
  }

  return (
    <span className="whitespace-nowrap inline-flex flex-col items-end gap-0">
      <span className="font-semibold tabular-nums text-txt">{row.market_odds}</span>
      {row.provider && (
        <span className="text-[10px] text-muted leading-none">{row.provider}</span>
      )}
    </span>
  );
}
