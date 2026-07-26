// AI-CONTEXT: the LAW 0 harness config. Runs against the dev server in the compose
// network, at the ONE viewport the constitution cares about first (360×800, LAW 0).
// Deliberately no screenshot baselines — see layout.spec.js for why.
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./layout",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  workers: 2,
  reporter: [["list"]],
  use: {
    viewport: { width: 360, height: 800 },
    baseURL: process.env.UI_BASE || "http://ui:9008",
  },
});
