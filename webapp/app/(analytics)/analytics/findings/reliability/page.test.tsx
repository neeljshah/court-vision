import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import ReliabilityPage from "./page";

it("renders the closure finding and links both related inspectors", () => {
  render(<ReliabilityPage />);
  expect(screen.getByRole("heading", { name: /published reliability components need a closure check/i })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "MLB" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "International soccer" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "score decomposition" })).toHaveAttribute("href", "/analytics/score-decomposition");
  expect(screen.getByRole("link", { name: "calibration inspector" })).toHaveAttribute("href", "/analytics/calibration");
});
