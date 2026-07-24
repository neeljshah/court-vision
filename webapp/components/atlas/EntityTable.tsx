"use client";

// EntityTable.tsx -- the atlas pack's sortable/filterable table (T1.3).
//
// Client component: sort-by-column + name filter over <=485 rows. No
// virtualization, no dep -- plain array sort/filter on every keystroke is
// trivial at this size (COMPONENTS.md sec.3).

import { useMemo, useState } from "react";
import Link from "next/link";
import type { EntityRow } from "@/lib/atlas.server";

export function EntityTable({
  columns,
  rows,
  sport,
}: {
  columns: string[];
  rows: EntityRow[];
  sport: string;
}) {
  const [query, setQuery] = useState("");
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<1 | -1>(1);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let out = q ? rows.filter((r) => r.entity.toLowerCase().includes(q)) : rows;
    if (sortCol) {
      out = [...out].sort((a, b) => {
        const av = sortCol === "entity" ? a.entity : a.nums[sortCol];
        const bv = sortCol === "entity" ? b.entity : b.nums[sortCol];
        if (av == null) return 1;
        if (bv == null) return -1;
        if (typeof av === "number" && typeof bv === "number") return (av - bv) * sortDir;
        return String(av).localeCompare(String(bv)) * sortDir;
      });
    }
    return out;
  }, [rows, query, sortCol, sortDir]);

  // ponytail: some packs (mlb-pitching) nest a breakdown object under a
  // key_number (e.g. count_leverage_pct: {pitcher_ahead, even, ...}) instead of
  // a scalar. React can't render an object child -- flatten it to one line.
  function formatCell(v: unknown): string {
    if (v == null) return "—";
    if (typeof v === "object") {
      return Object.entries(v as Record<string, unknown>)
        .map(([k, n]) => `${k}: ${n}`)
        .join(", ");
    }
    return String(v);
  }

  function onSort(col: string) {
    if (sortCol === col) setSortDir((d) => (d === 1 ? -1 : 1));
    else {
      setSortCol(col);
      setSortDir(1);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="filter by name..."
        className="w-full max-w-xs border border-border bg-card px-3 py-1.5 font-data text-sm text-foreground placeholder:text-faint focus:outline-none focus-visible:ring-1 focus-visible:ring-ring sm:w-64"
      />
      <div className="overflow-x-auto border border-border">
        <table className="w-full min-w-max border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th
                className="microlabel cursor-pointer select-none px-3 py-1.5"
                onClick={() => onSort("entity")}
              >
                entity{sortCol === "entity" ? (sortDir === 1 ? " ↑" : " ↓") : ""}
              </th>
              {columns.map((c) => (
                <th
                  key={c}
                  className="microlabel cursor-pointer select-none px-3 py-1.5 text-right"
                  onClick={() => onSort(c)}
                >
                  {c}
                  {sortCol === c ? (sortDir === 1 ? " ↑" : " ↓") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.slug} className="border-b border-border hover:bg-surface-2">
                <td className="px-3 py-1.5">
                  <Link
                    href={`/atlas/${sport}/${r.slug}`}
                    className="text-foreground underline decoration-dotted underline-offset-2 hover:text-primary"
                  >
                    {r.entity}
                  </Link>
                </td>
                {columns.map((c) => (
                  <td key={c} className="px-3 py-1.5 text-right font-data tabular-nums">
                    {formatCell(r.nums[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <p className="p-4 text-center text-sm text-faint">no entities match &quot;{query}&quot;</p>
        )}
      </div>
      <p className="text-[11px] text-faint">
        {filtered.length} of {rows.length} entries
      </p>
    </div>
  );
}
