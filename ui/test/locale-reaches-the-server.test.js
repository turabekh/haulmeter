// AI-CONTEXT: §23 entry 232 — the language a driver picks reaches their notifications.
//
// F8 writes every driver alert in the language on `f01.driver_profile.locale`. The app's
// picker wrote `localStorage` and nothing else, so that column was `en` for every account
// that has ever existed and a driver running the app in Uzbek got their detention alert
// in English. The whole six-locale notification catalogue — 64 strings per locale, live on
// production — had never once been reached by a real driver, and nothing failed to say so.
//
// What these defend:
// · Changing language TELLS THE SERVER, because that is the entire point.
// · It tells it WITHOUT BLOCKING and without being able to fail the switch. §15.1 makes
//   offline a mode; a driver in a dead zone still gets to change their language.
// · The device's stored choice WINS on reconcile — the picker is the only place a driver
//   states this, and it lives on the handset they stated it on.
// · A device with NO stored choice ADOPTS the server's, so a reinstall does not silently
//   reset someone to English. This is also the repair path for every existing account.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { useI18n, syncLocale, hasStoredLocale } from "../src/core/i18n.js";
import { setToken, logout } from "../src/core/api.js";

const KEY = "longhaul.locale";

describe("the language a driver picks reaches the server", () => {
  beforeEach(() => {
    localStorage.clear();
    setToken("t-locale");
    useI18n().setLocale("en", { push: false });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    logout();
    localStorage.clear();
  });

  it("PATCHes the new language when the picker is used", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ locale: "uz" }) }),
    );
    vi.stubGlobal("fetch", fetchMock);

    useI18n().setLocale("uz");
    await Promise.resolve();

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/auth/locale");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ locale: "uz" });
  });

  it("changes the app's language even when the write fails", async () => {
    // the dead zone. The screen is the driver's, not the network's.
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));

    const i18n = useI18n();
    i18n.setLocale("ru");
    await Promise.resolve();
    await Promise.resolve();

    expect(i18n.locale.value).toBe("ru");
    expect(localStorage.getItem(KEY)).toBe("ru");
  });

  it("records that the driver has actually chosen", () => {
    localStorage.clear(); // a fresh handset: the app has only ever GUESSED so far
    expect(hasStoredLocale(), "a guess is not a choice").toBe(false);

    useI18n().setLocale("so", { push: false });

    expect(hasStoredLocale()).toBe(true);
  });
});

describe("reconciling the device and the server (§23 entry 232)", () => {
  beforeEach(() => {
    localStorage.clear();
    setToken("t-sync");
  });
  afterEach(() => {
    vi.restoreAllMocks();
    logout();
    localStorage.clear();
  });

  function stub(meLocale, onPatch = () => {}) {
    return vi.fn((url, init = {}) => {
      if (String(url).includes("/auth/locale")) {
        onPatch(JSON.parse(init.body));
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ account_id: "a1", email: "d@x.com", locale: meLocale }),
      });
    });
  }

  it("pushes the device's choice up when the server disagrees", async () => {
    const pushed = [];
    vi.stubGlobal("fetch", stub("en", (b) => pushed.push(b.locale)));
    useI18n().setLocale("uz", { push: false }); // a real, stored choice

    await syncLocale();

    expect(pushed, "the picker is where a driver states this").toEqual(["uz"]);
  });

  it("adopts the server's language when the device has never chosen", async () => {
    // a reinstall, or a new phone. Resetting them to English would be the app forgetting
    // something the driver told it.
    const pushed = [];
    vi.stubGlobal("fetch", stub("pa", (b) => pushed.push(b.locale)));
    const i18n = useI18n();

    await syncLocale();

    expect(i18n.locale.value).toBe("pa");
    expect(pushed, "adopting is not a new choice — it must not echo back").toEqual([]);
  });

  it("says nothing when the two already agree", async () => {
    const pushed = [];
    vi.stubGlobal("fetch", stub("ru", (b) => pushed.push(b.locale)));
    useI18n().setLocale("ru", { push: false });

    await syncLocale();

    expect(pushed).toEqual([]);
  });

  it("is silent when the driver is offline", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
    useI18n().setLocale("es", { push: false });

    await expect(syncLocale()).resolves.toBeUndefined();
    expect(useI18n().locale.value, "the device keeps its own answer").toBe("es");
  });
});
