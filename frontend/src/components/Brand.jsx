import { MessagesSquare } from "lucide-react";
import { cn } from "@/lib/utils";

export const Logo = ({ size = "md", className }) => {
  const dims = size === "sm" ? "h-8 w-8" : size === "lg" ? "h-12 w-12" : "h-10 w-10";
  const icon = size === "sm" ? 18 : size === "lg" ? 26 : 22;
  const text = size === "sm" ? "text-lg" : size === "lg" ? "text-2xl" : "text-xl";
  return (
    <div className={cn("flex items-center gap-2.5 select-none", className)} data-testid="brand-logo">
      <div
        className={cn(
          "grid place-items-center rounded-2xl bg-primary text-primary-foreground shadow-floating",
          dims
        )}
      >
        <MessagesSquare size={icon} strokeWidth={2.4} />
      </div>
      <span className={cn("font-extrabold tracking-tight text-slate-900", text)}>
        Room<span className="text-primary">Chat</span>
      </span>
    </div>
  );
};

export const StatusDot = ({ status, className }) => {
  const map = {
    online: "bg-green-500",
    away: "bg-amber-400",
    offline: "bg-slate-300",
  };
  return (
    <span
      className={cn(
        "inline-block h-3 w-3 rounded-full ring-2 ring-white",
        map[status] || "bg-slate-300",
        status === "online" && "rc-online-ring",
        className
      )}
    />
  );
};
