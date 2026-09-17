import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AskEntry } from "@/lib/analytics/askSearch";
import { AskBox } from "./AskBox";

const staleText = "Stale calibration result kept as a dated record.";
const affected: AskEntry = {
  q: "Calibration question",
  alt_phrasings: [],
  tags: ["calibration"],
  bucket: "test",
  a: {
    status: "ok",
    answer: staleText,
    source_artifact: "webapp/public/data/showcase/calibration_stability.json",
  },
};

function ask(entry: AskEntry) {
  render(<AskBox entries={[entry]} tours={[]} />);
  fireEvent.change(screen.getByLabelText("Ask Scout a question"), { target: { value: entry.q } });
  fireEvent.click(screen.getByRole("button", { name: "Search Scout's cited answers" }));
}

describe("AskBox integrity warnings", () => {
  it("keeps the citation receipt and shows the finding before stale answer text", () => {
    ask(affected);
    const notices = screen.getAllByLabelText("Data integrity");
    const stale = screen.getByText(staleText);

    expect(screen.getByRole("button", { name: /^Receipt: CITED/ })).toBeInTheDocument();
    expect(notices).toHaveLength(2);
    expect(notices.map(notice => notice.getAttribute("data-status"))).toEqual([
      "withdrawn-pending-regeneration",
      "under-review",
    ]);
    expect(screen.getAllByText("calibration_stability")).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: "Read the full finding" })).toHaveLength(2);
    expect(screen.getAllByRole("link", { name: "Read the full finding" })[0]).toHaveAttribute("href", "/analytics/findings/ingame-join-integrity");
    expect(notices[0].compareDocumentPosition(stale) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("does not show a warning for an unaffected cited answer", () => {
    ask({ ...affected, a: { ...affected.a, source_artifact: "webapp/public/data/showcase/site_manifest.json" } });
    expect(screen.queryByLabelText("Data integrity")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Receipt: CITED/ })).toBeInTheDocument();
  });
});
