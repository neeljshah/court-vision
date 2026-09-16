import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { RankedPlot, ScatterPlot } from "./LabPlot";
import type { LabField, LabRow } from "@/lib/analytics/labTypes";

const x: LabField = { key: "x", label: "X measure", unit: "number" };
const y: LabField = { key: "y", label: "Y measure", unit: "number" };
const row = (id: string, xv: number | null, yv: number | null): LabRow =>
  ({ id, label: id.toUpperCase(), group: "test", values: { x: xv, y: yv } });

describe("LabPlot", () => {
  it("centers constant scatter values on distinct, padded axes", () => {
    const { container } = render(<ScatterPlot rows={[row("a", 5, 10), row("b", 5, 10)]} x={x} y={y} onSelect={() => {}} />);
    const points = [...container.querySelectorAll("circle")];
    expect(points).toHaveLength(2);
    expect(points[0].getAttribute("cx")).toBe(points[1].getAttribute("cx"));
    expect(points[0].getAttribute("cy")).toBe(points[1].getAttribute("cy"));
    expect(Number(points[0].getAttribute("cx"))).toBeGreaterThan(75);
    expect(Number(points[0].getAttribute("cy"))).toBeGreaterThan(24);
    expect(new Set([...container.querySelectorAll("text")].map(node => node.textContent)).size).toBeGreaterThan(4);
    expect(screen.getByText(/constant measurements receive symmetric axis padding/i)).toBeInTheDocument();
  });

  it("excludes null and nonfinite scatter pairs and supports keyboard selection", () => {
    const onSelect = vi.fn();
    render(<ScatterPlot rows={[row("valid", 1, 2), row("missing", null, 2), row("infinite", 1, Infinity)]} x={x} y={y} onSelect={onSelect} />);
    expect(screen.getByText(/^1 paired row/)).toBeInTheDocument();
    const point = screen.getByRole("button", { name: /^Inspect VALID/ });
    fireEvent.keyDown(point, { key: " " });
    fireEvent.keyDown(point, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledTimes(2);
  });

  it("keeps one scatter point in tab order and roves through source-order points", () => {
    const onSelect = vi.fn();
    render(<ScatterPlot rows={Array.from({ length: 24 }, (_, i) => row(`row-${i}`, i, i + 1))} x={x} y={y} onSelect={onSelect} />);
    const points = screen.getAllByRole("button", { name: /^Inspect ROW/ });
    expect(points.filter(point => point.getAttribute("tabindex") === "0")).toHaveLength(1);
    points[0].focus();
    fireEvent.keyDown(points[0], { key: "ArrowRight" });
    expect(points[1]).toHaveFocus();
    fireEvent.keyDown(points[1], { key: "ArrowLeft" });
    expect(points[0]).toHaveFocus();
    fireEvent.keyDown(points[0], { key: "End" });
    expect(points[23]).toHaveFocus();
    fireEvent.keyDown(points[23], { key: "Home" });
    expect(points[0]).toHaveFocus();
    fireEvent.keyDown(points[0], { key: "Enter" });
    fireEvent.keyDown(points[0], { key: " " });
    expect(onSelect).toHaveBeenCalledTimes(2);
    expect(screen.getByText(/Arrow keys to move through paired rows in the current row order/)).toBeInTheDocument();
  });

  it("recovers a valid tab stop when filtering removes the active point", () => {
    function FilteredScatter() {
      const [rows, setRows] = useState([row("first", 1, 2), row("active", 2, 3), row("last", 3, 4)]);
      return <><button onClick={() => setRows([rows[0], rows[2]])}>Remove active point</button><ScatterPlot rows={rows} x={x} y={y} onSelect={() => {}} /></>;
    }
    render(<FilteredScatter />);
    const active = screen.getByRole("button", { name: /^Inspect ACTIVE/ });
    fireEvent.focus(active);
    fireEvent.click(screen.getByRole("button", { name: "Remove active point" }));
    const points = screen.getAllByRole("button", { name: /^Inspect/ });
    expect(points.filter(point => point.getAttribute("tabindex") === "0")).toHaveLength(1);
    expect(screen.getByRole("button", { name: /^Inspect FIRST/ })).toHaveAttribute("tabindex", "0");
  });

  it("draws mixed-sign bars from zero and omits nonnumeric rows", () => {
    const { container } = render(<RankedPlot rows={[row("positive", 2, 0), row("negative", -1, 0), row("missing", null, 0)]} field={x} onSelect={() => {}} />);
    expect(screen.getAllByRole("button")).toHaveLength(2);
    expect(container.querySelector(".lab-bar-positive")).toHaveStyle({ left: "33.33333333333333%", width: "66.66666666666667%" });
    expect(container.querySelector(".lab-bar-negative")).toHaveStyle({ left: "0%", width: "33.33333333333333%" });
    expect(screen.getByText(/Showing 2 of 2 matching numeric rows/)).toBeInTheDocument();
  });

  it("keeps ranked entity rows as inspector buttons when an entity route exists", () => {
    const onSelect = vi.fn();
    const linked = { ...row("linked", 2, 0), href: "/analytics/players/nba_players/linked" };
    render(<RankedPlot rows={[linked]} field={x} onSelect={onSelect} />);
    const bar = screen.getByRole("button", { name: /^Inspect LINKED/ });
    expect(bar).not.toHaveAttribute("href");
    fireEvent.click(bar);
    expect(onSelect).toHaveBeenCalledWith(linked);
  });
});
