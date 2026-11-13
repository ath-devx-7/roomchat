import { useState } from "react";
import { Circle, Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";
import { currentMode, setMode } from "@/lib/theme";

const OPTIONS = [
  { mode: "light", label: "Light theme", Icon: Sun },
  { mode: "dark", label: "Dark theme", Icon: Moon },
  { mode: "black", label: "Black theme", Icon: Circle },
];

/** The three-way theme switch: light (warm-grey board), dark (the black wall), black (neutral grey). */
export default function ThemeToggle({ className }) {
  const [mode, setLocalMode] = useState(currentMode);

  const pick = (next) => {
    setMode(next);
    setLocalMode(next);
  };

  return (
    <div
      role="group"
      aria-label="Theme"
      className={cn("inline-flex border border-rule bg-paper-4 p-0.5", className)}
      data-testid="theme-toggle"
    >
      {OPTIONS.map(({ mode: m, label, Icon }) => (
        <button
          key={m}
          type="button"
          onClick={() => pick(m)}
          aria-pressed={mode === m}
          aria-label={label}
          title={label}
          className={cn(
            "grid h-8 w-9 place-items-center text-ink-3 transition-colors duration-micro hover:text-ink",
            // The current theme sits on the fluorescent, with toner type.
            mode === m && "bg-signal text-signal-ink hover:text-signal-ink"
          )}
          data-testid={`theme-${m}`}
        >
          <Icon size={15} fill={m === "black" ? "currentColor" : "none"} aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}
