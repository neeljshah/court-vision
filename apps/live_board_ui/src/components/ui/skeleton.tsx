/** Shimmering placeholder block for loading states. aria-hidden so screen readers skip it. */
import { cn } from "@/lib/utils";

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "relative overflow-hidden rounded-md bg-surface2",
        className
      )}
    >
      <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-surface to-transparent" />
    </div>
  );
}
