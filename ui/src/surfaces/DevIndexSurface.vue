<!-- AI-CONTEXT: DEV-ONLY directory ("map of everything") — NOT a product surface
     and NOT in the tab bar. A public page (meta.public) so it's always reachable
     without a session; it exists purely so a human can see and click through
     every surface in a browser during development. One-click dev sign-in (driver
     + seeded admin) gets past the auth guard; then every link works. Strings are
     hardcoded English on purpose — a dev tool, not a driver screen, so it stays
     out of the six-locale catalogs. Built from tokens to match the app. -->
<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import { BRAND } from "../core/brand.js";
import { isAuthenticated, email, logout, login, register } from "../core/api.js";
import { fallbackReport, resetFallbacksForTests } from "../core/i18n.js";

// AI-CONTEXT: U-03's counter. Every string that resolved to English because the
// driver's own locale did not have it, since this tab was opened. A dev tool is the
// right home for it — the number is a measurement for us, never a driver-facing one —
// and /dev is the one page that is always reachable without a session.
//
// It counts what has been RENDERED, so it only knows about screens someone has walked.
// A zero here means nobody has looked yet; it does not mean the catalogues are complete.
const i18nGaps = ref(fallbackReport());
function refreshGaps() {
  i18nGaps.value = fallbackReport();
}
function clearGaps() {
  resetFallbacksForTests();
  refreshGaps();
}

const router = useRouter();
const busy = ref(false);
const note = ref("");

const DRIVER = { email: "dev-driver@longhaul.local", password: "longhaul-dev-1" };
const ADMIN = { email: "admin@longhaul.local", password: "longhaul-admin-dev" };

async function signIn(who) {
  busy.value = true;
  note.value = "";
  try {
    try {
      await login(who.email, who.password); // existing account (e.g. seeded admin)
    } catch {
      await register(who.email, who.password); // first run: create the dev driver
    }
    note.value = `Signed in as ${email.value}`;
  } catch (e) {
    note.value = `Sign-in failed (${e.message}). Is the API up on :8008?`;
  } finally {
    busy.value = false;
  }
}

function signOut() {
  logout();
  note.value = "Signed out.";
}

const GROUPS = [
  {
    title: "Driver app (needs a session)",
    hint: "The mobile-first driver experience. Sign in as driver first.",
    links: [
      { to: "/map", label: "Map", desc: "The daily-open truck-aware map + The Meter entry" },
      { to: "/load", label: "Load", desc: "Active stop + The Meter (start a demo load here)" },
      { to: "/money", label: "Money", desc: "Receivables, recovered detention/accessorial" },
      { to: "/docs", label: "Docs", desc: "Document wallet (CDL/BOL/POD)" },
      { to: "/more", label: "More", desc: "Points/reputation + account + sign out" },
    ],
  },
  {
    title: "Driver full-screen flows (session)",
    hint: "Reached in-app from CTAs; linked here directly for testing.",
    links: [
      { to: "/load/calc", label: "True-profit calculator", desc: "M8 pre-acceptance decision" },
      { to: "/money/audit", label: "Settlement auditor", desc: "M9 — flags missed pay" },
      { to: "/protection/condition", label: "Condition capture", desc: "M5 — guided photo chain (needs an active load)" },
    ],
  },
  {
    title: "Web portals",
    hint: "Desktop-first §18 surfaces. Admin needs the admin sign-in.",
    links: [
      { to: "/fleet", label: "Fleet Workspace", desc: "M12 — KPIs, members, claims desk (session)" },
      { to: "/owner", label: "Property-Owner portal", desc: "M6 — listings, bookings, payout (session)" },
      { to: "/admin", label: "Admin Console", desc: "F14 — flags, funnel, config, audit (ADMIN only)" },
    ],
  },
  {
    title: "Public (no login)",
    hint: "Reachable with no session at all.",
    links: [
      { to: "/scorecard", label: "Public Scorecard", desc: "Facility dock-time + rating, aggregate only" },
      { to: "/login", label: "Login / Register", desc: "The real auth screen" },
    ],
  },
];

function go(to) {
  router.push(to);
}
</script>

<template>
  <div class="dev">
    <header class="dev__head">
      <h1 class="dev__title">{{ BRAND }} — dev directory</h1>
      <p class="dev__sub">Every surface in one place. This page is a dev tool, not a product screen.</p>
    </header>

    <section class="session">
      <div class="session__state">
        <span class="dot" :class="{ 'dot--on': isAuthenticated }" aria-hidden="true" />
        <span v-if="isAuthenticated">Signed in: <strong>{{ email }}</strong></span>
        <span v-else>Not signed in — most links will bounce to /login until you do.</span>
      </div>
      <div class="session__actions">
        <button class="btn btn--primary" type="button" :disabled="busy" @click="signIn(DRIVER)">
          Sign in as driver
        </button>
        <button class="btn btn--primary" type="button" :disabled="busy" @click="signIn(ADMIN)">
          Sign in as admin
        </button>
        <button class="btn" type="button" :disabled="busy || !isAuthenticated" @click="signOut">
          Sign out
        </button>
      </div>
      <p v-if="note" class="session__note">{{ note }}</p>
    </section>

    <section class="session i18n-gaps">
      <div class="session__state">
        <span class="dot" :class="{ 'dot--on': i18nGaps.total === 0 }" aria-hidden="true" />
        <span>
          English reaching a non-English driver:
          <strong>{{ i18nGaps.total }}</strong> string(s) since this tab opened
        </span>
      </div>
      <p class="session__note">
        Walk the tabs in each locale, then Refresh. A zero means nobody has looked yet —
        it is not a claim that the catalogues are complete.
      </p>
      <ul v-if="i18nGaps.total" class="gaps">
        <li v-for="(n, loc) in i18nGaps.byLocale" :key="loc" class="gaps__row">
          <strong>{{ loc }}</strong> — {{ n }} missing
        </li>
      </ul>
      <ul v-if="i18nGaps.total" class="gaps">
        <li v-for="e in i18nGaps.entries" :key="`${e.locale}|${e.key}`" class="gaps__key">
          {{ e.locale }} · {{ e.key }}
        </li>
      </ul>
      <div class="session__actions">
        <button class="btn" type="button" @click="refreshGaps">Refresh</button>
        <button class="btn" type="button" @click="clearGaps">Reset</button>
      </div>
    </section>

    <section v-for="g in GROUPS" :key="g.title" class="group">
      <h2 class="group__title">{{ g.title }}</h2>
      <p class="group__hint">{{ g.hint }}</p>
      <ul class="cards">
        <li v-for="l in g.links" :key="l.to">
          <button class="card" type="button" @click="go(l.to)">
            <span class="card__label">{{ l.label }}</span>
            <span class="card__path">{{ l.to }}</span>
            <span class="card__desc">{{ l.desc }}</span>
          </button>
        </li>
      </ul>
    </section>

    <p class="tip">
      Tip: to see The Meter live, sign in as driver → open <strong>Load</strong> → "Start a load" →
      "I've arrived". To test the admin knobs, sign in as admin → <strong>Admin Console</strong>.
    </p>
  </div>
</template>

<style scoped>
.dev {
  padding: var(--s-5);
  max-width: 960px;
  margin: 0 auto;
}
.dev__title {
  margin: 0;
  font-size: var(--type-display-size);
  line-height: var(--type-display-line);
  font-weight: var(--type-display-weight);
}
.dev__sub {
  margin: var(--s-1) 0 var(--s-4);
  color: var(--text-3);
  font-size: var(--type-body-size);
}
.session {
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
  padding: var(--s-4);
  margin-bottom: var(--s-5);
}
.session__state {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  font-size: var(--type-body-size);
  margin-bottom: var(--s-3);
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--text-3);
  flex: none;
}
.dot--on {
  background: var(--ledger-500);
}
.session__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
}
.btn {
  min-height: 44px;
  padding: 0 var(--s-4);
  border: 1px solid var(--line-1);
  border-radius: var(--r-control);
  background: transparent;
  color: var(--text-1);
  font-size: var(--type-label-size);
  font-weight: 500;
}
.btn--primary {
  background: var(--accent-fill);
  color: var(--on-accent);
  border-color: transparent;
}
.btn:disabled {
  opacity: 0.5;
}
.session__note {
  margin: var(--s-3) 0 0;
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
.gaps {
  margin: var(--s-3) 0 0;
  padding-left: var(--s-4);
  color: var(--text-2);
  font-size: var(--type-caption-size);
  max-height: 240px;
  overflow-y: auto;
}
.gaps__key {
  font-family: var(--font-mono);
}
.group {
  margin-bottom: var(--s-5);
}
.group__title {
  margin: 0;
  font-size: var(--type-title-size);
  line-height: var(--type-title-line);
  font-weight: var(--type-title-weight);
}
.group__hint {
  margin: var(--s-1) 0 var(--s-3);
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.cards {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--s-2);
}
@media (min-width: 640px) {
  .cards {
    grid-template-columns: 1fr 1fr;
  }
}
.card {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  text-align: left;
  padding: var(--s-3) var(--s-4);
  border: 1px solid var(--line-1);
  border-radius: var(--r-card);
  background: var(--ink-1);
  color: var(--text-1);
}
.card__label {
  font-weight: 500;
  font-size: var(--type-body-size);
}
.card__path {
  font-family: var(--font-mono);
  color: var(--shield-500);
  font-size: var(--type-caption-size);
}
.card__desc {
  color: var(--text-3);
  font-size: var(--type-caption-size);
}
.tip {
  margin: var(--s-4) 0 0;
  padding: var(--s-3) var(--s-4);
  border: 1px dashed var(--line-1);
  border-radius: var(--r-card);
  color: var(--text-2);
  font-size: var(--type-caption-size);
}
</style>
