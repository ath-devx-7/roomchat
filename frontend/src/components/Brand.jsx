import { MessagesSquare } from "lucide-react";
import { cn } from "@/lib/utils";

/** The RoomChat mark: a fluorescent square on a hard ink offset, beside the wordmark in
 *  League Gothic capitals (never under 28px, the theme's floor for that face). */
export const Logo = ({ size = "md", className }) => {
  const dims = size === "sm" ? "h-8 w-8" : size === "lg" ? "h-11 w-11" : "h-9 w-9";
  const icon = size === "sm" ? 17 : size === "lg" ? 24 : 20;
  const text = size === "lg" ? "text-[40px]" : size === "md" ? "text-[34px]" : "text-[28px]";
  return (
    <div className={cn("flex items-center gap-3 select-none", className)} data-testid="brand-logo">
      <div className={cn("grid place-items-center bg-signal text-signal-ink shadow-offset-xs", dims)} aria-hidden="true">
        <MessagesSquare size={icon} strokeWidth={2.2} />
      </div>
      <span className={cn("font-display uppercase leading-none tracking-[0.02em] text-ink", text)}>RoomChat</span>
    </div>
  );
};

/** A small square presence mark. Only used where it states a live fact (a friend in a room);
 *  the text beside it says the same thing, so screen readers skip it. */
export const StatusDot = ({ status, className }) => {
  const map = {
    online: "bg-success",
    away: "bg-signal",
    offline: "border border-ink-3 bg-paper-3",
  };
  return (
    <span
      aria-hidden="true"
      className={cn("inline-block h-2.5 w-2.5", map[status] || map.offline, className)}
    />
  );
};
