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

initTheme(); // §6.1 C-3: a stored override wins over the system setting, from boot
createApp(App).use(createAppRouter()).mount("#app");
