import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import EntityPage from "./page";

function rankNote() {
  const text = screen.getByText(/Percentiles (?:are calculated|rank)|Stored percentiles rank/);
  return text as HTMLElement;
}

describe("entity rank context", () => {
  it("renders Como's stored soccer ranks with the published pack caveat and receipt", () => {
    render(<EntityPage params={{ pack: "soccer", slug: "como" }} />);

    expect(screen.getByRole("heading", { name: "Como" })).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: "Percentile rank 92 among 187 measured profiles" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("img", { name: "Percentile rank 100 among 187 measured profiles" }).length).toBeGreaterThan(0);
    const note = rankNote();
    expect(note).toHaveTextContent("published soccer pack");
    expect(note).toHaveTextContent("six divisions without team league or match dates");
    expect(note).toHaveTextContent("like-for-like comparisons are unverified");
    expect(note).not.toHaveTextContent("compatible published cohort");
    expect(within(note).getByRole("button")).toHaveAccessibleName("Receipt: descriptive_only for entity_percentiles.json");
    fireEvent.click(within(note).getByRole("button"));
    expect(within(note).getByRole("link", { name: "webapp/public/data/showcase/entity_percentiles.json" }))
      .toHaveAttribute("href", "/data/showcase/entity_percentiles.json");
  });

  it("describes MLB pitch ranks as calculated within the card-type cohort", () => {
    render(<EntityPage params={{ pack: "mlb_pitch", slug: "ch" }} />);

    expect(screen.getAllByRole("img", { name: /Percentile rank .* among 19 measured profiles/ }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("img", { name: /Percentile rank .* among 61 measured profiles/ })).not.toBeInTheDocument();
    const note = rankNote();
    expect(note).toHaveTextContent("within the MLB pitch types group using each field's measured values");
    expect(note).not.toHaveTextContent("published pack");
    fireEvent.click(within(note).getByRole("button"));
    expect(within(note).getByRole("link", { name: "webapp/public/data/showcase/atlas_mlb_pitch_manifest.json" }))
      .toHaveAttribute("href", "/data/showcase/atlas_mlb_pitch_manifest.json");
  });

  it("uses neutral published-pack wording for other stored ranks", () => {
    render(<EntityPage params={{ pack: "nba_players", slug: "nolan_traore" }} />);

    const note = rankNote();
    expect(note).toHaveTextContent("measured rows in this published pack");
    expect(note).not.toHaveTextContent("compatible published cohort");
    expect(note).not.toHaveTextContent("six divisions");
  });

  it("omits rank context when a calibration card has no published percentiles", () => {
    render(<EntityPage params={{ pack: "calibration", slug: "mlb_inning_1" }} />);

    expect(screen.getByRole("heading", { name: /mlb inning 1/i })).toBeInTheDocument();
    expect(screen.queryByText(/Stored percentiles rank|Percentiles are calculated/)).not.toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Percentile rank/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /entity_percentiles\.json/ })).not.toBeInTheDocument();
  });
});
