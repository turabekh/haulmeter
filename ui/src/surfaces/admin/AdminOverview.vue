<!-- AI-CONTEXT: Overview — the operator's morning glance. Three questions in one
     screen: did the machinery run, what is waiting for a human, and are the value
     loops converting.

     The honesty rules here mirror the driver app's:
     · A job that never ran says "never ran", not "0". Those are different facts.
     · A job that is switched off is not a job that is failing — both are stated.
     · The overdue count is the number that should make an operator act first, so it
       carries the flare token and is never folded into the queue total. -->
<script setup>
import { computed, onMounted, ref } from "vue";
import { useI18n } from "../../core/i18n.js";
import { fetchAdminOverview } from "../../core/api.js";

const { t } = useI18n();
const data = ref(null);
// AI-CONTEXT: a switched-off module contributes no figures (§23 entry 234). Same rule
// as the rail's, and the same fail-open default: unknown renders, only a definite `false`
// hides. A zero from a dormant module is not "nothing is waiting" — it is "this cannot
// happen", and §21.3's objection to decoration applies to a stat that can only ever be 0.
const vendorLive = computed(() => data.value?.modules?.m13_vendor !== false);

function jobState(job) {
  if (!job.enabled) return { key: "admin.ov.job_off", token: "--text-3" };
  if (job.ok === null) return { key: "admin.ov.never_ran", token: "--text-3" };
  return job.ok
    ? { key: "admin.ov.job_ok", token: "--ledger-500" }
    : { key: "admin.ov.job_failing", token: "--flare-500" };
}

function stamp(iso) {
  // never localized: an operator correlating with logs needs one stable format
  return iso ? iso.replace("T", " ").slice(0, 16) : null;
}

onMounted(async () => {
  data.value = await fetchAdminOverview().catch(() => null);
});
</script>

<template>
  <div v-if="data" class="ov">
    <section class="panel">
      <h2 class="panel__title">{{ t("admin.ov.jobs") }}</h2>
      <table class="table">
        <tbody>
          <tr v-for="job in data.jobs" :key="job.job">
            <td class="table__name">{{ job.job }}</td>
            <td>
              <!-- state is colour + label, never colour alone (§16 C-1) -->
              <span class="pill" :style="{ color: `var(${jobState(job).token})` }">
                {{ t(jobState(job).key) }}
              </span>
            </td>
            <td class="table__figure">{{ stamp(job.last_run_at) || "—" }}</td>
            <td class="table__figure">
              <span v-if="job.consecutive_failures">×{{ job.consecutive_failures }}</span>
            </td>
            <td class="table__muted">
              <span v-if="job.error">{{ job.error }}</span>
              <span v-else-if="job.next_run_at">
                {{ t("admin.ov.retry_at") }} {{ stamp(job.next_run_at) }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="panel">
      <h2 class="panel__title">{{ t("admin.ov.pending") }}</h2>
      <ul class="stats">
        <li v-if="vendorLive" class="stat">
          <span class="stat__figure">{{ data.pending.vendor_verification }}</span>
          <span class="stat__label">{{ t("admin.ov.verification") }}</span>
        </li>
        <li class="stat">
          <span class="stat__figure">{{ data.pending.moderation }}</span>
          <span class="stat__label">{{ t("admin.ov.moderation") }}</span>
        </li>
        <!-- carried separately and in flare: the SLA made visible (Q-8) -->
        <li v-if="data.pending.moderation_overdue" class="stat stat--late">
          <span class="stat__figure">{{ data.pending.moderation_overdue }}</span>
          <span class="stat__label">{{ t("admin.ov.overdue") }}</span>
        </li>
        <li class="stat">
          <span class="stat__figure">{{ data.pending.claim_disputes }}</span>
          <span class="stat__label">{{ t("admin.ov.disputes") }}</span>
        </li>
      </ul>
      <p
        v-if="!(vendorLive && data.pending.vendor_verification) && !data.pending.moderation && !data.pending.claim_disputes"
        class="panel__empty"
      >
        {{ t("admin.ov.all_clear") }}
      </p>
    </section>

    <section class="panel">
      <h2 class="panel__title">{{ t("admin.ov.funnels") }}</h2>
      <ul class="stats">
        <li v-for="step in data.funnels.detention" :key="step.event" class="stat">
          <span class="stat__figure">{{ step.count }}</span>
          <span class="stat__label">{{ t(`admin.step.${step.event}`) }}</span>
        </li>
      </ul>
      <p v-if="vendorLive" class="panel__note">
        {{ t("admin.ov.appearances") }}:
        <span class="table__figure">{{ data.funnels.vendor_appearances.confirmed }}</span>
        {{ t("admin.ov.confirmed_of") }}
        <span class="table__figure">{{ data.funnels.vendor_appearances.published }}</span>
      </p>
    </section>

    <section class="panel">
      <h2 class="panel__title">{{ t("admin.ov.facilities") }}</h2>
      <ul class="stats">
        <li class="stat">
          <span class="stat__figure">{{ data.facilities.total }}</span>
          <span class="stat__label">{{ t("admin.ov.facilities") }}</span>
        </li>
        <li v-for="(n, source) in data.facilities.by_source" :key="source" class="stat">
          <span class="stat__figure">{{ n }}</span>
          <span class="stat__label">{{ source }}</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
@import "./admin-shared.css";
.stat--late .stat__figure {
  color: var(--flare-500);
}
</style>
