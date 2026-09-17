import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import IngameJoinIntegrityPage from "./page";

it("renders the receipt, agreement, and artifact status tables", () => {
  render(<IngameJoinIntegrityPage />);
  expect(screen.getByRole("heading", { name: "MLB in-game calibration now runs on a segment-clean corpus." })).toBeInTheDocument();
  const counts = screen.getByRole("region", { name: "Corpus integrity counts scroll horizontally" });
  expect(within(counts).getByText("78,986")).toBeInTheDocument();
  expect(within(counts).getByText(/2 \(Draws truncated at minute 60 and 42/)).toBeInTheDocument();
  const agreement = screen.getByRole("region", { name: "Tick-level label agreement scroll horizontally" });
  expect(within(agreement).getByText("0.7284")).toBeInTheDocument();
  expect(within(agreement).getByText("0.9200")).toBeInTheDocument();
  expect(within(agreement).getByText("n = 6,623")).toBeInTheDocument();
  const registry = screen.getAllByRole("region", { name: "Artifact status registry scroll horizontally" })[0];
  expect(within(registry).getAllByText("state_conditioned_calibration")[0]).toBeInTheDocument();
  expect(within(registry).getAllByText("regenerated").length).toBeGreaterThan(0);
  expect(within(registry).getAllByText("blowout_dynamics").length).toBeGreaterThan(0);
  expect(within(registry).getAllByText("ess_ledger").length).toBeGreaterThan(0);
  expect(within(registry).getAllByText("under-review").length).toBeGreaterThan(0);
  expect(screen.getAllByText((_, node) => node?.tagName === "P" && /Stale input: residual_autocorrelation\./.test(node.textContent || "")).length).toBeGreaterThan(0);
  expect(screen.getByRole("heading", { name: "What clears the status" })).toBeInTheDocument();
});

it("shows the regeneration before/after table and links the regeneration receipt", () => {
  render(<IngameJoinIntegrityPage />);
  const table = screen.getByRole("region", { name: "Artifact headline before and after regeneration scroll horizontally" });
  const row = within(table).getAllByText("state_conditioned_calibration")[0].closest("tr");
  expect(row).not.toBeNull();
  expect(within(row as HTMLElement).getByText("78,986")).toBeInTheDocument();
  expect(within(row as HTMLElement).getByText("27,351")).toBeInTheDocument();
  expect(within(row as HTMLElement).getByText(/model 0\.079, reference quote 0\.0591/)).toBeInTheDocument();
  expect(within(row as HTMLElement).getByText(/model 0\.0494, reference quote 0\.0397/)).toBeInTheDocument();
  expect(within(table).getAllByRole("row")).toHaveLength(14);
  expect(screen.getAllByText(/these are population changes, not forecaster improvement/i).length).toBeGreaterThan(0);
  expect(screen.getByText(/27,076 of the 78,986 MLB ticks, 34\.3 percent/)).toBeInTheDocument();
  expect(screen.getByText(/excluded 51,635, 65\.4 percent/)).toBeInTheDocument();
  expect(screen.getByText(/excluded 4,738, 52\.6 percent/)).toBeInTheDocument();
  expect(screen.queryByText(/a third of the MLB ticks/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/widens every interval/i)).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Read the full regeneration receipt" })).toHaveAttribute("href", expect.stringContaining("/data/audits/mlb-ingame-regeneration.json"));
});

it("shows the timing before/after table and links the timing regeneration receipt", () => {
  render(<IngameJoinIntegrityPage />);
  const table = screen.getByRole("region", { name: "Timing artifact headline before and after regeneration scroll horizontally" });
  expect(within(table).getAllByRole("row")).toHaveLength(7);
  const row = within(table).getAllByText("blowout_dynamics")[0].closest("tr");
  expect(row).not.toBeNull();
  expect(within(row as HTMLElement).getByText("178")).toBeInTheDocument();
  expect(within(row as HTMLElement).getByText("174")).toBeInTheDocument();
  expect(within(row as HTMLElement).getByText(/median inning 7\.5 in 27 percent/)).toBeInTheDocument();
  expect(within(row as HTMLElement).getByText(/median inning 6\.0 in 32 percent/)).toBeInTheDocument();
  expect(screen.getByText(/comeback_atlas is the honest exception/i)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Read the full timing regeneration receipt" })).toHaveAttribute("href", expect.stringContaining("/data/audits/mlb-ingame-timing-regeneration.json"));
});

it("links published artifacts and gives each table a focusable scroll region", () => {
  render(<IngameJoinIntegrityPage />);
  const registered = screen.getAllByRole("link", { name: "state_conditioned_calibration" });
  expect(registered.length).toBeGreaterThan(0);
  registered.forEach(link => expect(link).toHaveAttribute("href", expect.stringMatching(/\/analytics\/m\/[^/]+\/$/)));

  const essLedger = screen.getAllByRole("link", { name: "ess_ledger" });
  expect(essLedger.length).toBeGreaterThan(0);
  essLedger.forEach(link => expect(link).toHaveAttribute("href", "/analytics/m/ess_ledger/"));

  const labels = [
    "Corpus integrity counts",
    "Tick-level label agreement",
    "Artifact headline before and after regeneration",
    "Timing artifact headline before and after regeneration",
    "Artifact status registry",
  ];
  labels.forEach(label => expect(screen.getByRole("region", { name: `${label} scroll horizontally` })).toHaveAttribute("tabindex", "0"));
});
