// AI-CONTEXT: the OBSERVATION finding F5 asks for — look at the screen a driver reads
// after tapping "Send notice" when the send did NOT succeed.
//
// The defect was never visible to the suite, and could not have been: every notice test
// in the project ran against the recording gateway, where "a message object came back"
// and "the mail went out" are the same thing. Under real SMTP they are not, and the
// screen said "Broker notified — detention on record." over a message sitting in a
// dead-letter queue.
//
// Six states now. Three from the Load tab, at 360 × 800 dp:
//   · retrying — the send failed and the sweep will try again
//   · no_email — there is no address on file, which is the DEFAULT for every load
//                created in this product today (nothing has ever written contact_email)
//   · sent     — the one that is allowed to say the broker was notified
//
// ...and three for the address itself, which is what makes any of them deliverable:
//   · the field offered when a load is created
//   · the inline fix, in the claim screen's no_email state
//   · the same claim once the address is saved and Send is available
//
// Same shape as `observe-loading.spec.js` and for the same reason: it runs inside
// `make ui-layout`, because an observation nobody re-runs decays into a screenshot in an
// old handoff. Screenshots are opt-in behind OBSERVE_SHOTS=1 so a sweep leaves the tree
// clean. To refresh them:
//
//   docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm \
//     --entrypoint sh -v "$PWD/docs/handoffs:/repo-docs" ui \
//     -c "npx --yes playwright install --with-deps chromium; OBSERVE_SHOTS=1 npx playwright test layout/observe-notice-delivery.spec.js"
import { test, expect } from "@playwright/test";

const SHOTS = !!process.env.OBSERVE_SHOTS;
async function shoot(page, name) {
  if (!SHOTS) return;
  await page.screenshot({ path: `/repo-docs/assets/${name}.png`, fullPage: false });
}

const API = "http://localhost:8008";
const STOP = "00000000-0000-0000-0000-0000000000c1";
const SESSION = {
  token: "observe-notice",
  account_id: "00000000-0000-0000-0000-000000000001",
  email: "harness@example.com",
};

// a stop on the dock with free time exhausted — the state in which a notice is due
function meter(delivery) {
  return {
    stop_id: STOP,
    claim_id: "00000000-0000-0000-0000-0000000000d1",
    facility_name: "Dallas Cold Storage",
    counterparty: "Acme Brokerage",
    appointment: null,
    arrived: true,
    free_time_minutes: 120,
    rate_cents_per_hour: 7500,
    phase: "accruing",
    free_time_remaining_seconds: 0,
    detention_seconds: 3600,
    detention_cents: 7500,
    notice_sent: delivery === "sent",
    notice_delivery: delivery,
    photos_captured: 4,
    photos_required: 4,
    bol_captured: true,
    filed: false,
  };
}

async function openLoadTab(page, delivery) {
  await page.route(`${API}/**`, (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (body) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (path.endsWith("/meter")) return json(meter(delivery));
    if (path.includes("/stop-packets")) return json({ packets: [] });
    return json({});
  });
  await page.addInitScript(
    (s) => {
      localStorage.setItem("longhaul.session", JSON.stringify(s.session));
      localStorage.setItem("longhaul.cache.active_stop", s.stop);
      localStorage.setItem("longhaul.theme", "dark");
    },
    { session: SESSION, stop: STOP },
  );
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/load");
  await page.waitForSelector("li.checklist__item", { state: "attached", timeout: 15_000 });
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
  await page.waitForTimeout(200);
  return page.locator("body").innerText();
}

test("a notice that did not go out does not say the broker was notified", async ({ page }) => {
  const body = await openLoadTab(page, "retrying");
  await shoot(page, "notice-retrying-360dp");

  expect(body).toContain("retrying");
  // the whole finding: the screen must not assert a delivery that did not happen
  expect(body).not.toContain("Broker notified");
  console.log("OBSERVED — retrying: the row names the failure, no delivery claimed");
});

test("a load with no broker address says so, and says what fixes it", async ({ page }) => {
  const body = await openLoadTab(page, "no_email");
  await shoot(page, "notice-no-email-360dp");

  expect(body).toContain("No broker email");
  // §12.6: never name an action the driver cannot take — and never stay silent about a
  // blocker they CAN clear. This is the default state of every load today.
  expect(body).toContain("add one to notify");
  expect(body).not.toContain("Broker notified");
  console.log("OBSERVED — no_email: the blocker and its remedy, no delivery claimed");
});

test("a notice that did go out is the only state allowed to say so", async ({ page }) => {
  const body = await openLoadTab(page, "sent");
  await shoot(page, "notice-sent-360dp");

  expect(body).toContain("Broker notified");
  expect(body).not.toContain("retrying");
  console.log("OBSERVED — sent: the broker was notified, and the row may say it");
});


// --- the address, which is what the three states above are actually about ---
const CLAIM = {
  claim_id: "00000000-0000-0000-0000-0000000000d1",
  load_id: "00000000-0000-0000-0000-0000000000e1",
  amount_cents: 15000,
  detention_seconds: 7200,
  free_time_minutes: 120,
  rate_cents_per_hour: 7500,
  state: "invoiced",
  mode: "invoice",
  facility: "Dallas Cold Storage",
  counterparty: "Acme Brokerage",
  counterparty_email: null,
  notice_sent: false,
  notice_delivery: "no_email",
  filed: true,
  chain_valid: true,
  record_count: 3,
  artifact_count: 1,
  timeline: [{ type: "GEOFENCE", occurred_at: "2026-08-11T10:00:00Z" }],
};

async function openClaim(page, claim) {
  await page.route(`${API}/**`, (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (body) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (path.includes("/claim")) return json(claim);
    return json({});
  });
  await page.addInitScript((s) => {
    localStorage.setItem("longhaul.session", JSON.stringify(s));
    localStorage.setItem("longhaul.theme", "dark");
  }, SESSION);
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto(`/claim/${STOP}`);
  await page.waitForSelector(".timeline", { state: "attached", timeout: 15_000 });
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
  await page.waitForTimeout(200);
  return page.locator("body").innerText();
}

test("a load can be given the address its notices will go to", async ({ page }) => {
  // driven through the real path: open the sheet, hand it a file, let the parse come back
  // unreadable — which is the state this stack actually runs in with no model key — and
  // land on the confirm form, which IS the manual form.
  await page.route(`${API}/**`, (route) => {
    const path = new URL(route.request().url()).pathname;
    const json = (body) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (path.endsWith("/load/import")) {
      return json({ document_id: "doc-1", readable: false, parsed: {}, stops: [] });
    }
    return json({});
  });
  await page.addInitScript((s) => {
    localStorage.setItem("longhaul.session", JSON.stringify(s));
    localStorage.setItem("longhaul.theme", "dark");
  }, SESSION);
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/load");
  await page.getByRole("button", { name: "Add a load" }).first().click();
  await page.setInputFiles('input[type="file"]', {
    name: "ratecon.png",
    mimeType: "image/png",
    buffer: Buffer.from("not-a-real-rate-con"),
  });
  await page.getByRole("button", { name: "Read the rate con" }).click();
  await page.waitForSelector('input[type="email"]', { state: "attached", timeout: 15_000 });
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
  await page.locator('input[type="email"]').scrollIntoViewIfNeeded();
  await page.waitForTimeout(200);
  await shoot(page, "broker-email-create-360dp");

  const body = await page.locator("body").innerText();
  expect(body).toContain("Broker email");
  // labelled for its PURPOSE — "Email" on a load form could be anyone's
  expect(body).toContain("detention notices");
  console.log("OBSERVED — creation: the broker email field is offered on the confirm form");
});

test("the claim screen offers the fix where it states the problem", async ({ page }) => {
  const body = await openClaim(page, CLAIM);
  await shoot(page, "broker-email-inline-fix-360dp");

  expect(body).toContain("No broker email");
  // the affordance is HERE, not a hint to go and find it
  expect(await page.locator(".ev--fix input").count()).toBe(1);
  console.log("OBSERVED — no_email: the input is inline, in the state that complains");
});

test("once the address is saved the claim is sendable and says nothing about email", async ({
  page,
}) => {
  const fixed = {
    ...CLAIM,
    counterparty_email: "ap@acme.example",
    notice_delivery: "not_sent",
  };
  const body = await openClaim(page, fixed);
  await shoot(page, "broker-email-fixed-360dp");

  expect(body).not.toContain("No broker email");
  expect(await page.locator(".ev--fix").count()).toBe(0);
  console.log("OBSERVED — fixed: the blocker is gone, the notice is merely unsent");
});
