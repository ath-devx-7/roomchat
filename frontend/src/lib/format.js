import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import calendar from "dayjs/plugin/calendar";

dayjs.extend(relativeTime);
dayjs.extend(calendar);

/** "2m ago" — for invitation and notification cards. */
export const fromNow = (iso) => (iso ? dayjs(iso).fromNow() : "");

/** "9:02 AM" — the timestamp under a chat bubble. */
export const clockTime = (iso) => (iso ? dayjs(iso).format("h:mm A") : "");

/** "Today" / "Yesterday" / "Mar 4, 2026" — the divider between days of history. */
export function dayLabel(iso) {
  const d = dayjs(iso);
  const today = dayjs().startOf("day");
  if (d.isAfter(today)) return "Today";
  if (d.isAfter(today.subtract(1, "day"))) return "Yesterday";
  return d.format("MMM D, YYYY");
}

/** Stable YYYY-MM-DD key so message grouping does not depend on the label text. */
export const dayKey = (iso) => dayjs(iso).format("YYYY-MM-DD");

// The mock UI carried a hardcoded `accent` per room. Rooms have no colour field and
// don't need one — deriving it from the immutable room_code gives every room a stable
// identity colour with no backend involvement.
const ACCENTS = [
  "#3390EC", "#8B5CF6", "#F59E0B", "#22C55E",
  "#EC4899", "#14B8A6", "#EF4444", "#6366F1",
];

export function accentFor(code) {
  if (!code) return ACCENTS[0];
  let hash = 0;
  for (let i = 0; i < code.length; i++) {
    hash = (hash * 31 + code.charCodeAt(i)) >>> 0;
  }
  return ACCENTS[hash % ACCENTS.length];
}

/** Avatar fallback. There are no avatar images — see features.txt #2. */
export const initial = (name) => (name ? name.charAt(0).toUpperCase() : "?");
