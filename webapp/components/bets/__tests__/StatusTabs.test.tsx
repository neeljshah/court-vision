import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { StatusTabs } from "../StatusTabs";

// StatusTabs.test.tsx -- per-component vitest covering the ARIA tab pattern:
//   - role=tablist + role=tab structure
//   - Roving tabindex (active=0, inactive=-1)
//   - ArrowRight / ArrowLeft / Home / End move selection via onChange
//   - aria-controls wiring to the panel id
//   - count badges render without $ (honest rails)

const PANEL_ID = "bets-board-panel";

function renderTabs(
  value: "live" | "pregame" | "done" = "pregame",
  counts = { live: 3, pregame: 7, done: 0 },
  onChange = vi.fn(),
) {
  return { onChange, ...render(
    <StatusTabs
      value={value}
      onChange={onChange}
      counts={counts}
      panelId={PANEL_ID}
    />,
  )};
}

// Helper: fire a keydown with the given key on the given element.
function key(el: Element, k: string) {
  fireEvent.keyDown(el, { key: k, bubbles: true });
}

describe("StatusTabs -- ARIA structure", () => {
  it("renders exactly one role=tablist with aria-label", () => {
    renderTabs();
    const list = screen.getByRole("tablist");
    expect(list).toBeInTheDocument();
    expect(list).toHaveAttribute("aria-label", "Bet status filter");
  });

  it("renders exactly 3 role=tab buttons", () => {
    renderTabs();
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(3);
  });

  it("each tab has aria-controls pointing at the panel id", () => {
    renderTabs();
    const tabs = screen.getAllByRole("tab");
    tabs.forEach((tab) => {
      expect(tab).toHaveAttribute("aria-controls", PANEL_ID);
    });
  });

  it("each tab has a stable id with the expected pattern", () => {
    renderTabs();
    expect(screen.getByRole("tab", { name: /live/i })).toHaveAttribute(
      "id",
      "status-tab-live",
    );
    expect(screen.getByRole("tab", { name: /pregame/i })).toHaveAttribute(
      "id",
      "status-tab-pregame",
    );
    expect(screen.getByRole("tab", { name: /done/i })).toHaveAttribute(
      "id",
      "status-tab-done",
    );
  });
});

describe("StatusTabs -- roving tabIndex", () => {
  it("active tab has tabIndex=0, inactive tabs have tabIndex=-1", () => {
    renderTabs("pregame");
    const tabs = screen.getAllByRole("tab");
    const liveTab = screen.getByRole("tab", { name: /live/i });
    const pregameTab = screen.getByRole("tab", { name: /pregame/i });
    const doneTab = screen.getByRole("tab", { name: /done/i });

    expect(pregameTab).toHaveAttribute("tabIndex", "0");
    expect(liveTab).toHaveAttribute("tabIndex", "-1");
    expect(doneTab).toHaveAttribute("tabIndex", "-1");
    // Exactly one tab in the tablist should have tabIndex=0.
    const withZero = tabs.filter((t) => t.getAttribute("tabIndex") === "0");
    expect(withZero).toHaveLength(1);
  });

  it("live tab is tabIndex=0 when value=live", () => {
    renderTabs("live");
    expect(screen.getByRole("tab", { name: /live/i })).toHaveAttribute(
      "tabIndex",
      "0",
    );
    expect(screen.getByRole("tab", { name: /pregame/i })).toHaveAttribute(
      "tabIndex",
      "-1",
    );
  });

  it("done tab is tabIndex=0 when value=done", () => {
    renderTabs("done");
    expect(screen.getByRole("tab", { name: /done/i })).toHaveAttribute(
      "tabIndex",
      "0",
    );
  });
});

describe("StatusTabs -- aria-selected", () => {
  it("only the active tab has aria-selected=true", () => {
    renderTabs("pregame");
    const tabs = screen.getAllByRole("tab");
    const selected = tabs.filter(
      (t) => t.getAttribute("aria-selected") === "true",
    );
    expect(selected).toHaveLength(1);
    expect(selected[0]).toHaveAttribute("id", "status-tab-pregame");
  });
});

describe("StatusTabs -- keyboard navigation (ArrowRight/Left/Home/End)", () => {
  it("ArrowRight from pregame calls onChange with done (next)", () => {
    const { onChange } = renderTabs("pregame");
    key(screen.getByRole("tab", { name: /pregame/i }), "ArrowRight");
    expect(onChange).toHaveBeenCalledWith("done");
  });

  it("ArrowLeft from pregame calls onChange with live (prev)", () => {
    const { onChange } = renderTabs("pregame");
    key(screen.getByRole("tab", { name: /pregame/i }), "ArrowLeft");
    expect(onChange).toHaveBeenCalledWith("live");
  });

  it("ArrowRight from done wraps to live (first)", () => {
    const { onChange } = renderTabs("done");
    key(screen.getByRole("tab", { name: /done/i }), "ArrowRight");
    expect(onChange).toHaveBeenCalledWith("live");
  });

  it("ArrowLeft from live wraps to done (last)", () => {
    const { onChange } = renderTabs("live");
    key(screen.getByRole("tab", { name: /live/i }), "ArrowLeft");
    expect(onChange).toHaveBeenCalledWith("done");
  });

  it("Home always calls onChange with live (first tab)", () => {
    const { onChange } = renderTabs("done");
    key(screen.getByRole("tab", { name: /done/i }), "Home");
    expect(onChange).toHaveBeenCalledWith("live");
  });

  it("End always calls onChange with done (last tab)", () => {
    const { onChange } = renderTabs("live");
    key(screen.getByRole("tab", { name: /live/i }), "End");
    expect(onChange).toHaveBeenCalledWith("done");
  });

  it("other keys (e.g. Tab) do not call onChange", () => {
    const { onChange } = renderTabs("pregame");
    key(screen.getByRole("tab", { name: /pregame/i }), "Tab");
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("StatusTabs -- count badges", () => {
  it("shows count badges for non-zero counts", () => {
    renderTabs("pregame", { live: 3, pregame: 7, done: 0 });
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    // done=0 badge should NOT appear
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("no $ in the DOM (honest rails: units not dollars)", () => {
    const { container } = renderTabs("pregame", { live: 5, pregame: 2, done: 1 });
    expect(container.textContent || "").not.toMatch(/\$\s?\d/);
  });
});

describe("StatusTabs -- click selection", () => {
  it("clicking a tab calls onChange with its key", () => {
    const { onChange } = renderTabs("pregame");
    fireEvent.click(screen.getByRole("tab", { name: /live/i }));
    expect(onChange).toHaveBeenCalledWith("live");
  });
});

describe("StatusTabs -- defaults", () => {
  it("uses default panelId when not provided", () => {
    const onChange = vi.fn();
    render(<StatusTabs value="pregame" onChange={onChange} />);
    screen.getAllByRole("tab").forEach((tab) => {
      expect(tab).toHaveAttribute("aria-controls", "bets-board-panel");
    });
  });
});
