import { forwardRef, useCallback, useImperativeHandle, useLayoutEffect, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CLOSE_CODES, GATE, LIFECYCLE, MIDDLEWARE, TABLES } from "@/lib/techFacts";

const NODES = [
  ["a", 30, 40, 190, 76, "Browser · alice", "React 19 · useSocket"],
  ["b", 30, 300, 190, 76, "Browser · bob", "same room, another socket"],
  ["u", 380, 140, 270, 130, "uvicorn · ASGI", "/api · /ws/chat · /ws/notifications"],
  ["p", 790, 30, 190, 76, "PostgreSQL", "rooms_message · INSERT"],
  ["r", 790, 300, 190, 76, "Redis", "pub/sub · msgpack"],
];
const WIRES = {
  au: "M220 78 C305 78 295 180 380 180",
  bu: "M220 338 C305 338 295 236 380 236",
  up: "M650 175 C720 175 710 68 790 68",
  ur: "M650 238 C720 238 710 338 790 338",
};

/**
 * The architecture as a drawing: two browsers, the ASGI app, Postgres and Redis. `journey()`
 * (via ref) flies one message through it: sender → app → Postgres and Redis → every socket.
 */
export const ArchDiagram = forwardRef(function ArchDiagram(_props, ref) {
  const svgRef = useRef(null);
  const busy = useRef(false);

  /** Moves one packet along a wire; resolves when it arrives. */
  const fly = useCallback((key, reverse = false) => new Promise((resolve) => {
    const svg = svgRef.current;
    const path = svg?.querySelector(`#wire-${key}`);
    if (!path) return resolve();
    const len = path.getTotalLength();
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    dot.setAttribute("class", "arch-packet");
    dot.setAttribute("width", 14);
    dot.setAttribute("height", 14);
    svg.querySelector(".packets").appendChild(dot);
    path.classList.add("live");
    const t0 = performance.now();
    const step = (t) => {
      const k = Math.min(1, (t - t0) / 650);
      const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      const pt = path.getPointAtLength(len * (reverse ? 1 - e : e));
      dot.setAttribute("x", pt.x - 7);
      dot.setAttribute("y", pt.y - 7);
      if (k < 1) requestAnimationFrame(step);
      else {
        dot.remove();
        path.classList.remove("live");
        resolve();
      }
    };
    requestAnimationFrame(step);
  }), []);

  const hot = (id, on) => svgRef.current?.querySelector(`#node-${id}`)?.classList.toggle("hot", on);

  useImperativeHandle(ref, () => ({
    async journey() {
      // One journey at a time, and none at all under reduced motion.
      if (busy.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      busy.current = true;
      hot("a", true); await fly("au"); hot("a", false); hot("u", true);
      await Promise.all([fly("up"), fly("ur")]); hot("p", true); hot("r", true);
      await fly("ur", true); hot("p", false); hot("r", false);
      await Promise.all([fly("au", true), fly("bu", true)]); hot("u", false);
      hot("a", true); hot("b", true);
      setTimeout(() => { hot("a", false); hot("b", false); busy.current = false; }, 450);
    },
  }), [fly]);

  return (
    <svg ref={svgRef} viewBox="0 0 1000 400" className="block h-auto w-full overflow-visible" role="img" aria-label="Architecture: two browsers connect over WebSockets to one uvicorn ASGI app, which writes to PostgreSQL and publishes through Redis to every socket in the room.">
      {Object.entries(WIRES).map(([k, d]) => <path key={k} id={`wire-${k}`} className="arch-wire" d={d} />)}
      <g className="arch-label font-mono text-[11px]">
        <text x="236" y="58">ws frame</text>
        <text x="672" y="124">INSERT + commit</text>
        <text x="664" y="294">PUBLISH room_82S0OT</text>
        <text x="236" y="372">message_created</text>
      </g>
      {NODES.map(([id, x, y, w, h, title, sub]) => (
        <g key={id} id={`node-${id}`} className="arch-node">
          <rect x={x} y={y} width={w} height={h} />
          <text x={x + 14} y={y + 34} className="font-display text-[22px] uppercase tracking-[0.04em]">{title}</text>
          <text x={x + 14} y={y + 56} className="arch-sub font-mono text-[11px]">{sub}</text>
        </g>
      ))}
      <g className="packets" />
    </svg>
  );
});

/** The eight middleware layers; "Send a request" lights them top to bottom, then back up. */
export function MiddlewareStack() {
  const [hit, setHit] = useState(-1);
  const [running, setRunning] = useState(false);

  const run = async () => {
    if (running) return;
    setRunning(true);
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    for (let i = 0; i < MIDDLEWARE.length; i++) { setHit(i); await wait(140); }
    for (let i = MIDDLEWARE.length - 1; i >= 0; i--) { setHit(i); await wait(80); }
    setHit(-1);
    setRunning(false);
  };

  return (
    <div>
      <Button variant="outline" size="sm" onClick={run} disabled={running} className="mt-3">
        <ArrowDown /> {running ? "Request in flight…" : "Send a request"}
      </Button>
      <ol className="mt-3 flex flex-col gap-1.5">
        {MIDDLEWARE.map(([name, role], i) => (
          <li
            key={name}
            className={`grid grid-cols-[34px_1fr] items-center gap-3 px-3.5 py-2.5 shadow-card transition-[transform,background-color] duration-short ease-out hover:translate-x-3 ${hit === i ? "translate-x-3 bg-signal text-signal-ink" : "bg-paper-4"}`}
          >
            <span className={`font-display text-[26px] leading-none ${hit === i ? "" : "text-ink-3"}`}>{i + 1}</span>
            <span className="min-w-0">
              <span className="block font-display text-[21px] uppercase leading-tight tracking-[0.03em]">{name}</span>
              <span className={`block font-mono text-xs ${hit === i ? "" : "text-ink-3"}`}>{role}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

/** The main tables as index cards, with dashed lines for their foreign keys. */
export function SchemaCards() {
  const boxRef = useRef(null);
  const [paths, setPaths] = useState([]);

  // Foreign-key lines are measured from the rendered cards, so they redraw on resize.
  const measure = useCallback(() => {
    const box = boxRef.current;
    if (!box) return;
    const b0 = box.getBoundingClientRect();
    const next = [];
    TABLES.forEach((t) => (t.fk || []).forEach((to) => {
      const a = box.querySelector(`[data-table="${t.id}"]`)?.getBoundingClientRect();
      const b = box.querySelector(`[data-table="${to}"]`)?.getBoundingClientRect();
      if (!a || !b) return;
      const leftward = b.left < a.left;
      const ax = a.left - b0.left + (leftward ? 0 : a.width);
      const ay = a.top - b0.top + 22;
      const bx = b.left - b0.left + (leftward ? b.width : 0);
      const by = b.top - b0.top + 22;
      next.push(`M${ax} ${ay} C${(ax + bx) / 2} ${ay} ${(ax + bx) / 2} ${by} ${bx} ${by}`);
    }));
    setPaths(next);
  }, []);

  useLayoutEffect(() => {
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(boxRef.current);
    return () => ro.disconnect();
  }, [measure]);

  return (
    <div ref={boxRef} className="relative mt-5 h-[440px] max-md:flex max-md:h-auto max-md:flex-col max-md:gap-4">
      <svg aria-hidden="true" className="schema-lines pointer-events-none absolute inset-0 h-full w-full overflow-visible max-md:hidden">
        {paths.map((d, i) => <path key={i} d={d} />)}
      </svg>
      {TABLES.map((t, i) => (
        <div
          key={t.id}
          data-table={t.id}
          className="reveal w-[210px] bg-paper-4 font-mono text-xs leading-[1.7] shadow-sheet md:absolute max-md:w-full"
          style={{ left: `${t.x}%`, top: `${t.y}%`, "--d": `${i * 0.06}s` }}
        >
          <p className="bg-paper-3 px-3 py-2 font-display text-xl uppercase tracking-[0.04em] text-ink">{t.name}</p>
          <ul className="px-3 py-2 text-ink-2">
            {t.rows.map((r) => (
              <li key={r} className={r === "id" ? "text-ink-3" : ""}>
                {r}
                {/_id\b/.test(r) && <span className="text-ink-3"> → fk</span>}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

/** Close codes as tags hung on the board. */
export function CloseCodes() {
  return (
    <ul className="mt-3 grid grid-cols-3 gap-3.5 max-sm:grid-cols-2">
      {CLOSE_CODES.map(([code, meaning, kind], i) => (
        <li key={code} className="reveal relative bg-paper-4 py-4 pl-9 pr-4 shadow-card transition-transform duration-short hover:-translate-y-1 hover:-rotate-2" style={{ "--d": `${i * 0.06}s` }}>
          <span aria-hidden="true" className="absolute left-3 top-[22px] h-2.5 w-2.5 rounded-full bg-paper shadow-[inset_0_0_0_2px_var(--color-rule)]" />
          <span className="code-figure block text-[44px] text-ink">{code}</span>
          <span className="block text-sm text-ink-2">{meaning}</span>
          <span className="mt-1.5 block font-mono text-[11px] text-ink-3">{kind}</span>
        </li>
      ))}
    </ul>
  );
}

/** room_detail_api's checks, in order. */
export function AccessGate() {
  return (
    <ol className="mt-3 grid grid-cols-4 max-sm:grid-cols-2">
      {GATE.map(([title, note], i) => (
        <li key={title} className="reveal border-l border-dashed border-rule p-4 first:border-l-0" style={{ "--d": `${i * 0.08}s` }}>
          <span className="code-figure block text-3xl text-ink-3">{i + 1}</span>
          <span className="block font-display text-2xl uppercase leading-tight text-ink">{title}</span>
          <span className="block font-mono text-xs text-ink-3">{note}</span>
        </li>
      ))}
    </ol>
  );
}

/** The room lifecycle as a taped timeline. */
export function Lifecycle() {
  return (
    <ol className="mt-5 grid grid-cols-5 max-md:grid-cols-1">
      {LIFECYCLE.map(([title, note], i) => (
        <li key={title} className="reveal relative border-t-[3px] border-signal px-4 py-4" style={{ "--d": `${i * 0.08}s` }}>
          <span aria-hidden="true" className="absolute -top-[9px] left-4 h-3.5 w-3.5 rotate-45 bg-signal" />
          <span className="block font-display text-[28px] uppercase leading-tight text-ink">{title}</span>
          <span className="block font-mono text-xs text-ink-3">{note}</span>
        </li>
      ))}
    </ol>
  );
}
