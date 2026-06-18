import { useMemo, useState } from "react";
import type { SlateRow } from "@/lib/api";

export type SortKey = "matchup" | "edge" | "arb_pct" | "model_ev_best";
export type SortDir = "asc" | "desc";

function val(row: SlateRow, key: SortKey): number | string | null {
  if (key === "matchup") return row.matchup;
  return row[key];
}

/** Sortable + min-edge-filterable view over slate rows. Nulls always sort last. */
export function useSortedRows(rows: SlateRow[], minEdgePct: number) {
  const [sortKey, setSortKey] = useState<SortKey>("edge");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  function toggle(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "matchup" ? "asc" : "desc");
    }
  }

  const view = useMemo(() => {
    const minFrac = (minEdgePct || 0) / 100;
    const filtered =
      minFrac > 0
        ? rows.filter((r) => r.edge !== null && Math.abs(r.edge) >= minFrac)
        : rows;
    const sorted = [...filtered].sort((a, b) => {
      const va = val(a, sortKey);
      const vb = val(b, sortKey);
      if (va === null && vb === null) return 0;
      if (va === null) return 1; // nulls last
      if (vb === null) return -1;
      let cmp = 0;
      if (typeof va === "string" && typeof vb === "string") cmp = va.localeCompare(vb);
      else cmp = (va as number) - (vb as number);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [rows, minEdgePct, sortKey, sortDir]);

  return { view, sortKey, sortDir, toggle };
}
