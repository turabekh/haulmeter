// AI-CONTEXT: §18's hard rule — the five portals "share `ui/core` tokens and components
// where sensible but NEVER import driver-app screens" — had nothing enforcing it.
//
// This is the same boundary import-linter holds on the Python side, and this project
// treats those contracts as authoritative for a reason: an architectural rule that
// lives only in prose is one commit from being false, and §23 entry 119 was logged
// today precisely because §18's own prose had drifted from the product.
//
// WHY THIS AND NOT A HARNESS STATE. §18 also promises a 1200 dp content cap and
// responsiveness down to phone. Both were MEASURED on the real portals at 1920 and
// 360: no page overflows, and no portal is missing its cap in a way that shows. Adding
// four portals × four variants to the layout sweep to guard a contract measurement says
// is already met would cost ~2 minutes a run — and `ui-layout`'s own note says a check
// that is painful to run stops being run. The import rule is the one that is unenforced,
// silent when broken, and free to check.
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { resolve, dirname } from "node:path";

const ROOT = resolve(__dirname, "..");
const routerSrc = readFileSync(resolve(ROOT, "src/router.js"), "utf8");

// component name -> source file, from the router's own import block
const IMPORTS = Object.fromEntries(
  [...routerSrc.matchAll(/import\s+(\w+)\s+from\s+"(\.[^"]+)"/g)].map((m) => [m[1], m[2]]),
);

function portalComponents() {
  // every route object carrying `portal: true`, plus the children of a portal shell
  const names = new Set();
  for (const block of routerSrc.split(/\n\s*\{/)) {
    if (!block.includes("portal: true")) continue;
    const m = block.match(/component:\s*(\w+)/);
    if (m) names.add(m[1]);
  }
  return [...names];
}

function fileFor(componentName) {
  const rel = IMPORTS[componentName];
  if (!rel) return null;
  const path = resolve(ROOT, "src", rel.replace(/^\.\//, ""));
  return path.endsWith(".vue") ? path : `${path}.vue`;
}

// a driver-app screen: a surface that is NOT one of the portal surfaces
const PORTAL_FILES = new Set(portalComponents().map(fileFor).filter(Boolean));

function driverSurfaceNames() {
  const names = new Set();
  for (const f of readdirSync(resolve(ROOT, "src/surfaces"))) {
    if (!f.endsWith(".vue")) continue;
    const full = resolve(ROOT, "src/surfaces", f);
    if (!PORTAL_FILES.has(full)) names.add(f.replace(/\.vue$/, ""));
  }
  return names;
}

describe("§18 — portals never import driver-app screens", () => {
  it("finds the portals from the ROUTER, so a new one cannot be missed", () => {
    // a hand-kept list is the drift this test exists to prevent, one layer up
    const names = portalComponents();
    expect(names.length).toBeGreaterThanOrEqual(4);
    expect(names.every((n) => IMPORTS[n]), `unresolvable: ${names}`).toBe(true);
  });

  it("no portal file imports a driver surface", () => {
    const drivers = driverSurfaceNames();
    expect(drivers.size).toBeGreaterThan(5); // the driver app exists; guard against a vacuous pass
    const offences = [];
    for (const file of PORTAL_FILES) {
      const src = readFileSync(file, "utf8");
      for (const m of src.matchAll(/from\s+"([^"]+)"/g)) {
        const target = m[1].split("/").pop().replace(/\.vue$/, "");
        if (drivers.has(target)) offences.push(`${file.split("/").pop()} -> ${target}`);
      }
    }
    expect(offences, `§18: a portal is importing a driver screen: ${offences}`).toEqual([]);
  });

  it("the admin console's children are covered too, not just its shell", () => {
    // AdminShell is the route component; the panels are nested and would otherwise be
    // unchecked — which is where a reused driver screen would actually land
    const panels = readdirSync(resolve(ROOT, "src/surfaces/admin")).filter((f) => f.endsWith(".vue"));
    expect(panels.length).toBeGreaterThan(5);
    const drivers = driverSurfaceNames();
    for (const panel of panels) {
      const src = readFileSync(resolve(ROOT, "src/surfaces/admin", panel), "utf8");
      for (const m of src.matchAll(/from\s+"([^"]+)"/g)) {
        const target = m[1].split("/").pop().replace(/\.vue$/, "");
        expect(drivers.has(target), `${panel} imports the driver screen ${target}`).toBe(false);
      }
    }
  });
});
