/** Cycles theme: system -> light -> dark -> system. Aria-label always describes the NEXT state. */
import { Monitor, Sun, Moon } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

type Theme = "system" | "light" | "dark";

const CYCLE: Theme[] = ["system", "light", "dark"];

const NEXT_LABEL: Record<Theme, string> = {
  system: "Switch to light mode",
  light: "Switch to dark mode",
  dark: "Switch to system theme",
};

const CURRENT_LABEL: Record<Theme, string> = {
  system: "Current theme: system",
  light: "Current theme: light",
  dark: "Current theme: dark",
};

const ICONS: Record<Theme, React.ReactNode> = {
  system: <Monitor size={18} aria-hidden="true" />,
  light: <Sun size={18} aria-hidden="true" />,
  dark: <Moon size={18} aria-hidden="true" />,
};

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  function handleClick() {
    const idx = CYCLE.indexOf(theme as Theme);
    const next = CYCLE[(idx + 1) % CYCLE.length];
    setTheme(next);
  }

  const current = (CYCLE.includes(theme as Theme) ? theme : "system") as Theme;

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-label={NEXT_LABEL[current]}
      className={cn(
        "rounded-md p-2 border border-line",
        "text-muted hover:text-txt hover:bg-surface2",
        "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      )}
    >
      <span className="sr-only" aria-live="polite">
        {CURRENT_LABEL[current]}
      </span>
      {ICONS[current]}
    </button>
  );
}
