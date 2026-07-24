// Display formatters for the analytics product. ASCII only, no deps.

// asOfDate -- normalize an as_of stamp for display. Machine timestamps collapse to
// their date; descriptive corpus labels pass through untouched.
//   "2026-07-24T00:18:11.535624+00:00" -> "2026-07-24"
//   "2026-05-21 16:05:11"              -> "2026-05-21"
//   "2025-26 regular season (through 2026-04-12)" -> unchanged (not a timestamp)
// Returns undefined for empty input so it drops cleanly into optional asOf props.
export function asOfDate(s?: string | null): string | undefined {
  if (!s) return undefined;
  return /^\d{4}-\d{2}-\d{2}[ T]\d{2}:/.test(s) ? s.slice(0, 10) : s;
}

// typeset -- the committed prose (essays, insights, ask corpus) is ASCII and uses
// " -- " as its em-dash convention; render it as a real em-dash so the reading
// surfaces match the rest of the chrome. Spaced form ONLY, so CLI flags in code
// prose ("--force", "--no-show") are never touched. Numbers are untouched.
// EM_DASH is built from its code point to keep this source file pure ASCII.
const EM_DASH = String.fromCharCode(0x2014);
export function typeset(s: string): string {
  return s.replace(/ -- /g, " " + EM_DASH + " ");
}
