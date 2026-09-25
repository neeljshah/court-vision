import { field as f, snapshot } from "./labHelpers";
import type { LabDataset, LabRow } from "./labTypes";

type RecordValue = Record<string, unknown>;
const object = (value: unknown): value is RecordValue => value !== null && typeof value === "object" && !Array.isArray(value);
const finite = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;
const nonnegativeInteger = (value: unknown): number | null =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;

function relativeRimShare(on: unknown, off: unknown): number | null {
  const onShare = finite(on);
  const offShare = finite(off);
  if (onShare === null || offShare === null || onShare < 0 || onShare > 1 || offShare <= 0 || offShare > 1) return null;
  const ratio = (onShare - offShare) / offShare;
  return Number.isFinite(ratio) && Number.isFinite(ratio * 100) ? ratio : null;
}

export function buildRimProfileLabDataset(source: unknown): LabDataset {
  if (!object(source) || !Array.isArray(source.seasons)) throw new Error("rim_deterrence.seasons must be an array");
  const fields = [
    f("delta", "On-minus-off rim share", "pp"),
    f("rim_share_allowed_on", "Opponent rim share: on", "percent"),
    f("rim_share_allowed_off", "Opponent rim share: off", "percent"),
    f("rim_efg_delta", "Rim eFG difference", "pp"),
    f("min_on", "On-court minutes"),
    f("relative_rim_share_difference", "Relative rim-share difference", "percent", 2),
  ];
  const scopeParts: string[] = [];
  const rows: LabRow[] = [];
  for (const [seasonIndex, rawSeason] of source.seasons.entries()) {
    const path = `rim_deterrence.seasons[${seasonIndex}]`;
    if (!object(rawSeason)) throw new Error(`${path} must be an object`);
    if (typeof rawSeason.season !== "string" || !rawSeason.season.trim()) throw new Error(`${path}.season must be a nonempty string`);
    if (!Array.isArray(rawSeason.leaders)) throw new Error(`${path}.leaders must be an array`);
    const season = rawSeason.season;
    const qualified = nonnegativeInteger(rawSeason.n_qualified);
    const floor = finite(rawSeason.min_on_floor);
    const floorText = floor !== null && floor >= 0 ? `${floor} on-court minute floor` : "on-court minute floor unavailable";
    scopeParts.push(`${season}: ${rawSeason.leaders.length} selected player-season rows from ${qualified === null ? "an unavailable number of" : qualified} qualified players; ${floorText}`);
    rawSeason.leaders.forEach((leader, index) => {
      const rowPath = `${path}.leaders[${index}]`;
      if (!object(leader)) throw new Error(`${rowPath} must be an object`);
      if (typeof leader.player_name !== "string" || !leader.player_name.trim()) throw new Error(`${rowPath}.player_name must be a nonempty string`);
      const rank = nonnegativeInteger(leader.rank);
      const on = finite(leader.rim_share_allowed_on);
      const off = finite(leader.rim_share_allowed_off);
      rows.push({
        id: `${season}-${index}`,
        label: leader.player_name,
        group: season,
        definition: { sport: "NBA", season },
        values: {
          delta: finite(leader.delta),
          rim_share_allowed_on: on,
          rim_share_allowed_off: off,
          rim_efg_delta: finite(leader.rim_efg_delta),
          min_on: finite(leader.min_on),
          relative_rim_share_difference: relativeRimShare(on, off),
        },
        note: `Source: rim_deterrence.json seasons[${seasonIndex}].leaders[${index}]. ` +
          `Original source rank: ${rank === null || rank < 1 ? "unavailable" : rank}. ` +
          `Season qualifiers: ${qualified === null ? "unavailable" : qualified}; ${floorText}. ` +
          "Relative rim-share difference = (published rounded on share - published rounded off share) / published rounded off share; off-court share is the baseline. " +
          "It is derived from the same on/off shares, not an independent metric; the published on-minus-off delta is retained separately because its operands were rounded. " +
          "Opponent shot-attempt counts and off-court minutes are unavailable, so this view cannot supply a confidence interval or imply extra precision.",
      });
    });
  }
  return {
    id: "rim-deterrence",
    title: "Opponent rim profile: on vs. off",
    sport: "nba",
    category: "Player & team",
    source: "rim_deterrence",
    description: "Compare opponent rim-attempt shares while a player is on and off court as a descriptive association.",
    scope: scopeParts.join(". ") + (scopeParts.length ? "." : "No season leaderboards published."),
    caveat: "Selected player-season leaderboard rows, not a census or a count of unique players. The source names seasons but does not publish exact calendar endpoints. Teammates, opponents, and roster context confound the on/off association; it does not isolate individual defensive impact. Opponent shot-attempt counts and off-court minutes are unavailable, so confidence intervals are unavailable.",
    status: "Descriptive",
    fields,
    rows,
  };
}

export function getRimProfileLabDataset(): LabDataset {
  return buildRimProfileLabDataset(snapshot<unknown>("rim_deterrence"));
}
