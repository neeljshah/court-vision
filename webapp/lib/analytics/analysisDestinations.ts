export type AnalysisDestination = {
  route: string;
  title: string;
  purpose: string;
  sourceModuleIds: readonly string[];
};

export const analysisDestinations: readonly AnalysisDestination[] = [
  {
    route: "/analytics/calibration",
    title: "Calibration reliability",
    purpose: "Inspect published reliability bins and their uncertainty intervals.",
    sourceModuleIds: ["calibration_stability"],
  },
  {
    route: "/analytics/pitch-sequencing",
    title: "Pitch sequencing",
    purpose: "Inspect published next-pitch transition matrices by count class.",
    sourceModuleIds: ["pitch_sequencing"],
  },
  {
    route: "/analytics/score-decomposition",
    title: "Score decomposition",
    purpose: "Inspect published Brier components and reconstruction remainders.",
    sourceModuleIds: ["murphy_decomposition"],
  },
  {
    route: "/analytics/observation-dependence",
    title: "Observation dependence",
    purpose: "Inspect published within-game residual autocorrelation distributions.",
    sourceModuleIds: ["residual_autocorrelation"],
  },
  {
    route: "/analytics/residual-anatomy",
    title: "Residual anatomy",
    purpose: "Inspect recorded absolute forecast error by game state, by volume and per row.",
    sourceModuleIds: ["residual_anatomy"],
  },
  {
    route: "/analytics/blowout-timing",
    title: "Blowout timing",
    purpose: "Inspect published permanent-margin frequency and conditional clock quartiles.",
    sourceModuleIds: ["blowout_dynamics"],
  },
];

export type SearchPageRecord = {
  id: string;
  title: string;
  subtitle: string;
  href: string;
  type: "page";
  keywords: string[];
};

export function destinationForSourceModule(moduleId: string): AnalysisDestination | undefined {
  return analysisDestinations.find(destination => destination.sourceModuleIds.includes(moduleId));
}

export function inspectorSearchRecords(): SearchPageRecord[] {
  return analysisDestinations.map(destination => ({
    id: `page-${destination.route.split("/").pop()}`,
    title: destination.title,
    subtitle: destination.purpose,
    href: destination.route,
    type: "page",
    keywords: ["inspector", "published", ...destination.title.toLowerCase().split(/\s+/)],
  }));
}
