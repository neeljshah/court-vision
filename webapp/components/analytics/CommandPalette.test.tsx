import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
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

beforeEach(() => {
  // Re-stubbed per test: a test may call vi.unstubAllGlobals().
  vi.stubGlobal("ResizeObserver", ResizeObserverMock);
  // cmdk scrolls the selected item into view on reopen; jsdom has no layout.
  Element.prototype.scrollIntoView = vi.fn();
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

  it("opens with the slash key and with Ctrl+K", async () => {
    fetchMock.mockReturnValue(response([]));
    render(<CommandPalette />);
    expect(screen.queryByRole("dialog", { name: "Search CourtVision" })).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: "/" });
    expect(await screen.findByRole("dialog", { name: "Search CourtVision" })).toBeInTheDocument();
    // Ctrl+K toggles: once to close the palette the slash opened, once to reopen it.
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Search CourtVision" })).not.toBeInTheDocument());
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(await screen.findByRole("dialog", { name: "Search CourtVision" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Search CourtVision" })).not.toBeInTheDocument());
  });

  it("lists site pages, papers and findings but not redirect stubs, and puts an exact title first", async () => {
    fetchMock.mockReturnValue(response([
      { id: "site-paper-trading", title: "Paper record", subtitle: "Site page", href: "/paper-trading", type: "page", keywords: ["paper record"] },
      { id: "site-evidence-retractions", title: "Retraction record", subtitle: "Site page", href: "/evidence/retractions", type: "page", keywords: ["retraction record"] },
      { id: "page-calibration", title: "Calibration reliability", subtitle: "Inspector", href: "/analytics/calibration", type: "page", keywords: ["calibration"] },
      { id: "module-calibration-stability", title: "Calibration Stability", subtitle: "Module", href: "/analytics/m/calibration_stability", type: "module", keywords: ["calibration"] },
      { id: "module-calibration", title: "Calibration", subtitle: "Module", href: "/analytics/m/calibration", type: "module", keywords: ["calibration"] },
      { id: "module-retraction-count", title: "Mechanism retraction count", subtitle: "Module", href: "/analytics/m/retraction_count", type: "module", keywords: ["retraction", "ledger"] },
      { id: "finding-verdict-flips", title: "Verdict flips", subtitle: "Finding", href: "/analytics/findings/verdict-flips", type: "finding", keywords: ["retraction", "verdict"] },
      { id: "paper-how-to-read", title: "How to read a CourtVision paper", subtitle: "Working paper", href: "/analytics/papers/how-to-read-a-courtvision-paper", type: "module", keywords: ["paper"] },
    ]));
    render(<CommandPalette />);
    await openPalette();
    const input = screen.getByRole("combobox", { name: "Search CourtVision" });
    const titles = () => screen.getAllByRole("option").map((option) => option.querySelector(".serif")?.textContent);

    await screen.findByText("Paper record");
    expect(titles()).toEqual(expect.arrayContaining(["Paper record", "Retraction record", "Verdict flips", "Working papers"]));
    expect(screen.queryByText("Page moved")).not.toBeInTheDocument();

    fireEvent.change(input, { target: { value: "calibration" } });
    await waitFor(() => expect(titles()[0]).toBe("Calibration"));
    // Groups stay intact on screen: the group holding the exact match renders first, so its sibling follows it.
    expect(titles().slice(0, 3)).toEqual(["Calibration", "Calibration Stability", "Calibration reliability"]);

    fireEvent.change(input, { target: { value: "retraction" } });
    await waitFor(() => expect(titles()[0]).toBe("Retraction record"));
    expect(titles()).toContain("Mechanism retraction count");

    fireEvent.change(input, { target: { value: "paper" } });
    await waitFor(() => expect(titles()).toContain("How to read a CourtVision paper"));
  });

  it("names three starting points when nothing matches", async () => {
    fetchMock.mockReturnValue(response([{ id: "a", title: "Zeta module", subtitle: "x", href: "/analytics/m/zeta", type: "module", keywords: ["zeta"] }]));
    render(<CommandPalette />);
    await openPalette();
    await screen.findByText("Evidence & Platform");
    fireEvent.change(screen.getByRole("combobox", { name: "Search CourtVision" }), { target: { value: "qqzzxx" } });
    expect(await screen.findByRole("status")).toHaveTextContent('No results for "qqzzxx". Three good starting points:');
    const titles = screen.getAllByRole("option").map((option) => option.querySelector(".serif")?.textContent);
    expect(titles).toEqual(["Calibration", "Retractions", "Paper record"]);
    expect(screen.queryByText("No results.")).not.toBeInTheDocument();
  });
});
