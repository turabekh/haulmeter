// AI-CONTEXT: Five-tab routing (design-prd §4). Each tab root is ≤2 taps to any
// feature (NAV-2); secondary tasks are sheets, not routes (NAV-3). The app is
// gated behind F1 auth: routes require a session except /login (meta.public +
// meta.chrome:false hides the tab shell for the full-screen onboarding flow).
import { createRouter, createWebHistory } from "vue-router";
import PasswordSurface from "./surfaces/PasswordSurface.vue";
import MapSurface from "./surfaces/MapSurface.vue";
import FacilityProfileSurface from "./surfaces/FacilityProfileSurface.vue";
import LoadSurface from "./surfaces/LoadSurface.vue";
import MoneySurface from "./surfaces/MoneySurface.vue";
import DocsSurface from "./surfaces/DocsSurface.vue";
import BookingSurface from "./surfaces/BookingSurface.vue";
import FuelSurface from "./surfaces/FuelSurface.vue";
import LoadCalcSurface from "./surfaces/LoadCalcSurface.vue";
import AuditSurface from "./surfaces/AuditSurface.vue";
import ConditionSurface from "./surfaces/ConditionSurface.vue";
import ClaimSurface from "./surfaces/ClaimSurface.vue";
import StopPacketsSurface from "./surfaces/StopPacketsSurface.vue";
import LoadRecordSurface from "./surfaces/LoadRecordSurface.vue";
import EvidenceSurface from "./surfaces/EvidenceSurface.vue";
import AuthSurface from "./surfaces/AuthSurface.vue";
import MoreSurface from "./surfaces/MoreSurface.vue";
import BookingsSurface from "./surfaces/BookingsSurface.vue";
import FleetWorkspaceSurface from "./surfaces/FleetWorkspaceSurface.vue";
import AdminShell from "./surfaces/admin/AdminShell.vue";
import AdminOverview from "./surfaces/admin/AdminOverview.vue";
import AdminFlags from "./surfaces/admin/AdminFlags.vue";
import AdminVendors from "./surfaces/admin/AdminVendors.vue";
import AdminModeration from "./surfaces/admin/AdminModeration.vue";
import AdminAccounts from "./surfaces/admin/AdminAccounts.vue";
import AdminData from "./surfaces/admin/AdminData.vue";
import AdminModules from "./surfaces/admin/AdminModules.vue";
import AdminAudit from "./surfaces/admin/AdminAudit.vue";
import AdminRoadside from "./surfaces/admin/AdminRoadside.vue";
import PublicScorecardSurface from "./surfaces/PublicScorecardSurface.vue";
import OwnerPortalSurface from "./surfaces/OwnerPortalSurface.vue";
import VendorPortalShell from "./surfaces/vendor/VendorPortalShell.vue";
import VendorOverview from "./surfaces/vendor/VendorOverview.vue";
import VendorWeek from "./surfaces/vendor/VendorWeek.vue";
import VendorMenu from "./surfaces/vendor/VendorMenu.vue";
import VendorPromotions from "./surfaces/vendor/VendorPromotions.vue";
import VendorVerification from "./surfaces/vendor/VendorVerification.vue";
import VendorReputation from "./surfaces/vendor/VendorReputation.vue";
import VendorProfile from "./surfaces/vendor/VendorProfile.vue";
import VendorSite from "./surfaces/vendor/VendorSite.vue";
import VendorJoinSurface from "./surfaces/vendor/VendorJoinSurface.vue";
import RoadsideSurface from "./surfaces/RoadsideSurface.vue";
import RoadsideConsentSurface from "./surfaces/RoadsideConsentSurface.vue";
import RoadsideSessionSurface from "./surfaces/RoadsideSessionSurface.vue";
import RoadsideResultSurface from "./surfaces/RoadsideResultSurface.vue";
import RoadsideCoachSurface from "./surfaces/RoadsideCoachSurface.vue";
import RoadsideDrillSurface from "./surfaces/RoadsideDrillSurface.vue";
import { mustChangePassword, isAuthenticated } from "./core/api.js";

// DEV-ONLY: the /dev directory ships ONLY in development builds. Vite replaces
// import.meta.env.DEV with `false` in production, so the route (and its lazily
// imported component chunk) is tree-shaken out — the dev tool never reaches prod.
const devRoutes = import.meta.env.DEV
  ? [
      {
        path: "/dev",
        name: "dev",
        component: () => import("./surfaces/DevIndexSurface.vue"),
        meta: { public: true, chrome: false, portal: true },
      },
    ]
  : [];

export const routes = [
  { path: "/", redirect: "/map" },
  // full-screen onboarding flow — no tab chrome, no auth required
  { path: "/login", name: "login", component: AuthSurface, meta: { public: true, chrome: false } },
  { path: "/map", name: "map", component: MapSurface, meta: { driving: "withdraws" } },
  { path: "/facility/:id", name: "facility", component: FacilityProfileSurface, meta: { driving: "withdraws" } },
  // full-screen linear flows (NAV-3); reached from the map card CTAs (NAV-5)
  { path: "/book/:spotId", name: "book", component: BookingSurface, meta: { driving: "withdraws" } },
  { path: "/fuel/:stationId", name: "fuel", component: FuelSurface, meta: { driving: "withdraws" } },
  { path: "/load", name: "load", component: LoadSurface, meta: { driving: "withdraws" } },
  { path: "/load/calc", name: "load-calc", component: LoadCalcSurface, meta: { driving: "withdraws" } },
  { path: "/money", name: "money", component: MoneySurface, meta: { driving: "withdraws" } },
  { path: "/money/audit", name: "money-audit", component: AuditSurface, meta: { driving: "withdraws" } },
  { path: "/protection/condition", name: "condition", component: ConditionSurface, meta: { driving: "withdraws" } },
  { path: "/claim/:stopId", name: "claim", component: ClaimSurface, meta: { driving: "safe" } },
  // A1 req 5: a full-screen push like claim review (§NAV-3 names it), reached by a
  // NAV-5 cross-link. `withdraws` at speed — sending a document to a broker is the last
  // decision that belongs in front of someone at 65 mph, and the packet waits.
  {
    path: "/protection/packets",
    name: "stop-packets",
    component: StopPacketsSurface,
    meta: { driving: "withdraws" },
  },
  // AI-CONTEXT: a finished load's record — what it CONTAINS, before it is downloaded
  // or sent (§23 entry 137). A screen rather than a step inside the Past loads sheet
  // (owner decision): it carries photo thumbnails and a per-dock breakdown, the sheet
  // it would have lived in is already 1 deep (§8), and a route gives it Android back
  // and a deep link. `withdraws` — the record stays readable at speed, the two acting
  // controls do not.
  { path: "/load/:loadId/record", name: "load-record", component: LoadRecordSurface, meta: { driving: "withdraws" } },
  { path: "/load/:stopId/evidence", name: "evidence", component: EvidenceSurface, meta: { driving: "withdraws" } },
  { path: "/docs", name: "docs", component: DocsSurface, meta: { driving: "withdraws" } },
  { path: "/bookings", name: "bookings", component: BookingsSurface, meta: { driving: "withdraws" } },
  { path: "/more", name: "more", component: MoreSurface, meta: { driving: "safe" } },
  // AI-CONTEXT: M15 (E3 §E3.1.6). A LINEAR FLOW as four full-screen pushes — §NAV-3
  // reserves that shape for exactly this and names claim review as the precedent. No new
  // bottom-nav tab: tab changes remain the standing A8/D7 owner decision, so the entry is
  // a row on More.
  //
  // Every one declares `withdraws`, the session included. A spoken inspection at 65 mph is
  // the worst thing on this list, and Q-4 makes the engine refuse anyway — the session
  // surface turns that refusal into a paused state rather than a closed socket.
  { path: "/roadside", name: "roadside", component: RoadsideSurface, meta: { driving: "withdraws" } },
  {
    path: "/roadside/consent/:scenarioId",
    name: "roadside-consent",
    component: RoadsideConsentSurface,
    meta: { driving: "withdraws" },
  },
  {
    path: "/roadside/session/:sessionId",
    name: "roadside-session",
    component: RoadsideSessionSurface,
    meta: { chrome: false, driving: "withdraws" },
  },
  {
    path: "/roadside/drill",
    name: "roadside-drill",
    component: RoadsideDrillSurface,
    meta: { driving: "withdraws" },
  },
  {
    path: "/roadside/coach/:sessionId",
    name: "roadside-coach",
    component: RoadsideCoachSurface,
    meta: { driving: "withdraws" },
  },
  {
    path: "/roadside/result/:sessionId",
    name: "roadside-result",
    component: RoadsideResultSurface,
    meta: { driving: "withdraws" },
  },
  // §18 web-first portal — no tab chrome, wider frame; auth required (fleet owner)
  { path: "/fleet", name: "fleet", component: FleetWorkspaceSurface, meta: { chrome: false, portal: true } },
  // Admin Console 2.0 (§23 E-D4): sections are router CHILDREN so a queue can be
  // bookmarked, browser back behaves, and each section fetches only its own data.
  {
    path: "/admin",
    component: AdminShell,
    meta: { chrome: false, portal: true },
    children: [
      { path: "", name: "admin", component: AdminOverview },
      { path: "flags", name: "admin-flags", component: AdminFlags },
      { path: "vendors", name: "admin-vendors", component: AdminVendors },
      { path: "moderation", name: "admin-moderation", component: AdminModeration },
      { path: "accounts", name: "admin-accounts", component: AdminAccounts },
      { path: "data", name: "admin-data", component: AdminData },
      { path: "modules", name: "admin-modules", component: AdminModules },
      { path: "roadside", name: "admin-roadside", component: AdminRoadside },
      { path: "audit", name: "admin-audit", component: AdminAudit },
    ],
  },
  { path: "/owner", name: "owner", component: OwnerPortalSurface, meta: { chrome: false, portal: true } },
  // §18 fourth portal (§23 E-D3): the vendor manages their week at a desk.
  // Sections are router CHILDREN behind the rail approved for the admin console
  // (§23 E-D4), reused rather than reinvented — §22.2 makes navigation structure a
  // never-improvise category, and this is the same portal family.
  {
    path: "/vendor-portal",
    component: VendorPortalShell,
    meta: { chrome: false, portal: true },
    children: [
      { path: "", name: "vendor-portal", component: VendorOverview },
      { path: "week", name: "vendor-week", component: VendorWeek },
      { path: "menu", name: "vendor-menu", component: VendorMenu },
      { path: "promotions", name: "vendor-promotions", component: VendorPromotions },
      { path: "verification", name: "vendor-verification", component: VendorVerification },
      { path: "reputation", name: "vendor-reputation", component: VendorReputation },
      // FR7. The rail shows this only to a service centre — a mobile cook has no
      // site to claim — but the ROUTE stays open, so a vendor who switches type
      // (or arrives from a link) gets the section rather than a dead URL.
      { path: "site", name: "vendor-site", component: VendorSite },
      { path: "profile", name: "vendor-profile", component: VendorProfile },
    ],
  },
  // the way IN. Public, because a cook who has not signed up yet cannot be behind
  // the gate — and the DRIVER login is the wrong door for them (mobile-first, asks
  // for an authority number, lands on the trucking map).
  {
    path: "/vendor-portal/join",
    name: "vendor-join",
    component: VendorJoinSurface,
    meta: { public: true, chrome: false, portal: true },
  },
  // §18 PUBLIC portal — no login (meta.public bypasses the auth guard)
  { path: "/scorecard", name: "scorecard", component: PublicScorecardSurface, meta: { public: true, chrome: false, portal: true } },
  // a credential form is the definition of a task that must not be attempted at speed
  { path: "/password", name: "password", component: PasswordSurface, meta: { chrome: false, driving: "withdraws" } },
  ...devRoutes, // /dev — development builds only (see above)
];

// AI-CONTEXT: the auth gate. No session -> the login flow; already signed in ->
// never sit on /login. Public routes (login) bypass the check.
export function installAuthGuard(router) {
  router.beforeEach((to) => {
    if (!to.meta.public && !isAuthenticated.value) {
      // a cook who lands on the portal without a session belongs at the portal's
      // own door, not the driver login — that door asks for an authority number
      // and drops them on the trucking map afterwards
      if (to.path.startsWith("/vendor-portal")) return { name: "vendor-join" };
      // everyone else goes to the driver login, and comes BACK here afterwards
      // rather than being dumped on the map having forgotten where they were going
      return { name: "login", query: { next: to.fullPath } };
    }
    // AI-CONTEXT: the forced change, and it lives HERE because this is the one place a
    // deep link cannot route around (D5). The flag exists only because an admin just
    // issued a temporary credential, the remedy takes seconds, and a dismissible force is
    // not a force — this flag has been ignorable for its entire existence, which is how a
    // temporary password came to be a permanent one.
    //
    // The server does NOT enforce it beyond setting the flag (D6): an API client that
    // ignores it is not forced. That is acceptable because the flag prompts a cooperating
    // app rather than containing an adversary who already holds a valid credential — and
    // it is stated in the report rather than papered over.
    if (mustChangePassword.value && !to.meta.public && to.name !== "password") {
      return { name: "password" };
    }
    if (to.name === "login" && isAuthenticated.value) {
      const next = typeof to.query.next === "string" ? to.query.next : null;
      return next && next.startsWith("/") ? next : { name: "map" };
    }
    return true;
  });
}

export function createAppRouter() {
  const router = createRouter({ history: createWebHistory(), routes });
  installAuthGuard(router);
  return router;
}
