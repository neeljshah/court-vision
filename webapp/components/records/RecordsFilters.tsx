"use client";

// RecordsFilters.tsx -- W1-records-surface filter bar (sport / result / tier).
// Emits onChange on each select change; parent holds state and re-fetches.
// No $ / ROI / P&L token anywhere. ASCII only.
//
// 300 LOC rail: this file stays well under 300 lines.

import { cn } from "@/lib/utils";

export interface RecordsFiltersState {
  sport:  string; // "all" | "nba" | "mlb" | "soccer" | "tennis"
  result: string; // "all" | "win" | "loss" | "push" | "void" | "pending"
  tier:   string; // "all" | "S" | "A" | "B" | "C"
}

interface RecordsFiltersProps {
  value:    RecordsFiltersState;
  onChange: (next: RecordsFiltersState) => void;
  disabled?: boolean;
}

const SELECT_CLS = cn(
  "border border-border bg-secondary px-2 py-1",
  "font-data text-[11px] text-foreground",
  "focus:outline-none focus:ring-1 focus:ring-ring",
  "disabled:opacity-40",
);

export function RecordsFilters({ value, onChange, disabled = false }: RecordsFiltersProps) {
  const set = (key: keyof RecordsFiltersState) =>
    (e: React.ChangeEvent<HTMLSelectElement>) =>
      onChange({ ...value, [key]: e.target.value });

  return (
    <div
      role="group"
      aria-label="records filters"
      data-testid="records-filters"
      className="flex flex-wrap items-center gap-2"
    >
      <label className="flex items-center gap-1.5">
        <span className="microlabel">sport</span>
        <select
          data-testid="filter-sport"
          className={SELECT_CLS}
          value={value.sport}
          onChange={set("sport")}
          disabled={disabled}
        >
          <option value="all">all</option>
          <option value="nba">nba</option>
          <option value="mlb">mlb</option>
          <option value="soccer">soccer</option>
          <option value="tennis">tennis</option>
        </select>
      </label>

      <label className="flex items-center gap-1.5">
        <span className="microlabel">result</span>
        <select
          data-testid="filter-result"
          className={SELECT_CLS}
          value={value.result}
          onChange={set("result")}
          disabled={disabled}
        >
          <option value="all">all</option>
          <option value="win">win</option>
          <option value="loss">loss</option>
          <option value="push">push</option>
          <option value="void">void</option>
          <option value="pending">pending</option>
        </select>
      </label>

      <label className="flex items-center gap-1.5">
        <span className="microlabel">tier</span>
        <select
          data-testid="filter-tier"
          className={SELECT_CLS}
          value={value.tier}
          onChange={set("tier")}
          disabled={disabled}
        >
          <option value="all">all</option>
          <option value="S">S</option>
          <option value="A">A</option>
          <option value="B">B</option>
          <option value="C">C</option>
        </select>
      </label>
    </div>
  );
}
