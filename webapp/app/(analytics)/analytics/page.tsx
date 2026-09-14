import type { Metadata } from "next";
import Workspace from "@/components/analytics/workspace/Workspace";
import { getDashboardData } from "@/lib/analytics/dashboardData";
import "./workspace.css";

export const metadata: Metadata = {
  title: { absolute: "CourtVision Analytics | Sports Intelligence Workspace" },
  description: "Explore four sports through interactive model comparisons, a searchable research ledger, player and team profiles, and source-linked analytics.",
};
export default function AnalyticsHome() {
  return <Workspace data={getDashboardData()} />;
}
