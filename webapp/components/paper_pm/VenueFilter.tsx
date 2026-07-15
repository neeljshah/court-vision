"use client";

// VenueFilter -- venue/result/tier chip-set filters for the PM paper trail.
// All state lives in the parent; this is purely presentational.

import { cn } from "@/lib/utils";

type FilterChipProps = {
  label: string;
  active: boolean;
  onClick: () => void;
};

function FilterChip({ label, active, onClick }: FilterChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "h-6 border px-3 text-[10px] font-data uppercase tracking-wide transition-colors",
        active
          ? "border-primary text-primary bg-surface-2"
          : "border-border bg-transparent text-faint hover:bg-surface-2 hover:text-foreground",
      )}
    >
      {label}
    </button>
  );
}

type VenueFilterProps = {
  venues: string[];
  venue: string;
  onVenue: (v: string) => void;
  result: string;
  onResult: (v: string) => void;
  tier: string;
  onTier: (v: string) => void;
};

const RESULT_OPTIONS = ["all", "win", "loss", "void", "pending"] as const;
const TIER_OPTIONS = ["all", "A", "B", "C"] as const;

export function VenueFilter({
  venues,
  venue,
  onVenue,
  result,
  onResult,
  tier,
  onTier,
}: VenueFilterProps) {
  const allVenues = ["all", ...venues];

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      {/* Venue chips */}
      <span className="microlabel">
        Venue
      </span>
      <div className="flex flex-wrap gap-1">
        {allVenues.map((v) => (
          <FilterChip
            key={v}
            label={v === "all" ? "All" : v}
            active={venue === v}
            onClick={() => onVenue(v)}
          />
        ))}
      </div>

      {/* Result chips */}
      <span className="microlabel">
        Result
      </span>
      <div className="flex flex-wrap gap-1">
        {RESULT_OPTIONS.map((v) => (
          <FilterChip
            key={v}
            label={v === "all" ? "All" : v}
            active={result === v}
            onClick={() => onResult(v)}
          />
        ))}
      </div>

      {/* Tier chips */}
      <span className="microlabel">
        Tier
      </span>
      <div className="flex flex-wrap gap-1">
        {TIER_OPTIONS.map((v) => (
          <FilterChip
            key={v}
            label={v === "all" ? "All" : v}
            active={tier === v}
            onClick={() => onTier(v)}
          />
        ))}
      </div>
    </div>
  );
}
