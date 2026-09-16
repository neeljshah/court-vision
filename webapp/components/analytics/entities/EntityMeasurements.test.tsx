import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { EntityMeasurements } from "./EntityMeasurements";

const props = { sourceArtifact: "webapp/public/data/showcase/atlas_mlb_pitch_manifest.json", measurements: {
  scalars: [{ key: "n_pitches", label: "n pitches", value: "71,270", percentile: 82, nRanked: 69 }],
  distributions: [{ key: "outcome_mix_pct", label: "outcome mix %", rows: [{ key: "ball", share: 40.7 }, { key: "strike", share: 40.1 }, { key: "in-play", share: 19.2 }] }],
  unavailable: [{ key: "velo_p10", label: "velo p10", floor: "velo: sample floor" }],
} };

it("renders every published distribution row", () => {
  render(<EntityMeasurements {...props} />);
  expect(screen.getByText("ball")).toBeInTheDocument();
  expect(screen.getByText("40.7%")).toBeInTheDocument();
  expect(screen.getByLabelText("outcome mix % distribution")).toBeInTheDocument();
  expect(screen.getByLabelText("outcome mix % distribution")).toHaveAttribute("role", "img");
  expect(document.querySelectorAll("dl > div > dt")).toHaveLength(1);
});

it("states unavailable measurement coverage in one line", () => {
  render(<EntityMeasurements {...props} />);
  expect(screen.getByText((_, el) => el?.tagName === "P" && /1 of 3 expected measurements unavailable: velo p10/.test(el.textContent || ""))).toBeInTheDocument();
});

it("does not render an absent Scout-note apology", () => {
  render(<EntityMeasurements {...props} />);
  expect(screen.queryByText(/No written Scout note/)).not.toBeInTheDocument();
});
