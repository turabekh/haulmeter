// AI-CONTEXT: §23 entry 102 — the surface F8 never had.
//
// F8 decided tiers, budgets, quiet hours and classes since it shipped and every
// decision ended in a row nobody could read: zero notification endpoints existed, the
// client has no service worker or push registration, and the only gateway wired in
// application code is the recording one used by tests. §23 entry 429 caught the
// miniature — "nothing may be filed P2 until a surface renders the digest".
//
// What these defend:
// · §13.5 — the deep link is the SERVER's and is followed exactly, never a tab root.
// · A suppressed notification is shown AND says it was held. §13.1 caps unprompted
//   interruptions; opening a list is asking. Quiet hours FILE — they do not defer and
//   they do not destroy (§13.3, §23 entry 116). Rendering the held row is what keeps
//   the information reachable; nothing ever re-sends it. This comment asserted
//   "defer" until HANDOFF-109 — the FOURTH copy of a claim 108 corrected in three
//   other files and missed here, which is the whole argument for the shape test below.
// · No unread COUNT reaches the driver's chrome. §10.5 forbids badges in More and the
//   affordance has since moved to the status strip (§23 entry 230) — the rule survived
//   the surface, because entry 102's reasoning was never about which tab it sat on: a
//   number that follows a driver around is an interruption in a different hat. A dot
//   says something is waiting; a count asks to be cleared.
// · Empty is a real state with real words, because an empty inbox and a broken one
//   look identical otherwise — which is how this area went unnoticed this long.
import { describe, it, expect, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import NotificationsSheet from "../src/core/components/NotificationsSheet.vue";
import en from "../src/core/i18n/en.json";

const NOW = Date.UTC(2026, 6, 29, 12, 0, 0);

const ROWS = [
  {
    id: "n1",
    tier: "P0",
    category: "detention_started",
    title: "Detention started · $75/h",
    body: "Notice ready to send",
    deep_link: "/load/abc/evidence",
    status: "sent",
    suppressed_reason: null,
    created_at: new Date(NOW - 20 * 60000).toISOString(),
    read_at: null,
  },
  {
    id: "n2",
    tier: "P1",
    category: "free_time_warning",
    title: "30 minutes of free time left",
    body: "Arrived 09:12",
    deep_link: "/load",
    status: "suppressed",
    suppressed_reason: "quiet_hours",
    created_at: new Date(NOW - 3 * 3600000).toISOString(),
    read_at: "2026-07-29T09:00:00Z",
  },
];

function mountSheet(notifications = ROWS) {
  return mount(NotificationsSheet, { props: { notifications, now: NOW } });
}

describe("NotificationsSheet (§23 entry 102)", () => {
  it("says plainly when there is nothing, rather than showing a blank", () => {
    const w = mountSheet([]);
    expect(w.text()).toContain(en["notifications.empty"]);
  });

  it("renders what F8 decided, including what it held back", () => {
    const w = mountSheet();
    expect(w.findAll(".notif__row")).toHaveLength(2);
    expect(w.text()).toContain("Detention started · $75/h");
    // the suppressed one is present AND labelled as held — filing is not deleting
    expect(w.text()).toContain(en["notifications.held"]);
  });

  it("marks the unread one and only the unread one", () => {
    const w = mountSheet();
    const unread = w.findAll(".notif__row--unread");
    expect(unread).toHaveLength(1);
    expect(unread[0].text()).toContain("Detention started");
  });

  it("emits the whole notification so the caller can follow its deep link", async () => {
    const w = mountSheet();
    await w.findAll(".notif__row")[0].trigger("click");
    expect(w.emitted("open")[0][0]).toMatchObject({ deep_link: "/load/abc/evidence" });
  });

  it("uses the same coarse relative age the map uses for freshness", () => {
    // one vocabulary everywhere (§14.3) — not a second date format for this screen
    const w = mountSheet();
    expect(w.find(".notif__age").text()).toBe("20m");
  });
});

// AI-CONTEXT: the test HANDOFF-108 §8 asked for — it asserts the SHAPE of the label,
// not its key.
//
// "Held until morning" shipped and was wrong for FOUR of the five suppression reasons
// from the day it was written — `budget`, `muted`, `resting` and `not_opted_in` have no
// morning — and no test caught it for two sessions, because every assertion in this
// file compares against `en["notifications.held"]`. Comparing a render to the same
// table it renders from can only prove the plumbing works; it is true whatever the
// string says, so it was still green while the product lied to drivers.
//
// §13.3's operative clause is what is checked here instead: NO SURFACE MAY PROMISE
// THAT A HELD NOTIFICATION WILL ARRIVE LATER. That is a claim about words, so the test
// reads the words — in all six locales, because the label was corrected in six and a
// seventh translation could reintroduce the promise in a language nobody here reads.
//
// Matching is by TOKEN, never by substring, and the match MODE is per term because a
// single mode is wrong in at least two of these languages:
//   ·  `word`  exact — `до` is a Russian preposition, and as a prefix it would also
//              fire on `документ`, failing a correct label. A check that cries wolf is
//              a check people delete.
//   · `word*`  prefix — inflection. `утр*` catches `утра` and `утром` without listing
//              either; `ਸਵੇਰ*` catches the Gurmukhi locative.
//   · `*word`  suffix — Uzbek is agglutinative and glues these on: "until morning" is
//              `ertalabgacha`, one token, which a prefix match would sail past.
const SUPPRESSION_REASONS = ["budget", "quiet_hours", "resting", "not_opted_in", "muted"];

// a held label may not name a time, and these are the ways each locale would name one.
const TIME_PROMISE_TERMS = {
  en: ["morning", "tomorrow", "later", "soon", "until", "resume*", "resent", "requeue*"],
  es: ["mañana", "manana", "luego", "hasta", "pronto", "después", "despues"],
  pa: ["ਸਵੇਰ*", "ਕੱਲ੍ਹ", "ਬਾਅਦ", "ਤੱਕ", "ਜਲਦੀ"],
  ru: ["утр*", "завтра", "позже", "скоро", "до"],
  uz: ["ertalab*", "ertaga", "keyin*", "*gacha", "tez"],
  so: ["subax*", "berri", "dambe", "ilaa", "dhaqso"],
};

function matchesTerm(token, term) {
  if (term.startsWith("*")) return token.endsWith(term.slice(1));
  if (term.endsWith("*")) return token.startsWith(term.slice(0, -1));
  return token === term;
}

function suppressedRow(reason, i) {
  return {
    id: `s${i}`,
    tier: "P1",
    category: "free_time_warning",
    title: "30 minutes of free time left",
    body: "Arrived 09:12",
    deep_link: "/load",
    status: "suppressed",
    suppressed_reason: reason,
    created_at: new Date(NOW - 3 * 3600000).toISOString(),
    read_at: null,
  };
}

describe("a held label may not promise delivery (§13.3, §23 entry 116)", () => {
  it("labels EVERY suppression reason, and labels them identically", () => {
    // the label renders off `status`, not off the reason, so one promise-shaped word
    // would be wrong for whichever reasons it does not describe — which is exactly how
    // "until morning" was wrong four ways at once. Identical labels are what make the
    // single-string check below sufficient.
    const w = mountSheet(SUPPRESSION_REASONS.map(suppressedRow));
    const held = w.findAll(".notif__held");
    expect(held, "every suppressed row says it was held").toHaveLength(
      SUPPRESSION_REASONS.length,
    );
    const rendered = new Set(held.map((h) => h.text().trim()));
    expect([...rendered], "one label for all five reasons").toHaveLength(1);
  });

  it("names no time and no later delivery, in any of the six locales", async () => {
    for (const [loc, terms] of Object.entries(TIME_PROMISE_TERMS)) {
      const table = (await import(`../src/core/i18n/${loc}.json`)).default;
      const label = table["notifications.held"];
      expect(label, `${loc} ships the label`).toBeTruthy();

      const tokens = label.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean);
      for (const term of terms) {
        const hit = tokens.find((tok) => matchesTerm(tok, term.toLowerCase()));
        expect(
          hit,
          `${loc}: "${label}" promises a time via "${hit}" (${term}) — §13.3 forbids any surface promising a held notification will arrive later, because nothing re-sends it`,
        ).toBeUndefined();
      }

      expect(
        label,
        `${loc}: "${label}" names a clock time, which is a promise §13.3 forbids`,
      ).not.toMatch(/\d{1,2}\s*[:.]\s*\d{2}/);
    }
  });
});

describe("More — the inbox row (§10.5)", () => {
  it("marks unread with a dot and never a count (§23 entry 230)", async () => {
    // §10.5's "NO BADGES" was written about the More tab, and entry 102 gave the reason
    // that outlives the surface: a NUMBER that follows a driver around all day is an
    // interruption the §13 budget never got to rule on. The affordance moved to the
    // status strip; the rule did not move with the surface, it survived it.
    //
    // This reads the SHIPPED template, because that is the thing that can drift — a
    // mounted assertion would need a session, a router and a live fetch.
    const src = (await import("../src/core/components/StatusStrip.vue?raw")).default;
    const bell = src.match(/<button\n\s+class="strip__bell"([\s\S]*?)<\/button>/);
    expect(bell, "the bell must exist in the status strip").toBeTruthy();
    expect(bell[1]).toContain("strip__dot");
    // the dot is an empty span: no interpolation inside it, ever
    expect(bell[1]).toMatch(/<span v-if="unread > 0" class="strip__dot"[^>]*><\/span>/);
    expect(bell[1]).not.toMatch(/\{\{\s*unread/);
  });

  it("is gone from the More tab, which is boring again (§10.5)", async () => {
    const src = (await import("../src/surfaces/MoreSurface.vue?raw")).default;
    expect(src).not.toContain("openNotifications");
    expect(src).not.toContain("alerts--link");
  });

  it("ships all six locales for every new string (Forbidden #7)", async () => {
    const locales = ["en", "es", "pa", "ru", "uz", "so"];
    const keys = [
      "notifications.title",
      "notifications.empty",
      "notifications.held",
      "more.notifications",
      "notifications.unread",
    ];
    for (const loc of locales) {
      const table = (await import(`../src/core/i18n/${loc}.json`)).default;
      for (const k of keys) expect(table[k], `${loc}:${k}`).toBeTruthy();
    }
  });
});

// AI-CONTEXT: §23 entry 230 — the bell that is always there.
//
// Reached from a row on the More tab, the inbox required a driver to already suspect
// there was something to read. These mount the real strip, because the things worth
// pinning are behaviours, not template shapes: that the bell survives an empty inbox,
// that a failed read asserts nothing, and that it withdraws at speed.
describe("The status strip's bell (§23 entry 230)", () => {
  const StatusStrip = () => import("../src/core/components/StatusStrip.vue");
  const PROPS = { online: true, pending: 0, failed: 0 };

  async function strip(unread) {
    const api = await import("../src/core/api.js");
    vi.spyOn(api, "fetchNotifications").mockResolvedValue({ notifications: [], unread });
    const w = mount((await StatusStrip()).default, { props: PROPS });
    await flushPromises();
    return w;
  }

  it("is present on a screen with nothing else to say", async () => {
    const w = await strip(0);
    expect(w.find(".strip__bell").exists()).toBe(true);
    expect(w.find(".strip__dot").exists(), "nothing unread, no dot").toBe(false);
  });

  it("shows a dot when something is unread, and never the number", async () => {
    const w = await strip(7);
    expect(w.find(".strip__dot").exists()).toBe(true);
    expect(w.text()).not.toContain("7");
  });

  it("asserts nothing when the read fails", async () => {
    // offline or signed out. A control that misreports itself is worse than one that
    // does nothing, because the driver acts on it (§23 entry 131).
    const api = await import("../src/core/api.js");
    vi.spyOn(api, "fetchNotifications").mockRejectedValue(new Error("no session"));
    const w = mount((await StatusStrip()).default, { props: PROPS });
    await flushPromises();
    expect(w.find(".strip__bell").exists()).toBe(true);
    expect(w.find(".strip__dot").exists(), "a failed read is not an unread state").toBe(false);
  });

  it("withdraws at speed rather than disappearing (§13.4, SM-1)", async () => {
    const state = await import("../src/core/state.js");
    state.__resetStateForTests();
    const w = await strip(3);
    expect(w.find(".strip__bell").attributes("disabled")).toBeUndefined();

    // sustained motion above walking speed for longer than the entry threshold
    const t0 = Date.now();
    state.observeMotion({ speedMps: 25, now: t0 });
    state.observeMotion({ speedMps: 25, now: t0 + state.DRIVING_SUSTAIN_MS + 1 });
    await w.vm.$nextTick();

    expect(w.find(".strip__bell").exists(), "chrome must not strobe at 5.6 mph").toBe(true);
    expect(w.find(".strip__bell").attributes("disabled")).toBeDefined();
    state.__resetStateForTests();
  });

  it("emits the server's deep link rather than routing itself (§13.5)", async () => {
    const api = await import("../src/core/api.js");
    vi.spyOn(api, "markNotificationRead").mockResolvedValue({});
    const w = await strip(1);
    await w.find(".strip__bell").trigger("click");
    await flushPromises();
    await w.findComponent(NotificationsSheet).vm.$emit("open", {
      id: "n1", deep_link: "/load/abc/evidence", read_at: null,
    });
    expect(w.emitted("navigate")[0]).toEqual(["/load/abc/evidence"]);
  });
});
