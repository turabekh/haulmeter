// AI-CONTEXT: the four-state model every fetching surface declares (§23 entry 131,
// §22.3 DoD).
//
// Before this, surfaces had TWO states — data and no-data — so `null` had to mean one
// of them and the codebase chose data: `livePins.value ?? SAMPLE_PINS`. That is the
// whole of UI audit U-06, U-09 and U-10. The third and fourth states are what make a
// fixture unnecessary.
//
//   loading        the skeleton (§8)
//   loaded + data  the content
//   loaded + none  one sentence of purpose + one action (§15.3)
//   failed         inline, specific, actionable (§15.4) — NEVER data
//
// `loaded` is deliberately not split into two constants: whether it has data is a
// question about the payload, which the surface already asks to decide what to render.
export const LoadState = {
  LOADING: "loading",
  LOADED: "loaded",
  FAILED: "failed",
};

// AI-CONTEXT: offline versus failed, which every bare `catch` in this codebase used to
// conflate. §15.1 says offline is a MODE, not an error, and the two call for different
// next actions: "check your signal" and "we couldn't load that" are different sentences
// to a driver, and only one of them is worth retrying on the spot.
//
// TWO signals, because api.js has two kinds of caller and reading only one gets the
// map wrong. This was measured, not assumed:
//
//   · `apiGet` callers — it flips the shared `online` ref on a transport throw and
//     rethrows a 4xx/5xx untouched, so `online` is already the answer.
//   · DIRECT `fetch` callers — `fetchOverlay`, which the map uses, does NOT go through
//     `apiGet`. It never touches `online`, so a dead zone on the map would have read
//     as a server error and sent a driver looking for the wrong fix.
//
// So the transport failure is also identified at the source: `fetch` rejects with a
// TypeError when it cannot reach the network at all, while every non-ok response in
// this codebase becomes an `Error` carrying its status. That is a distinction about
// where the failure happened, which is exactly the distinction the driver needs.
import { online } from "./api.js";

export const Failure = {
  OFFLINE: "offline",
  SERVER: "failed",
};

export function failureOf(err) {
  // an absent session is not a dead zone: the surface genuinely cannot answer, and
  // telling a driver to check their signal would send them looking for the wrong fix
  if (err && err.message === "no session") return Failure.SERVER;
  if (err instanceof TypeError) return Failure.OFFLINE; // never reached the network
  return online.value ? Failure.SERVER : Failure.OFFLINE;
}
