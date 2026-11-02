import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

const STACK_QUERY = "(max-width: 900px)";

/** True when the viewport is too narrow for a pinned board, so cards stack instead. */
function useStacked() {
  const [stacked, setStacked] = useState(() => window.matchMedia(STACK_QUERY).matches);
  useEffect(() => {
    const mq = window.matchMedia(STACK_QUERY);
    const sync = () => setStacked(mq.matches);
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return stacked;
}

/**
 * An evidence board: <Pin> cards placed on a design-size canvas, joined by tape lines.
 * - The canvas is `width` × `height` design pixels and scales down to fit its column.
 * - When `draggable`, a card is dragged by its [data-handle] (or anywhere, if it has none) and its
 *   tape follows. Buttons, inputs and links inside a card never start a drag.
 * - Under 900px the cards stack in reading order with no dragging and no tape.
 */
export function Board({ links = [], width = 1264, height, draggable = false, className, children, ...rest }) {
  const fitRef = useRef(null);
  const boardRef = useRef(null);
  const svgRef = useRef(null);
  const scaleRef = useRef(1);
  const stacked = useStacked();

  // Redraw every tape line from the cards' current positions (in design pixels).
  const draw = useCallback(() => {
    const board = boardRef.current;
    const svg = svgRef.current;
    if (!board || !svg || stacked) return;
    const box = board.getBoundingClientRect();
    const s = scaleRef.current;
    svg.innerHTML = links
      .map(([a, b]) => {
        const A = board.querySelector(`[data-pin="${a}"]`);
        const B = board.querySelector(`[data-pin="${b}"]`);
        if (!A || !B) return "";
        const ra = A.getBoundingClientRect();
        const rb = B.getBoundingClientRect();
        const x1 = (ra.left - box.left + ra.width / 2) / s;
        const y1 = (ra.top - box.top) / s + 14;
        const x2 = (rb.left - box.left + rb.width / 2) / s;
        const y2 = (rb.top - box.top) / s + 14;
        return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
      })
      .join("");
  }, [links, stacked]);

  // Scale the canvas to its column and keep the outer box as tall as the scaled board.
  const fit = useCallback(() => {
    const fitBox = fitRef.current;
    const board = boardRef.current;
    if (!fitBox || !board) return;
    if (stacked) {
      scaleRef.current = 1;
      board.style.transform = "";
      fitBox.style.height = "";
      return;
    }
    const s = Math.min(1, fitBox.clientWidth / width);
    scaleRef.current = s;
    board.style.transform = `scale(${s})`;
    fitBox.style.height = `${height * s}px`;
    draw();
  }, [stacked, width, height, draw]);

  useLayoutEffect(() => {
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(fitRef.current);
    // Fonts and reveal animations shift card sizes slightly after the first paint.
    const t = setTimeout(fit, 400);
    return () => {
      ro.disconnect();
      clearTimeout(t);
    };
  }, [fit]);

  // Pointer dragging, done on the DOM directly so a drag never re-renders React.
  useEffect(() => {
    const board = boardRef.current;
    if (!board || !draggable || stacked) return undefined;
    let card = null;
    let offset = null;
    const down = (e) => {
      const target = e.target.closest("[data-pin]");
      if (!target || e.button !== 0) return;
      if (e.target.closest("button, input, a, textarea, [role='button']")) return;
      if (target.querySelector("[data-handle]") && !e.target.closest("[data-handle]")) return;
      const s = scaleRef.current;
      card = target;
      offset = [e.clientX / s - card.offsetLeft, e.clientY / s - card.offsetTop];
      card.setPointerCapture(e.pointerId);
      card.dataset.lifted = "true";
      e.preventDefault();
    };
    const move = (e) => {
      if (!card) return;
      const s = scaleRef.current;
      // Keep the card on the board.
      const x = Math.max(0, Math.min(width - card.offsetWidth, e.clientX / s - offset[0]));
      const y = Math.max(0, Math.min(height - 60, e.clientY / s - offset[1]));
      card.style.left = `${x}px`;
      card.style.top = `${y}px`;
      draw();
    };
    const up = () => {
      if (card) delete card.dataset.lifted;
      card = null;
    };
    board.addEventListener("pointerdown", down);
    board.addEventListener("pointermove", move);
    board.addEventListener("pointerup", up);
    board.addEventListener("pointercancel", up);
    return () => {
      board.removeEventListener("pointerdown", down);
      board.removeEventListener("pointermove", move);
      board.removeEventListener("pointerup", up);
      board.removeEventListener("pointercancel", up);
    };
  }, [draggable, stacked, width, height, draw]);

  return (
    <div ref={fitRef} className={cn("relative", className)} {...rest}>
      <div
        ref={boardRef}
        data-board=""
        data-stacked={stacked ? "true" : undefined}
        className={cn(stacked ? "flex flex-col gap-8" : "absolute left-0 top-0 origin-top-left")}
        style={stacked ? undefined : { width, height }}
      >
        {!stacked && <svg ref={svgRef} aria-hidden="true" className="tape-lines pointer-events-none absolute inset-0 z-[1] h-full w-full overflow-visible" />}
        {children}
      </div>
    </div>
  );
}

/**
 * One card pinned to a <Board>: `x`/`y` are design pixels, `rotate` its resting tilt in degrees.
 * In the stacked (narrow) layout it becomes an ordinary block that keeps its tilt.
 */
export function Pin({ id, x = 0, y = 0, w, rotate = 0, pin = true, className, style, children, ...rest }) {
  return (
    <div
      data-pin={id}
      className={cn(
        "z-[2] max-w-full [[data-board]:not([data-stacked])_&]:absolute",
        "data-[lifted=true]:z-20 data-[lifted=true]:shadow-[0_30px_60px_rgb(0_0_0/0.5)]",
        pin && "pin",
        className
      )}
      style={{ left: x, top: y, width: w, "--rest": `rotate(${rotate}deg)`, transform: "var(--rest)", ...style }}
      {...rest}
    >
      {children}
    </div>
  );
}
