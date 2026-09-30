// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import manifest from "../../../public/data/showcase/atlas_calibration_manifest.json";
import { normalizeComparisonPack } from "@/lib/analytics/comparisonData";
import { CalibrationComparison } from "./CalibrationComparison";

vi.mock("next/link", () => ({ default: ({ children, ...props }: React.ComponentProps<"a">) => <a {...props}>{children}</a> }));

const pack = normalizeComparisonPack("calibration", manifest, {}, {});
const card = (name: string) => {
  const entity = pack.entities.find((item) => item.sourceEntity === name);
  if (!entity) throw new Error(`Fixture missing ${name}`);
  return entity;
};
const sourceHref = "/data/showcase/atlas_calibration_manifest.json";

it("preserves reported checkpoint ECE values and row counts on their published scale", () => {
  render(<CalibrationComparison a={card("mlb inning 1")} b={card("mlb inning 2")} sourceHref={sourceHref} />);
  const table = screen.getByRole("table", { name: "Published calibration values" });
  expect(within(table).getByRole("row", { name: /Rows in card \(n\) 3,589 2,803/ })).toBeInTheDocument();
  expect(within(table).getByRole("row", { name: /Model ECE \(0-1 scale\) 0\.0768 0\.0460/ })).toBeInTheDocument();
  expect(within(table).getByRole("row", { name: /Market ECE \(0-1 scale\) 0\.0716 0\.0527/ })).toBeInTheDocument();
  expect(within(table).queryByRole("rowheader", { name: /Time buckets with data/ })).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "mlb inning 1" })).toHaveAttribute("href", `/analytics/players/calibration/${card("mlb inning 1").slug}`);
  expect(screen.getByRole("link", { name: /raw calibration manifest/ })).toHaveAttribute("href", sourceHref);
  expect(screen.getAllByText(/Source snapshot:/)).toHaveLength(2);
});

it("shows missing checkpoint and band fields separately, including the actual bucket rows", () => {
  render(<CalibrationComparison a={card("mlb inning 1")} b={card("mlb band 0-.2")} sourceHref={sourceHref} />);
  const table = screen.getByRole("table", { name: "Published calibration values" });
  expect(within(table).getByRole("row", { name: /Model ECE \(0-1 scale\) 0\.0768 Not reported/ })).toBeInTheDocument();
  expect(within(table).getByRole("row", { name: /Overall mean outcome \(0-1 scale\) Not reported 0\.0549/ })).toBeInTheDocument();
  expect(within(table).getByRole("row", { name: /Band reference probability \(0-1 scale\) Not reported 0\.1000/ })).toBeInTheDocument();
  expect(within(table).getByRole("row", { name: /Time buckets with data \(count\) Not reported 7/ })).toBeInTheDocument();
  expect(within(table).getByRole("row", { name: /Rows in card \(n\) 3,589 3,972/ })).toBeInTheDocument();
  const buckets = screen.getByRole("table", { name: "mlb band 0-.2: published time-bucket rows" });
  expect(within(buckets).getByRole("row", { name: /^4 3 0\.0000$/ })).toBeInTheDocument();
  expect(within(buckets).getByRole("row", { name: /^10\+ 26 0\.2692$/ })).toBeInTheDocument();
  expect(screen.queryByRole("table", { name: "mlb inning 1: published time-bucket rows" })).not.toBeInTheDocument();
  expect(screen.getByText(/Bucket row counts and means are separate from the card row count/)).toBeInTheDocument();
  expect(screen.getAllByText(/n>=30 rows required/)).toHaveLength(2);
});

it("keeps zero and a textual band reference distinct from unreported values", () => {
  const band = card("mlb band 0-.2");
  render(<CalibrationComparison a={card("mlb inning 1")} b={{ ...band, values: { ...band.values, band_reference: "source band", n_time_buckets_with_data: 0, mean_y_overall: NaN } }} sourceHref={sourceHref} />);
  const table = screen.getByRole("table", { name: "Published calibration values" });
  expect(within(table).getByRole("row", { name: /Band reference probability \(0-1 scale\) Not reported source band/ })).toBeInTheDocument();
  expect(within(table).getByRole("row", { name: /Time buckets with data \(count\) Not reported 0/ })).toBeInTheDocument();
  expect(within(table).getByRole("row", { name: /Overall mean outcome \(0-1 scale\) Not reported Not reported/ })).toBeInTheDocument();
});
