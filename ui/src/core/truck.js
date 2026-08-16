// AI-CONTEXT: the truck's self-reported fuel economy, checked on the client with the SAME
// rule the server applies (`f01.validate_mpg`).
//
// The same two-copies-of-one-rule arrangement `contact.js` sets out, and taken for the same
// reason: the server's copy is the one that decides, and this one exists so a driver sees
// "between 3 and 12" in their own language rather than a 422 carrying a sentence of English
// from a Python exception. If the two ever disagree, the server wins and this is the bug.
//
// THE BOUNDS ARE A TYPO CHECK, NOT A CLAIM ABOUT TRUCKING. A loaded Class 8 runs roughly
// 5.5-7; a light run beats it and a reefer pulling grades does worse, and none of that is
// this function's business. What it catches is 60 typed for the pickup, or 0.6 from a
// decimal slip — either one puts the fuel cost out by an order of magnitude on the one
// screen whose whole job is telling a driver whether a load pays.
export const MIN_MPG = 3;
export const MAX_MPG = 12;

// null when there is nothing to complain about — including "empty", which means CLEAR the
// figure and go back to the app's own default; otherwise a translation KEY.
export function mpgError(raw) {
  const text = String(raw ?? "").trim();
  if (!text) return null;
  const value = Number(text);
  if (!Number.isFinite(value)) return "mpg.number";
  if (value < MIN_MPG || value > MAX_MPG) return "mpg.range";
  return null;
}

// what to send: the trimmed text, or "" to clear it. Deliberately NOT a number — an empty
// string and 0 must stay distinguishable on the wire, and `Number("")` is 0.
export function normalizeMpg(raw) {
  return String(raw ?? "").trim();
}
