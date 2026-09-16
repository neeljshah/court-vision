import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StateReliabilityPage from "./page";

describe("StateReliabilityPage", () => {
  it("renders the state-conditioned inspector headings", () => {
    render(<StateReliabilityPage />);
    expect(screen.getByRole("heading", { name: /where calibration changes during the game/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Model source" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Reference source" })).toBeInTheDocument();
    expect(screen.getByText("Artifact date: date not published")).toBeInTheDocument();
  });
});
