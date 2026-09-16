import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
// @ts-expect-error -- the executable scanner is deliberately dependency-free ESM.
import { scanRenderedText } from "../../../../../scripts/check-analytics-copy.mjs";
import RetractionPage from "./page";
import { RETRACTIONS, validateRetractionCitations } from "./retractions";

it("renders dated withdrawal records with evidence citations and related reading", () => {
  const { container } = render(<RetractionPage />);
  const articles = screen.getAllByRole("article");

  expect(articles).toHaveLength(RETRACTIONS.length);
  RETRACTIONS.forEach((retraction, index) => {
    const record = within(articles[index]);

    expect(record.getByText(retraction.withdrawnMeasurement)).toBeInTheDocument();
    expect(record.getByText(retraction.status)).toBeInTheDocument();
    expect(record.getByText(retraction.editorialDate)).toBeInTheDocument();
    expect(record.getByText(retraction.replacement)).toBeInTheDocument();
    expect(record.getByText("Evidence citation")).toBeInTheDocument();
    expect(record.getAllByText((_, element) => element?.tagName === "P" && (element.textContent || "").includes(retraction.citation.document)).length).toBeGreaterThan(0);
    expect(record.getByText(`Section: ${retraction.citation.section}`)).toBeInTheDocument();
    expect(record.getByText(`Editorial date: ${retraction.citation.date} | Sport: ${retraction.citation.sportsCovered.join(", ")}`)).toBeInTheDocument();
    expect(record.getByText(`Measures: ${retraction.citation.measurementIdentity}`)).toBeInTheDocument();
    expect(record.getByText("No published evidence document.")).toBeInTheDocument();
    expect(record.getByText("Related reading")).toBeInTheDocument();
    retraction.relatedReading.forEach((reading) => {
      expect(record.getByRole("link", { name: reading.label })).toBeInTheDocument();
    });
  });

  expect(scanRenderedText(container.textContent || "")).toEqual([]);
});

it("separates the withdrawal event date from the editorial date of the record", () => {
  render(<RetractionPage />);
  const articles = screen.getAllByRole("article");

  RETRACTIONS.forEach((retraction, index) => {
    const record = within(articles[index]);
    expect(record.getByText("Withdrawal date")).toBeInTheDocument();
    expect(record.getByText("Editorial date of the record")).toBeInTheDocument();
    expect(record.getByText(retraction.eventDate || "date not recorded")).toBeInTheDocument();
    expect(record.getByText(retraction.editorialDate)).toBeInTheDocument();
  });

  // Only the assists withdrawal carries a date the packet states for the event itself.
  const withEvent = RETRACTIONS.filter((entry) => entry.eventDate !== null);
  expect(withEvent.map((entry) => entry.id)).toEqual(["assists-playoffs"]);
  expect(withEvent[0].eventDate).toBe("2026-07-21");
  expect(withEvent[0].editorialDate).toBe("2026-07-23");

  const withoutEvent = RETRACTIONS.filter((entry) => entry.eventDate === null);
  expect(withoutEvent).toHaveLength(RETRACTIONS.length - 1);
  withoutEvent.forEach((entry) => expect(entry.editorialDate).toBe("2026-07-23"));
  expect(screen.getAllByText("date not recorded")).toHaveLength(withoutEvent.length);
});

it("states the replacement Brier as an approximation, never as an exact figure", () => {
  const { container } = render(<RetractionPage />);
  const text = container.textContent || "";
  const replacement = RETRACTIONS.find((entry) => entry.id === "end-of-third-quarter-brier")?.replacement || "";

  expect(replacement).toContain("approximately 0.141");
  expect(replacement).not.toMatch(/(?<!approximately )0\.141/);
  expect(text).toContain("approximately 0.141");
  expect(text.match(/0\.141/g)).toHaveLength(1);
});

it("keeps citations dated and scoped to the withdrawn NBA measurement", () => {
  validateRetractionCitations(RETRACTIONS);

  RETRACTIONS.forEach((retraction) => {
    expect(retraction.citation.sportsCovered).toContain(retraction.sport);
    expect(retraction.citation.document).toBeTruthy();
    expect(retraction.citation.section).toBeTruthy();
    expect(retraction.citation.date).toBeTruthy();
    expect(retraction.citation.measurementIdentity).toBeTruthy();
  });

  expect(RETRACTIONS.find((entry) => entry.id === "end-of-third-quarter-brier")?.citation.document)
    .not.toBe("state_conditioned_calibration.json");
  expect(() => validateRetractionCitations([{ ...RETRACTIONS[0], citation: {
    ...RETRACTIONS[0].citation, sportsCovered: ["MLB"],
  } }])).toThrow(/does not cover NBA/);

  // A citation that predates the withdrawal event without recording it is still rejected.
  const assists = RETRACTIONS.find((entry) => entry.id === "assists-playoffs")!;
  expect(() => validateRetractionCitations([{ ...assists, citation: {
    ...assists.citation, date: "2026-07-01", recordsWithdrawal: false,
  } }])).toThrow(/predates withdrawal/);
});

it("keeps retracted values only inside withdrawn sentences", () => {
  const { container } = render(<RetractionPage />);
  const text = container.textContent || "";
  const retractedValues = ["18.38", "0.119", "54.57", "78.11", "8.94", "0.79", "0.06"];

  retractedValues.forEach((value) => {
    expect(RETRACTIONS.some((retraction) => retraction.withdrawnMeasurement.includes(value))).toBe(true);
    expect(text.match(new RegExp(value.replace(".", "\\."), "g"))).toHaveLength(1);
  });
});
