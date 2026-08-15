/* AI-CONTEXT: the facility page a driver can actually use (§23 entry 153).
 *
 * Owner report: "viewing facilities and rating them is not working properly and it is
 * very noisy for a non tech savvy user." Both halves were true and both were measured in
 * a real browser against the real API before a line changed here.
 *
 * WHY THESE TESTS MOUNT AND CLICK RATHER THAN CALL. Every existing facility test calls
 * `askQuestion()` — the API function — directly, and that is exactly how a permanently
 * disabled submit button survived: the suite exercised the code UNDER the control, and
 * the control could never reach it. `asking` was the sheet's open flag and the button's
 * busy flag at once, so `:disabled="asking"` was true in every state where the button was
 * on screen. Measured live: label " Sending…" before a character is typed, isDisabled()
 * true, click refused. **Nobody has ever asked a question in this product.**
 *
 * So: these drive the DOM. A test that proves the button works has to press the button.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import FacilityProfileSurface from "../src/surfaces/FacilityProfileSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout } from "../src/core/api.js";
import en from "../src/core/i18n/en.json";

// AI-CONTEXT: the shape the REAL endpoint returns, name included (§23 entry 153). The
// name is the field the response never carried while the surface rendered it, so a
// fixture that supplies one without the API sending one is how the blank `<h1>` survived
// — which is precisely what happened in `ui-components.test.js`. `test_facility_api.py`
// holds the server end of this same contract.
const BARE = {
  facility_id: "f-1",
  name: "Blue Beacon",
  facility_type: "truck_stop",
  ratings: { overall: null, review_count: 0, per_aspect: {} },
  reviews: [],
  dwell: { overall: { sample_size: 0, median_seconds: null }, by_hour: {} },
};
const RICH = {
  ...BARE,
  name: "Dallas Distribution Center",
  facility_type: "shipper_receiver",
  ratings: { overall: 4.33, review_count: 2, per_aspect: {} },
  reviews: [{ id: "r1", text: "Doors usually open, minimal detention.", ratings: {} }],
  dwell: { overall: { sample_size: 3, median_seconds: 9000 }, by_hour: {} },
};

function jsonOk(body) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

// `risk`/`hours` are what the two intel fetches return; `sample` drives the honesty floor
function net(profile, { risk = null, hours = [], questions = [], muted = null } = {}) {
  return vi.fn((url, opts) => {
    const u = String(url);
    if (opts?.method === "POST") return jsonOk({ ok: true });
    if (u.includes("/profile")) return jsonOk(profile);
    if (u.includes("/intel/detention-risk")) {
      return jsonOk(risk ?? { exceed_rate: null, sample_size: 0, basis: "tracked_stops" });
    }
    if (u.includes("/intel/appointment-hours")) return jsonOk(hours);
    if (u.includes("/community/questions")) return jsonOk(questions);
    if (u.includes("/prompt-pref")) return jsonOk({ muted });
    if (u.includes("/vendors/service-center/")) return jsonOk(null);
    return jsonOk({});
  });
}

async function mountFacility() {
  const router = createRouter({ history: createMemoryHistory(), routes });
  router.push("/facility/f-1");
  await router.isReady();
  const w = mount(FacilityProfileSurface, { global: { plugins: [router] } });
  await flushPromises();
  await flushPromises();
  return w;
}

beforeEach(() => {
  localStorage.clear();
  setToken("tok-facility");
});
afterEach(() => {
  logout();
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("the driver is told which place they are looking at", () => {
  it("renders the facility's name", async () => {
    // the `<h1>` was empty on every facility page in this product's life
    vi.stubGlobal("fetch", net(RICH));
    const w = await mountFacility();

    expect(w.find("h1").text()).toBe("Dallas Distribution Center");
    w.unmount();
  });

  it("names it on a facility with nothing else to show", async () => {
    // the 99.8% case: no profile, no reviews, no questions. The name is the ONLY thing
    // on the screen that is known, which makes it the one thing that must be there.
    vi.stubGlobal("fetch", net(BARE));
    const w = await mountFacility();

    expect(w.find("h1").text()).toBe("Blue Beacon");
    w.unmount();
  });
});

describe("a driver can ask a question", () => {
  it("the submit control is usable the moment there is something to send", async () => {
    vi.stubGlobal("fetch", net(RICH));
    const w = await mountFacility();

    await w.find(".cta--ghost").trigger("click");
    await flushPromises();

    const submit = w.find(".ask .cta");
    expect(submit.exists()).toBe(true);
    // empty: nothing to send, so disabled is CORRECT here and is a different reason
    expect(submit.attributes("disabled")).toBeDefined();
    expect(submit.text()).toContain(en["qa.submit"]);
    expect(submit.text()).not.toContain(en["busy.sending"]);

    await w.find(".ask__input").setValue("Is the north gate open after 8pm?");
    // the whole defect in one assertion: with text typed, the button must be pressable
    expect(w.find(".ask .cta").attributes("disabled")).toBeUndefined();
    w.unmount();
  });

  it("pressing it actually sends the question", async () => {
    const fetchMock = net(RICH);
    vi.stubGlobal("fetch", fetchMock);
    const w = await mountFacility();

    await w.find(".cta--ghost").trigger("click");
    await flushPromises();
    await w.find(".ask__input").setValue("Is the north gate open after 8pm?");
    await w.find(".ask .cta").trigger("click");
    await flushPromises();

    const posted = fetchMock.mock.calls.find(
      ([u, o]) => String(u).includes("/community/questions") && o?.method === "POST",
    );
    expect(posted, "the question was never sent").toBeTruthy();
    expect(JSON.parse(posted[1].body).text).toBe("Is the north gate open after 8pm?");
    w.unmount();
  });

  it("closes and clears once the write is done", async () => {
    vi.stubGlobal("fetch", net(RICH));
    const w = await mountFacility();

    await w.find(".cta--ghost").trigger("click");
    await flushPromises();
    await w.find(".ask__input").setValue("Anything I should know?");
    await w.find(".ask .cta").trigger("click");
    await flushPromises();

    expect(w.find(".ask__input").exists()).toBe(false);
    w.unmount();
  });
});

describe("a facility nobody has reported on is quiet (§15.3)", () => {
  it("says one sentence and offers the two things a driver can do", async () => {
    /* MEASURED BEFORE THE FIX, in a real browser at 360 dp: six cards, every one of them
       a heading over an empty state — "No dock-time data yet", "Not enough tracked stops
       yet", "— · 0 reviews", "No reviews yet", "No questions yet", "Lot status prompts" —
       under a blank title. 41 of 18,326 facilities carry a profile, so THIS is the
       ordinary screen, not an edge case. */
    vi.stubGlobal("fetch", net(BARE));
    const w = await mountFacility();

    expect(w.findAll(".card")).toHaveLength(0);
    expect(w.find(".profile__bare").text()).toBe(en["profile.empty"]);
    expect(w.find(".add-review").exists()).toBe(true);
    expect(w.find(".cta--ghost").text()).toBe(en["qa.ask"]);
    w.unmount();
  });

  it("still renders the cards that DO have something", async () => {
    // the collapse must not swallow real intel — the failure mode opposite to the noise
    vi.stubGlobal("fetch", net(RICH));
    const w = await mountFacility();

    expect(w.find(".profile__bare").exists()).toBe(false);
    const titles = w.findAll(".card__title").map((n) => n.text());
    expect(titles).toContain(en["profile.dock_time"]);
    expect(titles).toContain(en["profile.rating"]);
    expect(titles).toContain(en["profile.reviews_title"]);
    // and the heading is the Title-case one, not the "· 2 reviews" suffix it used to reuse
    expect(titles).not.toContain(en["profile.reviews"]);
    w.unmount();
  });

  it("keeps the mute control reachable when the lot IS muted", async () => {
    /* Entry 114's rule survives the collapse: "a mute a driver cannot see is a mute they
       cannot undo". A bare facility hides this row — but never when it is the row that
       switched something off. */
    vi.stubGlobal("fetch", net(BARE, { muted: true }));
    const w = await mountFacility();

    expect(w.find(".prompt-mute").exists()).toBe(true);
    expect(w.text()).toContain(en["prompts.lot_unmute"]);
    w.unmount();
  });

  it("hides the un-muted prompt row on a facility with nothing on it", async () => {
    vi.stubGlobal("fetch", net(BARE, { muted: false }));
    const w = await mountFacility();

    expect(w.find(".prompt-mute").exists()).toBe(false);
    w.unmount();
  });
});

describe("a rate is not shown until it is one (§11.7)", () => {
  it("suppresses a percentage drawn from too few stops", async () => {
    /* MEASURED: `exceed_rate 0.67` over `sample_size 3` rendered a display-size 67% in
       --flare-500, the alarm token. Two stops out of three is not a two-in-three chance,
       and the decision log already settled this shape for vendor reliability: a raw pair,
       never a percentage, because "95% over two appearances would overstate what we
       know". */
    vi.stubGlobal(
      "fetch",
      net(RICH, { risk: { exceed_rate: 0.67, sample_size: 3, basis: "tracked_stops" } }),
    );
    const w = await mountFacility();

    expect(w.text()).not.toContain("67%");
    expect(w.find(".risk__figure").exists()).toBe(false);
    w.unmount();
  });

  it("shows it once the sample carries it", async () => {
    vi.stubGlobal(
      "fetch",
      net(RICH, { risk: { exceed_rate: 0.67, sample_size: 12, basis: "tracked_stops" } }),
    );
    const w = await mountFacility();

    expect(w.find(".risk__figure").text()).toBe("67%");
    // the sample is never dropped from the figure it qualifies
    expect(w.text()).toContain("12");
    w.unmount();
  });

  it("suppresses a fastest hour drawn from too few stops", async () => {
    // "00:00" off two stops is a midnight that means nothing
    vi.stubGlobal(
      "fetch",
      net(RICH, { hours: [{ hour: 0, median_seconds: 8100, sample_size: 2 }] }),
    );
    const w = await mountFacility();

    expect(w.find(".best-hour").exists()).toBe(false);
    w.unmount();
  });
});
