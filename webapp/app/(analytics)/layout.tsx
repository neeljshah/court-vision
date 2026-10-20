// app/(analytics)/layout.tsx -- the /analytics/* group: its stylesheets and the shared
// shell. <html>/<body>, the theme init, fonts, metadata and the search palette live in
// the one root layout (app/layout.tsx). URLs are unchanged: app/(analytics)/analytics/*.
import "./analytics.css";
import "./brand.css";
import "./analytics/measurement-position.css";

import type { ReactNode } from "react";
import { SiteHeader } from "@/components/shell/SiteHeader";
import { Breadcrumbs } from "@/components/shell/Breadcrumbs";
import { SiteFooter } from "@/components/shell/SiteFooter";
import { snapshotDates } from "@/components/shell/snapshot.server";

export default function AnalyticsGroupLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <SiteHeader />
      <Breadcrumbs />
      <main id="main-content" tabIndex={-1}>{children}</main>
      <SiteFooter dates={snapshotDates()} />
    </>
  );
}
