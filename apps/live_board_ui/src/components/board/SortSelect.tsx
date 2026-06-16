/** Labeled native select for choosing the board sort order within each section. */

import type { SortMode } from "@/lib/sort";
import { SORT_OPTIONS } from "@/lib/sort";

interface SortSelectProps {
  value: SortMode;
  onChange: (m: SortMode) => void;
}

export function SortSelect({ value, onChange }: SortSelectProps) {
  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor="sort-select"
        className="text-xs text-muted"
      >
        Sort
      </label>
      <select
        id="sort-select"
        value={value}
        onChange={(e) => onChange(e.target.value as SortMode)}
        className="bg-surface border border-line rounded-md px-2.5 py-1.5 text-sm text-txt tabular-nums focus:outline-none focus:ring-2 focus:ring-accent"
      >
        {SORT_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
