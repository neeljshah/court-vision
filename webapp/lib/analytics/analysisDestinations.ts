export type AnalysisDestination = {
  id: string;
  route: string;
  title: string;
  purpose: string;
  sport: "all" | "nba" | "mlb";
  populationId: string;
  prerequisite: string;
  nextQuestion: string;
  sourceModuleIds: readonly string[];
};

export const analysisDestinations: readonly AnalysisDestination[] = [
  {
    id: "calibration",
    route: "/analytics/calibration",
    title: "Calibration reliability",
    purpose: "Inspect published reliability bins and their uncertainty intervals.",
    sport: "all",
    populationId: "cross_sport_calibration_bins",
    prerequisite: "Read the reliability finding before comparing published bins.",
    nextQuestion: "Where do repeated observations reduce the distinct support behind a bin?",
    sourceModuleIds: ["calibration_stability"],
  },
  {
    id: "state-reliability",
    route: "/analytics/state-reliability",
    title: "State reliability",
    purpose: "Inspect published state-conditioned calibration rows and source-specific support.",
    sport: "all",
    populationId: "state_conditioned_calibration_buckets",
    prerequisite: "Read the calibration reliability bins before comparing state-conditioned cells.",
    nextQuestion: "Which time and probability cells carry the least support behind their gap?",
    sourceModuleIds: ["state_conditioned_calibration"],
  },
  {
    id: "pitch-sequencing",
    route: "/analytics/pitch-sequencing",
    title: "Pitch sequencing",
    purpose: "Inspect published next-pitch transition matrices by count class.",
    sport: "mlb",
    populationId: "mlb_pitch_sequences",
    prerequisite: "Read the pitch-type distribution before interpreting a transition row.",
    nextQuestion: "Which count states change the published pitch sequence?",
    sourceModuleIds: ["pitch_sequencing"],
  },
  {
    id: "count-context",
    route: "/analytics/count-context",
    title: "Count context",
    purpose: "Inspect published pitch mix and outcome proxies by count-leverage class.",
    sport: "mlb",
    populationId: "mlb_count_leverage_classes",
    prerequisite: "Read the count-state cards before comparing pitch mixes across leverage classes.",
    nextQuestion: "Which previous pitch changes the next-pitch probability inside a count class?",
    sourceModuleIds: ["mlb_count_leverage"],
  },
  {
    id: "score-decomposition",
    route: "/analytics/score-decomposition",
    title: "Score decomposition",
    purpose: "Inspect published Brier components and reconstruction remainders.",
    sport: "all",
    populationId: "cross_sport_score_decomposition_rows",
    prerequisite: "Read the calibration reliability view before assigning meaning to a Brier component.",
    nextQuestion: "How much of the recorded score differs after binned reconstruction?",
    sourceModuleIds: ["murphy_decomposition"],
  },
  {
    id: "observation-dependence",
    route: "/analytics/observation-dependence",
    title: "Observation dependence",
    purpose: "Inspect published within-game residual autocorrelation distributions.",
    sport: "all",
    populationId: "cross_sport_residual_series",
    prerequisite: "Read the effective sample size finding before treating repeated ticks as separate evidence.",
    nextQuestion: "Which residual patterns remain after the repeated observations are made visible?",
    sourceModuleIds: ["residual_autocorrelation"],
  },
  {
    id: "residual-anatomy",
    route: "/analytics/residual-anatomy",
    title: "Residual anatomy",
    purpose: "Inspect recorded absolute forecast error by game state, by volume and per row.",
    sport: "nba",
    populationId: "nba_game_state_residual_rows",
    prerequisite: "Read observation dependence before comparing state rows by their repeated ticks.",
    nextQuestion: "Which game states carry the largest recorded absolute residuals?",
    sourceModuleIds: ["residual_anatomy"],
  },
  {
    id: "blowout-timing",
    route: "/analytics/blowout-timing",
    title: "Blowout timing",
    purpose: "Inspect published permanent-margin frequency and conditional clock quartiles.",
    sport: "nba",
    populationId: "nba_games",
    prerequisite: "Read comeback rates by deficit and time remaining before treating a margin as permanent.",
    nextQuestion: "When does a published margin remain in place through the final clock?",
    sourceModuleIds: ["blowout_dynamics"],
  },
  {
    id: "state-contrasts",
    route: "/analytics/state-contrasts",
    title: "State contrasts",
    purpose: "Compare published outcome-frequency differences between adjacent state buckets.",
    sport: "nba",
    populationId: "nba_state_contrasts",
    prerequisite: "Read blowout timing before comparing adjacent margin and clock states.",
    nextQuestion: "How do adjacent published state buckets differ without implying a causal threshold?",
    sourceModuleIds: ["why_attribution"],
  },
  {
    id: "cross-sport-comparability",
    route: "/analytics/cross-sport-comparability",
    title: "Cross-sport comparability",
    purpose: "Read the published gate for reliability-component comparisons across sports.",
    sport: "all",
    populationId: "cross_sport_reliability_rows",
    prerequisite: "Read each sport's calibration reliability before comparing components across sports.",
    nextQuestion: "Which sports publish a reference the model can be held against?",
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
