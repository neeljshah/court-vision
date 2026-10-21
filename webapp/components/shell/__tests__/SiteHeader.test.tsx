import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, render, screen, fireEvent, within } from "@testing-library/react";
import { hydrateRoot, type Root } from "react-dom/client";
import { renderToString } from "react-dom/server";

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
    // next/link drops the trailing slash in jsdom; the export adds it (trailingSlash: true)
    const norm = (h: string | null) => (h ?? "").replace(/\/+$/, "") || "/";
    expect(links.map((l) => norm(l.getAttribute("href")))).toEqual([
      "/", "/desk", "/analytics/calibration", "/analytics/papers", "/evidence", "/about",
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
    expect(screen.getByRole("link", { name: "Ask Scout" })).toHaveAttribute("href", expect.stringMatching(/^\/analytics\/ask\/?$/));
    window.removeEventListener("cv-open-palette", spy);
  });

  it("theme toggle sets both theme hooks and stores one key", () => {
    render(<SiteHeader />);
    const toggle = screen.getByRole("button", { name: "Dark theme" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("cv-theme")).toBe("dark");
    expect(toggle).toHaveAttribute("aria-pressed", "true");
  });

  it.each(["dark", "light"])("hydrates after the head script applies the %s theme", async (theme) => {
    const container = document.createElement("div");
    container.innerHTML = renderToString(<SiteHeader />);
    document.body.appendChild(container);
    document.documentElement.setAttribute("data-theme", theme);
    const onRecoverableError = vi.fn();
    let root: Root | undefined;
    try {
      await act(async () => {
        root = hydrateRoot(container, <SiteHeader />, { onRecoverableError });
      });
      expect(onRecoverableError).not.toHaveBeenCalled();
      const toggle = within(container).getByRole("button", {
        name: "Dark theme",
      });
      expect(toggle).toHaveAttribute("aria-pressed", String(theme === "dark"));
    } finally {
      await act(async () => root?.unmount());
      container.remove();
    }
  });
});
