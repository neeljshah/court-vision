// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { ComparisonEntity, ComparisonPack } from "@/lib/analytics/comparisonData";
import { ComparisonResults } from "./ComparisonResults";

vi.mock("next/link", () => ({ default: ({ children, ...props }: React.ComponentProps<"a">) => <a {...props}>{children}</a> }));

const a: ComparisonEntity = { slug: "a", name: "Alpha", values: { rate: 0.6 }, percentiles: { rate: 82 } };
const b: ComparisonEntity = { slug: "b", name: "Beta", values: { rate: 0.5 }, percentiles: { rate: 50 } };

it("uses the per-field ranked count instead of the full pack size", () => {
  const pack: ComparisonPack = {
    key: "tennis", nInPack: 278, metricKeys: ["rate"], nRankedByMetric: { rate: 69 }, entities: [a, b],
  };
  render(<ComparisonResults pack={pack} a={a} b={b} manifest="atlas_tennis_manifest.json" surface="hard" onSurfaceChange={() => undefined} />);
  expect(screen.getAllByText("Percentile rank 82 among 69 measured profiles").length).toBeGreaterThan(0);
  expect(screen.queryByText(/among 278 measured profiles/)).not.toBeInTheDocument();
});
