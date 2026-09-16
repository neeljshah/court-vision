import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StateReliabilityPage from "./page";

describe("StateReliabilityPage", () => {
  it("renders the state-conditioned inspector headings", () => {
    render(<StateReliabilityPage />);
    expect(screen.getByRole("heading", { name: /inspect reliability across the published game-state grid/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Model source" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Reference source" })).toBeInTheDocument();
  });
});
