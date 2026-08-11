// AI-CONTEXT: App entry. Loads the token layer + global scaffold, then mounts the
// Vue app with the five-tab router. Business logic lives in core/ (swappable-UI
// discipline, design-prd §19) — this file only wires. Theme follows the system
// setting by default (§6.1 C-3); DRIVING glance-mode is stamped by core/state.
import "./core/tokens.scss";
import "./core/app-shell.scss";
import { createApp } from "vue";
import App from "./App.vue";
import { createAppRouter } from "./router.js";
import { initTheme } from "./core/theme.js";
import { registerServiceWorker } from "./core/pwa.js";

initTheme(); // §6.1 C-3: a stored override wins over the system setting, from boot
createApp(App).use(createAppRouter()).mount("#app");
// AI-CONTEXT: on boot, for EVERY driver (§23 entry 143). The worker used to be
// registered inside push.js's `enable()`, so the offline shell would have existed only
// for drivers who had opted into notifications — an unrelated choice. Registration is
// fire-and-forget and never blocks the mount above: a browser that refuses a worker
// gets the app exactly as it was before service workers existed.
registerServiceWorker();
