import { fireEvent, render, screen } from "@testing-library/react";
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

  it("draws mixed-sign bars from zero and omits nonnumeric rows", () => {
    const { container } = render(<RankedPlot rows={[row("positive", 2, 0), row("negative", -1, 0), row("missing", null, 0)]} field={x} onSelect={() => {}} />);
    expect(screen.getAllByRole("button")).toHaveLength(2);
    expect(container.querySelector(".lab-bar-positive")).toHaveStyle({ left: "33.33333333333333%", width: "66.66666666666667%" });
    expect(container.querySelector(".lab-bar-negative")).toHaveStyle({ left: "0%", width: "33.33333333333333%" });
    expect(screen.getByText(/Showing 2 of 2 matching numeric rows/)).toBeInTheDocument();
  });
});
