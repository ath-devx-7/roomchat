import { useState } from "react";
import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { currentMode, setMode } from "@/lib/theme";

/** One square icon button that flips between the light and dark colourways. */
export default function ThemeToggle({ className }) {
  const [mode, setLocalMode] = useState(currentMode);
  const next = mode === "dark" ? "light" : "dark";

  const flip = () => {
    setMode(next);
    setLocalMode(next);
  };

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      onClick={flip}
      aria-label={`Switch to ${next} mode`}
      title={`Switch to ${next} mode`}
      className={className}
      data-testid="theme-toggle"
    >
      {mode === "dark" ? <Sun size={18} /> : <Moon size={18} />}
    </Button>
  );
}
