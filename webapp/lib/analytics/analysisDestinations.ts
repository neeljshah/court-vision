export type AnalysisDestination = {
  id: string;
  route: string;
  title: string;
  purpose: string;
  sport: "all" | "nba" | "mlb";
  sports: string[];
  populationId: string;
  prerequisite: string;
  prerequisiteId: string | null;
  nextQuestion: string;
  nextId: string | null;
  sourceModuleIds: readonly string[];
};

export const analysisDestinations: readonly AnalysisDestination[] = [
  {
    id: "calibration",
    route: "/analytics/calibration",
    title: "Calibration reliability",
    purpose: "Inspect published reliability bins and their uncertainty intervals.",
    sport: "all",
    sports: ["mlb", "soccer_intl"],
    populationId: "cross_sport_calibration_bins",
    prerequisite: "Read the reliability finding before comparing published bins.",
    prerequisiteId: "reliability",
    nextQuestion: "Where do repeated observations reduce the distinct support behind a bin?",
    nextId: "observation-dependence",
    sourceModuleIds: ["calibration_stability"],
  },
  {
    id: "state-reliability",
    route: "/analytics/state-reliability",
    title: "State reliability",
    purpose: "Inspect published state-conditioned calibration rows and source-specific support.",
    sport: "all",
    sports: ["mlb", "soccer_intl"],
    populationId: "state_conditioned_calibration_buckets",
    prerequisite: "Read the calibration reliability bins before comparing state-conditioned cells.",
    prerequisiteId: "calibration",
    nextQuestion: "Which published game states carry the largest recorded absolute residuals?",
    nextId: "residual-anatomy",
    sourceModuleIds: ["state_conditioned_calibration"],
  },
  {
    id: "pitch-sequencing",
    route: "/analytics/pitch-sequencing",
    title: "Pitch sequencing",
    purpose: "Inspect published next-pitch transition matrices by count class.",
    sport: "mlb",
    sports: ["mlb"],
    populationId: "mlb_pitch_sequences",
    prerequisite: "Read the pitch-type distribution before interpreting a transition row.",
    prerequisiteId: "mlb-pitch-mix-concentration",
    nextQuestion: "Which count states change the published pitch sequence?",
    nextId: "count-context",
    sourceModuleIds: ["pitch_sequencing"],
  },
  {
    id: "count-context",
    route: "/analytics/count-context",
    title: "Count context",
    purpose: "Compare exact ball-strike counts: top pitch share, coded strike rate, in-zone rate, and broader count-class pitch mixes.",
    sport: "mlb",
    sports: ["mlb"],
    populationId: "mlb_count_leverage_classes",
    prerequisite: "Read the count-state cards before comparing pitch mixes across leverage classes.",
    prerequisiteId: "mlb-count-contrast",
    nextQuestion: "Which previous pitch changes the next-pitch probability inside a count class?",
    nextId: "pitch-sequencing",
    sourceModuleIds: ["mlb_count_leverage"],
  },
  {
    id: "score-decomposition",
    route: "/analytics/score-decomposition",
    title: "Score decomposition",
    purpose: "Inspect published Brier components and reconstruction remainders.",
    sport: "all",
    sports: ["mlb", "soccer_intl"],
    populationId: "cross_sport_score_decomposition_rows",
    prerequisite: "Read the calibration reliability view before assigning meaning to a Brier component.",
    prerequisiteId: "calibration",
    nextQuestion: "Which published reliability components can be compared across sports?",
    nextId: "cross-sport-comparability",
    sourceModuleIds: ["murphy_decomposition"],
  },
  {
    id: "observation-dependence",
    route: "/analytics/observation-dependence",
    title: "Observation dependence",
    purpose: "Inspect published within-game residual autocorrelation distributions.",
    sport: "all",
    sports: ["mlb", "soccer_intl"],
    populationId: "cross_sport_residual_series",
    prerequisite: "Read the effective sample size finding before treating repeated ticks as separate evidence.",
    prerequisiteId: "effective-sample-size",
    nextQuestion: "Which time and probability cells carry the least support behind their gap?",
    nextId: "state-reliability",
    sourceModuleIds: ["residual_autocorrelation"],
  },
  {
    id: "residual-anatomy",
    route: "/analytics/residual-anatomy",
    title: "Residual anatomy",
    purpose: "Inspect recorded absolute forecast error by game state, by volume and per row.",
    sport: "all",
    sports: ["mlb", "soccer_intl"],
    populationId: "cross_sport_game_state_residual_rows",
    prerequisite: "Read observation dependence before interpreting residual rows with repeated observations.",
    prerequisiteId: "observation-dependence",
    nextQuestion: "How does the published Brier score separate into its recorded components?",
    nextId: "score-decomposition",
    sourceModuleIds: ["residual_anatomy"],
  },
  {
    id: "blowout-timing",
    route: "/analytics/blowout-timing",
    title: "Blowout timing",
    purpose: "Inspect published permanent-margin frequency and conditional clock quartiles.",
    sport: "all",
    sports: ["mlb", "soccer_intl"],
    populationId: "cross_sport_games",
    prerequisite: "Read comeback rates by deficit and time remaining before treating a margin as permanent.",
    prerequisiteId: "comeback-rates-deficit-time",
    nextQuestion: "How do adjacent published score and clock states differ?",
    nextId: "state-contrasts",
    sourceModuleIds: ["blowout_dynamics"],
  },
  {
    id: "state-contrasts",
    route: "/analytics/state-contrasts",
    title: "State contrasts",
    purpose: "Compare published outcome-frequency differences between adjacent state buckets.",
    sport: "all",
    sports: ["mlb", "soccer_intl"],
    populationId: "cross_sport_state_contrasts",
    prerequisite: "Read blowout timing before comparing published adjacent state buckets.",
    prerequisiteId: "blowout-timing",
    nextQuestion: "How much independent support remains when observations repeat within a game?",
    nextId: "observation-dependence",
    sourceModuleIds: ["why_attribution"],
  },
  {
    id: "cross-sport-comparability",
    route: "/analytics/cross-sport-comparability",
    title: "Cross-sport comparability",
    purpose: "Read the published gate for reliability-component comparisons across sports.",
    sport: "all",
    sports: ["mlb", "soccer_intl", "nba", "tennis"],
    populationId: "cross_sport_reliability_rows",
    prerequisite: "Read each sport's calibration reliability before comparing components across sports.",
    prerequisiteId: "calibration",
    nextQuestion: "How closely do published forecast bins align with observed outcomes?",
    nextId: "calibration",
    sourceModuleIds: ["kernel_transfer"],
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
