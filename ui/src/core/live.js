// AI-CONTEXT: §23 entry 103 — the live channel, client side.
//
// EventSource rather than a WebSocket because every event travels server→client only.
// It reconnects by itself, needs no framing or heartbeat code here, and rides plain
// HTTP through Caddy with no second protocol path.
//
// The rule this module keeps: **the stream is an accelerator, never a source of
// truth.** Everything it carries is also a row the REST path returns, so every
// failure — no session, no EventSource, Redis down, a carrier that kills long-lived
// sockets — degrades to exactly the behaviour the app had before it existed. That is
// why nothing here reports an error to the driver: there is nothing for them to do
// about it, and §15.1 already treats an unreliable network as a normal mode.
//
// The token rides in the query string because EventSource cannot set headers. It is
// the same session token the REST calls send, over the same TLS, to the same origin —
// but it lands in access logs, which a header does not. Logged in §23 as the cost.
import { API_BASE, token } from "./api.js";

const RECONNECT_CEILING_MS = 60_000;

export function openStream({ kind = "handoff", lat, lon, onEvent }) {
  if (typeof EventSource === "undefined") return () => {};
  if (!token.value || lat == null || lon == null) return () => {};

  let source = null;
  let closed = false;
  let retryMs = 5_000;
  let timer = null;

  function connect() {
    if (closed) return;
    const url =
      `${API_BASE}/events/stream?kind=${encodeURIComponent(kind)}` +
      `&lat=${lat}&lon=${lon}&access_token=${encodeURIComponent(token.value)}`;
    source = new EventSource(url);

    source.addEventListener(kind, (e) => {
      try {
        onEvent?.(JSON.parse(e.data));
      } catch {
        /* a malformed frame is not worth a broken map */
      }
      retryMs = 5_000; // a delivered event proves the path works
    });

    // the server caps a stream and says goodbye; reconnecting is expected, not an error
    source.addEventListener("bye", () => {
      source?.close();
      schedule();
    });

    source.onerror = () => {
      source?.close();
      schedule();
    };
  }

  function schedule() {
    if (closed) return;
    clearTimeout(timer);
    timer = setTimeout(connect, retryMs);
    // back off so a server that is down does not get a reconnect per driver per 5s
    retryMs = Math.min(retryMs * 2, RECONNECT_CEILING_MS);
  }

  connect();
  return () => {
    closed = true;
    clearTimeout(timer);
    source?.close();
  };
}
