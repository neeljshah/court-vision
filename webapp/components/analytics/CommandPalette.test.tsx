import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import CommandPalette from "./CommandPalette";

const push = vi.fn();
const fetchMock = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function response(records: unknown[]) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve({ records }) });
}
function openPalette() {
  window.dispatchEvent(new CustomEvent("cv-open-palette"));
  return screen.findByRole("dialog", { name: "Search CourtVision" });
}

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", ResizeObserverMock);
  // jsdom has no layout: cmdk scrolls the selected item into view once focus is in the list.
  Element.prototype.scrollIntoView = () => {};
});

beforeEach(() => {
  push.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

describe("CommandPalette", () => {
  it("adds the new page destinations to the lazy corpus", async () => {
    fetchMock.mockReturnValue(response([]));
    render(<CommandPalette />);
    await openPalette();
    expect(await screen.findByText("Measurement lab")).toBeInTheDocument();
    expect(screen.getByText("Compare profiles")).toBeInTheDocument();
    expect(screen.getByText("Evidence & Platform")).toBeInTheDocument();
  });

  it("scopes fuzzy hits before applying the result limit", async () => {
    const modules = Array.from({ length: 31 }, (_, index) => ({ id: `module-${index}`, title: `Archive module ${index}`, subtitle: "module", href: `/analytics/m/${index}`, type: "module", keywords: ["archive"] }));
    fetchMock.mockReturnValue(response([...modules, { id: "entity-archive", title: "Archive entity", subtitle: "entity", href: "/analytics/player/archive", type: "entity", keywords: ["archive"] }]));
    render(<CommandPalette />);
    await openPalette();
    const input = screen.getByRole("combobox", { name: "Search CourtVision" });
    fireEvent.change(input, { target: { value: "archive" } });
    await screen.findByText("Archive module 0");
    fireEvent.click(screen.getByRole("button", { name: "Entities" }));
    await waitFor(() => expect(screen.getByText("Archive entity")).toBeInTheDocument());
    expect(screen.queryByText("Archive module 0")).not.toBeInTheDocument();
  });

  it("retries a failed lazy fetch", async () => {
    fetchMock.mockReturnValueOnce(Promise.reject(new Error("offline"))).mockReturnValueOnce(response([]));
    render(<CommandPalette />);
    await openPalette();
    expect(await screen.findByText(/Search unavailable/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Evidence & Platform")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("hands focus back to the element that opened it when Escape closes it", async () => {
    fetchMock.mockReturnValue(response([]));
    render(<><button type="button">Open search</button><a href="#top">Top link</a><CommandPalette /></>);
    const trigger = screen.getByRole("button", { name: "Open search" });
    trigger.focus();
    await openPalette();
    // Radix moves focus into the dialog (the combobox) while it is open.
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("combobox", { name: "Search CourtVision" })));
    fireEvent.keyDown(document.activeElement as Element, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(document.activeElement).toBe(trigger));

    // A later open from the "/" shortcut (the impl's own listener) returns to that opener too.
    const link = screen.getByRole("link", { name: "Top link" });
    link.focus();
    fireEvent.keyDown(window, { key: "/" });
    await screen.findByRole("dialog", { name: "Search CourtVision" });
    await waitFor(() => expect(document.activeElement).not.toBe(link));
    fireEvent.keyDown(document.activeElement as Element, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(document.activeElement).toBe(link));
  });

  it("full-loads a cross-group result and soft-navigates a same-group one", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, pathname: "/desk/", assign });
    fetchMock.mockReturnValue(response([
      { id: "a", title: "Zeta analytics", subtitle: "x", href: "/analytics/zeta/", type: "module", keywords: ["zeta"] },
      { id: "b", title: "Zeta desk", subtitle: "x", href: "/desk/zeta/", type: "module", keywords: ["zeta"] },
    ]));
    render(<CommandPalette />);
    await openPalette();
    fireEvent.change(screen.getByRole("combobox", { name: "Search CourtVision" }), { target: { value: "zeta" } });
    fireEvent.click(await screen.findByText("Zeta analytics"));
    expect(assign).toHaveBeenCalledWith("/analytics/zeta/");
    expect(push).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
