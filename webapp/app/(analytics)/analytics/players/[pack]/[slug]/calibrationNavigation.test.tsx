import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EntityPage, { generateMetadata } from "./page";

describe("entity detail cohort navigation", () => {
  it.each(["mlb_band_2_4", "soccer_intl_band_2_4"])("labels published probability band %s and links to its cohort", (slug) => {
    const params = { pack: "calibration", slug };
    render(<EntityPage params={params} />);

    expect(generateMetadata({ params }).title).toMatch(/ -- Probability-band calibration$/);
    expect(within(screen.getByRole("navigation", { name: "Breadcrumb" }))
      .getByRole("link", { name: "Probability-band calibration" }))
      .toHaveAttribute("href", "/analytics/players#calibration-probability-bands");
    expect(document.body).toHaveTextContent("these are measured probability-band outcomes, not projections.");
    expect(document.querySelector("header .overline"))
      .toHaveTextContent("Probability-band calibration");
    expect(document.querySelector("header .overline"))
      .toHaveTextContent("Cross-sport");
    expect(document.querySelector("header .overline"))
      .toHaveTextContent("as of 2026-09-16");
    expect(screen.getByRole("link", { name: /^All Probability-band calibration/ }))
      .toHaveAttribute("href", "/analytics/players#calibration-probability-bands");
    expect(within(screen.getByRole("region", { name: "Measurements" })).getByText("0.3")).toBeInTheDocument();
  });

  it("keeps a published time checkpoint in the checkpoint cohort", () => {
    const params = { pack: "calibration", slug: "mlb_inning_1" };
    render(<EntityPage params={params} />);

    expect(generateMetadata({ params }).title).toMatch(/ -- Calibration checkpoints$/);
    expect(within(screen.getByRole("navigation", { name: "Breadcrumb" }))
      .getByRole("link", { name: "Calibration checkpoints" }))
      .toHaveAttribute("href", "/analytics/players#calibration");
    expect(document.body).toHaveTextContent("these are measured calibration checkpoints, not projections.");
    expect(document.querySelector("header .overline")).toHaveTextContent("Calibration checkpoints");
    expect(document.querySelector("header .overline")).toHaveTextContent("Cross-sport");
    expect(screen.getByRole("link", { name: /^All Calibration checkpoints/ }))
      .toHaveAttribute("href", "/analytics/players#calibration");
  });

  it("leaves another pack's labels and destination unchanged", () => {
    const params = { pack: "nba_players", slug: "nolan_traore" };
    render(<EntityPage params={params} />);

    expect(generateMetadata({ params }).title).toMatch(/ -- NBA players$/);
    expect(within(screen.getByRole("navigation", { name: "Breadcrumb" }))
      .getByRole("link", { name: "NBA players" }))
      .toHaveAttribute("href", "/analytics/players#nba_players");
    expect(document.body).toHaveTextContent("these are measured per-36 rates, not projections.");
    expect(screen.getByRole("link", { name: /^All NBA players/ }))
      .toHaveAttribute("href", "/analytics/players#nba_players");
  });
});
