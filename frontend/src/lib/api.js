// Thin fetch wrappers over the Django JSON API.
//
// The backend signals failure in two shapes and both reach the user:
//   {"error": "..."}                     — a single message (flat failures, 4xx)
//   {"errors": {"field": "message"}}     — per-field, from format_pydantic_errors
// apiError() normalises them so a caller can `catch (e) { toast.error(e.message) }`
// and still reach e.fieldErrors when it wants to pin messages to inputs.

export const BOOTSTRAP = window.__ROOMCHAT__ || { user: null };

function getCookie(name) {
  const match = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[2]) : null;
}

export class ApiError extends Error {
  constructor(message, { status, fieldErrors } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors || null;
  }
}

async function parse(res) {
  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    // Django's HTML debug page, a proxy error page, anything non-JSON. Never show
    // markup to the user.
    throw new ApiError(`Server error (${res.status}). Please try again.`, {
      status: res.status,
    });
  }

  if (!res.ok) {
    const fieldErrors = data.errors || null;
    const message =
      data.error ||
      (fieldErrors && Object.values(fieldErrors)[0]) ||
      "Something went wrong.";
    throw new ApiError(message, { status: res.status, fieldErrors });
  }
  return data;
}

export async function getJSON(url) {
  const res = await fetch(url, {
    headers: { Accept: "application/json" },
  });
  return parse(res);
}

/**
 * POST as form-urlencoded — the Django views read request.POST, so this keeps them
 * free of manual json.loads and keeps CSRF handling on Django's normal path.
 */
export async function postJSON(url, fields) {
  const headers = { "X-CSRFToken": getCookie("csrftoken") || "", Accept: "application/json" };
  let body;
  if (fields) {
    headers["Content-Type"] = "application/x-www-form-urlencoded";
    body = new URLSearchParams(
      Object.entries(fields).filter(([, v]) => v !== undefined && v !== null)
    ).toString();
  }
  const res = await fetch(url, { method: "POST", headers, body });
  return parse(res);
}

export const api = {
  register: (fields) => postJSON("/api/auth/register/", fields),
  login: (fields) => postJSON("/api/auth/login/", fields),
  logout: () => postJSON("/api/auth/logout/"),

  dashboard: () => getJSON("/api/dashboard/"),
  friends: () => getJSON("/api/friends/"),
  sendFriendRequest: (username) => postJSON("/api/friends/send/", { username }),
  acceptFriendRequest: (id) => postJSON(`/api/friends/accept/${id}/`),
  rejectFriendRequest: (id) => postJSON(`/api/friends/reject/${id}/`),
  removeFriend: (id) => postJSON(`/api/friends/remove/${id}/`),

  createRoom: (fields) => postJSON("/api/rooms/create/", fields),
  joinRoom: (fields) => postJSON("/api/rooms/join/", fields),
  room: (code) => getJSON(`/api/rooms/${encodeURIComponent(code)}/`),
};
