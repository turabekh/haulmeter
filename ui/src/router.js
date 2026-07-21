// AI-CONTEXT: Five-tab routing (design-prd §4). Each tab root is ≤2 taps to any
// feature (NAV-2); secondary tasks are sheets, not routes (NAV-3). The app is
// gated behind F1 auth: routes require a session except /login (meta.public +
// meta.chrome:false hides the tab shell for the full-screen onboarding flow).
import { createRouter, createWebHistory } from "vue-router";
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
import EvidenceSurface from "./surfaces/EvidenceSurface.vue";
import AuthSurface from "./surfaces/AuthSurface.vue";
import MoreSurface from "./surfaces/MoreSurface.vue";
import FleetWorkspaceSurface from "./surfaces/FleetWorkspaceSurface.vue";
import AdminConsoleSurface from "./surfaces/AdminConsoleSurface.vue";
import PublicScorecardSurface from "./surfaces/PublicScorecardSurface.vue";
import OwnerPortalSurface from "./surfaces/OwnerPortalSurface.vue";
import { isAuthenticated } from "./core/api.js";

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
  { path: "/map", name: "map", component: MapSurface },
  { path: "/facility/:id", name: "facility", component: FacilityProfileSurface },
  // full-screen linear flows (NAV-3); reached from the map card CTAs (NAV-5)
  { path: "/book/:spotId", name: "book", component: BookingSurface },
  { path: "/fuel/:stationId", name: "fuel", component: FuelSurface },
  { path: "/load", name: "load", component: LoadSurface },
  { path: "/load/calc", name: "load-calc", component: LoadCalcSurface },
  { path: "/money", name: "money", component: MoneySurface },
  { path: "/money/audit", name: "money-audit", component: AuditSurface },
  { path: "/protection/condition", name: "condition", component: ConditionSurface },
  { path: "/claim/:stopId", name: "claim", component: ClaimSurface },
  { path: "/load/:stopId/evidence", name: "evidence", component: EvidenceSurface },
  { path: "/docs", name: "docs", component: DocsSurface },
  { path: "/more", name: "more", component: MoreSurface },
  // §18 web-first portal — no tab chrome, wider frame; auth required (fleet owner)
  { path: "/fleet", name: "fleet", component: FleetWorkspaceSurface, meta: { chrome: false, portal: true } },
  { path: "/admin", name: "admin", component: AdminConsoleSurface, meta: { chrome: false, portal: true } },
  { path: "/owner", name: "owner", component: OwnerPortalSurface, meta: { chrome: false, portal: true } },
  // §18 PUBLIC portal — no login (meta.public bypasses the auth guard)
  { path: "/scorecard", name: "scorecard", component: PublicScorecardSurface, meta: { public: true, chrome: false, portal: true } },
  ...devRoutes, // /dev — development builds only (see above)
];

// AI-CONTEXT: the auth gate. No session -> the login flow; already signed in ->
// never sit on /login. Public routes (login) bypass the check.
export function installAuthGuard(router) {
  router.beforeEach((to) => {
    if (!to.meta.public && !isAuthenticated.value) return { name: "login" };
    if (to.name === "login" && isAuthenticated.value) return { name: "map" };
    return true;
  });
}

export function createAppRouter() {
  const router = createRouter({ history: createWebHistory(), routes });
  installAuthGuard(router);
  return router;
}
