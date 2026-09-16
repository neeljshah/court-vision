export const integrityFinding = {
  measuredOn: "2026-09-16",
  counts: [
    { sport: "MLB", files: "227 game files", ticks: "78,986 ticks", contaminated: "126 files; 27,076 ticks (34.3 percent)", stateless: "26,340 ticks (33.3 percent)", truncated: "61 of 227 games" },
    { sport: "International soccer", files: "51 game files", ticks: "9,003 ticks", contaminated: "1 file (0.9 percent)", stateless: "Not reported", truncated: "2 truncated draws" },
  ],
  agreement: [
    { population: "Late-inning (inning 7+) leading-side labels across all MLB ticks", agreement: "0.7284", n: "n = 12,588" },
    { population: "Late-inning (inning 7+) leading-side labels in the final MLB segment", agreement: "0.9200", n: "n = 6,623" },
  ],
  leaderAgreement: "Game-level labels agree with the last stated score in all 166 games with a leader (frequency 1.0000).",
  cause: "The capture matched a market ticker to a live game by team pair only, so consecutive-day series games were appended to one file. The settlement join then copied one label onto every tick.",
  exposedArtifacts: [
    "state_conditioned_calibration", "calibration_stability", "murphy_decomposition",
    "brier_skill_scores", "residual_anatomy", "calibration_by_market_type",
    "residual_autocorrelation", "calibration_over_time", "calibration_atlas",
    "market_disagreement_profile", "info_arrival_curve", "market_overreaction",
    "soccer_calibration_pack",
  ],
  notExposedArtifacts: ["market_convergence", "blowout_dynamics"],
} as const;
