// AI-CONTEXT: Theme control (design-prd §6.1 C-3). Dark is primary; light is
// derived. Default follows the system setting (no data-theme attribute → the
// prefers-color-scheme media query decides); a manual override stamps
// data-theme to win over the system. The token values themselves live in
// tokens.scss — this only flips the attribute.
import { ref } from "vue";

export const ThemeMode = { SYSTEM: "system", LIGHT: "light", DARK: "dark" };

const mode = ref(ThemeMode.SYSTEM);

function apply(next) {
  const root = document.documentElement;
  if (next === ThemeMode.SYSTEM) root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", next);
}

export function useTheme() {
  const setMode = (next) => {
    mode.value = next;
    apply(next);
  };
  return { mode, setMode };
}
