import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PaperBlockView } from "./PaperBlocks";

describe("PaperBlockView", () => {
  it("names table regions with the horizontal-scroll instruction and renders the phone hint", () => {
    render(
      <PaperBlockView
        block={{
          type: "table",
          caption: "Published calibration table",
          columns: ["Bin", "Observed"],
          rows: [["0.4 to 0.5", "0.43"]],
        }}
      />,
    );

    expect(screen.getByRole("region", { name: /Published calibration table, scroll horizontally for all columns$/ })).toBeInTheDocument();
    expect(screen.getByText("Scroll horizontally to see all columns.")).toHaveClass("paper-scroll-hint");
  });
});
