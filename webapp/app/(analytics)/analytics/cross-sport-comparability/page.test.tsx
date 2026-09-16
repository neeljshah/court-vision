import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CrossSportComparabilityPage from "./page";

describe("CrossSportComparabilityPage", () => {
  it("renders the published comparability reading view", () => {
    render(<CrossSportComparabilityPage />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Read the published comparability decisions first.");
    expect(screen.getByRole("region", { name: "Cross-sport capability matrix" })).toBeInTheDocument();
    expect(screen.getByTestId("comparability-chart")).toBeInTheDocument();
  });
});
