// SportTabs -- renders MLB / Soccer / Tennis tabs; clicking calls onChange with the sport value.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SportTabs } from "@/components/board/SportTabs";

describe("SportTabs", () => {
  it("renders three tabs: MLB, Soccer, Tennis", () => {
    render(<SportTabs sport="mlb" onChange={vi.fn()} />);
    expect(screen.getByRole("tab", { name: "MLB" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Soccer" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Tennis" })).toBeInTheDocument();
  });

  it("calls onChange with 'soccer' when the Soccer tab is clicked", async () => {
    const onChange = vi.fn();
    render(<SportTabs sport="mlb" onChange={onChange} />);
    await userEvent.click(screen.getByRole("tab", { name: "Soccer" }));
    expect(onChange).toHaveBeenCalledWith("soccer");
  });

  it("calls onChange with 'tennis' when the Tennis tab is clicked", async () => {
    const onChange = vi.fn();
    render(<SportTabs sport="mlb" onChange={onChange} />);
    await userEvent.click(screen.getByRole("tab", { name: "Tennis" }));
    expect(onChange).toHaveBeenCalledWith("tennis");
  });
});
