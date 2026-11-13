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

/** Avatar fallback. There are no avatar images — see features.txt #2. */
export const initial = (name) => (name ? name.charAt(0).toUpperCase() : "?");

/** The coloured copy paper for a room or a person: one of six stocks, picked from the
 *  room code or username so it never changes. Returns a CSS colour (a token var). */
export function paperFor(key) {
  if (!key) return "var(--color-room-2)";
  let hash = 0;
  for (let i = 0; i < key.length; i++) {
    hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  }
  return `var(--color-room-${(hash % 6) + 1})`;
}
