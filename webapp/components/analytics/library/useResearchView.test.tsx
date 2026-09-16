import { act, render, screen } from "@testing-library/react";
import { StrictMode, useLayoutEffect, useRef } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useResearchView } from "./useResearchView";
import type { ResearchAnalysis } from "@/lib/analytics/researchTypes";

const analysis: ResearchAnalysis = {
  id: "first", title: "First", sport: "nba", category: "Test", source: "test", description: "Test", scope: "Test", caveat: "Test", status: "published", formula: "Test", interpretation: "Test", references: [], novelty: "Derived analysis",
  fields: [{ key: "score", label: "Score", unit: "number" }, { key: "rate", label: "Rate", unit: "percent" }],
  rows: [{ id: "alpha", label: "Alpha", group: "East", values: { score: 1, rate: 0.5 } }, { id: "beta", label: "Beta", group: "West", values: { score: 2, rate: 0.25 } }],
};

const replacement: ResearchAnalysis = {
  ...analysis,
  id: "second",
  fields: [{ key: "pace", label: "Pace", unit: "number" }, { key: "rating", label: "Rating", unit: "number" }],
  rows: [{ id: "gamma", label: "Gamma", group: "North", values: { pace: 99, rating: 4 } }],
};

const sameIdReplacement: ResearchAnalysis = { ...replacement, id: analysis.id };

function State({ a, intent }: { a: ResearchAnalysis; intent?: "query" | "reset" | "multiple" }) {
  const { state, change, reset } = useResearchView(a);
  const accepted = useRef(false);
  useLayoutEffect(() => {
    if (accepted.current) return;
    accepted.current = true;
    if (intent === "query") change({ query: "Alpha", view: "table" });
    if (intent === "reset") reset();
    if (intent === "multiple") {
      change({ query: "Alpha" });
      change({ group: "East", view: "table" });
    }
  }, [change, intent, reset]);
  return <output data-testid="state">{JSON.stringify(state)}</output>;
}

const view = () => JSON.parse(screen.getByTestId("state").textContent || "{}") as ReturnType<typeof useResearchView>["state"];

beforeEach(() => window.history.replaceState(null, "", "/analytics/research/first/"));
afterEach(() => window.history.replaceState(null, "", "/analytics/research/first/"));

describe("useResearchView hydration intent", () => {
  it("keeps an early query over restored valid fields and preserves unrelated URL parameters", () => {
    window.history.replaceState(null, "", "?metric=rate&group=East&utm_source=shared");
    render(<State a={analysis} intent="query" />);

    expect(view()).toMatchObject({ metric: "rate", group: "East", query: "Alpha", view: "table" });
    const params = new URLSearchParams(window.location.search);
    expect(params.get("q")).toBe("Alpha");
    expect(params.get("view")).toBe("table");
    expect(params.get("utm_source")).toBe("shared");
  });

  it("keeps an early reset over URL restoration", () => {
    window.history.replaceState(null, "", "?metric=rate&group=East&q=Alpha&view=table&utm_source=shared");
    render(<State a={analysis} intent="reset" />);

    expect(view()).toMatchObject({ metric: "score", second: "rate", group: "all", query: "", view: "rank" });
    const params = new URLSearchParams(window.location.search);
    expect(params.get("metric")).toBeNull();
    expect(params.get("utm_source")).toBe("shared");
  });

  it("clears a URL-selected row made incompatible by an early query", () => {
    window.history.replaceState(null, "", "?metric=rate&row=beta&utm_source=shared");
    render(<State a={analysis} intent="query" />);

    expect(view()).toMatchObject({ metric: "rate", query: "Alpha", row: "" });
    const params = new URLSearchParams(window.location.search);
    expect(params.get("row")).toBeNull();
    expect(params.get("utm_source")).toBe("shared");
  });

  it("preserves multiple early patches made before passive hydration", () => {
    window.history.replaceState(null, "", "?metric=rate&utm_source=shared");
    render(<State a={analysis} intent="multiple" />);

    expect(view()).toMatchObject({ metric: "rate", group: "East", query: "Alpha", view: "table" });
    expect(new URLSearchParams(window.location.search).get("utm_source")).toBe("shared");
  });

  it("lets a later popstate replace an early intent", () => {
    window.history.replaceState(null, "", "?metric=rate&utm_source=shared");
    render(<State a={analysis} intent="query" />);

    act(() => {
      window.history.pushState(null, "", "?metric=score&group=West&q=Beta&view=distribution&utm_source=shared");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    expect(view()).toMatchObject({ metric: "score", group: "West", query: "Beta", view: "distribution" });
    expect(new URLSearchParams(window.location.search).get("utm_source")).toBe("shared");
  });

  it("restores against the current analysis identity when it changes", () => {
    window.history.replaceState(null, "", "?metric=rate&utm_source=shared");
    const rendered = render(<State a={analysis} />);
    expect(view().metric).toBe("rate");

    rendered.rerender(<State a={replacement} />);

    expect(view()).toMatchObject({ metric: "pace", second: "rating", group: "all" });
    expect(new URLSearchParams(window.location.search).get("utm_source")).toBe("shared");
  });

  it("restores a replacement schema even when its analysis id is unchanged", () => {
    window.history.replaceState(null, "", "?metric=rate&utm_source=shared");
    const rendered = render(<State a={analysis} />);
    expect(view().metric).toBe("rate");

    rendered.rerender(<State a={sameIdReplacement} />);

    expect(view()).toMatchObject({ metric: "pace", second: "rating", group: "all" });
    const params = new URLSearchParams(window.location.search);
    expect(params.get("metric")).toBeNull();
    expect(params.get("utm_source")).toBe("shared");
  });

  it("keeps an early query in StrictMode", () => {
    window.history.replaceState(null, "", "?metric=rate&utm_source=shared");
    render(<StrictMode><State a={analysis} intent="query" /></StrictMode>);

    expect(view()).toMatchObject({ metric: "rate", query: "Alpha", view: "table" });
  });
});
