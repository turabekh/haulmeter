// AI-CONTEXT: SM-3, enforced instead of remembered.
//
// §22.3 requires "DRIVING-state behavior explicitly defined for the screen" and the
// sweep that checked it found SEVEN of thirteen driver surfaces with none — including
// `ConditionSurface`, whose file input carries `capture="environment"` and so opens
// the rear camera directly, on a route with no guard of its own.
//
// The obvious systemic fix — a global `beforeEach` that redirects while DRIVING —
// is FORBIDDEN by §13.5: "every notification deep-links to the exact screen and state
// it describes; no landing on tab roots." A redirecting guard would break every
// notification the product sends. So the enforcement is a declaration plus this test:
// every driver route states what it does at speed, and any route claiming to withdraw
// something must actually consult the driver state.
//
// What this CANNOT check is that the withdrawal is correct — only that the surface
// considers the question. Behaviour is covered per surface in ui-components.test.js;
// this is the completeness net that catches the next screen somebody forgets.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { routes } from "../src/router.js";

// route name -> its source file. Kept here rather than in `meta` because the router
// ships to production and this is test knowledge; the first assertion below keeps the
// two in step, so adding a route without classifying it fails.
const SOURCE = {
  // a credential form withdraws at speed for the obvious reason: two password fields
  // and a keyboard is precisely what SM-3 exists to take off the screen
  password: "PasswordSurface",
  map: "MapSurface",
  facility: "FacilityProfileSurface",
  book: "BookingSurface",
  fuel: "FuelSurface",
  load: "LoadSurface",
  "load-calc": "LoadCalcSurface",
  money: "MoneySurface",
  "money-audit": "AuditSurface",
  condition: "ConditionSurface",
  claim: "ClaimSurface",
  evidence: "EvidenceSurface",
  "load-record": "LoadRecordSurface",
  docs: "DocsSurface",
  bookings: "BookingsSurface",
  more: "MoreSurface",
  "stop-packets": "StopPacketsSurface",
  // M15 — the session withdraws by PAUSING rather than by hiding a control, which is
  // still a consultation of the driver state and still the same claim
  roadside: "RoadsideSurface",
  "roadside-consent": "RoadsideConsentSurface",
  "roadside-session": "RoadsideSessionSurface",
  "roadside-result": "RoadsideResultSurface",
  "roadside-coach": "RoadsideCoachSurface",
  "roadside-drill": "RoadsideDrillSurface",
};

// the driver app: everything that is not a §18 portal and not a public page
const driverRoutes = routes.filter(
  (r) => r.name && !r.meta?.portal && !r.meta?.public && !r.redirect,
);

describe("SM-3 — every driver surface declares what it does at speed", () => {
  it("covers exactly the driver routes, so a new one cannot slip through", () => {
    expect(driverRoutes.map((r) => r.name).sort()).toEqual(Object.keys(SOURCE).sort());
  });

  it("declares a DRIVING posture on every driver route (§22.3)", () => {
    const undeclared = driverRoutes.filter((r) => !r.meta?.driving).map((r) => r.name);
    expect(undeclared, `routes with no DRIVING posture: ${undeclared.join(", ")}`).toEqual([]);
  });

  it("only uses postures the test knows how to hold", () => {
    const unknown = driverRoutes
      .filter((r) => !["withdraws", "safe"].includes(r.meta.driving))
      .map((r) => `${r.name}:${r.meta.driving}`);
    expect(unknown).toEqual([]);
  });

  // the teeth. A route that claims to withdraw something at speed and never reads the
  // driver state is claiming a behaviour it does not have — which is the exact defect
  // this whole mechanism exists to stop repeating.
  it("backs every 'withdraws' claim with a surface that consults the driver state", () => {
    const hollow = [];
    for (const route of driverRoutes.filter((r) => r.meta.driving === "withdraws")) {
      const src = readFileSync(
        resolve(process.cwd(), "src/surfaces", `${SOURCE[route.name]}.vue`),
        "utf8",
      );
      if (!src.includes("isDriving")) hollow.push(route.name);
    }
    expect(hollow, `claims to withdraw at speed but never checks: ${hollow.join(", ")}`).toEqual([]);
  });
});
