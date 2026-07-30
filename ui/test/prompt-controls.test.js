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

  async function mountFacility(handlers) {
    stubFetch(handlers);
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

    const buttons = w.findAll(".cta--ghost");
    await buttons.at(buttons.length - 1).trigger("click");
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
