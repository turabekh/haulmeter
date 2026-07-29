<!-- AI-CONTEXT: §23 entry 102 — the surface F8 never had.

     F8 has decided tiers, budgets, quiet hours and classes since it shipped and every
     decision ended in a row nobody could read. §23 entry 429 caught the miniature —
     "nothing may be filed P2 until a surface renders the digest" — and the general
     case was larger: nothing rendered ANY of it.

     Rules this list must not soften:
     · §13.5 — every notification deep-links to the exact screen and state it
       describes, never a tab root. The link is the server's, carried down rather than
       re-derived here, so push and inbox can never disagree about where a thing is.
     · A SUPPRESSED notification is shown, and says it was held. §13.1 caps unprompted
       INTERRUPTIONS; a driver who opens this list is asking, not being interrupted.
       Quiet hours defer — they do not destroy — and a list that hid what it deferred
       would turn a considerate rule into a lossy one.
     · "Nothing yet" is a real state and says so plainly (§15.3), because an empty
       inbox and a broken inbox look identical otherwise — which is exactly how this
       whole area went unnoticed for as long as it did.
     · Time is relative and coarse (`ageLabel`), the same vocabulary the map uses for
       crowd freshness. One wording everywhere (§14.3).

     DRIVING: this is reached from More, which is an S3 surface — a driver is not
     browsing an inbox at speed, and §13.4 already routes in-motion notifications to
     audio summaries rather than to a list. -->
<script setup>
import { computed } from "vue";
import { Bell, Clock } from "lucide-vue-next";
import { useI18n } from "../i18n.js";
import { ageLabel } from "../presentation.js";

const props = defineProps({
  notifications: { type: Array, default: () => [] },
  now: { type: Number, default: () => Date.now() },
});
const emit = defineEmits(["open"]);
const { t } = useI18n();

const rows = computed(() =>
  props.notifications.map((n) => ({
    ...n,
    unread: !n.read_at,
    // the server said why it held this one back; the list repeats it rather than
    // rendering a silent gap the driver has to interpret
    held: n.status === "suppressed",
    age: n.created_at ? ageLabel(new Date(n.created_at).getTime(), props.now) : null,
  })),
);
</script>

<template>
  <div class="notif">
    <p v-if="!rows.length" class="notif__empty">{{ t("notifications.empty") }}</p>

    <ul v-else class="notif__list">
      <li v-for="n in rows" :key="n.id">
        <button
          class="notif__row"
          :class="{ 'notif__row--unread': n.unread }"
          type="button"
          @click="emit('open', n)"
        >
          <span class="notif__head">
            <Bell v-if="n.unread" :size="16" :stroke-width="2.5" aria-hidden="true" />
            <span class="notif__title">{{ n.title }}</span>
          </span>
          <span class="notif__body">{{ n.body }}</span>
          <span class="notif__meta">
            <span v-if="n.age" class="notif__age">{{ n.age }}</span>
            <span v-if="n.held" class="notif__held">
              <Clock :size="14" :stroke-width="2.5" aria-hidden="true" />
              {{ t("notifications.held") }}
            </span>
          </span>
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.notif__empty {
  margin: 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.notif__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.notif__row {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
  width: 100%;
  min-height: 64px;
  padding: var(--s-3);
  text-align: left;
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
}
.notif__row--unread {
  border-color: var(--marker-500);
}
.notif__head {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  color: var(--text-1);
  font-size: var(--type-label-size);
  font-weight: 600;
}
.notif__title {
  min-width: 0;
}
.notif__body {
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.notif__meta {
  display: flex;
  align-items: center;
  gap: var(--s-3);
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.notif__age {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
.notif__held {
  display: inline-flex;
  align-items: center;
  gap: var(--s-1);
}
</style>
