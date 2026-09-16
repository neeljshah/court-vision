import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { EntityMeasurements } from "./EntityMeasurements";
import { entityMeasurements } from "@/lib/analytics/entityMeasurements";

const props = { sourceArtifact: "webapp/public/data/showcase/atlas_mlb_pitch_manifest.json", measurements: {
  scalars: [{ key: "n_pitches", label: "n pitches", value: "71,270", percentile: 82, nRanked: 69 }],
  distributions: [{ key: "outcome_mix_pct", label: "outcome mix %", rows: [{ key: "ball", share: 40.7 }, { key: "strike", share: 40.1 }, { key: "in-play", share: 19.2 }] }],
  tables: [{ key: "velo_percentiles_by_type" as const, label: "velocity percentiles by pitch type", rows: [{ type: "FF", n: 8366, p10: 90.6, p50: 93.8, p90: 97.9 }] }],
  unavailable: [{ key: "velo_p10", label: "velo p10", floor: "velo: sample floor" }],
  notApplicable: [{ key: "balls", label: "balls in count" }],
  cohort: "MLB pitching teams",
} };

it("renders every published distribution row", () => {
  render(<EntityMeasurements {...props} />);
  expect(screen.getByText("ball")).toBeInTheDocument();
  expect(screen.getByText("40.7%")).toBeInTheDocument();
  expect(screen.getByLabelText("outcome mix % distribution")).toBeInTheDocument();
  expect(screen.getByLabelText("outcome mix % distribution")).toHaveAttribute("role", "img");
  expect(document.querySelectorAll("dl > div > dt")).toHaveLength(1);
});

it("distinguishes unpublished and inapplicable measurements", () => {
  render(<EntityMeasurements {...props} />);
  expect(screen.getByText((_, el) => el?.tagName === "P" && /1 of 4 expected measurements not published: velo p10/.test(el.textContent || ""))).toBeInTheDocument();
  expect(screen.getByText(/balls in count not applicable to MLB pitching teams/)).toBeInTheDocument();
});

it("renders the velocity table with its published sample count", () => {
  render(<EntityMeasurements {...props} />);
  expect(screen.getByRole("columnheader", { name: "P50 mph" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "8366" })).toBeInTheDocument();
});

it("does not render an absent Scout-note apology", () => {
  render(<EntityMeasurements {...props} />);
  expect(screen.queryByText(/No written Scout note/)).not.toBeInTheDocument();
});

it("renders the published pitch share without percentage inference", () => {
  const measurements = entityMeasurements("mlb_pitch", { key_numbers: { pct_of_all_pitches: 0.06 } }, "cs");
  render(<EntityMeasurements sourceArtifact="atlas_mlb_pitch_manifest" measurements={measurements} />);
  expect(screen.getAllByText("0.06%").length).toBeGreaterThanOrEqual(1);
  expect(screen.queryByText("6.0%")).not.toBeInTheDocument();
});
