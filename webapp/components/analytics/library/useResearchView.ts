"use client";
import { useEffect, useState } from "react";
import type { ResearchAnalysis } from "@/lib/analytics/researchTypes";

type View = { metric: string; second: string; group: string; query: string; ascending: boolean; view: string; row: string };
const defaults = (a: ResearchAnalysis): View => ({ metric: a.fields[0].key, second: a.fields[1]?.key || a.fields[0].key, group: "all", query: "", ascending: false, view: "rank", row: "" });
const parameters = { metric: "metric", second: "y", group: "group", query: "q", ascending: "order", view: "view", row: "row" } as const;

export function useResearchView(a: ResearchAnalysis) {
  const [state, setState] = useState(() => defaults(a));
  const [ready, setReady] = useState("");
  useEffect(() => {
    const restore = () => {
      const p = new URLSearchParams(window.location.search), next = defaults(a);
      if (a.fields.some(f => f.key === p.get("metric"))) next.metric = p.get("metric")!;
      if (a.fields.some(f => f.key === p.get("y"))) next.second = p.get("y")!;
      if (a.rows.some(r => r.group === p.get("group"))) next.group = p.get("group")!;
      next.query = p.get("q") || "";
      next.ascending = p.get("order") === "asc";
      if (["rank", "scatter", "table"].includes(p.get("view") || "")) next.view = p.get("view")!;
      const terms = next.query.toLowerCase().trim().split(/\s+/).filter(Boolean);
      const selected = a.rows.find(r => r.id === p.get("row") && (next.group === "all" || r.group === next.group) && terms.every(t => `${r.label} ${r.group} ${r.note || ""}`.toLowerCase().includes(t)));
      next.row = selected?.id || "";
      setState(next); setReady(a.id);
    };
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [a]);
  useEffect(() => {
    if (ready !== a.id) return;
    const url = new URL(window.location.href), initial = defaults(a);
    for (const key of Object.keys(parameters) as (keyof View)[]) {
      if (state[key] === initial[key]) url.searchParams.delete(parameters[key]);
      else url.searchParams.set(parameters[key], key === "ascending" ? "asc" : String(state[key]));
    }
    window.history.replaceState(window.history.state, "", url);
  }, [a, ready, state]);
  return { state: ready === a.id ? state : defaults(a), change: (patch: Partial<View>) => setState(previous => ({ ...previous, ...patch })), reset: () => setState(defaults(a)) };
}
