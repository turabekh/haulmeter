// AI-CONTEXT: the broker's address on the three surfaces that touch it.
//
// The previous session established that the product had NOWHERE to put this address, so
// every detention notice went to an invented literal. These tests are about the three
// places a driver can now supply it — and, in the claim screen's case, that the fix is
// offered exactly where the app complains rather than as a hint to go elsewhere.
//
// Every address here is `@example`: dev SMTP points at a live account and this work makes
// real recipients possible for the first time.
import { describe, it, expect, vi, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import BrokerEmailField from "../src/core/components/BrokerEmailField.vue";
import RateConImportSheet from "../src/core/components/RateConImportSheet.vue";
import ClaimSurface from "../src/surfaces/ClaimSurface.vue";
import LoadSurface from "../src/surfaces/LoadSurface.vue";
import { routes } from "../src/router.js";
import { setToken, logout, setActiveStop } from "../src/core/api.js";
import { contactEmailError } from "../src/core/contact.js";
import en from "../src/core/i18n/en.json";

function jsonOk(body) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

function router() {
  return createRouter({ history: createMemoryHistory(), routes });
}

afterEach(() => {
  vi.unstubAllGlobals();
  logout();
});

// --- the shared rule ---
describe("the client's address rule", () => {
  it("matches the server's, case for case", () => {
    expect(contactEmailError("ap@acme.example")).toBe(null);
    expect(contactEmailError("  ap@acme.example  ")).toBe(null);
    expect(contactEmailError("")).toBe(null); // empty means CLEAR, not invalid
    expect(contactEmailError(null)).toBe(null);
    expect(contactEmailError("acme.example")).toBe("email.one_at");
    expect(contactEmailError("a@b@c.example")).toBe("email.one_at");
    expect(contactEmailError("ap@acme")).toBe("email.domain_dot");
    expect(contactEmailError("ap acme@example.com")).toBe("email.no_spaces");
    expect(contactEmailError("@acme.example")).toBe("email.needs_both");
    expect(contactEmailError(`${"a".repeat(320)}@acme.example`)).toBe("email.too_long");
  });

  it("names every error with a key that exists in the catalogue", () => {
    for (const bad of ["acme.example", "ap@acme", "ap acme@x.example", "@a.example"]) {
      expect(en[contactEmailError(bad)]).toBeTruthy();
    }
  });
});

// --- collect at creation ---
describe("the load-creation form", () => {
  // the sheet opens on the photo step; the confirm form is step 2. An unreadable parse is
  // the state this stack actually runs in with no model key, and it is the shortest honest
  // way in — the manual form IS the confirm form.
  async function atConfirm() {
    const w = mount(RateConImportSheet, { global: { plugins: [router()] } });
    w.vm.$.setupState.draft = { readable: false };
    await flushPromises();
    return w;
  }

  function emailField(w) {
    return w.findAll("input").find((i) => i.attributes("type") === "email");
  }

  it("offers a broker email labelled for what it is FOR", async () => {
    const w = await atConfirm();

    expect(w.text()).toContain(en["load.broker_email"]);
    // labelled by PURPOSE: "Email" on a load form could be anyone's
    expect(en["load.broker_email"]).toContain("detention notices");
  });

  it("refuses to submit a junk address, and says why", async () => {
    const w = await atConfirm();

    await emailField(w).setValue("acme.example");

    expect(w.text()).toContain(en["email.one_at"]);
    const create = w.findAll("button.rc__cta").at(-1);
    expect(create.attributes("disabled")).toBeDefined();
  });

  it("stays skippable — the field is an offer, not a gate", async () => {
    const w = await atConfirm();

    expect(emailField(w).element.value).toBe("");
    expect(w.text()).not.toContain(en["email.one_at"]);
    expect(w.text()).not.toContain(en["email.domain_dot"]);
  });
});

// --- the field itself ---
describe("the broker email field", () => {
  it("states the absence rather than showing an empty box", () => {
    const w = mount(BrokerEmailField, { props: { loadId: "load-1", email: null } });

    expect(w.text()).toContain(en["load.broker_email_none"]);
    expect(w.text()).toContain(en["load.broker_email_add"]);
  });

  it("shows the address on file and offers an edit", () => {
    const w = mount(BrokerEmailField, {
      props: { loadId: "load-1", email: "ap@acme.example" },
    });

    expect(w.text()).toContain("ap@acme.example");
    expect(w.text()).toContain(en["load.broker_email_edit"]);
  });

  it("PATCHes the load and reports the save upward", async () => {
    const calls = [];
    setToken("tok");
    vi.stubGlobal(
      "fetch",
      vi.fn((url, opts) => {
        calls.push({ url: String(url), method: opts?.method, body: opts?.body });
        return jsonOk({ counterparty_email: "ap@acme.example", copied: false });
      }),
    );
    const w = mount(BrokerEmailField, {
      props: { loadId: "load-1", email: null, variant: "inline" },
    });

    await w.find("input").setValue("ap@acme.example");
    await w.findAll("button").find((b) => b.text() === en["load.broker_email_save"]).trigger("click");
    await flushPromises();

    const patch = calls.find((c) => c.method === "PATCH");
    expect(patch).toBeTruthy();
    expect(patch.url).toContain("/load/load-1/counterparty-email");
    expect(JSON.parse(patch.body)).toEqual({ email: "ap@acme.example" });
    expect(w.emitted("saved")).toBeTruthy();
  });

  it("blocks the save while the address is junk", async () => {
    setToken("tok");
    const fetchSpy = vi.fn(() => jsonOk({}));
    vi.stubGlobal("fetch", fetchSpy);
    const w = mount(BrokerEmailField, {
      props: { loadId: "load-1", email: null, variant: "inline" },
    });

    await w.find("input").setValue("acme.example");
    const save = w.findAll("button").find((b) => b.text() === en["load.broker_email_save"]);

    expect(save.attributes("disabled")).toBeDefined();
    expect(w.text()).toContain(en["email.one_at"]);
    await save.trigger("click");
    await flushPromises();
    // no PATCH — `setToken` fires an unrelated prefs sync, so the assertion is about the
    // write this component owns rather than about fetch being idle
    const patches = fetchSpy.mock.calls.filter(([, opts]) => opts?.method === "PATCH");
    expect(patches).toHaveLength(0);
  });

  it("shows the server's refusal when the client's rule let something through", async () => {
    setToken("tok");
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 422,
          json: () => Promise.resolve({ detail: "email domain needs a dot" }),
        }),
      ),
    );
    const w = mount(BrokerEmailField, {
      props: { loadId: "load-1", email: null, variant: "inline" },
    });

    await w.find("input").setValue("ap@acme.example");
    await w.findAll("button").find((b) => b.text() === en["load.broker_email_save"]).trigger("click");
    await flushPromises();

    expect(w.text()).toContain("email domain needs a dot");
  });
});

// --- the fix, where the complaint is ---
const CLAIM = {
  claim_id: "c-1",
  load_id: "load-1",
  amount_cents: 15000,
  detention_seconds: 7200,
  free_time_minutes: 120,
  rate_cents_per_hour: 7500,
  state: "invoiced",
  mode: "invoice",
  facility: "Dock 4",
  counterparty: "Acme",
  counterparty_email: null,
  notice_sent: false,
  notice_delivery: "no_email",
  filed: true,
  chain_valid: true,
  record_count: 3,
  artifact_count: 1,
  timeline: [],
};

describe("the claim screen's no_email state", () => {
  async function mountClaim(sequence) {
    setToken("tok");
    let n = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((url, opts) => {
        const u = String(url);
        if (u.includes("/claim")) return jsonOk(sequence[Math.min(n++, sequence.length - 1)]);
        if (opts?.method === "PATCH") {
          return jsonOk({ counterparty_email: "ap@acme.example", copied: false });
        }
        return jsonOk({});
      }),
    );
    const r = router();
    r.push("/claim/stop-1");
    await r.isReady();
    const w = mount(ClaimSurface, { global: { plugins: [r] } });
    await flushPromises();
    return w;
  }

  it("puts the input inline, not a hint to go somewhere else", async () => {
    const w = await mountClaim([CLAIM]);

    expect(w.text()).toContain(en["notice.delivery.no_email"]);
    expect(w.find(".ev--fix").exists()).toBe(true);
    expect(w.find(".ev--fix input").exists()).toBe(true);
  });

  it("re-derives the delivery state on save, without leaving the screen", async () => {
    const fixed = { ...CLAIM, counterparty_email: "ap@acme.example", notice_delivery: "not_sent" };
    const w = await mountClaim([CLAIM, fixed]);

    await w.find(".ev--fix input").setValue("ap@acme.example");
    await w
      .findAll("button")
      .find((b) => b.text() === en["load.broker_email_save"])
      .trigger("click");
    await flushPromises();

    // the blocker is gone and the row now reads as a notice waiting to be sent
    expect(w.text()).not.toContain(en["notice.delivery.no_email"]);
    expect(w.text()).toContain(en["notice.delivery.not_sent"]);
    expect(w.find(".ev--fix").exists()).toBe(false);
  });

  it("does not offer the fix when the address is not the problem", async () => {
    const w = await mountClaim([{ ...CLAIM, notice_delivery: "sent", notice_sent: true }]);

    expect(w.find(".ev--fix").exists()).toBe(false);
  });
});

// --- the load tab shows it ---
describe("the load tab", () => {
  const METER = {
    stop_id: "stop-1",
    load_id: "load-1",
    facility_name: "Dock 4",
    counterparty: "Acme",
    counterparty_email: null,
    appointment: null,
    arrived: true,
    free_time_minutes: 120,
    rate_cents_per_hour: 7500,
    phase: "accruing",
    free_time_remaining_seconds: 0,
    detention_seconds: 3600,
    detention_cents: 7500,
    notice_sent: false,
    notice_delivery: "no_email",
    photos_captured: 4,
    photos_required: 4,
    bol_captured: true,
    filed: false,
  };

  it("shows the address state on the load the driver is running", async () => {
    setToken("tok");
    setActiveStop("stop-1");
    vi.stubGlobal(
      "fetch",
      vi.fn((url) =>
        String(url).includes("/meter") ? jsonOk(METER) : jsonOk({}),
      ),
    );
    const w = mount(LoadSurface, { global: { plugins: [router()] } });
    await flushPromises();

    expect(w.text()).toContain(en["load.broker_email_none"]);
    expect(w.text()).toContain(en["load.broker_email_add"]);
  });
});
