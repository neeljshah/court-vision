import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import NovelStatsPage from "./page";

const showcase = join(process.cwd(), "public", "data", "showcase");
const readJson = <T,>(file: string): T => JSON.parse(readFileSync(join(showcase, file), "utf8")) as T;

describe("NovelStatsPage", () => {
  it("renders one card per published measurement", () => {
    const index = readJson<{ stats: unknown[] }>("novel_stats_index.json");
    render(<NovelStatsPage />);

    expect(screen.getAllByTestId(/novel-card-/)).toHaveLength(index.stats.length);
  });

  it("keeps the Load-Bearing Index estimator observation windows separate", () => {
    render(<NovelStatsPage />);
    expect(screen.getByText(/Estimator A: Observation window 2024-25/)).toBeInTheDocument();
    expect(screen.getByText(/Estimator B: Observation window 2025-26 regular season/)).toBeInTheDocument();
  });

  it("renders the starter-rest artifact verdict without generic overshoot copy", () => {
    const starter = readJson<{ verdict: string }>("novel_starter_rest_absorption.json");
    render(<NovelStatsPage />);
    const card = screen.getByTestId("novel-card-novel_starter_rest_absorption");

    expect(screen.queryByText(/reason to trust/i)).not.toBeInTheDocument();
    expect(within(card).queryByText(/market overshoot/i)).not.toBeInTheDocument();
    expect(card).toHaveTextContent(starter.verdict.split(". ")[0]);
  });
});
