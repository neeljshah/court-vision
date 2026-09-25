import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import lcf from "@/public/data/showcase/novel_live_clock_fraction.json";
import mfp from "@/public/data/showcase/novel_market_foresight_premium.json";
import { generateMetadata, type Mod, type Out } from "@/app/(analytics)/analytics/m/[id]/page";
import { ModuleDetail } from "./ModuleDetail";
import { getLabData } from "@/lib/analytics/labData";
import { readLabViewState } from "../lab/labViewState";

const lcfId = "novel_live_clock_fraction";
const mfpId = "novel_market_foresight_premium";
function show(id: string, out: Out) {
  const mod: Mod = { id, title: "Old module title", one_line: "Unsupported sport ranking", out_path: `${id}.json`, chart_path: `${id}.png`, status: "published", as_of: "2026-07-24" };
  return render(<ModuleDetail mod={mod} out={out} insight={null} subtitle="Unsupported sport ranking" />);
}

describe("timing module evidence", () => {
  it("replaces the LCF headline and empty receipts with source-backed populations", () => {
    show(lcfId, lcf);
    expect(screen.getByRole("heading", { level: 1, name: "Live-Clock Fraction" })).toBeInTheDocument();
    expect(screen.queryByText("Unsupported sport ranking")).not.toBeInTheDocument();
    expect(screen.queryByText("n not published")).not.toBeInTheDocument();
    expect(screen.queryByText("No cited measurements are published for this module.")).not.toBeInTheDocument();
    const mlb = screen.getByRole("table", { name: "MLB published timing measurements" });
    const soccer = screen.getByRole("table", { name: "International soccer published timing measurements" });
    for (const value of ["0.7368", "97", "174", "0.5575"]) expect(within(mlb).getByText(value)).toBeInTheDocument();
    for (const value of ["0.5994", "12", "26", "0.4615"]) expect(within(soccer).getByText(value)).toBeInTheDocument();
    expect(mlb).toHaveTextContent("inning");
    expect(soccer).toHaveTextContent("minute");
    expect(screen.getByLabelText("Timing measurement receipts")).toHaveTextContent("174");
    expect(screen.getByLabelText("Timing measurement evidence")).toHaveTextContent("observation window is not published");
    expect(screen.getByText("Published date 2026-09-17", { selector: "figcaption span" })).toBeInTheDocument();
  });

  it("publishes every MFP checkpoint with its own observation count and reference fields", () => {
    show(mfpId, mfp);
    const mlb = screen.getByRole("table", { name: "MLB published timing measurements" });
    const soccer = screen.getByRole("table", { name: "International soccer published timing measurements" });
    expect(within(mlb).getAllByRole("row")).toHaveLength(11);
    expect(within(soccer).getAllByRole("row")).toHaveLength(20);
    for (const [table, source] of [[mlb, mfp.results.mlb], [soccer, mfp.results.soccer_intl]] as const) {
      const rows = within(table).getAllByRole("row").slice(1);
      source.checkpoints.forEach((point, index) => {
        expect(within(rows[index]).getByRole("rowheader")).toHaveTextContent(point.checkpoint);
        expect(rows[index]).toHaveTextContent(point.n.toLocaleString("en-US"));
        expect(rows[index]).toHaveTextContent(String(point.mfp));
      });
    }
    expect(within(mlb).getByRole("columnheader", { name: /closing reference skill/i })).toBeInTheDocument();
    expect(screen.getByLabelText("Timing measurement evidence").textContent?.toLowerCase()).toContain("closing reference");
    expect(screen.queryByText(/rises from/)).not.toBeInTheDocument();
  });

  it("exposes keyboard-scrollable regions, source downloads, and the corrected Scout question", () => {
    show(mfpId, mfp);
    expect(screen.getByRole("region", { name: "MLB measurements (scrollable table)" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("region", { name: "International soccer measurements (scrollable table)" })).toHaveAttribute("tabindex", "0");
    const links = screen.getAllByRole("link", { name: `${mfpId}.json` });
    for (const link of links) expect(link).toHaveAttribute("href", `/data/showcase/${mfpId}.json`);
    expect(screen.getByRole("link", { name: "Ask Scout about this module" })).toHaveAttribute("href", "/analytics/ask?q=What%20is%20the%20Market%20Foresight%20Premium%3F");
    expect(screen.getByRole("link", { name: "Explore these measurements in the lab" })).toHaveAttribute("href", "/analytics/lab?dataset=market-foresight&view=table&allCohorts=1");
    expect(within(screen.getByRole("table", { name: "MLB published timing measurements" })).getAllByRole("columnheader").every(header => header.getAttribute("scope") === "col")).toBe(true);
  });

  it("opens both populations in the lab's real table view", () => {
    const data = getLabData();
    for (const [id, out, dataset] of [[lcfId, lcf, "live-clock"], [mfpId, mfp, "market-foresight"]] as const) {
      const page = show(id, out);
      const href = screen.getByRole("link", { name: "Explore these measurements in the lab" }).getAttribute("href")!;
      const state = readLabViewState(new URL(href, "https://example.test").search, data);
      expect(state).toMatchObject({ id: dataset, mode: "table", allCohorts: true });
      page.unmount();
    }
  });

  it("does not substitute a manifest date or zero for missing source fields", () => {
    const sparse = { results: [{ sport: "mlb", live_clock_fraction: null, n_games_total: null, n_games_decided: null }] };
    show(lcfId, sparse);
    const table = screen.getByRole("table", { name: "MLB published timing measurements" });
    expect(table).toHaveTextContent("Unavailable");
    expect(within(table).queryByText("0")).not.toBeInTheDocument();
    expect(screen.getByText("Date not published.", { selector: "figcaption span" })).toBeInTheDocument();
    expect(screen.queryByText(/2026-07-24/)).not.toBeInTheDocument();
  });

  it("uses the same neutral framing in exported page metadata", () => {
    const liveClock = generateMetadata({ params: { id: lcfId } });
    const foresight = generateMetadata({ params: { id: mfpId } });
    expect(liveClock.title).toBe("Live-Clock Fraction");
    expect(foresight.title).toBe("Market Foresight Premium");
    expect(liveClock.description).not.toMatch(/stays contested later|cross.sport ranking/i);
    expect(foresight.description).not.toMatch(/rises from|over the game/i);
    expect(foresight.description?.toLowerCase()).toContain("closing reference");
  });
});
