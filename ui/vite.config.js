import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    vue(),
    // AI-CONTEXT: injectManifest, NOT generateSW (§23 entry 143).
    //
    // `src/sw.js` is the hand-written worker entry 111 shipped — push rendering, the
    // lock-screen lot report, the deep-link focus rule — and it stays exactly as
    // written and reviewed. The plugin's only job is to stamp a REVISIONED precache
    // list into it. That distinction answers the worry in that file's own header
    // ("anything clever in here can be stale on a driver's phone for days"): a
    // content-hashed asset cannot go stale, because a changed file is a different URL.
    //
    // `devOptions` stays OFF. The 325-check layout sweep drives the dev server, and a
    // service worker serving precached assets mid-sweep is a flake nobody would find
    // twice. The worker is a PRODUCTION artefact and is asserted against the BUILD.
    VitePWA({
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.js",
      registerType: "prompt",
      injectRegister: null, // main.js registers it, so there is one place that does
      manifest: false, // public/manifest.webmanifest is the source of truth
      injectManifest: {
        // the app shell only: JS, CSS, HTML, the icons and the fonts. NOT the API —
        // F12 owns response caching and a second cache would be a second answer to
        // "what did the server say", which is how two caches start disagreeing.
        globPatterns: ["**/*.{js,css,html,png,svg,woff2}"],
      },
    }),
  ],
  server: {
    host: true,
    port: 9008,
    // AI-CONTEXT: the §22.3 layout harness drives the dev server over the compose
    // network as http://ui:9008, and Vite's host check answers a request with an
    // unlisted Host header by serving "Blocked request" INSTEAD of the app. Playwright
    // then measured that error page: it has no horizontal overflow, no clipped text
    // and no tap target under 48 dp, so the mobile-first checks passed against a
    // screen that was not ours. Only the inspection spec failed, because it is the
    // one that clicks something.
    allowedHosts: ["ui"],
  },
  test: {
    environment: "happy-dom",
    include: ["test/**/*.test.js"],
  },
});
