// AI-CONTEXT: Boot smoke only — NOT a design surface. Applies the app-background
// token and shows the brand wordmark + a plain dev status line so the dev server
// (port 9008) proves tokens + i18n are wired. It intentionally shows NO app
// screens: the five-tab shell and all surfaces (design-prd §4/§10) are built
// after the Common Ground DoD and must follow the design constitution — none are
// improvised here. Copy here is a dev placeholder, not driver-facing product copy.
import "./core/tokens.scss";
import { LAUNCH_LOCALES } from "./core/i18n/index.js";

const root = document.getElementById("app");
root.style.minHeight = "100vh";
root.style.display = "grid";
root.style.placeItems = "center";
root.style.background = "var(--ink-0)";
root.style.color = "var(--text-1)";
root.style.fontFamily = "var(--font-sans)";
root.style.textAlign = "center";
root.style.padding = "var(--s-4)";

const brand = document.createElement("div");
brand.textContent = "LONGHAUL";
brand.style.fontSize = "var(--type-display-size)";
brand.style.fontWeight = "var(--type-display-weight)";
brand.style.letterSpacing = "0.04em";

const status = document.createElement("div");
status.textContent = "Foundation build in progress — no app screens yet";
status.style.fontSize = "var(--type-body-size)";
status.style.color = "var(--text-2)";
status.style.marginTop = "var(--s-3)";

const detail = document.createElement("div");
detail.textContent = `dev shell · tokens + i18n wired (${LAUNCH_LOCALES.length} locales)`;
detail.style.fontSize = "var(--type-caption-size)";
detail.style.color = "var(--text-3)";
detail.style.marginTop = "var(--s-2)";
detail.style.fontFamily = "var(--font-mono)";

root.append(brand, status, detail);
