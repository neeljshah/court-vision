import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

import { Breadcrumbs } from "../Breadcrumbs";
import { crumbsFor } from "../nav";
import { resolveRedirect } from "@/lib/redirects";

describe("Breadcrumbs", () => {
  it("renders nothing on home or a section root", () => {
    const { container } = render(<Breadcrumbs path="/" />);
    expect(container.innerHTML).toBe("");
    expect(crumbsFor("/desk/")).toEqual([]);
    expect(crumbsFor("/court-vision/analytics/calibration/")).toEqual([]);
  });

  it("renders Home > Section > Page with the page as current", () => {
    render(<Breadcrumbs path="/court-vision/analytics/findings/nba-momentum/" />);
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    const items = within(nav).getAllByRole("listitem").map((li) => li.textContent);
    expect(items).toEqual(["Home", "Research", "Findings", "Nba momentum"]);
    expect(within(nav).getByRole("link", { name: "Research" })).toHaveAttribute("href", expect.stringMatching(/^\/analytics\/papers\/?$/));
    expect(within(nav).getByText("Nba momentum")).toHaveAttribute("aria-current", "page");
  });

  it("labels desk pages and skips the section segment", () => {
    expect(crumbsFor("/desk/model-cards/").map((c) => c.label)).toEqual(["Home", "Desk", "Model cards"]);
    expect(crumbsFor("/evidence/retractions/").map((c) => c.label)).toEqual(["Home", "Evidence", "Retraction record"]);
  });
});

describe("lib/redirects", () => {
  it("maps retired routes and dynamic families to their new homes", () => {
    expect(resolveRedirect("/today")).toBe("/desk/");
    expect(resolveRedirect("/use-it/")).toBe("/about/");
    expect(resolveRedirect("/evidence/retraction-story/")).toBe("/evidence/retractions/");
    expect(resolveRedirect("/atlas/nba/lebron/")).toBe("/analytics/players/");
    expect(resolveRedirect("/paper/abc%7Cdef/")).toBe("/paper-trading/");
    expect(resolveRedirect("/games/")).toBeNull();
    expect(resolveRedirect("/paper-trading/")).toBeNull();
  });
});
