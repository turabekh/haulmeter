// AI-CONTEXT: Core UI logic tests (framework-agnostic modules) — driver state
// machine (SM-4), presentation helpers (§11), and the i18n resolver (F15).
import { describe, it, expect, beforeEach } from "vitest";
import { useDriverState, DriverState } from "../src/core/state.js";
import { statusPresentation, freshnessLabel, isStale } from "../src/core/presentation.js";
import { useI18n } from "../src/core/i18n.js";

describe("driver state machine (design-prd §5, SM-4)", () => {
  beforeEach(() => useDriverState().setState(DriverState.IDLE));

  it("stamps data-state only while DRIVING", () => {
    const s = useDriverState();
    s.setState(DriverState.DRIVING);
    expect(s.isDriving.value).toBe(true);
    expect(document.documentElement.getAttribute("data-state")).toBe("driving");
    s.setState(DriverState.IDLE);
    expect(document.documentElement.getAttribute("data-state")).toBe(null);
  });
});

describe("presentation (design-prd §11)", () => {
  it("maps parking status to token + label (color never alone)", () => {
    expect(statusPresentation("empty")).toEqual({ token: "--ledger-500", label: "Empty" });
    expect(statusPresentation("full").token).toBe("--flare-500");
    expect(statusPresentation(null).label).toBe("Unknown");
  });

  it("freshness is honest and relative (§11.7)", () => {
    const now = 1_000_000_000_000;
    const fresh = { reported_at: new Date(now - 40 * 60000).toISOString(), sample_size: 3 };
    expect(freshnessLabel(fresh, now)).toBe("40m · 3 drivers");
    expect(isStale(fresh, now)).toBe(false);
    const old = { reported_at: new Date(now - 5 * 3600 * 1000).toISOString(), sample_size: 1 };
    expect(isStale(old, now)).toBe(true);
    expect(freshnessLabel(null, now)).toBe(null);
  });
});

describe("i18n (F15)", () => {
  it("resolves the user locale, falls back to English, echoes unknown keys", () => {
    const { t, setLocale } = useI18n();
    expect(t("nav.map")).toBe("Map");
    setLocale("es");
    expect(t("nav.map")).toBe("Mapa");
    setLocale("en");
    expect(t("does.not.exist")).toBe("does.not.exist");
  });
});
