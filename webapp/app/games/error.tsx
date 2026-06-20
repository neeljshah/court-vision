"use client";

import { RouteError } from "@/components/honest/RouteError";

export default function GamesError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError section="Games" {...props} />;
}
