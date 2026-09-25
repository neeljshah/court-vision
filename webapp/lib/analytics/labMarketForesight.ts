import { field as f, snapshot } from "./labHelpers";
import type { LabDataset, LabRow } from "./labTypes";

type SourceObject = Record<string, unknown>;
const object = (value: unknown): value is SourceObject => value !== null && typeof value === "object" && !Array.isArray(value);
const finite = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;
const entropy = (value: unknown): number | null => {
  const parsed = finite(value);
  return parsed !== null && parsed >= 0 ? parsed : null;
};
const count = (value: unknown): number | null =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
const sportName = (sport: string) => sport.replace("soccer_intl", "International soccer").toUpperCase();
const available = (value: number | null) => value === null ? "unavailable" : String(value);

function artifactDate(value: unknown): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value ? value : null;
}

function checkpointNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) && value >= 0 ? value : null;
  if (typeof value !== "string" || !/^\d+(?:\.\d+)?$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function buildMarketForesightLabDataset(source: unknown): LabDataset {
  if (!object(source) || !object(source.results)) {
    throw new Error("novel_market_foresight_premium.results must be an object");
  }
  const fields = [
    f("mfp", "Market foresight premium", "number", 4),
    f("market_skill", "Closing reference skill vs. naive", "number", 4),
    f("model_skill", "State-only model skill vs. naive", "number", 4),
    f("entropy_market_bits", "Reference entropy (bits)", "number", 4),
    f("n", "Checkpoint observations", "number", 0),
    f("checkpoint", "Game-clock checkpoint", "number", 0),
  ];
  const checkpointScopes: string[] = [];
  const rows: LabRow[] = Object.entries(source.results).flatMap(([sport, result]) => {
    const path = `novel_market_foresight_premium.results.${sport}`;
    if (!object(result) || !Array.isArray(result.checkpoints)) {
      throw new Error(`${path}.checkpoints must be an array`);
    }
    const group = sportName(sport);
    const clockField = sport === "mlb" ? "inning" : sport === "soccer_intl" ? "minute (5-minute bucket)" : undefined;
    const sportRows: LabRow[] = result.checkpoints.map((raw, index) => {
      const rowPath = `${path}.checkpoints[${index}]`;
      if (!object(raw)) throw new Error(`${rowPath} must be an object`);
      const checkpoint = checkpointNumber(raw.checkpoint);
      const checkpointLabel = typeof raw.checkpoint === "string" || typeof raw.checkpoint === "number"
        ? String(raw.checkpoint) : "unavailable";
      const floorState = raw.entropy_floored === true ? "Yes" : raw.entropy_floored === false ? "No" : "Unavailable";
      const clockNote = sport === "mlb" ? "inning" : sport === "soccer_intl"
        ? checkpoint === 90 ? "5-minute bucket; 90+ includes minute 90 and later" : "5-minute bucket of match minutes"
        : "clock unit unavailable";
      return {
        id: `${group}-${index}`,
        label: `${group} / ${checkpointLabel}`,
        group,
        values: {
          mfp: finite(raw.mfp),
          market_skill: finite(raw.market_skill),
          model_skill: finite(raw.model_skill),
          entropy_market_bits: entropy(raw.entropy_market_bits),
          n: count(raw.n),
          checkpoint,
        },
        note: `Source: novel_market_foresight_premium.json results.${sport}.checkpoints[${index}]. ` +
          `Game-clock checkpoint: ${checkpointLabel} (${clockNote}). ` +
          `Entropy floored: ${floorState}. ${available(count(raw.n))} checkpoint observations; unique game count unavailable.`,
        definition: { sport: group, ...(clockField ? { clockField } : {}) },
      };
    });
    const first = sportRows[0]?.values.checkpoint ?? null;
    const last = sportRows.at(-1)?.values.checkpoint ?? null;
    const lastLabel = sport === "soccer_intl" && last === 90 ? "90+" : available(last);
    checkpointScopes.push(`${group} ${clockField ?? "clock"} checkpoints ${available(first)} to ${lastLabel}`);
    return sportRows;
  });
  const date = artifactDate(source.as_of);
  const floor = finite(source.entropy_floor_bits);
  const usableFloor = floor !== null && floor > 0 ? floor : null;
  return {
    id: "market-foresight",
    title: "Market Foresight Premium",
    sport: "all",
    category: "Experimental metrics",
    source: "novel_market_foresight_premium",
    description: "Closing reference forecast skill minus one state-only model's skill, scaled by remaining reference uncertainty at each game-clock checkpoint.",
    scope: `${checkpointScopes.length ? checkpointScopes.join("; ") : "No sport checkpoints published"}. Artifact date: ${date ?? "unavailable"}; observation window unavailable. ` +
      `Entropy floor: ${usableFloor === null ? "unavailable" : `${usableFloor} bits`}. Checkpoint counts are observations; unique game count unavailable.`,
    caveat: "The closing reference forecast and one state-only model use different information; their difference cannot isolate news from model misspecification. " +
      `The source ${usableFloor === null ? "does not provide a valid entropy floor" : `uses a ${usableFloor}-bit entropy floor`} in the denominator. ` +
      "MLB innings and soccer minute buckets differ, and sparse checkpoints do not establish a time trend or a live forecast.",
    status: "Incremental metric",
    fields,
    rows,
  };
}

export function getMarketForesightLabDataset(): LabDataset {
  return buildMarketForesightLabDataset(snapshot<unknown>("novel_market_foresight_premium"));
}
