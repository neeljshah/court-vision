// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ComparisonPack } from "@/lib/analytics/comparisonData";
import { ComparableContext } from "./ComparableContext";

const nbaPack: ComparisonPack = {
  key: "nba_players", nInPack: 482, metricKeys: [], entities: [],
  comparableContext: {
    method: "Cosine similarity on z-scored key_numbers.",
    fieldsUsed: ["career_games", "career_minutes", "seasons_played"],
    droppedZeroVariance: [],
  },
};

describe("ComparableContext", () => {
  it("renders the published fields used and population", () => {
    render(<ComparableContext pack={nbaPack} />);
    expect(screen.getByText("Corpus games")).toBeInTheDocument();
    expect(screen.getByText("Corpus minutes")).toBeInTheDocument();
    expect(screen.getByText("482 profiles.")).toBeInTheDocument();
  });

  it("renders the published tennis skipped-pack reason", () => {
    const tennisPack: ComparisonPack = { key: "tennis", nInPack: 278, metricKeys: [], entities: [], comparableContext: { fieldsUsed: [], droppedZeroVariance: [], skipped: { reason: "too few common fields", nCommonFields: 0 } } };
    render(<ComparableContext pack={tennisPack} />);
    expect(screen.getByText("tennis: 0 common fields, no comparables published.")).toBeInTheDocument();
    expect(screen.getByText("Published reason: too few common fields.")).toBeInTheDocument();
  });

  it("states that a score is neither a probability nor a quality rating", () => {
    render(<ComparableContext pack={nbaPack} />);
    expect(screen.getByText(/not a probability or a quality rating/i)).toBeInTheDocument();
  });
});
