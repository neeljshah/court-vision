"use client";

import { RouteError } from "@/components/honest/RouteError";

export default function HowItWorksError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError section="How it works" {...props} />;
}
