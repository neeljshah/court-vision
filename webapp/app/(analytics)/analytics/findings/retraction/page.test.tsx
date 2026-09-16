import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
// @ts-expect-error -- the executable scanner is deliberately dependency-free ESM.
import { scanRenderedText } from "../../../../../scripts/check-analytics-copy.mjs";
import { resolveResearchSourceDestination } from "@/lib/analytics/researchSourceDestinations";
import RetractionPage from "./page";
import { RETRACTIONS } from "./retractions";

it("renders dated withdrawal records with evidence links and valid replacement language", () => {
  const { container } = render(<RetractionPage />);
  const articles = screen.getAllByRole("article");

  expect(articles).toHaveLength(RETRACTIONS.length);
  RETRACTIONS.forEach((retraction, index) => {
    const record = within(articles[index]);

    expect(record.getByText(retraction.withdrawnMeasurement)).toBeInTheDocument();
    expect(record.getByText(retraction.status)).toBeInTheDocument();
    expect(record.getByText(retraction.withdrawnOn)).toBeInTheDocument();
    expect(record.getByText(retraction.replacement)).toBeInTheDocument();
    expect(record.getByRole("link", { name: retraction.evidenceArtifact })).toHaveAttribute(
      "href", resolveResearchSourceDestination(retraction.evidenceSourceId).href,
    );
  });

  expect(within(articles[1]).getByText(/Brier score 0\.141 \(unitless\)/)).toBeInTheDocument();
  expect(scanRenderedText(container.textContent || "")).toEqual([]);
});
