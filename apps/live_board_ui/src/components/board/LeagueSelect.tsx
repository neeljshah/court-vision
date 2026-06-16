/** Labeled native select for filtering the board by soccer league. */

import { SOCCER_LEAGUES } from "@/types/board";

interface LeagueSelectProps {
  league: string;
  onChange: (v: string) => void;
}

export function LeagueSelect({ league, onChange }: LeagueSelectProps) {
  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor="league-select"
        className="text-xs text-muted"
      >
        League
      </label>
      <select
        id="league-select"
        value={league}
        onChange={(e) => onChange(e.target.value)}
        className="bg-surface border border-line rounded-md px-2.5 py-1.5 text-sm text-txt tabular-nums focus:outline-none focus:ring-2 focus:ring-accent"
      >
        <option value="">All Leagues</option>
        {SOCCER_LEAGUES.map((l) => (
          <option key={l.value} value={l.value}>
            {l.label}
          </option>
        ))}
      </select>
    </div>
  );
}
