import { useEffect, useRef, useState } from "react";
import { Reply, Send, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { clockTime, initial, paperFor } from "@/lib/format";

const ROLES = { alice: "Owner", bob: "Member", carol: "Member", you: "Member" };

/**
 * A simulated room for the landing page: no server involved, and it says so. A short script
 * plays joins, messages, a reply and an edit; the visitor can send and reply too. Every event
 * is reported to `onFrame` as the WebSocket frame the real app would carry.
 */
export default function DemoRoom({ onFrame, height = 500 }) {
  const [members, setMembers] = useState(["alice", "you"]);
  const [messages, setMessages] = useState(() => [
    { id: 1, who: "alice", text: "Welcome! The code is 82S0OT, share it around.", at: new Date().toISOString() },
  ]);
  const [flash, setFlash] = useState(null);
  const [draft, setDraft] = useState("");
  const [replyTo, setReplyTo] = useState(null);
  const listRef = useRef(null);
  const nextId = useRef(2);
  const frameRef = useRef(onFrame);
  frameRef.current = onFrame;

  const frame = (f) => frameRef.current?.(f);

  /** Appends a message (or a system notice) and returns its id. */
  const add = (who, text, extra = {}) => {
    const id = nextId.current++;
    setMessages((list) => [...list, { id, who, text, at: new Date().toISOString(), fresh: true, ...extra }]);
    return id;
  };

  // The script: two joins, a question, a reply, and an edit, two seconds apart.
  useEffect(() => {
    const join = (name) => {
      setMembers((m) => (m.includes(name) ? m : [...m, name]));
      setFlash(name);
      add(null, `${name} joined the room`, { system: true });
      frame({ type: "user_joined", username: name });
    };
    const steps = [
      () => join("bob"),
      () => {
        add("bob", "are we still on for 9?");
        frame({ type: "message_created", sender_username: "bob", content: "are we still on for 9?" });
      },
      () => {
        add("alice", "yes, starting in five", { reply: { who: "bob", text: "are we still on for 9?" } });
        frame({ type: "message_created", sender_username: "alice", reply_to: { sender_username: "bob" } });
      },
      () => join("carol"),
      () => {
        const id = add("carol", "hi all, running late");
        frame({ type: "message_created", sender_username: "carol", content: "hi all, running late" });
        setTimeout(() => {
          setMessages((list) => list.map((m) => (m.id === id ? { ...m, text: "hi all, there in 2", edited: true } : m)));
          frame({ type: "message_edited", message_id: id, content: "hi all, there in 2" });
        }, 1800);
      },
    ];
    const timers = steps.map((step, i) => setTimeout(step, 1400 + i * 2200));
    return () => timers.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the newest message in view (scrolls the list only, never the page).
  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTo({ top: list.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = (e) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    frame(replyTo ? { type: "reply_message", reply_to_id: replyTo.id, content: text } : { type: "send_message", content: text });
    add("you", text, replyTo ? { reply: { who: replyTo.who, text: replyTo.text } } : {});
    setDraft("");
    setReplyTo(null);
  };

  return (
    <div className="fibre-bg flex flex-col bg-paper-2" style={{ height }} data-testid="demo-room">
      <div className="flex items-center gap-3 border-b border-rule px-3.5 py-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center font-display text-2xl text-room-ink" style={{ background: "var(--color-room-5)" }} aria-hidden="true">F</span>
        <div className="min-w-0">
          <p className="font-display text-[30px] uppercase leading-none text-ink">Friday plans</p>
          <p className="text-[13px] text-ink-3"><span className="measure">{members.length}/10</span> members · simulated</p>
        </div>
        <span className="code-figure ml-auto bg-paper-4 px-2.5 py-0.5 text-2xl text-ink">82S0OT</span>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[auto_minmax(0,1fr)] sm:grid-cols-[minmax(0,1fr)_150px] sm:grid-rows-1">
        <ul ref={listRef} className="rc-scroll row-start-2 flex flex-col gap-2.5 overflow-y-auto px-4 py-3.5 sm:row-start-1" aria-live="polite">
          {messages.map((m) =>
            m.system ? (
              <li key={m.id} className={`text-center text-sm italic text-ink-3 ${m.fresh ? "rc-drop" : ""}`}>{m.text}</li>
            ) : (
              <li key={m.id} className={`group flex items-end gap-2.5 ${m.who === "you" ? "justify-end" : ""} ${m.fresh ? "rc-drop" : ""}`}>
                {m.who !== "you" && (
                  <span className="grid h-[30px] w-[30px] shrink-0 place-items-center font-display text-lg text-room-ink" style={{ background: paperFor(m.who) }} aria-hidden="true">{initial(m.who)}</span>
                )}
                {m.who === "you" && <ReplyButton onClick={() => setReplyTo(m)} />}
                <div className={`max-w-[75%] px-3 py-2 shadow-card ${m.who === "you" ? "own-sheet" : "bg-paper-3"}`}>
                  {m.reply && (
                    <p className="mb-1 truncate border-l-2 border-ink-3 pl-2 text-[13px] text-ink-3">
                      <span className="font-medium text-ink-2">{m.reply.who}</span> {m.reply.text}
                    </p>
                  )}
                  {m.who !== "you" && <p className="text-[13px] font-medium text-ink-3">{m.who}</p>}
                  <p className="text-[15px] leading-snug text-ink">{m.text}</p>
                  <p className="mt-0.5 font-mono text-[11px] text-ink-3">{clockTime(m.at)}{m.edited ? " · edited" : ""}</p>
                </div>
                {m.who !== "you" && <ReplyButton onClick={() => setReplyTo(m)} />}
              </li>
            )
          )}
        </ul>
        <div className="row-start-1 flex gap-2 border-b border-rule px-3 py-2 sm:col-start-2 sm:flex-col sm:border-b-0 sm:border-l sm:p-3">
          <p className="hidden font-display text-[22px] uppercase leading-none text-ink sm:block">Members</p>
          <ul className="flex gap-1 sm:flex-col">
            {members.map((name) => (
              <li key={name} className={`flex items-center gap-2 p-1 text-sm ${flash === name ? "rc-flash" : ""}`}>
                <span className="grid h-6 w-6 place-items-center font-display text-base text-room-ink" style={{ background: paperFor(name) }} aria-hidden="true">{initial(name)}</span>
                <span className="min-w-0 flex-1 truncate text-ink">{name === "you" ? "You" : name}</span>
                <span className="hidden font-mono text-[10px] text-ink-3 sm:inline">{ROLES[name]}</span>
              </li>
            ))}
          </ul>
          <p className="mt-auto hidden text-[13px] italic text-ink-3 sm:block">No server involved: this room runs in your browser.</p>
        </div>
      </div>
      {replyTo && (
        <div className="flex items-center gap-2 bg-signal px-3.5 py-2 text-sm text-signal-ink">
          <span className="min-w-0 flex-1 truncate">Replying to {replyTo.who === "you" ? "yourself" : replyTo.who}: {replyTo.text}</span>
          <button type="button" onClick={() => setReplyTo(null)} aria-label="Cancel reply" className="grid h-7 w-7 place-items-center hover:bg-signal-hover"><X size={15} /></button>
        </div>
      )}
      <form onSubmit={send} className="flex gap-2.5 border-t border-rule px-3.5 py-3">
        <label htmlFor="demo-message" className="visually-hidden">Message (simulated)</label>
        <input
          id="demo-message"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Type a message… (try it)"
          maxLength={200}
          autoComplete="off"
          className="h-11 min-w-0 flex-1 border border-ink bg-paper px-3 text-ink placeholder:text-ink-3"
        />
        <Button type="submit" className="h-11" aria-label="Send message">
          <Send /> Send
        </Button>
      </form>
    </div>
  );
}

/** The reply arrow beside a message: hidden until hover or focus, always shown on touch screens. */
function ReplyButton({ onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Reply"
      className="grid h-8 w-8 shrink-0 place-items-center self-center text-ink-3 opacity-0 transition-opacity hover:text-ink focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100"
    >
      <Reply size={16} />
    </button>
  );
}
