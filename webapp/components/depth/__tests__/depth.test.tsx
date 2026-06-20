import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { InfoTip } from "../InfoTip";
import { Legend } from "../Legend";
import { ProvenanceBadge } from "../ProvenanceBadge";
import { SignalVerdictBadge } from "../SignalVerdictBadge";
import { UncertaintyBar } from "../UncertaintyBar";
import { MarketSurfaceTable } from "../MarketSurfaceTable";
import { GLOSSARY, GLOSSARY_TERMS, lookupTerm } from "../glossary";

// ---------------------------------------------------------------------------
// DEPTH primitives honesty-rail tests:
//   * the glossary defines every required term and never implies a $ edge
//   * InfoTip renders a glossary definition + an accessible trigger
//   * ProvenanceBadge shows "model | phase"
//   * SignalVerdictBadge: SHIP carries "calibration-only, vs_close UNPROVEN"
//   * UncertaintyBar renders prob + band, honest "--" on missing prob
//   * MarketSurfaceTable renders the surface and has NO $ header
//   * no depth source file emits a $/pnl/roi/payout field
// ---------------------------------------------------------------------------

const REQUIRED_TERMS = [
  "units",
  "clv",
  "calibration",
  "brier",
  "bss",
  "devig",
  "tier",
  "inert",
  "vs_close",
];

describe("GLOSSARY -- required terms + honest framing", () => {
  it("defines every required term", () => {
    for (const t of REQUIRED_TERMS) {
      expect(GLOSSARY[t], `missing glossary term: ${t}`).toBeTruthy();
      expect(GLOSSARY[t].definition.length).toBeGreaterThan(20);
    }
  });

  it("lookupTerm is case-insensitive and GLOSSARY_TERMS is complete", () => {
    expect(lookupTerm("CLV")?.term).toBe("clv");
    expect(GLOSSARY_TERMS.length).toBe(Object.keys(GLOSSARY).length);
  });

  it("never implies a dollar profit edge", () => {
    const blob = GLOSSARY_TERMS.map((e) => e.definition).join(" ");
    expect(/\$\d/.test(blob)).toBe(false);
    // calibration is explicitly NOT a market edge
    expect(GLOSSARY.calibration.definition).toMatch(/not.*edge/i);
    expect(GLOSSARY.vs_close.definition).toMatch(/UNPROVEN/);
  });
});

describe("InfoTip -- accessible explanatory affordance", () => {
  it("exposes an accessible trigger for a glossary term", () => {
    render(<InfoTip term="clv" />);
    expect(screen.getByRole("button", { name: /what is CLV/i })).toBeTruthy();
  });

  it("falls back without fabricating a definition", () => {
    render(<InfoTip term="not_a_real_term" />);
    expect(
      screen.getByRole("button", { name: /what is not_a_real_term/i })
    ).toBeTruthy();
  });
});

describe("Legend -- key of terms / swatches", () => {
  it("renders term labels from the glossary", () => {
    render(<Legend terms={["clv", "tier"]} />);
    expect(screen.getByText("CLV")).toBeTruthy();
    expect(screen.getByText("tier")).toBeTruthy();
  });

  it("renders nothing when empty", () => {
    const { container } = render(<Legend />);
    expect(container.firstChild).toBeNull();
  });
});

describe("ProvenanceBadge -- model | phase", () => {
  it("joins model and phase", () => {
    render(<ProvenanceBadge model="Dixon-Coles" phase="pregame" />);
    expect(screen.getByText("Dixon-Coles | pregame")).toBeTruthy();
  });

  it("joins a backend provenance trail", () => {
    render(<ProvenanceBadge trail={["MOV-Elo", "in-game"]} showTip={false} />);
    expect(screen.getByText("MOV-Elo | in-game")).toBeTruthy();
  });
});

describe("SignalVerdictBadge -- honest verdict framing", () => {
  it("SHIP shows calibration-only, vs_close UNPROVEN", () => {
    render(<SignalVerdictBadge verdict="SHIP" stat="clustered-DM p ~= 0.0015" />);
    expect(screen.getByText("SHIP")).toBeTruthy();
    expect(
      screen.getByText(/calibration-only, vs_close UNPROVEN/)
    ).toBeTruthy();
  });

  it("renders REJECT / INSUFFICIENT_DATA / TIER3_BLOCKED labels", () => {
    render(<SignalVerdictBadge verdict="REJECT" />);
    expect(screen.getByText("REJECT")).toBeTruthy();
    render(<SignalVerdictBadge verdict="INSUFFICIENT_DATA" />);
    expect(screen.getByText("INSUFFICIENT DATA")).toBeTruthy();
    render(<SignalVerdictBadge verdict="TIER3_BLOCKED" />);
    expect(screen.getByText("TIER-3 BLOCKED")).toBeTruthy();
  });
});

describe("UncertaintyBar -- probability + band", () => {
  it("renders the point probability and the band", () => {
    render(<UncertaintyBar prob={0.62} low={0.55} high={0.69} label="P(home win)" />);
    expect(screen.getByText("62.0%")).toBeTruthy();
    expect(screen.getByText(/\[55\.0%, 69\.0%\]/)).toBeTruthy();
    expect(screen.getByRole("meter")).toBeTruthy();
  });

  it("renders an honest empty state for a missing probability", () => {
    render(<UncertaintyBar prob={null} label="P(home win)" />);
    expect(screen.getByText("--")).toBeTruthy();
    expect(screen.queryByRole("meter")).toBeNull();
  });
});

describe("MarketSurfaceTable -- coherent surface, no $", () => {
  const markets = [
    { market_type: "moneyline", side: "home", line: null, devigged_prob: 0.58 },
    { market_type: "total", side: "over", line: 220.5, devigged_prob: 0.51 },
  ];

  it("renders each market row with model prob and provenance", () => {
    render(<MarketSurfaceTable markets={markets} model="possession MC" />);
    expect(screen.getByText("moneyline")).toBeTruthy();
    expect(screen.getByText("58.0%")).toBeTruthy();
    expect(screen.getByText("220.5")).toBeTruthy();
    expect(screen.getAllByText("possession MC | pregame").length).toBe(2);
  });

  it("has NO price/$ column header", () => {
    render(<MarketSurfaceTable markets={markets} />);
    const headers = screen
      .getAllByRole("columnheader")
      .map((h) => h.textContent ?? "");
    for (const h of headers) {
      expect(/price|odds|payout|\$/i.test(h), `banned header: ${h}`).toBe(false);
    }
    expect(headers.some((h) => /model prob/i.test(h))).toBe(true);
  });

  it("renders an honest empty state for no markets", () => {
    render(<MarketSurfaceTable markets={[]} />);
    expect(screen.getByText(/No market surface available/i)).toBeTruthy();
  });
});

describe("NO $ field across depth sources", () => {
  it("no depth source emits a $/pnl/roi/payout field", () => {
    const dir = dirname(fileURLToPath(import.meta.url));
    const root = join(dir, "..");
    const files = readdirSync(root).filter(
      (f) => f.endsWith(".ts") || f.endsWith(".tsx")
    );
    // A real $ AMOUNT ($ next to a digit) or a money FIELD identifier is banned.
    // The honest prose "never dollars / no $ field" is allowed (it asserts the rail).
    const banned = /\$\s*\d|\d\s*\$|\bpnl\b|\b(pnl|roi|payout)\s*[:=]/i;
    for (const f of files) {
      const code = readFileSync(join(root, f), "utf8");
      expect(banned.test(code), `banned $ token in ${f}`).toBe(false);
    }
  });
});
