import { cn } from "@/lib/utils";

interface Props {
  stars: number;
  className?: string;
}

const STAR_CONFIG = [
  { label: "★★★", border: "border-yellow-400 text-yellow-400" },
  { label: "★★",  border: "border-gray-400  text-gray-400"   },
  { label: "★",   border: "border-[#cd7c2f] text-[#cd7c2f]"  },
];

export function StarBadge({ stars, className }: Props) {
  const cfg = STAR_CONFIG[(3 - Math.min(3, Math.max(1, stars))) > 2 ? 2 : 3 - Math.min(3, Math.max(1, stars))];
  if (stars < 1) return <span className="text-[#4b5563] text-xs">—</span>;
  return (
    <span
      className={cn(
        "border rounded px-1 py-0.5 text-[10px] font-mono font-bold",
        cfg.border,
        className
      )}
    >
      {cfg.label}
    </span>
  );
}
