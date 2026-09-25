import { field as f, snapshot } from "./labHelpers";
import type { LabDataset, LabRow } from "./labTypes";

type Source = {
  observation_window?: { first_date?: unknown; last_date?: unknown; n_matches_played?: unknown };
  by_era?: unknown;
};

const finite = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

const count = (value: unknown): number | null =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;

const eraRule = (era: string): string =>
  era === "pre-2000" ? "year < 2000" : era === "2000+" ? "year >= 2000" : "era rule not defined by producer";

function corpusWindow(source: Source): string {
  const window = source.observation_window;
  const first = window?.first_date;
  const last = window?.last_date;
  if (typeof first !== "string" || typeof last !== "string" ||
      !/^\d{4}-\d{2}-\d{2}$/.test(first) || !/^\d{4}-\d{2}-\d{2}$/.test(last) || first > last) {
    return "Overall observation window unavailable in the published source";
  }
  return `Overall corpus observation window ${first} to ${last}`;
}

export function buildSoccerVenueLabDataset(source: Source): LabDataset {
  const window = corpusWindow(source);
  const total = count(source.observation_window?.n_matches_played);
  const fields = [
    f("true_home_goal_diff", "True-home goal difference", "number", 4),
    f("neutral_goal_diff", "Neutral-site goal difference", "number", 4),
    f("effect_goal_diff", "Home-minus-neutral gap", "number", 4),
    f("n_true_home", "True-home matches", "number", 0),
    f("n_neutral", "Neutral matches", "number", 0),
    f("neutral_match_share", "Neutral-site match share", "percent"),
  ];
  const eras = Array.isArray(source.by_era) ? source.by_era : [];
  const rows: LabRow[] = eras.flatMap((raw, index) => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return [];
    const entry = raw as Record<string, unknown>;
    const era = entry.era;
    if (typeof era !== "string" || !era.trim()) return [];
    const trueHome = count(entry.n_true_home);
    const neutral = count(entry.n_neutral);
    const denominator = trueHome !== null && neutral !== null ? trueHome + neutral : null;
    const share = denominator !== null && Number.isSafeInteger(denominator) && denominator > 0
      ? neutral! / denominator : null;
    return [{
      id: `Published rows-${index}`,
      label: era,
      group: "Published rows",
      values: {
        true_home_goal_diff: finite(entry.true_home_goal_diff),
        neutral_goal_diff: finite(entry.neutral_goal_diff),
        effect_goal_diff: finite(entry.effect_goal_diff),
        n_true_home: trueHome,
        n_neutral: neutral,
        neutral_match_share: share,
      },
      note: `Source: soccer_home_advantage.json by_era[${index}]. ` +
        `Era predicate: ${eraRule(era)}. Neutral-site match share = ` +
        `by_era[${index}].n_neutral / (by_era[${index}].n_true_home + by_era[${index}].n_neutral); ` +
        "unavailable unless both counts are valid and their sum is positive. " +
        `Goal differences and gap are published by_era[${index}] values, not reconstructed. ` +
        "This row is one aggregate era summary, not a match-level distribution; row ranks are not match ranks.",
      definition: {
        sport: "International soccer",
        population: "Matches with recorded scores in the published era, split by the source neutral flag",
        observationWindow: era,
      },
    }];
  });
  return {
    id: "soccer-home-advantage",
    title: "Home advantage across eras",
    sport: "soccer",
    category: "Game context",
    source: "soccer_home_advantage",
    description: "Compare published true-home and neutral-site goal differences with each era's neutral-site match share.",
    scope: `${total === null ? "Published international matches (total unavailable)" : `${total.toLocaleString("en-US")} played international matches`}; ${window}. Eras use year < 2000 and year >= 2000.`,
    caveat: "Neutral venues are not randomly assigned; team strength and tournament mix are uncontrolled. Venue share is descriptive and does not explain the goal gap. Travel effects are not testable from this source.",
    status: "Descriptive",
    fields,
    rows,
  };
}

export function getSoccerVenueLabDataset(): LabDataset {
  return buildSoccerVenueLabDataset(snapshot<Source>("soccer_home_advantage"));
}
