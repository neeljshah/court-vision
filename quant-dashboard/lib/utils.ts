import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function edgeStars(edge?: number): number {
  if (!edge) return 0;
  if (edge >= 0.12) return 3;
  if (edge >= 0.08) return 2;
  if (edge >= 0.05) return 1;
  return 0;
}
