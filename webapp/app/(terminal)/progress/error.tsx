"use client";

import { RouteError } from "@/components/honest/RouteError";

export default function ProgressError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError section="Progress" {...props} />;
}
