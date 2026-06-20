// glossary.ts -- plain-language definitions for the in-depth product.
//
// The single source of truth for "what is this number?" copy used by InfoTip,
// Legend, and the verdict/provenance badges. Every page can surface the SAME
// honest definition, so a reader can always understand what a value means.
//
// HONESTY RAILS: calibration is NOT a market edge; vs_close is UNPROVEN; the
// self-improve loop is READY but INERT; real money is DENY; UNITS / probability
// only, never a $ amount. These definitions must never imply a profit edge.
// ASCII only.

export interface GlossaryEntry {
  /** Stable key used by InfoTip term={...}. */
  term: string;
  /** Short display label (what shows next to the tip trigger). */
  label: string;
  /** Plain-language, one-to-three sentence definition. */
  definition: string;
}

export const GLOSSARY: Record<string, GlossaryEntry> = {
  units: {
    term: "units",
    label: "units",
    definition:
      "Stake sizing is expressed in abstract UNITS (probability-derived), never " +
      "dollars. There is no money in this product -- a unit is a relative size, " +
      "not a currency amount.",
  },
  clv: {
    term: "clv",
    label: "CLV",
    definition:
      "Closing Line Value -- whether the price we recorded was better than the " +
      "market's final (closing) line. It is the honest yardstick for prediction " +
      "quality, not a profit figure. Here vs_close is UNPROVEN where no liquid " +
      "closing price exists.",
  },
  calibration: {
    term: "calibration",
    label: "calibration",
    definition:
      "Whether stated probabilities match reality (of events called 70% likely, " +
      "about 70% happen). This product's honest win is CALIBRATION -- it is NOT " +
      "the same as a market edge and implies no profit.",
  },
  edge: {
    term: "edge",
    label: "edge vs calibration",
    definition:
      "An EDGE means beating the efficient market price for profit. We do NOT " +
      "claim one. Matching the devigged close within noise is good CALIBRATION, " +
      "not an edge.",
  },
  brier: {
    term: "brier",
    label: "Brier score",
    definition:
      "Mean squared error of probabilistic forecasts (lower is better; 0 is " +
      "perfect). Measures how sharp AND calibrated the probabilities are.",
  },
  bss: {
    term: "bss",
    label: "BSS",
    definition:
      "Brier Skill Score -- the Brier score relative to a naive baseline " +
      "(higher is better; positive means it beats the baseline). A calibration " +
      "metric, not a dollar metric.",
  },
  devig: {
    term: "devig",
    label: "devig",
    definition:
      "Removing the bookmaker's margin (the vig) from quoted odds to recover the " +
      "market's implied fair probability. The devigged close is the honest " +
      "benchmark we compare our probability against.",
  },
  tier: {
    term: "tier",
    label: "tier",
    definition:
      "A confidence band (S/A/B/C) gating how a pick is treated. tier = null " +
      "means no_bet: the model matches the efficient close, which is a SUCCESS, " +
      "not a failure.",
  },
  inert: {
    term: "inert",
    label: "INERT",
    definition:
      "The self-improve loop is built and READY but human-gated OFF -- it ships " +
      "NOTHING and only measures. INERT means present-but-not-running, never " +
      "'learning' or 'shipping'.",
  },
  vs_close: {
    term: "vs_close",
    label: "vs_close",
    definition:
      "Whether a signal beats the market's closing line. It is UNPROVEN " +
      "everywhere here because no liquid in-play closing price is available. A " +
      "calibration survivor is NOT a vs_close winner.",
  },
  probability: {
    term: "probability",
    label: "probability",
    definition:
      "A model-implied chance between 0 and 1 (shown as a percent). This product " +
      "outputs probabilities and UNITS only -- never a price or payout.",
  },
  provenance: {
    term: "provenance",
    label: "provenance",
    definition:
      "Where a number came from: which model/engine produced it and at which " +
      "phase (e.g. 'Dixon-Coles | pregame'). Provenance lets you trust what each " +
      "value is.",
  },
  uncertainty: {
    term: "uncertainty",
    label: "uncertainty",
    definition:
      "The held-out residual band around a probability -- how much the forecast " +
      "could plausibly move given out-of-sample error. A wider band means less " +
      "certainty, expressed in probability, not dollars.",
  },
};

/** Lookup a glossary entry by term key (case-insensitive). */
export function lookupTerm(term: string): GlossaryEntry | undefined {
  return GLOSSARY[term?.toLowerCase?.()];
}

/** Ordered list of all glossary terms (for a Legend / glossary index). */
export const GLOSSARY_TERMS: GlossaryEntry[] = Object.values(GLOSSARY);
