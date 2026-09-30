import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { EntityMeasurements } from "./EntityMeasurements";
import { entityMeasurements } from "@/lib/analytics/entityMeasurements";
import pitchManifest from "../../../public/data/showcase/atlas_mlb_pitch_manifest.json";

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

it.each([
  ["pitch_type:CU", "0.04%"],
  ["pitch_type:KC", "0.03%"],
])("preserves the published small 3-0 share for %s in the table and tooltip", (entity, share) => {
  const entry = pitchManifest.entries.find((item) => item.entity === entity)!;
  render(<EntityMeasurements measurements={entityMeasurements("mlb_pitch", entry, entity)} sourceArtifact={props.sourceArtifact} />);
  const section = screen.getByRole("table", { name: "Pitch share by count state distribution" }).closest("section")!;
  const row = within(section).getByRole("row", { name: /3-0/ });
  expect(within(row).getByRole("cell", { name: share })).toBeInTheDocument();
  expect(within(section).getByTitle(`3-0: ${share}`)).toBeInTheDocument();
});

it("keeps a true zero and ordinary one-decimal shares unchanged", () => {
  const measurements = { ...props.measurements, distributions: [{
    key: "count_state_pct", label: "Pitch share by count state", rows: [{ key: "3-0", share: 0 }, { key: "0-0", share: 40.7 }],
  }] };
  render(<EntityMeasurements measurements={measurements} sourceArtifact={props.sourceArtifact} />);
  const section = screen.getByRole("table", { name: "Pitch share by count state distribution" }).closest("section")!;
  expect(within(within(section).getByRole("row", { name: /3-0/ })).getByRole("cell", { name: "0.0%" })).toBeInTheDocument();
  expect(within(section).getByTitle("3-0: 0.0%")).toBeInTheDocument();
  expect(within(within(section).getByRole("row", { name: /0-0/ })).getByRole("cell", { name: "40.7%" })).toBeInTheDocument();
  expect(within(section).getByTitle("0-0: 40.7%")).toBeInTheDocument();
});

it("names all three published CH distributions and gives each a local source receipt", () => {
  const entry = pitchManifest.entries.find((item) => item.entity === "pitch_type:CH")!;
  const sourceArtifact = "webapp/public/data/showcase/atlas_mlb_pitch_manifest.json";
  render(<EntityMeasurements measurements={entityMeasurements("mlb_pitch", entry, "ch")} sourceArtifact={sourceArtifact} asOf={entry.as_of} />);
  for (const label of ["Pitch share by count leverage", "Pitch share by count state", "Pitch outcome mix"]) {
    const table = screen.getByRole("table", { name: `${label} distribution` });
    const section = table.closest("section")!;
    const receipt = within(section).getByRole("button", { name: new RegExp(`Receipt: ${label} distribution`) });
    fireEvent.click(receipt);
    expect(section).toHaveTextContent(sourceArtifact);
    expect(section).toHaveTextContent("2025-09-28");
  }
  expect(screen.getAllByRole("table")).toHaveLength(3);
});

it("names velocity and calibration bucket tables and keeps their receipts scoped", () => {
  const sourceArtifact = "webapp/public/data/showcase/atlas_calibration_manifest.json";
  const measurements = { ...props.measurements, tables: [
    props.measurements.tables[0],
    { key: "by_time_bucket" as const, label: "Calibration by time bucket", rows: [{ bucket: "5", n: 3, meanY: 0.25 }] },
  ] };
  render(<EntityMeasurements measurements={measurements} sourceArtifact={sourceArtifact} asOf="2026-09-16" />);
  for (const label of ["velocity percentiles by pitch type", "Calibration by time bucket"]) {
    const table = screen.getByRole("table", { name: label });
    const section = table.closest("section")!;
    const receipt = within(section).getByRole("button", { name: new RegExp(`Receipt: ${label} table`) });
    fireEvent.click(receipt);
    expect(section).toHaveTextContent(sourceArtifact);
    expect(section).toHaveTextContent("2026-09-16");
  }
  expect(screen.getByRole("cell", { name: "3" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "0.2500" })).toBeInTheDocument();
});

it("keeps the published-date fallback when a section has no as-of value", () => {
  render(<EntityMeasurements {...props} />);
  const section = screen.getByRole("table", { name: "velocity percentiles by pitch type" }).closest("section")!;
  fireEvent.click(within(section).getByRole("button", { name: /Receipt: velocity percentiles by pitch type table/ }));
  expect(section).toHaveTextContent("Date not published.");
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
