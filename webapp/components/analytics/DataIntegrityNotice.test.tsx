import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { dataIntegrityNotices } from "@/lib/analytics/dataIntegrity";
import { DataIntegrityNotice } from "./DataIntegrityNotice";

describe("DataIntegrityNotice", () => {
  it("renders the summary, current artifacts, and full finding route", () => {
    render(<DataIntegrityNotice notices={dataIntegrityNotices} moduleIds={["state_conditioned_calibration"]} />);
    const notice = screen.getByRole("complementary", { name: "Data integrity" });
    expect(within(notice).getByText("Data integrity")).toBeInTheDocument();
    expect(within(notice).getByText(/126 of 227 MLB game files/)).toBeInTheDocument();
    expect(within(notice).getByText("state_conditioned_calibration")).toBeInTheDocument();
    expect(within(notice).queryByText("blowout_dynamics")).not.toBeInTheDocument();
    expect(within(notice).getByRole("link", { name: "Read the full finding" })).toHaveAttribute("href", expect.stringMatching(/^\/analytics\/findings\/ingame-join-integrity\/?$/));
  });

  it("does not render without an applicable notice", () => {
    render(<DataIntegrityNotice notices={[]} moduleIds={["blowout_dynamics"]} />);
    expect(screen.queryByRole("complementary", { name: "Data integrity" })).not.toBeInTheDocument();
  });
});
