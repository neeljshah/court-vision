import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { FindingUnavailable } from "./FindingUnavailable";

it("keeps an unavailable finding connected to its index and published source", () => {
  render(<FindingUnavailable artifactId="bookmaker_accuracy" />);
  expect(screen.getByText("Exhibit data not available in this build.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Findings" })).toHaveAttribute("href", "/analytics/findings");
  expect(screen.getByRole("link", { name: "Published source JSON" })).toHaveAttribute("href", "/data/showcase/bookmaker_accuracy.json");
});
