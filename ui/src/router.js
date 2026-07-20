// AI-CONTEXT: Five-tab routing (design-prd §4). Each tab root is ≤2 taps to any
// feature (NAV-2); secondary tasks are sheets, not routes (NAV-3). Load/Money/
// Docs/More are placeholders until their modules land.
import { createRouter, createWebHistory } from "vue-router";
import MapSurface from "./surfaces/MapSurface.vue";
import FacilityProfileSurface from "./surfaces/FacilityProfileSurface.vue";
import LoadSurface from "./surfaces/LoadSurface.vue";
import PlaceholderSurface from "./surfaces/PlaceholderSurface.vue";

export const routes = [
  { path: "/", redirect: "/map" },
  { path: "/map", name: "map", component: MapSurface },
  { path: "/facility/:id", name: "facility", component: FacilityProfileSurface },
  { path: "/load", name: "load", component: LoadSurface },
  { path: "/money", name: "money", component: PlaceholderSurface, props: { titleKey: "nav.money" } },
  { path: "/docs", name: "docs", component: PlaceholderSurface, props: { titleKey: "nav.docs" } },
  { path: "/more", name: "more", component: PlaceholderSurface, props: { titleKey: "nav.more" } },
];

export function createAppRouter() {
  return createRouter({ history: createWebHistory(), routes });
}
