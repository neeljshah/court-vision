import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import FindingsIndexPage from "./page";
import { findingsIndex } from "@/lib/analytics/findingsIndex";

it("shows derived finding count and per-card publication metadata", () => {
  render(<FindingsIndexPage />);
  expect(screen.getByText(new RegExp(`^${findingsIndex.length} findings document`))).toBeInTheDocument();
  const first = findingsIndex[0];
  // The as-of is an AsOfBadge (<time>) inside the metadata line; match the line's full text.
  const meta = `as of ${first.asOf || "date not published"} / ${first.sport}`;
  expect(screen.getByText((_, element) => element?.tagName === "P" && element.textContent === meta)).toBeInTheDocument();
  expect(screen.getByText(first.artifactStatus)).toBeInTheDocument();
});
