import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";

vi.mock("next/navigation", () => ({ usePathname: () => "/nope/" }));

import NotFound from "./not-found";

describe("site 404", () => {
  it("is wrapped in the shell and links the six sections", () => {
    render(<NotFound />);
    expect(screen.getByRole("navigation", { name: "Main" })).toBeTruthy();
    expect(screen.getByRole("contentinfo")).toBeTruthy();
    const body = screen.getByRole("region", { name: "This page is not in the record." });
    expect(within(body).getAllByRole("link").map((l) => l.textContent)).toEqual(
      ["Today", "Desk", "Calibration", "Research", "Evidence", "About"],
    );
  });

  it("ships the retired-family redirect script", () => {
    const { container } = render(<NotFound />);
    const js = [...container.querySelectorAll("script")].map((sc) => sc.innerHTML).join("");
    expect(js).toContain("/atlas/");
    expect(js).toContain("location.replace");
  });
});
