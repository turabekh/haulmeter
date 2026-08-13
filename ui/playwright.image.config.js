// AI-CONTEXT: the image pipeline's own config, and it exists for the same reason
// `playwright.pwa.config.js` does — a defect this product actually ships cannot be seen
// by the environment the unit tests run in.
//
// `prepareImage` degrades to returning the original blob whenever the browser cannot do
// better, which is correct (a photograph must reach the server even slowly) and totally
// silent. happy-dom implements neither `createImageBitmap` nor `OffscreenCanvas`, so
// every vitest assertion about uploads exercises the PASSTHROUGH: the suite would stay
// green if the downscale never ran once. Only a real browser can decode and re-encode.
//
// It runs against the DEV server rather than the built preview the PWA check uses,
// because it imports `src/core/image.js` directly — the unit under test is the module,
// not the screen, and testing a copy of its rules is what this codebase keeps finding in
// its own history. Separate from the LAW 0 harness so the 325-check sweep stays a count
// of layout checks and nothing else.
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./browser",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  workers: 1,
  reporter: [["list"]],
  use: {
    viewport: { width: 360, height: 800 },
    baseURL: process.env.UI_BASE || "http://ui:9008",
  },
});
