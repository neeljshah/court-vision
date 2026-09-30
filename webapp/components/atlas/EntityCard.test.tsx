import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { EntityCard } from "./EntityCard";
import calibrationManifest from "../../public/data/showcase/atlas_calibration_manifest.json";
import pitchManifest from "../../public/data/showcase/atlas_mlb_pitch_manifest.json";

vi.mock("@/components/showcase/ReceiptChip", () => ({
  ReceiptChip: ({ sourceArtifact, asOf }: { sourceArtifact: string; asOf: string | null }) =>
    <button data-source={sourceArtifact} data-as-of={asOf}>Receipt</button>,
}));

function card(keyNumbers: Record<string, unknown>, asOf: string | null, sourceArtifact: string) {
  render(<EntityCard slug="fixture" entity="fixture" label="Atlas fixture" sport="mlb"
    keyNumbers={keyNumbers} floors={null} asOf={asOf}
    pngHref={null} chip={{ sourceArtifact, asOf, verified: "descriptive_only", href: null }} />);
}

function receipt(table: HTMLElement, sourceArtifact: string, asOf: string | null) {
  const section = table.closest("section")!;
  const chips = within(section).getAllByRole("button", { name: "Receipt" });
  expect(chips).toHaveLength(1);
  expect(chips[0]).toHaveAttribute("data-source", sourceArtifact);
  expect(chips[0]).toHaveAttribute("data-as-of", asOf);
}

it("renders every published calibration time bucket with its count, mean and receipt", () => {
  const entry = calibrationManifest.entries.find((item) => item.card_path.endsWith("mlb_band_4_6.png"))!;
  const buckets = entry.key_numbers.by_time_bucket!;
  const source = "webapp/public/data/showcase/atlas_calibration_manifest.json";
  card(entry.key_numbers, entry.as_of, source);
  const table = screen.getByRole("table", { name: "Calibration by time bucket" });
  expect(within(table).getAllByRole("row")).toHaveLength(buckets.length + 1);
  expect(within(table).getByRole("columnheader", { name: "Observed outcome mean" })).toBeInTheDocument();
  for (const bucket of buckets) {
    const row = within(table).getByRole("rowheader", { name: bucket.bucket }).closest("tr")!;
    expect(within(row).getByRole("cell", { name: String(bucket.n) })).toBeInTheDocument();
    expect(within(row).getByRole("cell", { name: String(bucket.mean_y) })).toBeInTheDocument();
  }
  receipt(table, source, entry.as_of);
  expect(screen.queryByText(/\[object Object\]/)).not.toBeInTheDocument();
});

it("renders every published ATH velocity type with mph percentiles and one table receipt", () => {
  const entry = pitchManifest.entries.find((item) => item.entity === "team:ATH")!;
  const velocities = entry.key_numbers.velo_percentiles_by_type! as unknown as Record<string, { n: number; p10: number; p50: number; p90: number }>;
  const source = "webapp/public/data/showcase/atlas_mlb_pitch_manifest.json";
  card(entry.key_numbers, entry.as_of, source);
  const table = screen.getByRole("table", { name: "Velocity percentiles by pitch type" });
  expect(within(table).getAllByRole("row")).toHaveLength(Object.keys(velocities).length + 1);
  for (const heading of ["P10 mph", "P50 mph", "P90 mph"]) {
    expect(within(table).getByRole("columnheader", { name: heading })).toBeInTheDocument();
  }
  for (const [type, values] of Object.entries(velocities)) {
    const row = within(table).getByRole("row", { name: new RegExp(`^${type} `) });
    expect(within(row).getByRole("cell", { name: String(values.n) })).toBeInTheDocument();
    for (const percentile of [values.p10, values.p50, values.p90]) {
      expect(within(row).getByRole("cell", { name: percentile.toFixed(1) })).toBeInTheDocument();
    }
  }
  expect(screen.getByText("strike: 45.3, ball: 37.5, in-play: 17.2")).toBeInTheDocument();
  receipt(table, source, entry.as_of);
  expect(screen.queryByText(/\[object Object\]/)).not.toBeInTheDocument();
});

it("distinguishes true zero from missing nested values", () => {
  card({ by_time_bucket: [{ bucket: "0", n: 0, mean_y: 0 }, { bucket: "missing", n: null, mean_y: null }],
    velo_percentiles_by_type: { ZZ: { n: 0, p10: 0, p50: null, p90: 90.5 } } }, null, "fixture.json");
  const bucketTable = screen.getByRole("table", { name: "Calibration by time bucket" });
  const zero = within(bucketTable).getByRole("row", { name: /^0 / });
  expect(within(zero).getAllByRole("cell", { name: "0" })).toHaveLength(2);
  const missing = within(bucketTable).getByRole("row", { name: /^missing / });
  expect(within(missing).getAllByRole("cell", { name: "Not published" })).toHaveLength(2);
  const velocityTable = screen.getByRole("table", { name: "Velocity percentiles by pitch type" });
  const velocity = within(velocityTable).getByRole("row", { name: /^ZZ / });
  expect(within(velocity).getByRole("cell", { name: "0" })).toBeInTheDocument();
  expect(within(velocity).getByRole("cell", { name: "0.0" })).toBeInTheDocument();
  expect(within(velocity).getByRole("cell", { name: "Not published" })).toBeInTheDocument();
});
