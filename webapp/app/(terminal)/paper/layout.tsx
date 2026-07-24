// paper/layout.tsx -- sets the page title for /paper (the page.tsx is
// "use client" so metadata must live in this server-side layout wrapper).
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Paper | CourtVision",
};

export default function PaperLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
