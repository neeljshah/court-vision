import { ForecasterReport } from "./ForecasterReport";
import { loadForecasterArms } from "./forecaster.server";
import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo/meta";

export const metadata: Metadata = pageMeta("/analytics/forecaster/", {
  title: "The Forecaster",
  description: "Published calibration checks for pregame and in-game forecasts.",
});

export default function ForecasterPage() {
  return <ForecasterReport data={loadForecasterArms()} />;
}
