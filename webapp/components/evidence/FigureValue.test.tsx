import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FigureValue, figureText } from "./FigureValue";

const BLOB = "https://github.com/neeljshah/court-vision/blob/master/";

describe("FigureValue", () => {
  it("renders a count figure by key with its as-of and a receipt to the canonical JSON", () => {
    render(<FigureValue k="published_module_count" />);
    const figure = screen.getByText("77").parentElement as HTMLElement;
    expect(figure).toHaveAttribute("data-figure-key", "published_module_count");
    expect(within(figure).getByText("as of 2026-10-19")).toHaveAttribute("dateTime", "2026-10-19");
    const receipt = within(figure).getByRole("link");
    expect(receipt).toHaveAttribute("href", `${BLOB}docs/evidence/CANONICAL_FIGURES.json`);
    expect(receipt.getAttribute("title")).toContain("module_count in webapp/public/data/showcase/site_manifest.json");
    expect(receipt.getAttribute("aria-label")).toContain("descriptive_only");
  });

  it("formats a large count with separators and renders a string figure verbatim", () => {
    expect(figureText({ k: "public_commit_count" })).toBe("6,508");
    expect(figureText({ k: "g6_status" })).toBe("has not started as of 2026-10-19 (zero weeks collected)");
    expect(figureText({ k: "forward_window_end" })).toBe("2026-10-16");
  });

  it("renders one named field of a comparison figure with the kit formats", () => {
    expect(figureText({ k: "nba_ml_pregame_vs_close_shin", field: "gap" })).toBe("+0.0069");
    expect(figureText({ k: "nba_ml_pregame_vs_close_shin", field: "model" })).toBe("0.1735");
    expect(figureText({ k: "nba_ml_pregame_vs_close_shin", field: "close" })).toBe("0.1666");
    expect(figureText({ k: "nba_ml_pregame_vs_close_shin", field: "ci95" })).toBe("[-0.0038, +0.0175]");
    expect(figureText({ k: "nba_ml_pregame_vs_close_shin", field: "n" })).toBe("372");
    expect(figureText({ k: "nba_ml_pregame_vs_close_shin", field: "dm_p" })).toBe("0.20");
    expect(figureText({ k: "mlb_ml_pregame_vs_close", field: "n" })).toBe("13,992");
    expect(figureText({ k: "paper_desk_fill_counts", field: "ttl_30_fills_credited" })).toBe("136");
  });

  it("attaches the packet verdict with its qualifier and links the memo as the receipt", () => {
    render(<FigureValue k="nba_ml_pregame_vs_close_shin" field="gap" verdict />);
    const figure = screen.getByText("+0.0069").parentElement as HTMLElement;
    expect(within(figure).getByText("MATCHES_CLOSE")).toBeInTheDocument();
    expect(within(figure).getByText("underpowered, MDE 0.0152")).toBeInTheDocument();
    expect(within(figure).getByText("as of 2026-09-24")).toBeInTheDocument();
    const receipt = within(figure).getByRole("link");
    expect(receipt).toHaveAttribute("href", `${BLOB}docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md`);
    expect(receipt.getAttribute("aria-label")).toContain("edge_claimed:false");
  });

  it("can drop the badges and take a custom format", () => {
    render(<FigureValue k="titled_findings_count" asOf={false} receipt={false} format={(v) => `${v} findings`} />);
    expect(screen.getByText("17 findings")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("refuses an unknown key and a field on a count figure at the type level", () => {
    // @ts-expect-error -- not a canonical key
    const unknown = <FigureValue k="nba_win_rate" />;
    // @ts-expect-error -- a count figure has no fields to pick
    const field = <FigureValue k="published_module_count" field="model" />;
    expect(unknown && field).toBeTruthy();
  });
});
