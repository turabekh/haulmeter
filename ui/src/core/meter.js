// AI-CONTEXT: The Meter's number logic (design-prd §9). Money and time are ALWAYS
// Mono + tabular (T-2); this formats them and picks the variant color per §9's
// logic: free-time countdown = text-1, last 30 min = marker, accruing money =
// ledger, disputed/overdue = flare. computeDetentionState mirrors the backend
// M3 clock (compute_detention) so The Meter can tick live in-app between syncs.

export function formatClock(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export function formatMoney(cents) {
  return (
    "$" +
    (cents / 100).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  );
}

export function computeDetentionState(arrivalMs, freeMinutes, rateCentsPerHour, nowMs, departedMs = null) {
  const detentionStart = arrivalMs + (freeMinutes || 0) * 60000;
  if (departedMs == null && nowMs < detentionStart) {
    return {
      phase: "within_free_time",
      freeTimeRemainingSeconds: (detentionStart - nowMs) / 1000,
      detentionSeconds: 0,
      amountCents: 0,
    };
  }
  const end = departedMs ?? nowMs;
  const accrued = Math.max(0, (end - detentionStart) / 1000);
  return {
    phase: departedMs != null ? "ended" : "accruing",
    freeTimeRemainingSeconds: 0,
    detentionSeconds: accrued,
    amountCents: Math.round((accrued / 3600) * (rateCentsPerHour || 0)),
  };
}

export const METER_VARIANT_TOKEN = {
  countdown: "--text-1",
  warning: "--marker-500",
  accruing: "--ledger-500",
  disputed: "--flare-500",
};

export function meterVariant(state) {
  if (state.phase === "within_free_time") {
    return state.freeTimeRemainingSeconds <= 1800 ? "warning" : "countdown";
  }
  return "accruing";
}
