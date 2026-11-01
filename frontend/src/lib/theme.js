// Light/dark mode. The choice lives on <html data-mode="light|dark"> and in localStorage
// under "roomchat-mode". With nothing stored, tokens.css follows the OS setting instead.
// templates/index.html applies the stored choice before first paint, so there is no flash.

const KEY = "roomchat-mode";

/** The mode on screen right now: the stored choice, else what the OS prefers. Light (the
 *  kraft board) is the default, so only an explicit OS dark preference means dark. */
export function currentMode() {
  const set = document.documentElement.dataset.mode;
  if (set === "light" || set === "dark") return set;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Switch to `mode` and remember it. Storage can throw (private windows), so it is optional. */
export function setMode(mode) {
  document.documentElement.dataset.mode = mode;
  try {
    localStorage.setItem(KEY, mode);
  } catch {
    // The switch still works for this page view; it just won't be remembered.
  }
}
