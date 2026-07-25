// AI-CONTEXT: M13 vendor presentation logic (design-prd §11.7, §E1.9 Q-6/Q-7).
// Framework-free like presentation.js — the server returns semantic data and this
// maps it to labels and badge state; components render tokens.
//
// The load-bearing rule here is the honesty split. A CROWD reading is "N drivers";
// the vendor's own claim is "vendor says here". They are different kinds of truth
// and the UI must never blur them, so `presenceLabel` refuses to produce a driver
// count for a vendor-sourced belief — the shape of the function makes it impossible
// rather than merely discouraged.

import { freshnessLabel } from "./presentation.js";

// every helper below coerces its input: an unexpected or malformed response must
// degrade to "no food here" (a quiet, honest empty state) rather than break the map
// a driver is using at speed. The map outranks the food layer, always.
const asList = (value) => (Array.isArray(value) ? value : []);

// Q-6: the driver-side noise budget. Mirrored from the server so the client can
// never render more than the server would send.
export const MAX_VENDORS_PER_CARD = 2;
export const MAX_CORRIDOR_VENDORS = 3;

// discovery buckets (server-side Q-3 ranking); the client only labels them
export const BUCKET_LIVE_CONFIRMED = 0;
export const BUCKET_LIVE = 1;
export const BUCKET_UPCOMING_TODAY = 2;
export const BUCKET_THIS_WEEK = 3;

const BUCKET_LABEL = {
  [BUCKET_LIVE_CONFIRMED]: "vendor.live_now",
  [BUCKET_LIVE]: "vendor.live_now",
  [BUCKET_UPCOMING_TODAY]: "vendor.today",
  [BUCKET_THIS_WEEK]: "vendor.this_week",
};

export function bucketLabelKey(bucket) {
  return BUCKET_LABEL[bucket] ?? "vendor.this_week";
}

const TIER_LABEL = {
  verified: "vendor.verified",
  documents_on_file: "vendor.documents_on_file",
  unverified: "vendor.unverified",
};

// §16 C-1: a tier is never colour alone. `verified` earns the positive token; the
// middle rung is deliberately NEUTRAL, because "license on file" is a statement
// about paperwork, not an endorsement — colouring it green would overclaim.
const TIER_TOKEN = {
  verified: "--ledger-500",
  documents_on_file: "--text-2",
  unverified: "--text-3",
};

export function verificationPresentation(status) {
  return {
    labelKey: TIER_LABEL[status] ?? "vendor.unverified",
    token: TIER_TOKEN[status] ?? "--text-3",
  };
}

// §11.7: relative age + WHO said it. A vendor-sourced belief returns the "vendor
// says" label and NEVER a driver count, however many rows are behind it.
export function presenceLabel(presence, nowMs, labels = {}) {
  if (!presence || presence.present !== true) return null;
  if (presence.source === "vendor") {
    const age = freshnessLabel(
      { reported_at: presence.reported_at, source: "vendor" },
      nowMs,
      { feed: labels.vendorSays ?? "vendor says here" },
    );
    return age;
  }
  return freshnessLabel(
    { reported_at: presence.reported_at, sample_size: presence.sample_size },
    nowMs,
  );
}

// a pin carries a food badge when any vendor is discoverable at that facility.
// §11.1: extra signals ride as badges on existing pins, never as new pins.
export function foodBadgeFacilityIds(entries) {
  return new Set(asList(entries).map((e) => e.facility_id));
}

export function withFoodBadges(pins, entries) {
  const flagged = foodBadgeFacilityIds(entries);
  return asList(pins).map((pin) =>
    flagged.has(pin.facility_id) ? { ...pin, has_food: true } : pin,
  );
}

// Q-6: the card shows at most two. The server already caps, but a client that
// silently rendered everything it was handed would be one API change from noise.
export function cardVendors(entries) {
  return asList(entries).slice(0, MAX_VENDORS_PER_CARD);
}

export function corridorVendors(entries) {
  return asList(entries).slice(0, MAX_CORRIDOR_VENDORS);
}

// "until 9pm" — the one time fact a driver needs at a glance (§12.2 numbers first)
export function untilLabel(endsAt, locale = undefined) {
  if (!endsAt) return null;
  return new Date(endsAt).toLocaleTimeString(locale, {
    hour: "numeric",
    minute: "2-digit",
  });
}

// menu prices are Mono figures like every other money figure (§6.2 T-2)
export function priceLabel(cents) {
  if (cents === null || cents === undefined) return null;
  return `$${(cents / 100).toFixed(2)}`;
}

// Q-2 reliability reads as the raw pair, never a percentage: a fraction carries
// its own sample size, and "95%" over two appearances would overstate what we know.
export function showsUpLabel(showsUp) {
  if (!showsUp || !showsUp.published) return null;
  return { confirmed: showsUp.confirmed, published: showsUp.published };
}
