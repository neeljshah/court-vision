import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";

let pathname = "/";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

import { SiteHeader } from "../SiteHeader";

const ORDER = ["Today", "Desk", "Calibration", "Research", "Evidence", "About"];

beforeEach(() => {
  pathname = "/";
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.classList.remove("dark");
});

describe("SiteHeader", () => {
  it("renders the six nav links in order with their homes", () => {
    render(<SiteHeader />);
    const links = within(screen.getByRole("navigation", { name: "Main" })).getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual(ORDER);
    expect(links.map((l) => l.getAttribute("href"))).toEqual([
      "/", "/desk/", "/analytics/calibration/", "/analytics/papers/", "/evidence/", "/about/",
    ]);
  });

  it.each([
    ["/", "Today"],
    ["/court-vision/games/mlb/x/", "Today"],
    ["/desk/health/", "Desk"],
    ["/paper-trading/", "Desk"],
    ["/analytics/state-reliability/", "Calibration"],
    ["/analytics/findings/tennis/", "Research"],
    ["/receipts/3/", "Evidence"],
    ["/evidence/retractions/", "Evidence"],
    ["/how-it-works/", "About"],
  ])("highlights the current section for %s", (path, label) => {
    pathname = path;
    render(<SiteHeader />);
    const current = within(screen.getByRole("navigation", { name: "Main" })).getAllByRole("link")
      .filter((l) => l.getAttribute("aria-current") === "page");
    expect(current.map((l) => l.textContent)).toEqual([label]);
  });

  it("opens the mobile menu with aria-expanded and closes it on Escape, returning focus", () => {
    render(<SiteHeader />);
    const button = screen.getByRole("button", { name: "Menu" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-controls", "site-menu");
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    const menu = screen.getByRole("navigation", { name: "Main menu" });
    expect(within(menu).getAllByRole("link").map((l) => l.textContent).slice(0, 6)).toEqual(ORDER);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("navigation", { name: "Main menu" })).toBeNull();
    expect(document.activeElement).toBe(button);
  });

  it("search opens the palette and Ask Scout is linked", () => {
    const spy = vi.fn();
    window.addEventListener("cv-open-palette", spy);
    render(<SiteHeader />);
    fireEvent.click(screen.getByRole("button", { name: /search the site/i }));
    expect(spy).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: "Ask Scout" })).toHaveAttribute("href", "/analytics/ask/");
    window.removeEventListener("cv-open-palette", spy);
  });

  it("theme toggle sets both theme hooks and stores one key", () => {
    render(<SiteHeader />);
    const toggle = screen.getByRole("button", { name: "Switch to dark theme" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("cv-theme")).toBe("dark");
    expect(toggle).toHaveAttribute("aria-pressed", "true");
  });
});
