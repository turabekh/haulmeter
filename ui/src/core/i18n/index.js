// AI-CONTEXT: Launch locale registry (F15 / design-prd §12.5). All six ship
// together — a string missing any locale fails CI. Counterparty-facing
// artifacts are always English (handled server-side, not here). `xx-XL` is the
// build/CI pseudo-locale (+40% length) for mobile-first overflow testing and
// is never shipped to users.
import en from "./en.json";
import es from "./es.json";
import pa from "./pa.json";
import ru from "./ru.json";
import uz from "./uz.json";
import so from "./so.json";

export const LAUNCH_LOCALES = ["en", "es", "pa", "ru", "uz", "so"];
export const DEFAULT_LOCALE = "en";
export const PSEUDO_LOCALE = "xx-XL";

export const messages = { en, es, pa, ru, uz, so };
