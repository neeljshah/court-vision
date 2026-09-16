export type PublishedValue = number | null;

export type CrossSportSourceRow = {
  sport: string;
  market: string;
  reliability_model: PublishedValue;
  reliability_market: PublishedValue;
  reliability_gap: PublishedValue;
  reliability_unit: string | null;
  reliability_comparable: boolean;
  comparability_reason: string;
  n: number | null;
  sources: string[];
};

export type CrossSportEvidence = { href: string; title: string };

export type CrossSportRow = CrossSportSourceRow & {
  id: string;
  evidence: CrossSportEvidence;
  unavailableMeasurement: string | null;
};

export type SportCapability = {
  sport: string;
  scoreAvailable: boolean;
  referenceAvailable: boolean;
  decompositionAvailable: boolean;
  populationAvailable: boolean;
};

export type CrossSportComparability = {
  generatedAt: string;
  rows: CrossSportRow[];
  comparableRows: CrossSportRow[];
  unsupportedRows: CrossSportRow[];
  capabilities: SportCapability[];
};

export type CrossSportSnapshot = { generated_at: string; rows: CrossSportSourceRow[] };

function unavailableMeasurement(row: CrossSportSourceRow): string | null {
  if (row.reliability_comparable) return null;
  if (row.market.includes("CRPS")) return "Murphy reliability/resolution for a binary outcome probability";
  if (row.market.includes("no reliability decomposition")) return "10-bin Murphy reliability/resolution split";
  if (row.market.includes("no market side")) return "market probability";
  return "published reliability component";
}

function capabilityFor(sport: string, rows: CrossSportSourceRow[]): SportCapability {
  return {
    sport,
    scoreAvailable: rows.some(row => row.reliability_model !== null),
    referenceAvailable: rows.some(row => row.reliability_market !== null),
    decompositionAvailable: rows.some(row => row.reliability_gap !== null),
    populationAvailable: rows.some(row => row.n !== null),
  };
}

export function buildCrossSportComparability(
  snapshot: CrossSportSnapshot,
  resolveEvidence: (row: CrossSportSourceRow) => CrossSportEvidence,
): CrossSportComparability {
  const rows = snapshot.rows.map((row, index) => ({
    ...row,
    id: `${row.sport}-${index}`,
    evidence: resolveEvidence(row),
    unavailableMeasurement: unavailableMeasurement(row),
  }));
  const sportRows = new Map<string, CrossSportSourceRow[]>();
  snapshot.rows.forEach(row => sportRows.set(row.sport, [...(sportRows.get(row.sport) || []), row]));
  return {
    generatedAt: snapshot.generated_at,
    rows,
    comparableRows: rows.filter(row => row.reliability_comparable),
    unsupportedRows: rows.filter(row => !row.reliability_comparable),
    capabilities: [...sportRows].map(([sport, sportRows]) => capabilityFor(sport, sportRows)),
  };
}

export function formatReliability(value: PublishedValue): string {
  return value === null ? "Not published" : value.toFixed(6);
}
