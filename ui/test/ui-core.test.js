// AI-CONTEXT: Core UI logic tests (framework-agnostic modules) — driver state
// machine (SM-4), presentation helpers (§11), and the i18n resolver (F15).
import { describe, it, expect, beforeEach, vi } from "vitest";
import { useDriverState, DriverState } from "../src/core/state.js";
import { setToken, logout, online, fetchOwed } from "../src/core/api.js";
import {
  statusPresentation,
  freshnessLabel,
  isStale,
  formatDwell,
  receivableStatusToken,
} from "../src/core/presentation.js";
import { useI18n } from "../src/core/i18n.js";
import {
  formatClock,
  formatMoney,
  computeDetentionState,
  meterVariant,
} from "../src/core/meter.js";

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

  it("maps receivable state to a status token (§10.3)", () => {
    expect(receivableStatusToken("recovered")).toBe("--ledger-500");
    expect(receivableStatusToken("disputed")).toBe("--marker-500");
    expect(receivableStatusToken("escalated")).toBe("--flare-500");
    expect(receivableStatusToken("weird")).toBe("--text-2");
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

  it("formats dwell durations as tabular H/M", () => {
    expect(formatDwell(8100)).toBe("2h 15m");
    expect(formatDwell(1800)).toBe("30m");
    expect(formatDwell(null)).toBe(null);
  });
});

describe("The Meter logic (design-prd §9)", () => {
  it("formats time and money tabular", () => {
    expect(formatClock(3661)).toBe("1:01:01");
    expect(formatClock(-5)).toBe("0:00:00");
    expect(formatMoney(15000)).toBe("$150.00");
    expect(formatMoney(123456)).toBe("$1,234.56");
  });

  it("computes detention state (mirrors backend clock)", () => {
    const t0 = 1_000_000_000_000;
    const within = computeDetentionState(t0, 120, 7500, t0 + 60 * 60000);
    expect(within.phase).toBe("within_free_time");
    expect(Math.round(within.freeTimeRemainingSeconds)).toBe(3600);

    const accruing = computeDetentionState(t0, 120, 7500, t0 + 180 * 60000);
    expect(accruing.phase).toBe("accruing");
    expect(accruing.amountCents).toBe(7500); // 1h * $75
  });

  it("picks the variant per §9 color logic", () => {
    expect(meterVariant({ phase: "within_free_time", freeTimeRemainingSeconds: 3600 })).toBe(
      "countdown",
    );
    expect(meterVariant({ phase: "within_free_time", freeTimeRemainingSeconds: 600 })).toBe(
      "warning",
    );
    expect(meterVariant({ phase: "accruing" })).toBe("accruing");
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

describe("F12 read-cache (design-prd §15.1: offline is a mode)", () => {
  it("caches a successful read and serves last-known data offline", async () => {
    logout(); // clears any prior cache
    setToken("tok-cache");
    const okStub = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([{ receivable_id: "r1", amount_cents: 15000 }]),
    });
    vi.stubGlobal("fetch", okStub);
    const fresh = await fetchOwed();
    expect(fresh[0].amount_cents).toBe(15000);
    expect(online.value).toBe(true);

    // the network drops mid-trip
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network")));
    const cached = await fetchOwed();
    expect(cached[0].amount_cents).toBe(15000); // the real last-known data, not a fixture
    expect(online.value).toBe(false);

    vi.unstubAllGlobals();
    logout();
  });

  it("rethrows when offline with no cache (caller falls back to fixture)", async () => {
    logout();
    setToken("tok-nocache");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network")));
    await expect(fetchOwed()).rejects.toThrow();
    vi.unstubAllGlobals();
    logout();
  });
});
