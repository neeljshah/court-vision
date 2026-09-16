import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import IngameJoinIntegrityPage from "./page";

it("renders the corpus counts and tick-level agreement tables", () => {
  render(<IngameJoinIntegrityPage />);
  expect(screen.getByRole("heading", { name: "MLB in-game calibration needs a segment-clean corpus." })).toBeInTheDocument();
  const counts = screen.getByRole("region", { name: "Corpus integrity counts" });
  expect(within(counts).getByText("78,986 ticks")).toBeInTheDocument();
  expect(within(counts).getByText("2 truncated draws")).toBeInTheDocument();
  const agreement = screen.getByRole("region", { name: "Tick-level label agreement" });
  expect(within(agreement).getByText("0.7284")).toBeInTheDocument();
  expect(within(agreement).getByText("0.9200")).toBeInTheDocument();
  expect(within(agreement).getByText("n = 6,623")).toBeInTheDocument();
});
