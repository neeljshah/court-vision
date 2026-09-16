import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import anatomy from "@/public/data/showcase/verdict_flip_anatomy.json";
import { claimFamilyId } from "@/lib/analytics/claimHistory";
import { VerdictFlipCases, type VerdictFlipCase } from "./VerdictFlipCases";

const flips = anatomy.flips as VerdictFlipCase[];

describe("VerdictFlipCases", () => {
  it("links every published case to its ledger family and cites both artifacts", () => {
    render(<VerdictFlipCases flips={flips} generatedAt={anatomy.generated_at} upstreamArtifact={anatomy.source_artifact} undatedRunCount={142} />);

    const cases = screen.getAllByRole("article");
    expect(cases).toHaveLength(5);
    flips.forEach((flip, index) => {
      const card = within(cases[index]);
      expect(card.getByRole("link", { name: "View full ledger history" })).toHaveAttribute(
        "href", `/analytics/the-loop#${claimFamilyId(flip)}`,
      );
      expect(card.getByLabelText(/Receipt: case anatomy artifact/i)).toBeInTheDocument();
      expect(card.getByLabelText(/Receipt: upstream scoreboard/i)).toBeInTheDocument();
    });
  });

  it("publishes null effects and source-order dating limits", () => {
    render(<VerdictFlipCases flips={flips} upstreamArtifact={anatomy.source_artifact} undatedRunCount={142} />);
    expect(screen.getByText("Steps are shown in source order; 142 runs have no recorded date.")).toBeInTheDocument();
    expect(screen.getAllByText("effect not published")).toHaveLength(2);
  });
});
