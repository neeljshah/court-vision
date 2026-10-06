// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { ComparisonEntity, ComparisonPack } from "@/lib/analytics/comparisonData";
import { normalizeComparisonPack } from "@/lib/analytics/comparisonData";
import calibrationManifest from "../../../public/data/showcase/atlas_calibration_manifest.json";
import batterManifest from "../../../public/data/showcase/atlas_mlb_batters_manifest.json";
import entityPercentiles from "../../../public/data/showcase/entity_percentiles.json";
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

it("routes calibration cards to raw values without generic ranks or comparable sections", () => {
  const pack = normalizeComparisonPack("calibration", calibrationManifest, {}, {});
  const a = pack.entities.find((entity) => entity.sourceEntity === "mlb inning 1")!;
  const b = pack.entities.find((entity) => entity.sourceEntity === "mlb band 0-.2")!;
  render(<ComparisonResults pack={pack} a={a} b={b} manifest="atlas_calibration_manifest.json" surface="hard" onSurfaceChange={() => undefined} />);
  expect(screen.getByRole("table", { name: "Published calibration values" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Largest measured differences" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Percentile ladder" })).not.toBeInTheDocument();
  expect(screen.queryByText("Closest comparables")).not.toBeInTheDocument();
  expect(screen.queryByText(/Ranked among/)).not.toBeInTheDocument();
  expect(screen.queryByText(/games represented/)).not.toBeInTheDocument();
});

const batterEntries = batterManifest.entries.filter((entry) => ["Aaron Judge", "Brendan Rodgers"].includes(entry.entity));
const batterPack = normalizeComparisonPack("mlb_batters", { entries: batterEntries }, entityPercentiles, {});
const judge = batterPack.entities.find((entity) => entity.slug === "aaron_judge")!;
const rodgers = batterPack.entities.find((entity) => entity.slug === "brendan_rodgers")!;
const batterNote = "Each share is the frequency of that batter's most-seen pitch type; the pitch categories can differ between batters.";

function renderPair(pack: ComparisonPack, first: ComparisonEntity = pack.entities[0], second: ComparisonEntity = pack.entities[1]) {
  return render(<ComparisonResults pack={pack} a={first} b={second} manifest="atlas_mlb_batters_manifest.json" surface="hard" onSurfaceChange={() => undefined} />);
}

it.each([false, true])("pairs published batter pitch categories with their shares when swapped=%s", (swapped) => {
  const pair = swapped ? [rodgers, judge] : [judge, rodgers];
  renderPair(batterPack, pair[0], pair[1]);
  const table = screen.getByRole("table", { name: "Published values and within-pack percentile ranks" });
  const typeRow = within(table).getByRole("row", { name: "Most-seen pitch type " + (swapped ? "SI FF" : "FF SI") });
  const typeCells = within(typeRow).getAllByRole("cell");
  expect(typeCells.map((cell) => cell.textContent)).toEqual(swapped ? ["SI", "FF"] : ["FF", "SI"]);
  expect(within(typeRow).queryByText(/ranked|percentile/i)).not.toBeInTheDocument();
  expect(within(typeRow).queryByRole("img")).not.toBeInTheDocument();
  const shareRow = typeRow.nextElementSibling as HTMLElement;
  expect(within(shareRow).getByRole("rowheader")).toHaveTextContent("top pitch type seen %");
  const shareCells = within(shareRow).getAllByRole("cell");
  for (const [index, cell] of shareCells.entries()) {
    const isJudge = pair[index].slug === "aaron_judge";
    expect(within(cell).getByText(isJudge ? "24.5%" : "24.1%")).toBeInTheDocument();
    expect(within(cell).getByText(isJudge ? "5th percentile" : "4th percentile")).toBeInTheDocument();
    expect(within(cell).getByText("Ranked among 485 profiles")).toBeInTheDocument();
  }
  expect(within(table).getByText("2715")).toBeInTheDocument();
  expect(within(table).getByText("460")).toBeInTheDocument();
  const exitRow = within(table).getByRole("rowheader", { name: /^avg exit velo/ }).closest("tr")!;
  expect(within(exitRow).getByText("100th percentile")).toBeInTheDocument();
  expect(within(exitRow).getByText("43rd percentile")).toBeInTheDocument();
  expect(screen.getAllByText("As of 2025-09-28")).toHaveLength(2);
  expect(screen.getAllByText(/pitches_faced_2025>=300/)).toHaveLength(2);
  expect(screen.getByText(batterNote)).toBeInTheDocument();
});

it.each([undefined, null, 0, false, {}, [], "  "])("shows missing or malformed batter pitch type %j as unreported", (value) => {
  renderPair(batterPack, { ...judge, values: { ...judge.values, top_pitch_type_seen: value } });
  const typeRow = screen.getByRole("rowheader", { name: "Most-seen pitch type" }).closest("tr")!;
  expect(within(typeRow).getAllByRole("cell").map((cell) => cell.textContent)).toEqual(["Not reported", "SI"]);
  expect(within(typeRow.nextElementSibling as HTMLElement).getByText("24.5%")).toBeInTheDocument();
});

it("preserves a published unknown pitch code and zero share without inventing a rank", () => {
  const first = { ...judge, values: { ...judge.values, top_pitch_type_seen: " UNK ", top_pitch_type_seen_pct: 0 }, percentiles: {} };
  const second = { ...rodgers, values: { ...rodgers.values, top_pitch_type_seen: " FF ", top_pitch_type_seen_pct: "24.1" } };
  renderPair(batterPack, first, second);
  const typeRow = screen.getByRole("rowheader", { name: "Most-seen pitch type" }).closest("tr")!;
  expect(within(typeRow).getAllByRole("cell").map((cell) => cell.textContent)).toEqual(["UNK", "FF"]);
  const shareCells = within(typeRow.nextElementSibling as HTMLElement).getAllByRole("cell");
  expect(within(shareCells[0]).getByText("0.0%")).toBeInTheDocument();
  expect(within(shareCells[0]).getByText("Not ranked")).toBeInTheDocument();
  expect(within(shareCells[1]).getByText("Not reported")).toBeInTheDocument();
  expect(within(shareCells[1]).getByText("Not ranked")).toBeInTheDocument();
});

it("keeps batter code and share visible without percentile metadata", () => {
  renderPair(normalizeComparisonPack("mlb_batters", { entries: batterEntries }, {}, {}));
  const typeRow = screen.getByRole("rowheader", { name: "Most-seen pitch type" }).closest("tr")!;
  expect(within(typeRow).getAllByRole("cell").map((cell) => cell.textContent)).toEqual(["FF", "SI"]);
  const shareRow = typeRow.nextElementSibling as HTMLElement;
  expect(within(shareRow).getByText("24.5%")).toBeInTheDocument();
  expect(within(shareRow).getByText("24.1%")).toBeInTheDocument();
  expect(within(shareRow).getAllByText("Not ranked")).toHaveLength(2);
  expect(within(shareRow).queryByText(/percentile|Ranked among/)).not.toBeInTheDocument();
});

it.each([undefined, null, NaN, Infinity])("keeps batter code visible when its share is missing or invalid: %s", (value) => {
  renderPair(batterPack, { ...judge, values: { ...judge.values, top_pitch_type_seen_pct: value } });
  const typeRow = screen.getByRole("rowheader", { name: "Most-seen pitch type" }).closest("tr")!;
  expect(within(typeRow).getByText("FF")).toBeInTheDocument();
  const cell = within(typeRow.nextElementSibling as HTMLElement).getAllByRole("cell")[0];
  expect(within(cell).getByText("Not reported")).toBeInTheDocument();
  expect(within(cell).getByText("Not ranked")).toBeInTheDocument();
});

it("does not duplicate batter code or share rows when metric keys already contain them", () => {
  renderPair({ ...batterPack, metricKeys: ["top_pitch_type_seen", "top_pitch_type_seen_pct", "top_pitch_type_seen_pct"] }, { ...judge, percentiles: {} }, { ...rodgers, percentiles: {} });
  const table = screen.getByRole("table");
  expect(within(table).getAllByRole("rowheader", { name: "Most-seen pitch type" })).toHaveLength(1);
  expect(within(table).getAllByRole("rowheader", { name: "top pitch type seen % %" })).toHaveLength(1);
  expect(within(table).queryByRole("rowheader", { name: "top pitch type seen" })).not.toBeInTheDocument();
});

it.each(["nba_players", "tennis", "soccer", "mlb_pitch"])("limits batter context to the batter pack, excluding %s", (key) => {
  renderPair({ ...batterPack, key }, { ...judge, sourceEntity: "pitch_type:FF" }, { ...rodgers, sourceEntity: "pitch_type:SI" });
  expect(screen.queryByRole("rowheader", { name: "Most-seen pitch type" })).not.toBeInTheDocument();
  expect(screen.queryByText(batterNote)).not.toBeInTheDocument();
});
