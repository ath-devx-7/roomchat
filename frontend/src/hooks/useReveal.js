import { useEffect } from "react";

/**
 * Adds .is-in to every `.reveal` (and `.draw`) element inside `rootRef` when it scrolls into view,
 * which plays the paper drop-in from index.css. Elements marked data-count-to count up instead.
 * Pass `deps` to re-scan when new revealable elements are rendered.
 */
export function useReveal(rootRef, deps = []) {
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;
    // Diagram lines need their own length to draw themselves in.
    root.querySelectorAll(".draw path").forEach((p) => {
      try {
        p.style.setProperty("--len", Math.ceil(p.getTotalLength()));
      } catch {
        /* not rendered yet: the dash falls back to 1000 */
      }
    });
    const io = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          if (!e.isIntersecting) return;
          e.target.classList.add("is-in");
          if (e.target.dataset.countTo) countUp(e.target);
          io.unobserve(e.target);
        }),
      { threshold: 0.12 }
    );
    root.querySelectorAll(".reveal:not(.is-in), .draw:not(.is-in), [data-count-to]").forEach((el) => io.observe(el));
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

/** Counts an element's text up to data-count-to (keeping data-prefix), easing out over ~1s. */
function countUp(el) {
  const to = Number(el.dataset.countTo);
  const prefix = el.dataset.prefix || "";
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    el.textContent = prefix + to;
    return;
  }
  const t0 = performance.now();
  const step = (t) => {
    const k = Math.min(1, (t - t0) / 1100);
    el.textContent = prefix + Math.round(to * (1 - Math.pow(1 - k, 3)));
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
