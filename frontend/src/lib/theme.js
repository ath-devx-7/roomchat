// Light / dark / black mode. The choice lives on <html data-mode="light|dark|black"> and in
// localStorage under "roomchat-mode". With nothing stored, tokens.css follows the OS setting
// (dark OS → dark board, otherwise light). templates/index.html applies the stored choice before
// first paint, so there is no flash.

const KEY = "roomchat-mode";
export const MODES = ["light", "dark", "black"];

/** The mode on screen right now: the stored choice, else what the OS prefers. */
export function currentMode() {
  const set = document.documentElement.dataset.mode;
  if (MODES.includes(set)) return set;
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
