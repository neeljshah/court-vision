"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { matchesResearchPopulation, researchComparisonPolicy } from "@/lib/analytics/researchComparisonPolicy";
import type { ResearchAnalysis } from "@/lib/analytics/researchTypes";

type View = { metric: string; second: string; group: string; population: string; query: string; ascending: boolean; view: string; row: string };
const defaults = (a: ResearchAnalysis): View => {
  const comparison = researchComparisonPolicy(a.rows, a);
  return { metric: a.fields[0].key, second: a.fields[1]?.key || a.fields[0].key, group: "all", population: comparison.compatible ? "all" : comparison.populations.find(item => item.compatibility === "compatible")?.key || "all", query: "", ascending: false, view: "rank", row: "" };
};
const parameters = { metric: "metric", second: "y", group: "group", population: "population", query: "q", ascending: "order", view: "view", row: "row" } as const;

function visibleRows(a: ResearchAnalysis, view: View) {
  const comparison = researchComparisonPolicy(a.rows, a);
  if (comparison.compatible) return a.rows.filter(row => view.group === "all" || row.group === view.group);
  if (view.population === "all") return a.rows;
  const population = comparison.populations.find(item => item.key === view.population);
  return population ? a.rows.filter(row => matchesResearchPopulation(row, population)) : [];
}

function validateRow(a: ResearchAnalysis, next: View): View {
  const comparison = researchComparisonPolicy(a.rows, a), initial = defaults(a);
  if (!comparison.compatible && next.population !== "all" && !comparison.populations.some(item => item.key === next.population)) next.population = initial.population;
  const terms = next.query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  const aggregateIds = new Set(comparison.aggregateRows.map(row => row.id));
  const selected = visibleRows(a, next).find(r => r.id === next.row && (aggregateIds.has(r.id) || terms.every(t => `${r.label} ${r.group} ${r.note || ""}`.toLowerCase().includes(t))));
  return { ...next, row: selected?.id || "" };
}

function readView(a: ResearchAnalysis): View {
  const p = new URLSearchParams(window.location.search), next = defaults(a);
  if (a.fields.some(f => f.key === p.get("metric"))) next.metric = p.get("metric")!;
  if (a.fields.some(f => f.key === p.get("y"))) next.second = p.get("y")!;
  if (a.rows.some(r => r.group === p.get("group"))) next.group = p.get("group")!;
  if (p.get("population")) next.population = p.get("population")!;
  next.query = p.get("q") || "";
  next.ascending = p.get("order") === "asc";
  if (["rank", "scatter", "table", "distribution"].includes(p.get("view") || "")) next.view = p.get("view")!;
  next.row = p.get("row") || "";
  return validateRow(a, next);
}

type Snapshot = { analysis: ResearchAnalysis; view: View };

export function useResearchView(a: ResearchAnalysis) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const latest = useRef<Snapshot | null>(null);
  const publish = useCallback((view: View) => {
    const next = { analysis: a, view: validateRow(a, view) };
    latest.current = next;
    setSnapshot(next);
  }, [a]);
  useEffect(() => {
    const restore = () => publish(readView(a));
    // Accepted input may precede this passive effect, including StrictMode replay.
    if (latest.current?.analysis !== a) restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [a, publish]);
  useEffect(() => {
    // A newer input or navigation invalidates effects from an older render.
    if (!snapshot || snapshot.analysis !== a || latest.current !== snapshot) return;
    const state = snapshot.view;
    const url = new URL(window.location.href), initial = defaults(a);
    for (const key of Object.keys(parameters) as (keyof View)[]) {
      if (state[key] === initial[key]) url.searchParams.delete(parameters[key]);
      else url.searchParams.set(parameters[key], key === "ascending" ? "asc" : String(state[key]));
    }
    window.history.replaceState(window.history.state, "", url);
  }, [a, snapshot]);
  return {
    state: snapshot?.analysis === a ? snapshot.view : defaults(a),
    change: (patch: Partial<View>) => publish({ ...(latest.current?.analysis === a ? latest.current.view : readView(a)), ...patch }),
    reset: () => publish(defaults(a)),
  };
}
