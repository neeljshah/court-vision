import { field as f, snapshot } from "./labHelpers";
import type { LabDataset, LabRow } from "./labTypes";

type Entry = Record<string, unknown>;
type Source = { top?: unknown; bottom?: unknown; season?: unknown; n_qualified?: unknown };
type TeamSource = { players?: unknown };
type AtlasSource = { entries?: unknown };

const object = (value: unknown): value is Entry => value !== null && typeof value === "object" && !Array.isArray(value);
const finite = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;
const count = (value: unknown): number | null => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;

function rows(value: unknown, key: "top" | "bottom"): Entry[] {
  if (!Array.isArray(value)) throw new Error(`lineup_synergy.${key} must be an array`);
  value.forEach((row, index) => {
    if (!object(row)) throw new Error(`lineup_synergy.${key}[${index}] must be an object`);
    if (!Array.isArray(row.members) || row.members.length !== 5 ||
        !row.members.every((name: unknown) => typeof name === "string" && name.trim().length > 0)) {
      throw new Error(`lineup_synergy.${key}[${index}].members must contain five names`);
    }
  });
  return value as Entry[];
}

function teamNames(teams?: TeamSource, atlas?: AtlasSource): Map<number, string> {
  const codes = new Map<number, Set<string>>();
  for (const raw of Array.isArray(teams?.players) ? teams.players : []) {
    if (!object(raw) || typeof raw.team_id !== "number" || !Number.isSafeInteger(raw.team_id) || typeof raw.team !== "string" || !raw.team.trim()) continue;
    const id = raw.team_id as number;
    const set = codes.get(id) || new Set<string>();
    set.add(raw.team.trim());
    codes.set(id, set);
  }
  const names = new Map<string, Set<string>>();
  for (const raw of Array.isArray(atlas?.entries) ? atlas.entries : []) {
    if (!object(raw) || typeof raw.entity !== "string" || !object(raw.key_numbers) ||
        typeof raw.key_numbers.team_full_name !== "string") continue;
    const code = raw.entity.trim();
    const name = raw.key_numbers.team_full_name.trim();
    if (!code || !name) continue;
    const set = names.get(code) || new Set<string>();
    set.add(name);
    names.set(code, set);
  }
  return new Map([...codes].flatMap(([id, codeSet]) => {
    if (codeSet.size !== 1) return [];
    const nameSet = names.get([...codeSet][0]);
    return nameSet?.size === 1 ? [[id, [...nameSet][0]] as const] : [];
  }));
}

export function buildLineupSynergyLabDataset(source: Source, teams?: TeamSource, atlas?: AtlasSource): LabDataset {
  const top = rows(source.top, "top");
  const bottom = rows(source.bottom, "bottom");
  const knownTeams = teamNames(teams, atlas);
  const fields = [
    f("synergy_residual", "Residual points / 48 min"),
    f("net_per48", "Observed net points / 48 min"),
    f("expected_net_per48", "Expected net points / 48 min"),
    f("min", "On-court minutes"),
    f("n_games", "Recorded games", "number", 0),
    f("minutes_per_game", "Minutes per recorded game"),
  ];
  const buildRows = (entries: Entry[], key: "top" | "bottom", group: string): LabRow[] => entries.map((raw, index) => {
    const members = raw.members as string[];
    const id = count(raw.team_id);
    const team = id === null ? null : knownTeams.get(id) || null;
    const teamLabel = team || (id === null ? "Unknown team" : `Unknown team (ID ${id})`);
    const rank = count(raw.rank);
    const minutes = finite(raw.min);
    const games = count(raw.n_games);
    const perGame = minutes !== null && minutes >= 0 && games !== null && games > 0 ? minutes / games : null;
    return {
      id: `${group}-${index}`,
      label: `${teamLabel} - ${group} #${rank !== null && rank > 0 ? rank : index + 1}`,
      group,
      values: {
        synergy_residual: finite(raw.synergy_residual),
        net_per48: finite(raw.net_per48),
        expected_net_per48: finite(raw.expected_net_per48),
        min: minutes,
        n_games: games,
        minutes_per_game: perGame !== null && Number.isFinite(perGame) ? perGame : null,
      },
      note: `Roster: ${members.join(", ")}. Source: lineup_synergy.json ${key}[${index}]. ` +
        `Source team_id: ${id === null ? "unavailable" : id}. ` +
        `${team ? `Team: ${team}; name resolved via ctx_lineup_proxy.json and atlas_nba_teams_manifest.json for identity only.` : "Team name unavailable in public team mapping."} ` +
        "Expected net points / 48 min sums the five members' individual on/off contributions. " +
        "Residual points / 48 min is published observed minus published expected; the original residual is retained because source operands were rounded independently. " +
        "Minutes per recorded game divides the published rounded on-court minute total by recorded games; it is not a typical stint duration or a count of independent samples.",
    };
  });
  const qualified = count(source.n_qualified);
  const season = typeof source.season === "string" && source.season.trim() ? source.season.trim() : "season unavailable";
  return {
    id: "lineup-synergy",
    title: "Five-player lineup synergy",
    sport: "nba",
    category: "Player & team",
    source: "lineup_synergy",
    description: "Compare a lineup's observed net points per 48 minutes with the sum of its members' individual on/off contributions.",
    scope: `${top.length} top and ${bottom.length} bottom selected lineups from ${qualified === null ? "an unavailable number of" : qualified} qualified lineups; ${season}. Qualification requires all five members to qualify for individual on/off.`,
    caveat: "Selected extremes from one season; on-court minutes can be small. Individual on/off contributions carry roster confounds, opponents are unadjusted, and the residual does not establish causal chemistry. Rates are points per 48 minutes, not points per 100 possessions.",
    status: "Descriptive",
    fields,
    rows: [...buildRows(top, "top", "Top residuals"), ...buildRows(bottom, "bottom", "Bottom residuals")],
    nQualifying: qualified === null ? undefined : qualified,
  };
}

export function getLineupSynergyLabDataset(): LabDataset {
  return buildLineupSynergyLabDataset(
    snapshot<Source>("lineup_synergy"),
    snapshot<TeamSource>("ctx_lineup_proxy"),
    snapshot<AtlasSource>("atlas_nba_teams_manifest"),
  );
}
