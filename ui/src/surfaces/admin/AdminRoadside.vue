<!-- AI-CONTEXT: Q-6's operator surface (E3 §E3.1.5), and the reason Session C exists in
     this shape.

     `mark_reviewed` and `release` had lived in the domain since Session A with NO CALLER
     anywhere in the product. Nothing could ever become `released`, so every driver surface
     in M15 would have rendered its empty state permanently — on production and on the
     owner's own machine. This screen is the missing half.

     THE REVIEWER IS THE SIGNED-IN ADMIN, and there is no field for it. `mark_reviewed`
     demands a named human because a blank reviewer is how "reviewed" silently becomes
     "generated"; a text box would let that name be anything at all. The account that
     clicked is the only claim the server can honestly make, and it is kept in the audit
     entry rather than on the row.

     RELEASE IS NOT OFFERED FROM DRAFT. The server refuses it either way — the transition
     is guarded in `content.py`, not here — but a button that always 422s is a button that
     teaches an operator the surface is unreliable. The action ladder mirrors the law.

     HOLDOUTS ARE MARKED, loudly. Q-5 says a holdout never reaches a teaching surface, and
     that is enforced in the generators; but an operator releasing a batch without being
     able to see which of them are holdouts is how a well-meaning human becomes the leak. -->
<script setup>
import { onMounted, ref } from "vue";
import { useI18n } from "../../core/i18n.js";
import {
  fetchRoadsideContent,
  reviewRoadsideContent,
  releaseRoadsideContent,
} from "../../core/api.js";

const { t } = useI18n();
const content = ref(null);
const failed = ref(false);
const busy = ref(null);

async function load() {
  failed.value = false;
  try {
    content.value = await fetchRoadsideContent();
  } catch {
    failed.value = true;
  }
}

onMounted(load);

async function act(kind, id, action) {
  if (busy.value) return;
  busy.value = id;
  failed.value = false;
  try {
    await (action === "review" ? reviewRoadsideContent : releaseRoadsideContent)(kind, id);
    await load();
  } catch {
    failed.value = true;
  } finally {
    busy.value = null;
  }
}

const statusLabel = (status) => t(`admin.roadside.status.${status}`);
</script>

<template>
  <section class="panel">
    <h2 class="panel__title">{{ t("admin.roadside.title") }}</h2>
    <p class="panel__note">{{ t("admin.roadside.intro") }}</p>

    <p v-if="failed" class="panel__note" role="alert">{{ t("admin.roadside.failed") }}</p>

    <template v-if="content">
      <h3 class="panel__title">{{ t("admin.roadside.scenarios") }}</h3>
      <p v-if="!content.scenarios.length" class="panel__empty">{{ t("admin.roadside.empty") }}</p>
      <table v-else class="table">
        <tbody>
          <tr v-for="s in content.scenarios" :key="s.id">
            <td class="table__name">
              {{ s.intents.join(", ") }}
              <div class="table__muted">{{ t("admin.roadside.version", { n: s.version }) }}</div>
            </td>
            <td><span class="pill">{{ statusLabel(s.status) }}</span></td>
            <td>
              <button
                v-if="s.status === 'draft'"
                class="btn"
                type="button"
                :disabled="busy === s.id"
                @click="act('scenario', s.id, 'review')"
              >
                {{ t("admin.roadside.review") }}
              </button>
              <button
                v-else-if="s.status === 'reviewed'"
                class="btn btn--accent"
                type="button"
                :disabled="busy === s.id"
                @click="act('scenario', s.id, 'release')"
              >
                {{ t("admin.roadside.release") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>

      <h3 class="panel__title">{{ t("admin.roadside.intents") }}</h3>
      <p v-if="!content.intents.length" class="panel__empty">{{ t("admin.roadside.empty") }}</p>
      <div v-for="intent in content.intents" :key="intent.key">
        <h4 class="panel__title">{{ intent.key }}</h4>
        <table class="table">
          <tbody>
            <tr v-for="v in intent.variants" :key="v.id">
              <td class="table__name">
                {{ v.text }}
                <div v-if="v.holdout" class="table__muted">{{ t("admin.roadside.holdout") }}</div>
                <div class="table__muted">{{ t("admin.roadside.version", { n: v.version }) }}</div>
              </td>
              <td><span class="pill">{{ statusLabel(v.status) }}</span></td>
              <td>
                <button
                  v-if="v.status === 'draft'"
                  class="btn"
                  type="button"
                  :disabled="busy === v.id"
                  @click="act('variant', v.id, 'review')"
                >
                  {{ t("admin.roadside.review") }}
                </button>
                <button
                  v-else-if="v.status === 'reviewed'"
                  class="btn btn--accent"
                  type="button"
                  :disabled="busy === v.id"
                  @click="act('variant', v.id, 'release')"
                >
                  {{ t("admin.roadside.release") }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>
