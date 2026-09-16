import type { Metadata } from "next";
import Workspace from "@/components/analytics/workspace/Workspace";
import { getDashboardData } from "@/lib/analytics/dashboardData";
import { loadHomeCalibrationExample } from "@/lib/analytics/homeCalibrationExample.server";
import "./workspace.css";
import "./overview.css";

export const metadata: Metadata = {
  title: { absolute: "CourtVision Analytics | Forecast Calibration Workspace" },
  description: "Read published forecast calibration examples, source-linked research, and descriptive player and team profiles.",
};
export default function AnalyticsHome() {
  return <Workspace data={getDashboardData()} calibrationExample={loadHomeCalibrationExample()} />;
}
