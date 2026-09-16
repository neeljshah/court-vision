import type { Sport } from "@/lib/analytics/dashboardTypes";
import { labComparisonPolicy, matchesLabCohort } from "@/lib/analytics/labComparisonPolicy";
import type { LabData } from "@/lib/analytics/labTypes";

export type LabViewState = {
  id: string;
  sport: Sport;
  fieldKey: string;
  otherKey: string;
  mode: "rank" | "scatter" | "table" | "distribution";
  query: string;
  group: string;
  ascending: boolean;
  selectedId: string | null;
  cohort: string | null;
  allCohorts: boolean;
};

const sports = new Set<Sport>(["all", "nba", "mlb", "soccer", "tennis"]);
const modes = new Set<LabViewState["mode"]>(["rank", "scatter", "table", "distribution"]);
const sportGroup = (sport: Sport) => sport === "soccer" ? "INTERNATIONAL SOCCER" : sport.toUpperCase();
const rowsForSport = (dataset: LabData["datasets"][number], sport: Sport) =>
  dataset.sport === "all" && sport !== "all" ? dataset.rows.filter(row => row.group === sportGroup(sport)) : dataset.rows;

export function readLabViewState(search: string, data: LabData): LabViewState {
  const params = new URLSearchParams(search);
  const sport = sports.has(params.get("sport") as Sport) ? params.get("sport") as Sport : "all";
  const eligible = data.datasets.filter(dataset => sport === "all" || dataset.sport === sport || dataset.sport === "all");
  const requested = data.datasets.find(dataset => dataset.id === params.get("dataset"));
  const dataset = requested && eligible.includes(requested) ? requested : eligible[0] || data.datasets[0];
  const fieldKey = dataset.fields.some(field => field.key === params.get("field")) ? params.get("field")! : dataset.fields[0].key;
  const otherKey = dataset.fields.some(field => field.key === params.get("other")) ? params.get("other")! : dataset.fields[1]?.key || fieldKey;
  const mode = modes.has(params.get("view") as LabViewState["mode"]) ? params.get("view") as LabViewState["mode"] : "rank";
  const query = params.get("q") || "";
  const rows = rowsForSport(dataset, sport);
  const comparison = labComparisonPolicy(rows);
  const requestedCohort = comparison.cohorts.find(cohort => cohort.key === params.get("cohort"));
  const cohort = comparison.compatibility === "compatible" ? null : (requestedCohort || comparison.cohorts[0])?.key || null;
  const allCohorts = comparison.compatibility !== "compatible" && ["true", "1"].includes(params.get("allCohorts") || "");
  const group = params.get("group");
  const safeGroup = group === "all" || rows.some(row => row.group === group) ? group || "all" : "all";
  const cohortRows = cohort ? rows.filter(row => matchesLabCohort(row, comparison.cohorts.find(item => item.key === cohort)!)) : rows;
  const baseRows = comparison.compatibility === "compatible" ? rows.filter(row => safeGroup === "all" || row.group === safeGroup) : allCohorts ? rows : cohortRows;
  const visible = baseRows.filter(row => `${row.label} ${row.group} ${row.note || ""}`.toLowerCase().includes(query.toLowerCase()));
  const requestedRow = params.get("row");
  return { id: dataset.id, sport, fieldKey, otherKey, mode, query, group: safeGroup, ascending: params.get("order") === "asc", selectedId: visible.some(row => row.id === requestedRow) ? requestedRow : null, cohort, allCohorts };
}

export function labViewSearch(search: string, state: LabViewState): string {
  const params = new URLSearchParams(search);
  ["sport", "dataset", "field", "other", "group", "order", "view", "q", "row", "cohort", "allCohorts"].forEach(key => params.delete(key));
  params.set("sport", state.sport);
  params.set("dataset", state.id);
  params.set("field", state.fieldKey);
  params.set("other", state.otherKey);
  params.set("group", state.group);
  params.set("order", state.ascending ? "asc" : "desc");
  params.set("view", state.mode);
  if (state.query) params.set("q", state.query);
  if (state.selectedId) params.set("row", state.selectedId);
  if (state.cohort) params.set("cohort", state.cohort);
  if (state.allCohorts) params.set("allCohorts", "true");
  return params.toString();
}
