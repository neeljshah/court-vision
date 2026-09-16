import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ModuleReadingGuide } from "./ModuleReadingGuide";

describe("ModuleReadingGuide", () => {
  it("renders an authored reading guide", () => {
    render(<ModuleReadingGuide howToRead="For each (sport, threshold), decided_frac_of_games is how often that gap ever became permanent and decided_clock_median is the typical clinch time; cells below the game floor are masked." />);
    expect(screen.getByRole("heading", { name: "How to read this figure" })).toBeInTheDocument();
    expect(screen.getByText(/decided_frac_of_games/)).toBeInTheDocument();
    expect(screen.getByText(/decided_clock_median/)).toBeInTheDocument();
  });

  it("is absent without authored guidance", () => {
    render(<ModuleReadingGuide />);
    expect(screen.queryByRole("heading", { name: "How to read this figure" })).not.toBeInTheDocument();
  });
});
