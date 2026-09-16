import type { PitchSequencingData } from "./pitchSequencing";
import type { ResidualAnatomyData, ResidualMetric, ResidualSegment } from "./residualAnatomy";

export type PitchSequencingViewState = { classId: string; from: string; to: string };
export type ResidualAnatomyViewState = { sport: string; time: string; prob: string; metric: ResidualMetric };

const residualMetrics = new Set<ResidualMetric>(["n", "meanAbsResidual", "totalAbsResidualMass"]);

function pitchDefaults(data: PitchSequencingData): PitchSequencingViewState {
  return { classId: data.classes[0]?.id || "", from: data.pitchTypes[0] || "", to: data.pitchTypes[0] || "" };
}

function residualDefaults(data: ResidualAnatomyData): ResidualAnatomyViewState {
  const first = data.sports[0]?.segments[0];
  return { sport: first?.sport || data.sports[0]?.sport || "", time: first?.timeBucket || "", prob: first?.probBucket || "", metric: "totalAbsResidualMass" };
}

function selectionFor(data: ResidualAnatomyData, sport: string, time: string, prob: string): ResidualSegment | undefined {
  return data.sports.find(item => item.sport === sport)?.segments.find(item => item.timeBucket === time && item.probBucket === prob);
}

export function readPitchSequencingViewState(search: string, data: PitchSequencingData): PitchSequencingViewState {
  const defaults = pitchDefaults(data);
  const params = new URLSearchParams(search);
  const classId = data.classes.some(item => item.id === params.get("class")) ? params.get("class")! : defaults.classId;
  const from = data.pitchTypes.includes(params.get("from") || "") ? params.get("from")! : defaults.from;
  const to = data.pitchTypes.includes(params.get("to") || "") ? params.get("to")! : defaults.to;
  return { classId, from, to };
}

export function pitchSequencingViewSearch(search: string, state: PitchSequencingViewState, data: PitchSequencingData): string {
  const params = new URLSearchParams(search);
  ["class", "from", "to"].forEach(key => params.delete(key));
  const defaults = pitchDefaults(data);
  if (state.classId !== defaults.classId) params.set("class", state.classId);
  if (state.from !== defaults.from || state.to !== defaults.to) {
    params.set("from", state.from);
    params.set("to", state.to);
  }
  return params.toString();
}

export function readResidualAnatomyViewState(search: string, data: ResidualAnatomyData): ResidualAnatomyViewState {
  const defaults = residualDefaults(data);
  const params = new URLSearchParams(search);
  const requested = selectionFor(data, params.get("sport") || "", params.get("time") || "", params.get("prob") || "");
  const metric = residualMetrics.has(params.get("metric") as ResidualMetric) ? params.get("metric") as ResidualMetric : defaults.metric;
  return requested ? { sport: requested.sport, time: requested.timeBucket, prob: requested.probBucket, metric } : { ...defaults, metric };
}

export function residualAnatomyViewSearch(search: string, state: ResidualAnatomyViewState, data: ResidualAnatomyData): string {
  const params = new URLSearchParams(search);
  ["sport", "time", "prob", "metric"].forEach(key => params.delete(key));
  const defaults = residualDefaults(data);
  const selected = selectionFor(data, state.sport, state.time, state.prob);
  const changedSelection = selected && (state.sport !== defaults.sport || state.time !== defaults.time || state.prob !== defaults.prob);
  if (changedSelection) {
    params.set("sport", state.sport);
    params.set("time", state.time);
    params.set("prob", state.prob);
  }
  if (residualMetrics.has(state.metric) && state.metric !== defaults.metric) params.set("metric", state.metric);
  return params.toString();
}
