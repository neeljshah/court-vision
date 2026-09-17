import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import FindingsIndexPage from "./page";
import { findingsIndex } from "@/lib/analytics/findingsIndex";

it("shows derived finding count and per-card publication metadata", () => {
  render(<FindingsIndexPage />);
  expect(screen.getByText(new RegExp(`^${findingsIndex.length} findings document`))).toBeInTheDocument();
  const first = findingsIndex[0];
  expect(screen.getByText(`as of ${first.asOf || "date not published"} / ${first.sport}`)).toBeInTheDocument();
  expect(screen.getByText(first.artifactStatus)).toBeInTheDocument();
});
