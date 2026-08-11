// AI-CONTEXT: the PWA check's own config (§23 entry 143). Separate from the LAW 0
// harness because it needs the BUILT app behind a static server — the dev server
// generates no service worker at all, deliberately, so that a worker serving precached
// assets can never flake the 325-check layout sweep.
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./pwa",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  workers: 1,
  reporter: [["list"]],
  use: {
    viewport: { width: 360, height: 800 },
    baseURL: "http://127.0.0.1:4173",
  },
  // playwright owns the preview server's lifecycle, so the check cannot silently run
  // against a stale one left over from a previous invocation.
  webServer: {
    command: "npx vite preview --port 4173 --host 127.0.0.1",
    url: "http://127.0.0.1:4173/map",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
