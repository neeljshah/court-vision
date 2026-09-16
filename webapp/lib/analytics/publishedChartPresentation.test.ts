import { expect, it } from "vitest";
import { getPublishedChartPresentation, publishedChartPresentation } from "./publishedChartPresentation";

it("records a reviewed presentation for every published module", () => {
  expect(Object.keys(publishedChartPresentation)).toHaveLength(74);
  expect(getPublishedChartPresentation("ctx_team_states")).toMatchObject({ approved: false, moduleId: "ctx_team_states" });
  expect(getPublishedChartPresentation("micro_absorption")).toMatchObject({ approved: false, moduleId: "micro_absorption" });
  expect(getPublishedChartPresentation("blowout_dynamics")).toMatchObject({ approved: true, moduleId: "blowout_dynamics" });
});
