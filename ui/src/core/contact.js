// AI-CONTEXT: the broker's address, checked on the client with the SAME rule the server
// applies (`f05.validate_contact_email`).
//
// Two copies of a rule is a drift risk, and it is taken deliberately: the server's copy is
// the one that decides — it is the only one an offline-queued write or a second client can
// be held to — and this one exists so a driver finds a typo while they are still looking at
// the paper, rather than at a "422" three taps later. The rules are stated identically on
// both sides and the shapes are pinned by tests on both sides. If they ever disagree, the
// server wins and the UI is the bug.
//
// PRAGMATIC, NOT RFC-COMPLETE. A real address is whatever the receiving server accepts, so
// any rule here is a guess; the job is catching what a human can see and fix. The cost of
// being wrong in the strict direction is refusing an address that works, which is worse —
// the whole reason this session exists is that the product had NOWHERE to put one.
export const MAX_CONTACT_EMAIL = 320;

// null when there is nothing to complain about (including "empty", which means CLEAR the
// address on file); otherwise a translation KEY the caller renders.
export function contactEmailError(raw) {
  const email = (raw ?? "").trim();
  if (!email) return null;
  if (email.length > MAX_CONTACT_EMAIL) return "email.too_long";
  if (/\s/.test(email)) return "email.no_spaces";
  if ((email.match(/@/g) || []).length !== 1) return "email.one_at";
  const [local, domain] = email.split("@");
  if (!local || !domain) return "email.needs_both";
  if (!domain.includes(".") || domain.startsWith(".") || domain.endsWith(".")) {
    return "email.domain_dot";
  }
  return null;
}

// what to send: a trimmed address, or null to clear it
export function normalizeContactEmail(raw) {
  const email = (raw ?? "").trim();
  return email ? email : null;
}

// AI-CONTEXT: the same two-copies-of-one-rule arrangement as the address above, mirroring
// `f05.validate_contact_phone`. Ten digits, US: this product's counterparties are US
// brokers and every one of them prints a NANP number, and a looser rule would accept the
// extension digits too — "555-0134 x229" kept as a phone number is a number that dials
// someone else.
export function contactPhoneError(raw) {
  const digits = phoneDigits(raw);
  if (digits === null) return null; // nothing typed: clearing the number is allowed
  return digits.length === 10 ? null : "phone.ten_digits";
}

function phoneDigits(raw) {
  const text = (raw ?? "").trim();
  if (!text) return null;
  let digits = text.replace(/\D/g, "");
  if (digits.length === 11 && digits.startsWith("1")) digits = digits.slice(1);
  return digits;
}

export function normalizeContactPhone(raw) {
  const digits = phoneDigits(raw);
  return digits && digits.length === 10 ? digits : null;
}
