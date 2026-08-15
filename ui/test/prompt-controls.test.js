// AI-CONTEXT: the two switches the lot-status prompt shipped without (§23 entry 114).
//
// The class switch is not a nicety — it is the ONLY way a driver can turn the prompt on.
// `dispatch` refuses an opt-in class before any tier logic and the class defaults to off,
// so until this control existed the feature suppressed `not_opted_in` for every driver
// while its own server tests opted in by calling the service function. Third time in one
// feature that the rules were right and nothing could reach them (104 §4, 105 §4).
//
// What these defend:
// · Neither control renders a GUESS. Until the server has answered, there is no switch —
//   a toggle showing "off" when the truth is unknown teaches the driver something false
//   and §11.7 forbids exactly that.
// · A failed write leaves the switch where it was. Flipping optimistically would claim a
//   choice that never landed.
// · Muting one lot says, in words, that other stops still ask. A per-subject mute the
//   driver reads as a class-wide one is the class switch wearing a smaller label.
// · Off is exactly as easy as on (§21.8) — both controls are the same control twice.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import NotificationsSheet from "../src/core/components/NotificationsSheet.vue";
import FacilityProfileSurface from "../src/surfaces/FacilityProfileSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

const CLASSES = (optedIn) => ({
  classes: [
    { key: "lot_status_prompt", opted_in: optedIn, opt_in_default: false, max_per_day: 1, tier: "P1" },
  ],
});

function jsonOnce(body, ok = true) {
  return { ok, status: ok ? 200 : 500, json: () => Promise.resolve(body) };
}

// routes the handful of calls each surface makes on mount; anything unlisted rejects,
// which is what the surfaces' own fixture fallbacks are for
function stubFetch(handlers) {
  const fetchMock = vi.fn((url, init = {}) => {
    for (const [fragment, respond] of handlers) {
      if (String(url).includes(fragment)) return Promise.resolve(respond(init));
    }
    return Promise.reject(new Error(`unstubbed ${url}`));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => setToken("tok-prompts"));
afterEach(() => {
  vi.unstubAllGlobals();
  logout();
});

describe("the class switch in the notifications sheet", () => {
  it("offers to turn the prompt on, stating the cost before the switch", async () => {
    stubFetch([["/notifications/classes", () => jsonOnce(CLASSES(false))]]);

    const w = mount(NotificationsSheet, { props: { notifications: [] } });
    await flushPromises();

    expect(w.text()).toContain(en["prompts.lot_what"]);
    expect(w.text()).toContain(en["prompts.lot_on"]);
    // §21.8: the offer says what will be sent and how often BEFORE the tap
    expect(en["prompts.lot_what"]).toContain("once a day");
    w.unmount();
  });

  it("turning it on PUTs the class and then says it is on", async () => {
    const fetchMock = stubFetch([
      [
        "/notifications/classes/lot_status_prompt/opt-in",
        () => jsonOnce({ class: "lot_status_prompt", opted_in: true }),
      ],
      ["/notifications/classes", () => jsonOnce(CLASSES(false))],
    ]);

    const w = mount(NotificationsSheet, { props: { notifications: [] } });
    await flushPromises();
    const buttons = w.findAll(".push__cta");
    await buttons.at(buttons.length - 1).trigger("click");
    await flushPromises();

    const put = fetchMock.mock.calls.find(([u]) => String(u).includes("/opt-in"));
    expect(put, "nothing switched the class on").toBeTruthy();
    expect(put[1].method).toBe("PUT");
    expect(JSON.parse(put[1].body)).toEqual({ opted_in: true });
    expect(w.text()).toContain(en["prompts.lot_off"]);
    w.unmount();
  });

  it("offers to turn it back off once it is on", async () => {
    stubFetch([["/notifications/classes", () => jsonOnce(CLASSES(true))]]);

    const w = mount(NotificationsSheet, { props: { notifications: [] } });
    await flushPromises();

    expect(w.text()).toContain(en["prompts.lot_off"]);
    expect(w.text()).not.toContain(en["prompts.lot_on"]);
    w.unmount();
  });

  it("renders NO switch when the server never answered", async () => {
    stubFetch([]); // every call rejects — offline, or no session

    const w = mount(NotificationsSheet, { props: { notifications: [] } });
    await flushPromises();

    expect(w.text()).not.toContain(en["prompts.lot_what"]);
    expect(w.text()).not.toContain(en["prompts.lot_on"]);
    w.unmount();
  });

  it("a failed write leaves the switch where it was", async () => {
    stubFetch([
      ["/notifications/classes/lot_status_prompt/opt-in", () => jsonOnce({}, false)],
      ["/notifications/classes", () => jsonOnce(CLASSES(false))],
    ]);

    const w = mount(NotificationsSheet, { props: { notifications: [] } });
    await flushPromises();
    const buttons = w.findAll(".push__cta");
    await buttons.at(buttons.length - 1).trigger("click");
    await flushPromises();

    expect(w.text()).toContain(en["prompts.lot_on"]); // still offering to turn it ON
    w.unmount();
  });
});

describe("the mute toggle on the facility screen", () => {
  const FACILITY = "f-mute-1";

// AI-CONTEXT: the facility profile this surface needs to render at all (§23 entry
// 131). It used to come from `sampleProfile()` inside the SURFACE — the stub below
// left `/profile` unhandled on purpose, with a comment saying the fixture fallback
// was what made that work. It no longer is: an unreachable profile now renders
// §15.4's failed line, which is correct and has no mute control on it. Shape copied
// from GET /facility/{id}/profile.
const PROFILE = {
  facility_id: FACILITY,
  name: "Dallas Cold Storage",
  check_in_procedure: "Check in at guard shack; keep PPE on in the yard.",
  overnight_parking: true,
  restrooms: true,
  dwell: {
    overall: { median_seconds: 8100, p90_seconds: 15300, sample_size: 12 },
    by_hour: {},
  },
  ratings: { overall: 3.8, review_count: 2, per_aspect: {} },
  detention_risk: { rate: null, sample_size: 0, basis: "m3_pending" },
  reviews: [],
};

  async function mountFacility(handlers) {
    // the profile handler goes LAST so a test may still override it
    stubFetch([...handlers, ["/profile", () => jsonOnce(PROFILE)]]);
    const router = createRouter({ history: createMemoryHistory(), routes });
    router.push(`/facility/${FACILITY}`);
    await router.isReady();
    const w = mount(FacilityProfileSurface, { global: { plugins: [router] } });
    await flushPromises();
    return w;
  }

  it("offers to silence this lot and says the others still ask", async () => {
    const w = await mountFacility([
      ["/prompt-pref", () => jsonOnce({ facility_id: FACILITY, muted: false })],
    ]);

    expect(w.text()).toContain(en["prompts.lot_title"]);
    expect(w.text()).toContain(en["prompts.lot_mute"]);
    // the scope of the mute is stated, so a per-subject control is not read as the class
    expect(w.text()).toContain(en["prompts.lot_elsewhere"]);
    w.unmount();
  });

  it("muting POSTs to the mute route and flips to an undo", async () => {
    const w = await mountFacility([
      ["/mute-prompts", () => jsonOnce({ facility_id: FACILITY, muted: true })],
      ["/prompt-pref", () => jsonOnce({ facility_id: FACILITY, muted: false })],
    ]);
    const before = w.text();
    expect(before).toContain(en["prompts.lot_mute"]);

    // AI-CONTEXT: named, not positional (§23 entry 153). This was
    // `findAll(".cta--ghost").at(-1)`, and the moment "Ask a question" became a screen
    // action there were two ghost buttons — so the click landed on the ask sheet and the
    // assertion below failed on a screen where nothing was wrong with the mute at all.
    // A selector standing in for an idea stops standing for it when the page grows.
    await w.find(".prompt-mute__toggle").trigger("click");
    await flushPromises();

    expect(w.text()).toContain(en["prompts.lot_unmute"]);
    expect(w.text()).toContain(en["prompts.lot_muted"]);
    w.unmount();
  });

  it("shows the undo, not the mute, when the lot is already muted", async () => {
    const w = await mountFacility([
      ["/prompt-pref", () => jsonOnce({ facility_id: FACILITY, muted: true })],
    ]);

    expect(w.text()).toContain(en["prompts.lot_unmute"]);
    expect(w.text()).toContain(en["prompts.lot_muted"]);
    expect(w.text()).not.toContain(en["prompts.lot_mute"]);
    w.unmount();
  });

  it("renders no row at all when the preference is unknown", async () => {
    const w = await mountFacility([]); // /prompt-pref rejects

    expect(w.text()).not.toContain(en["prompts.lot_title"]);
    w.unmount();
  });
});

// AI-CONTEXT: §13.3's quiet hours (§23 entry 115) — the clause where BOTH halves were
// unreachable. "Default 22:00-06:00 local (driver-adjustable)": the server measured the
// window in UTC because nothing ever sent it a zone, and nothing could move the window.
describe("quiet hours in the notifications sheet", () => {
  const PREFS = { timezone: "America/Denver", quiet_start: "22:00", quiet_end: "06:00" };

  it("shows the window and names the zone it is measured in", async () => {
    stubFetch([["/notifications/prefs", () => jsonOnce(PREFS)]]);

    const w = mount(NotificationsSheet, { props: { notifications: [] } });
    await flushPromises();

    const inputs = w.findAll(".quiet__input");
    expect(inputs).toHaveLength(2);
    expect(inputs[0].element.value).toBe("22:00");
    expect(inputs[1].element.value).toBe("06:00");
    // the zone is STATED, not hidden: a phone reporting the wrong one is a fact the
    // driver can only act on if they can see it
    expect(w.text()).toContain("America/Denver");
    w.unmount();
  });

  it("PUTs the window the driver chose, and only the window", async () => {
    const fetchMock = stubFetch([
      ["/notifications/prefs", (init) => (init.method === "PUT"
        ? jsonOnce({ ...PREFS, quiet_start: "23:30" })
        : jsonOnce(PREFS))],
    ]);

    const w = mount(NotificationsSheet, { props: { notifications: [] } });
    await flushPromises();
    const start = w.findAll(".quiet__input")[0];
    await start.setValue("23:30");
    await start.trigger("change");
    await flushPromises();

    const put = fetchMock.mock.calls.find(([, init]) => init && init.method === "PUT");
    expect(put, "the window was never sent").toBeTruthy();
    const body = JSON.parse(put[1].body);
    expect(body.quiet_start).toBe("23:30");
    // the zone is the browser's answer and must not ride along here, or a driver editing
    // their window would overwrite a zone they never touched
    expect(body).not.toHaveProperty("timezone");
    w.unmount();
  });

  it("says plainly when the window is empty rather than leaving it as folklore", async () => {
    stubFetch([
      ["/notifications/prefs", () => jsonOnce({ ...PREFS, quiet_start: "03:00", quiet_end: "03:00" })],
    ]);

    const w = mount(NotificationsSheet, { props: { notifications: [] } });
    await flushPromises();

    expect(w.text()).toContain(en["quiet.always"]);
    expect(w.text()).not.toContain("America/Denver");
    w.unmount();
  });

  it("renders no window at all when the server never answered", async () => {
    stubFetch([]);

    const w = mount(NotificationsSheet, { props: { notifications: [] } });
    await flushPromises();

    expect(w.findAll(".quiet__input")).toHaveLength(0);
    w.unmount();
  });
});

describe("the timezone the server never had", () => {
  it("a session PUTs the browser's detected zone, and only the zone", async () => {
    logout();
    const fetchMock = stubFetch([["/notifications/prefs", () => jsonOnce({})]]);

    setToken("tok-zone");
    await flushPromises();

    const put = fetchMock.mock.calls.find(
      ([url, init]) => String(url).includes("/notifications/prefs") && init && init.method === "PUT",
    );
    expect(put, "nothing told the server where the driver is").toBeTruthy();
    const body = JSON.parse(put[1].body);
    expect(typeof body.timezone).toBe("string");
    expect(body.timezone.length).toBeGreaterThan(0);
    // partial on purpose: this fires on every sign-in and must not undo a window the
    // driver set
    expect(body).not.toHaveProperty("quiet_start");
  });
});

describe("crossing a time zone mid-trip", () => {
  it("re-checks the zone when the app comes back to the foreground", async () => {
    logout();
    const fetchMock = stubFetch([["/notifications/prefs", () => jsonOnce({})]]);
    const real = Intl.DateTimeFormat;
    const zoneStub = (zone) =>
      vi.stubGlobal("Intl", {
        ...Intl,
        DateTimeFormat: () => ({ resolvedOptions: () => ({ timeZone: zone }) }),
      });

    try {
      zoneStub("America/Denver");
      setToken("tok-crossing");
      await flushPromises();

      // ...and the truck rolls into Kansas
      zoneStub("America/Chicago");
      document.dispatchEvent(new Event("visibilitychange"));
      await flushPromises();

      const zones = fetchMock.mock.calls
        .filter(([url, init]) => String(url).includes("/notifications/prefs") && init?.method === "PUT")
        .map(([, init]) => JSON.parse(init.body).timezone);
      expect(zones).toEqual(["America/Denver", "America/Chicago"]);
    } finally {
      vi.stubGlobal("Intl", { ...Intl, DateTimeFormat: real });
    }
  });

  it("says nothing when the zone has not changed", async () => {
    logout();
    const fetchMock = stubFetch([["/notifications/prefs", () => jsonOnce({})]]);

    setToken("tok-samezone");
    await flushPromises();
    const before = fetchMock.mock.calls.length;

    document.dispatchEvent(new Event("visibilitychange"));
    await flushPromises();

    // the dedupe is what makes a foreground re-check free
    expect(fetchMock.mock.calls.length).toBe(before);
  });
});
