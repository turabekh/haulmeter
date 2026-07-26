// AI-CONTEXT: Theme control (design-prd §6.1 C-3). Dark is primary; light is
// derived. Default follows the system setting (no data-theme attribute → the
// prefers-color-scheme media query decides); a manual override stamps
// data-theme to win over the system. The token values themselves live in
// tokens.scss — this only flips the attribute.
import { ref } from "vue";

export const ThemeMode = { SYSTEM: "system", LIGHT: "light", DARK: "dark" };

// AI-CONTEXT: §6.1 C-3 says the light theme is "toggled by system setting + manual
// override". The override existed in this module and NOWHERE ELSE: nothing called
// `setMode`, so there was no control, and the mode lived in a ref that did not
// survive a reload. A driver who preferred light could not choose it, and the one
// who somehow did would lose it on the next app open. That also meant §22.3's "light
// theme verified" could not be checked by anything — the app could not be put into
// the state the check describes.
const STORAGE_KEY = "longhaul.theme";

function stored() {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return Object.values(ThemeMode).includes(v) ? v : ThemeMode.SYSTEM;
  } catch {
    return ThemeMode.SYSTEM;
  }
}

const mode = ref(stored());

function apply(next) {
  const root = document.documentElement;
  if (next === ThemeMode.SYSTEM) root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", next);
}

export function useTheme() {
  const setMode = (next) => {
    if (!Object.values(ThemeMode).includes(next)) return;
    mode.value = next;
    apply(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* private mode — the choice holds for this session */
    }
  };
  return { mode, setMode, modes: Object.values(ThemeMode) };
}

// applied at boot, before first paint, so a chosen theme never flashes the other one
export function initTheme() {
  apply(mode.value);
}
