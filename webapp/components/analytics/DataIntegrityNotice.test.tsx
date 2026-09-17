import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { dataIntegrityNotices, noticesForModules } from "@/lib/analytics/dataIntegrity";
import { DataIntegrityNotice } from "./DataIntegrityNotice";

describe("DataIntegrityNotice", () => {
  it("renders the revision-2 wording with the full finding route", () => {
    const moduleIds = ["state_conditioned_calibration"];
    render(<DataIntegrityNotice notices={noticesForModules(moduleIds)} moduleIds={moduleIds} />);
    const notices = screen.getAllByRole("complementary", { name: "Data integrity" });
    expect(notices).toHaveLength(1);
    expect(notices[0]).toHaveAttribute("data-status", "regenerated");
    expect(within(notices[0]).getByText(/These MLB\/soccer numbers are revision 2, computed on the segment-clean corpus \(2026-09-16\)\./)).toBeInTheDocument();
    expect(within(notices[0]).getByText(/Revision 1 values are withdrawn and kept in the regeneration receipt\./)).toBeInTheDocument();
    expect(within(notices[0]).getByText("state_conditioned_calibration")).toBeInTheDocument();
    expect(within(notices[0]).queryByText("blowout_dynamics")).not.toBeInTheDocument();
    expect(within(notices[0]).getByRole("link", { name: "Read the full finding" })).toHaveAttribute("href", expect.stringMatching(/^\/analytics\/findings\/ingame-join-integrity\/?$/));
  });

  it("renders the timing revision-2 wording for a regenerated timing artifact", () => {
    const moduleIds = ["blowout_dynamics"];
    render(<DataIntegrityNotice notices={noticesForModules(moduleIds)} moduleIds={moduleIds} />);
    const notices = screen.getAllByRole("complementary", { name: "Data integrity" });
    expect(notices).toHaveLength(1);
    expect(notices[0]).toHaveAttribute("data-status", "regenerated");
    expect(within(notices[0]).getByText(/rebuilt on the segment-clean corpus \(2026-09-17\)/)).toBeInTheDocument();
    expect(within(notices[0]).getByText("blowout_dynamics")).toBeInTheDocument();
  });

  it("does not render without an applicable notice", () => {
    render(<DataIntegrityNotice notices={[]} moduleIds={["blowout_dynamics"]} />);
    expect(screen.queryByRole("complementary", { name: "Data integrity" })).not.toBeInTheDocument();
  });

  it("exposes both regeneration notices and the unmatched review notice", () => {
    expect(dataIntegrityNotices.map((notice) => notice.status)).toEqual(["regenerated", "regenerated", "under-review"]);
    expect(dataIntegrityNotices.find((notice) => notice.status === "under-review")?.affectedModules).toEqual([]);
  });
});
