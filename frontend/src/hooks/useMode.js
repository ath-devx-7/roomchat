import { useEffect, useState } from "react";
import { currentMode } from "@/lib/theme";

/** The theme on screen ("light" | "dark" | "black"), kept in sync with the theme switch and the OS. */
export function useMode() {
  const [mode, setModeState] = useState(currentMode);
  useEffect(() => {
    const sync = () => setModeState(currentMode());
    // The switch writes data-mode on <html>; with nothing stored, the OS setting can change too.
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-mode"] });
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", sync);
    return () => {
      observer.disconnect();
      mq.removeEventListener("change", sync);
    };
  }, []);
  return mode;
}
