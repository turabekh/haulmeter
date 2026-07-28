// AI-CONTEXT: the LAW 0 harness config. Runs against the dev server in the compose
// network, at the ONE viewport the constitution cares about first (360×800, LAW 0).
// Deliberately no screenshot baselines — see layout.spec.js for why.
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./layout",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  // AI-CONTEXT: the harness was pinned at 2 workers on an 8-core machine and took
  // ~13 minutes for 612 checks, which is long enough that it stops being run — and a
  // check nobody runs is worth nothing. 4 is deliberate rather than "as many as
  // possible": each worker is a Chromium with a WebGL context, and the map surfaces
  // are the ones that flake first under memory pressure. Override with PW_WORKERS
  // when a machine can take more.
  //
  // This does NOT relax the standing rule that `make ui-layout` runs ALONE
  // (HANDOFF-097 §5): more workers makes a contended run worse, not better.
  workers: Number(process.env.PW_WORKERS) || 4,
  reporter: [["list"]],
  use: {
    viewport: { width: 360, height: 800 },
    baseURL: process.env.UI_BASE || "http://ui:9008",
  },
});
