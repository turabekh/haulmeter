import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
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
