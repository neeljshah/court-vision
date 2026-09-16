import { describe, expect, it } from "vitest";
import { pitchSequencingViewSearch, readPitchSequencingViewState, readResidualAnatomyViewState, residualAnatomyViewSearch } from "./inspectorViewState";
import type { PitchSequencingData } from "./pitchSequencing";
import type { ResidualAnatomyData } from "./residualAnatomy";

const pitch: PitchSequencingData = { pitchTypes: ["FF", "SL"], rowMinN: 200, asOf: null, classes: [{ id: "all", definition: "", overlapping: false, coverage: null, rowNFrom: [], rowBelowFloor: [], countMatrix: [], probabilityMatrix: [] }, { id: "behind", definition: "", overlapping: false, coverage: null, rowNFrom: [], rowBelowFloor: [], countMatrix: [], probabilityMatrix: [] }] };
const residual: ResidualAnatomyData = { exclusions: [], sports: [{ sport: "mlb", nFiles: null, nRecords: null, nSkipped: null, timeBuckets: [], probBuckets: [], grid: [], rankings: { byVolume: [], byPerRowError: [] }, segments: [{ sport: "mlb", timeBucket: "early", probBucket: "0-.2", n: 2, meanAbsResidual: 0.2, totalAbsResidualMass: 0.4 }, { sport: "mlb", timeBucket: "late", probBucket: ".2-.4", n: 1, meanAbsResidual: 0.8, totalAbsResidualMass: 0.8 }] }, { sport: "soccer_intl", nFiles: null, nRecords: null, nSkipped: null, timeBuckets: [], probBuckets: [], grid: [], rankings: { byVolume: [], byPerRowError: [] }, segments: [{ sport: "soccer_intl", timeBucket: "0-15", probBucket: "0-.2", n: 3, meanAbsResidual: 0.3, totalAbsResidualMass: 0.9 }] }] };

describe("inspector view state", () => {
  it("round-trips pitch sequencing selections and keeps unrelated parameters", () => {
    const state = readPitchSequencingViewState("?class=behind&from=SL&to=FF", pitch);
    expect(state).toEqual({ classId: "behind", from: "SL", to: "FF" });
    expect(pitchSequencingViewSearch("?utm=shared", state, pitch)).toBe("utm=shared&class=behind&from=SL&to=FF");
  });

  it("round-trips residual selections", () => {
    const state = readResidualAnatomyViewState("?sport=soccer_intl&time=0-15&prob=0-.2&metric=n", residual);
    expect(state).toEqual({ sport: "soccer_intl", time: "0-15", prob: "0-.2", metric: "n" });
    expect(residualAnatomyViewSearch("", state, residual)).toBe("sport=soccer_intl&time=0-15&prob=0-.2&metric=n");
    const sameSport = readResidualAnatomyViewState("?sport=mlb&time=late&prob=.2-.4", residual);
    expect(readResidualAnatomyViewState(`?${residualAnatomyViewSearch("", sameSport, residual)}`, residual)).toEqual(sameSport);
  });

  it("falls back to defaults and drops invalid inspector parameters", () => {
    const pitchState = readPitchSequencingViewState("?class=nope&from=bad&to=bad", pitch);
    expect(pitchState).toEqual({ classId: "all", from: "FF", to: "FF" });
    expect(pitchSequencingViewSearch("?class=nope&from=bad&to=bad&keep=yes", pitchState, pitch)).toBe("keep=yes");
    const residualState = readResidualAnatomyViewState("?sport=nope&time=bad&prob=bad&metric=wrong", residual);
    expect(residualState).toEqual({ sport: "mlb", time: "early", prob: "0-.2", metric: "totalAbsResidualMass" });
    expect(residualAnatomyViewSearch("?sport=nope&time=bad&prob=bad&metric=wrong&keep=yes", residualState, residual)).toBe("keep=yes");
  });
});
