<!-- AI-CONTEXT: §23 entry 99 — "show me somewhere else" on the Map.

     Neither PRD had a notion of viewing the map away from the driver: §10.1 assumes
     it is HERE and §11.4 assumes it is AHEAD. The owner asked for elsewhere, so §22.2
     applied and the two never-improvise questions (the destination, and whether it
     persists) were the owner's: a conditional chip opening this sheet, and a one-shot
     look that snaps back.

     Composed, not invented. BottomSheet is the shell every other sheet uses, the
     geocoder is the one already behind the rate-con import, and the chip that opens
     this reuses the saved-chip's shape — the same composition the saved queue's own
     note describes. No new component pattern.

     Two rules this sheet must not soften:
     · It moves the VIEW and never the driver's reported location. `lastFix` feeds the
       position pings behind F3 arrival, the geofence, the detention clock and
       `presence_proven`; a driver parked in Perth who could "pin" to Dallas would arm
       a stop there and run a clock on fiction. This sheet emits coordinates to look
       at. It never writes a fix.
     · The geocoder PROPOSES and the driver CONFIRMS — `label` is the geocoder's own
       wording for what it matched, rendered rather than assumed (§11.7), exactly as
       RateConImportSheet does it. Three candidates for "Dallas" is the honest answer;
       silently taking the first would be the map inventing a place again.

     DRIVING: never opened. Forbidden #11 bans keyboard input at speed, and the chip
     that opens this is not rendered while moving — the same rule MoreFiltersSheet
     follows one file over. -->
<script setup>
import { ref, watch } from "vue";
import { Search } from "lucide-vue-next";
import BottomSheet from "./BottomSheet.vue";
import { useI18n } from "../i18n.js";
import { geocodeAddress } from "../api.js";

const props = defineProps({ open: { type: Boolean, default: false } });
const emit = defineEmits(["close", "pick"]);
const { t } = useI18n();

const query = ref("");
const places = ref([]);
const searching = ref(false);
const searched = ref(false);
const failed = ref(false);

watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return;
    query.value = "";
    places.value = [];
    searching.value = false;
    searched.value = false;
    failed.value = false;
  },
);

async function search() {
  const address = query.value.trim();
  if (!address || searching.value) return;
  searching.value = true;
  failed.value = false;
  try {
    const body = await geocodeAddress(address);
    places.value = body.places || [];
  } catch {
    // offline or the geocoder is unreachable. Two different facts from "nothing
    // matched", and §11.7 does not let one be rendered as the other.
    places.value = [];
    failed.value = true;
  } finally {
    searching.value = false;
    searched.value = true;
  }
}

function pick(place) {
  emit("pick", place);
  emit("close");
}
</script>

<template>
  <BottomSheet :open="open" :title="t('place.title')" @close="emit('close')">
    <form class="place__form" @submit.prevent="search">
      <label class="place__label" for="place-q">{{ t("place.label") }}</label>
      <div class="place__row">
        <input
          id="place-q"
          v-model="query"
          class="place__input"
          type="text"
          autocomplete="off"
          :placeholder="t('place.placeholder')"
        />
        <button class="place__go" type="submit" :disabled="!query.trim() || searching">
          <Search :size="18" :stroke-width="2" aria-hidden="true" />
          <span class="place__go-text">{{ t("place.search") }}</span>
        </button>
      </div>
      <p class="place__hint">{{ t("place.hint") }}</p>
    </form>

    <p v-if="searching" class="place__note">{{ t("place.searching") }}</p>
    <p v-else-if="failed" class="place__note">{{ t("place.failed") }}</p>
    <p v-else-if="searched && !places.length" class="place__note">{{ t("place.none") }}</p>

    <ul v-if="places.length" class="place__list">
      <li v-for="place in places" :key="`${place.lat},${place.lon}`">
        <button class="place__item" type="button" @click="pick(place)">
          {{ place.label }}
        </button>
      </li>
    </ul>
  </BottomSheet>
</template>

<style scoped>
.place__form {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.place__label {
  display: block;
  color: var(--text-2);
  font-size: var(--type-label-size);
}
.place__row {
  display: flex;
  gap: var(--s-2);
}
.place__input {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 56px;
  padding: 0 var(--s-3);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
}
.place__go {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2);
  min-height: 56px;
  padding: 0 var(--s-3);
  border: 0;
  border-radius: var(--r-control);
  background: var(--accent-fill);
  color: var(--on-accent);
  font-size: var(--type-label-size);
}
.place__go:disabled {
  background: var(--ink-1);
  color: var(--text-3);
}
.place__hint {
  margin: 0;
  color: var(--text-3);
  font-size: var(--type-caption-size);
  line-height: var(--type-body-line);
}
.place__note {
  margin: var(--s-3) 0 0;
  color: var(--text-2);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
.place__list {
  margin: var(--s-3) 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
}
.place__item {
  width: 100%;
  min-height: 56px;
  padding: var(--s-2) var(--s-3);
  text-align: left;
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: var(--ink-0);
  color: var(--text-1);
  font-size: var(--type-body-size);
  line-height: var(--type-body-line);
}
</style>
