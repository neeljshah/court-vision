// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { ComparisonEntity, ComparisonPack } from "@/lib/analytics/comparisonData";
import { ComparisonResults } from "./ComparisonResults";

vi.mock("next/link", () => ({ default: ({ children, ...props }: React.ComponentProps<"a">) => <a {...props}>{children}</a> }));

const a: ComparisonEntity = { slug: "a", name: "Alpha", values: { rate: 0.6 }, percentiles: { rate: 82 } };
const b: ComparisonEntity = { slug: "b", name: "Beta", values: { rate: 0.5 }, percentiles: { rate: 50 } };

it("labels ranked NBA measurements by their corpus observation window", () => {
  const alpha: ComparisonEntity = { ...a, values: { career_games: 50, seasons_played: 1 }, percentiles: { career_games: 80, seasons_played: 25 } };
  const beta: ComparisonEntity = { ...b, values: { career_games: 100, seasons_played: 2 }, percentiles: { career_games: 40, seasons_played: 75 } };
  const pack: ComparisonPack = {
    key: "nba_players", nInPack: 2, metricKeys: ["career_games", "seasons_played"],
    nRankedByMetric: { career_games: 2, seasons_played: 2 }, entities: [alpha, beta],
  };
  render(<ComparisonResults pack={pack} a={alpha} b={beta} manifest="atlas_nba_manifest.json" surface="hard" onSurfaceChange={() => undefined} />);
  const ladder = screen.getByRole("heading", { name: "Percentile ladder" }).closest("section")!;
  expect(within(ladder).getByText("Corpus games")).toBeInTheDocument();
  expect(within(ladder).getByText("Seasons in corpus")).toBeInTheDocument();
  expect(within(ladder).getByText("50")).toBeInTheDocument();
  expect(within(ladder).getByText("100")).toBeInTheDocument();
  expect(within(ladder).getByText("Percentile rank 80 among 2 measured profiles")).toBeInTheDocument();
  expect(within(ladder).queryByText("career games")).not.toBeInTheDocument();
});

it("uses the per-field ranked count instead of the full pack size", () => {
  const pack: ComparisonPack = {
    key: "tennis", nInPack: 278, metricKeys: ["rate"], nRankedByMetric: { rate: 69 }, entities: [a, b],
  };
  render(<ComparisonResults pack={pack} a={a} b={b} manifest="atlas_tennis_manifest.json" surface="hard" onSurfaceChange={() => undefined} />);
  expect(screen.getAllByText("Percentile rank 82 among 69 measured profiles").length).toBeGreaterThan(0);
  expect(screen.queryByText(/among 278 measured profiles/)).not.toBeInTheDocument();
});

it("renders the published comparable method and most distant profiles", () => {
  const pack: ComparisonPack = {
    key: "tennis", nInPack: 278, metricKeys: ["rate"], entities: [a, b],
    comparableContext: { method: "Euclidean distance on standardized measurements.", fieldsUsed: ["rate"], droppedZeroVariance: [] },
    antipodeByEntity: { a: { slug: "zeta", name: "Zeta", score: 4.2 }, b: { slug: "eta", name: "Eta", score: 3.8 } },
  };
  render(<ComparisonResults pack={pack} a={a} b={b} manifest="atlas_tennis_manifest.json" surface="hard" onSurfaceChange={() => undefined} />);
  expect(screen.getByRole("heading", { name: "How similarity is measured" })).toBeInTheDocument();
  expect(screen.getAllByText("Most distant profile")).toHaveLength(2);
  expect(screen.getByRole("link", { name: "Zeta" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Largest measured differences" })).toBeInTheDocument();
});

it("uses plain language when profiles do not share a measurement", () => {
  const pack: ComparisonPack = {
    key: "nba_players", nInPack: 2, metricKeys: ["unshared"], entities: [a, b],
  };
  render(<ComparisonResults pack={pack} a={a} b={b} manifest="atlas_nba_manifest.json" surface="hard" onSurfaceChange={() => undefined} />);
  expect(screen.getByText("These profiles have no numerical measurements in common.")).toBeInTheDocument();
});
