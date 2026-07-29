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
//   interruptions; opening a list is asking. Quiet hours defer, they do not destroy.
// · §10.5 forbids badges in More, so no unread count leaks onto the row or the tab —
//   a number that follows a driver around is an interruption in a different hat.
// · Empty is a real state with real words, because an empty inbox and a broken one
//   look identical otherwise — which is how this area went unnoticed this long.
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
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
    // the suppressed one is present AND labelled as held — deferring is not deleting
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

describe("More — the inbox row (§10.5)", () => {
  it("carries no badge or unread count, per §10.5", async () => {
    // "deliberately boring; a plain 64 dp row list. No cards, no promos, NO BADGES."
    // A count on this row would be an interruption the §13 budget never got to rule
    // on — so this reads the SHIPPED template and asserts the row renders a label and
    // nothing else. Asserting it against a mounted component would need a session, a
    // router and a live fetch; the template is the thing that can actually drift.
    const src = (await import("../src/surfaces/MoreSurface.vue?raw")).default;
    const row = src.match(/<button class="alerts alerts--link" type="button" @click="openNotifications">([\s\S]*?)<\/button>/);
    expect(row, "the notifications row must exist in More").toBeTruthy();
    expect(row[1]).toContain("more.notifications");
    expect(row[1]).not.toMatch(/unread|count|badge/i);
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
