export interface TimingModuleEvidence {
  title: string;
  summary: string;
  method: string;
  caveat: string;
  snapshotDate: string | null;
  denominator: string;
  tables: Array<{
    id: string;
    title: string;
    columns: Array<{ key: string; label: string }>;
    rows: Array<Record<string, string | number | null>>;
  }>;
  receipts: Array<{ label: string; value: string }>;
  missing: string[];
  askQuestion: string;
}

type Source = Record<string, unknown>;
type Cell = string | number | null;
const object = (value: unknown): value is Source => value !== null && typeof value === "object" && !Array.isArray(value);
const number = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;
const fraction = (value: unknown): number | null => {
  const parsed = number(value);
  return parsed !== null && parsed >= 0 && parsed <= 1 ? parsed : null;
};
const nonnegative = (value: unknown): number | null => {
  const parsed = number(value);
  return parsed !== null && parsed >= 0 ? parsed : null;
};
const count = (value: unknown): number | null => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
const text = (value: unknown): string | null => typeof value === "string" && value.trim() ? value.trim() : null;
const available = (value: Cell): string => value === null ? "unavailable" : String(value);
const sportTitle = (sport: string): string => sport === "mlb" ? "MLB" : "International soccer";

function date(value: unknown): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value ? value : null;
}

function tracked(row: Source, key: string, label: string, parse: (value: unknown) => Cell, missing: string[]): Cell {
  const value = parse(row[key]);
  if (value === null) missing.push(label);
  return value;
}

function liveClock(source: Source): TimingModuleEvidence {
  const missing: string[] = [];
  const raw = Array.isArray(source.results) ? source.results : [];
  const tables: TimingModuleEvidence["tables"] = [];
  const receipts: TimingModuleEvidence["receipts"] = [];
  const columns = [
    { key: "sport", label: "Sport" }, { key: "live_clock_fraction", label: "LCF" },
    { key: "threshold", label: "Score-gap threshold" }, { key: "unit", label: "Threshold unit" },
    { key: "clock_field", label: "Clock" }, { key: "n_games_decided", label: "Decided paths" },
    { key: "n_games_total", label: "Usable score paths" }, { key: "decided_frac_of_games", label: "Decided fraction" },
  ];
  for (const sport of ["mlb", "soccer_intl"]) {
    const item = raw.find(value => object(value) && value.sport === sport);
    const label = sportTitle(sport);
    if (!object(item)) {
      missing.push(`${label} source row`);
      tables.push({ id: `lcf-${sport}`, title: label, columns, rows: [] });
      receipts.push({ label: `${label} threshold-decided paths`, value: "unavailable" });
      continue;
    }
    let decided = tracked(item, "n_games_decided", `${label} decided games`, count, missing);
    const total = tracked(item, "n_games_total", `${label} games with usable score paths`, count, missing);
    const inconsistent = typeof decided === "number" && typeof total === "number" && decided > total;
    if (inconsistent) {
      missing.push(`${label} decided games exceed usable score paths`);
      decided = null;
    }
    const row: Record<string, Cell> = {
      id: sport,
      sport: label,
      live_clock_fraction: tracked(item, "live_clock_fraction", `${label} live-clock fraction`, fraction, missing),
      threshold: tracked(item, "near_median_threshold", `${label} score-gap threshold`, nonnegative, missing),
      unit: tracked(item, "unit", `${label} threshold unit`, text, missing),
      clock_field: tracked(item, "clock_field", `${label} clock field`, text, missing),
      n_games_decided: decided,
      n_games_total: total,
      decided_frac_of_games: inconsistent ? null : tracked(item, "decided_frac_of_games", `${label} decided fraction`, fraction, missing),
    };
    tables.push({ id: `lcf-${sport}`, title: label, columns, rows: [row] });
    receipts.push({ label: `${label} threshold-decided paths`, value: `${available(decided)} of ${available(total)} games with usable score paths` });
  }
  const unavailableSports = Array.isArray(source.not_buildable)
    ? source.not_buildable.filter(object).map(item => text(item.sport)).filter((item): item is string => item !== null)
    : [];
  if (!raw.length) missing.push("LCF sport rows");
  return {
    title: "Live-Clock Fraction",
    summary: "A retrospective share of the observed clock before a threshold score gap stayed permanent in threshold-decided paths.",
    method: "The source selects the non-masked threshold closest to half of usable score paths being decided. For each threshold-decided score path, find the first tick after the last reversion where the absolute score gap remains at or above the threshold through the final observed tick. LCF is the median fraction of the final observed clock at that tick. The observation window is not published.",
    caveat: `Thresholds and clock units differ by sport, so these rows do not establish a cross-sport ranking. ${unavailableSports.length ? unavailableSports.map(sport => sport.toUpperCase()).join(" and ") + " are not buildable in this artifact." : "Other sports' buildability is unavailable."} This describes observed score paths, not prospective outcomes.`,
    snapshotDate: date(source.as_of),
    denominator: "LCF uses threshold-decided paths; decided fraction uses games with usable score paths. Unique stored corpus counts are not in this artifact.",
    tables,
    receipts, missing, askQuestion: "What is the Live-Clock Fraction?",
  };
}

function foresight(source: Source): TimingModuleEvidence {
  const missing: string[] = [];
  const results = object(source.results) ? source.results : {};
  const tables: TimingModuleEvidence["tables"] = [];
  const receipts: TimingModuleEvidence["receipts"] = [];
  for (const sport of ["mlb", "soccer_intl"]) {
    const label = sportTitle(sport);
    const section = results[sport];
    const checkpoints = object(section) && Array.isArray(section.checkpoints) ? section.checkpoints : [];
    if (!checkpoints.length) missing.push(`${label} checkpoint rows`);
    const rows = checkpoints.map((raw, index): Record<string, Cell> => {
      const item = object(raw) ? raw : {};
      const prefix = `${label} checkpoint row ${index + 1}`;
      const checkpoint = tracked(item, "checkpoint", `${prefix} checkpoint`, text, missing);
      const floored = item.entropy_floored === true ? "Yes" : item.entropy_floored === false ? "No" : null;
      if (floored === null) missing.push(`${prefix} entropy floor status`);
      return {
        id: `${sport}-${available(checkpoint)}-${index}`,
        checkpoint,
        mfp: tracked(item, "mfp", `${prefix} MFP`, number, missing),
        market_skill: tracked(item, "market_skill", `${prefix} closing reference skill`, number, missing),
        model_skill: tracked(item, "model_skill", `${prefix} state-only model skill`, number, missing),
        entropy_market_bits: tracked(item, "entropy_market_bits", `${prefix} entropy`, nonnegative, missing),
        n: tracked(item, "n", `${prefix} observations`, count, missing),
        entropy_floored: floored,
      };
    });
    tables.push({
      id: `mfp-${sport}`, title: label,
      columns: [
        { key: "checkpoint", label: sport === "mlb" ? "Inning" : "Minute" },
        { key: "mfp", label: "MFP" }, { key: "market_skill", label: "Closing reference skill" },
        { key: "model_skill", label: "State-only model skill" }, { key: "entropy_market_bits", label: "Reference entropy (bits)" },
        { key: "n", label: "Observations" }, { key: "entropy_floored", label: "Entropy floor applied" },
      ], rows,
    });
    const last = rows.at(-1);
    receipts.push({ label: `${label} last checkpoint observations`, value: last ? available(last.n) : "unavailable" });
  }
  const floor = number(source.entropy_floor_bits);
  if (floor === null || floor < 0) missing.push("Entropy floor in bits");
  return {
    title: "Market Foresight Premium",
    summary: "The closing reference forecast's skill advantage over a specific state-only model, scaled by remaining reference entropy at each checkpoint.",
    method: `At each checkpoint, compare closing reference and state-only model skill against the naive forecast, then divide their difference by reference entropy${floor !== null && floor >= 0 ? ` with a ${floor}-bit floor` : " with an unavailable floor"}. The observation window is not published.`,
    caveat: "The closing reference is a forecaster, not a live price. Checkpoints can contain different populations; inspect each observation count, especially late in the game. Endpoint differences alone do not establish a time trend or causal explanation. Model misspecification and information the reference prices remain confounded.",
    snapshotDate: date(source.as_of),
    denominator: "Checkpoint observations shown per row; unique game counts unavailable.",
    tables, receipts, missing, askQuestion: "What is the Market Foresight Premium?",
  };
}

export function getTimingModuleEvidence(id: string, out: Record<string, unknown>): TimingModuleEvidence | null {
  if (id === "novel_live_clock_fraction") return liveClock(out);
  if (id === "novel_market_foresight_premium") return foresight(out);
  return null;
}
