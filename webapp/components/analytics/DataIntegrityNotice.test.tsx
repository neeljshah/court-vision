import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { dataIntegrityNotices } from "@/lib/analytics/dataIntegrity";
import { DataIntegrityNotice } from "./DataIntegrityNotice";

describe("DataIntegrityNotice", () => {
  it("renders the withdrawal and review wording with the full finding route", () => {
    render(<DataIntegrityNotice notices={dataIntegrityNotices} moduleIds={["state_conditioned_calibration"]} />);
    const notices = screen.getAllByRole("complementary", { name: "Data integrity" });
    expect(notices).toHaveLength(2);
    expect(within(notices[0]).getByText(/MLB in-game results are withdrawn pending corpus correction/)).toBeInTheDocument();
    expect(within(notices[1]).getByText(/This artifact's MLB\/soccer rows are under review/)).toBeInTheDocument();
    expect(within(notices[0]).getByText("state_conditioned_calibration")).toBeInTheDocument();
    expect(within(notices[0]).queryByText("blowout_dynamics")).not.toBeInTheDocument();
    expect(within(notices[0]).getByRole("link", { name: "Read the full finding" })).toHaveAttribute("href", expect.stringMatching(/^\/analytics\/findings\/ingame-join-integrity\/?$/));
  });

  it("does not render without an applicable notice", () => {
    render(<DataIntegrityNotice notices={[]} moduleIds={["blowout_dynamics"]} />);
    expect(screen.queryByRole("complementary", { name: "Data integrity" })).not.toBeInTheDocument();
  });
});
