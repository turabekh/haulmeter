// AI-CONTEXT: Boot smoke only — NOT a design surface. Applies the app-background
// token and shows the brand wordmark + a localized "Loading" caption so the
// dev server (port 9008) proves tokens + i18n are wired. The five-tab shell and
// all surfaces (design-prd §4/§10) are built after the Common Ground DoD and
// must follow the design constitution — none are improvised here.
import "./core/tokens.scss";
import { messages, DEFAULT_LOCALE } from "./core/i18n/index.js";

const t = (key, locale = DEFAULT_LOCALE) => messages[locale]?.[key] ?? key;

const root = document.getElementById("app");
root.style.minHeight = "100vh";
root.style.display = "grid";
root.style.placeItems = "center";
root.style.background = "var(--ink-0)";
root.style.color = "var(--text-1)";
root.style.fontFamily = "var(--font-sans)";

const brand = document.createElement("div");
brand.textContent = "LONGHAUL";
brand.style.fontSize = "var(--type-display-size)";
brand.style.fontWeight = "var(--type-display-weight)";

const caption = document.createElement("div");
caption.textContent = t("system.loading");
caption.style.fontSize = "var(--type-caption-size)";
caption.style.color = "var(--text-3)";
caption.style.marginTop = "var(--s-3)";

root.append(brand, caption);
