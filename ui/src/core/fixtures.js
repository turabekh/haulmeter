// AI-CONTEXT: this module is DELIBERATELY EMPTY. Do not add anything to it.
//
// It held sixteen fixtures — SAMPLE_PINS, SAMPLE_WALLET, SAMPLE_OWED, SAMPLE_EARNINGS,
// SAMPLE_POINTS, SAMPLE_FLEET, SAMPLE_OWNER, SAMPLE_FUEL_ANALYTICS, sampleProfile,
// sampleFacilityIntel, sampleQuestions, sampleSleepPlan, sampleAudit, sampleHandoffs,
// sampleFacilities, sampleScorecard — imported by ten files. They are gone (§23 entry
// 131), and the file is kept rather than deleted so this note survives: the next
// person needing placeholder data will reach for this drawer, and the reasoning has to
// be here when they open it.
//
// WHY THEY WENT. Every surface that fetches had two states, data and no-data, so a
// null response had to mean one of the two — and the codebase chose data:
//
//     const rawPins = computed(() => livePins.value ?? SAMPLE_PINS.filter(...))
//
// That put fabricated truck stops on the map on EVERY cold open, not only offline
// (audit U-10). Five other surfaces did the same on failure: a CDL that was not the
// driver's (U-09), Driver Dollars Delivered they had not earned (U-06), a settlement
// discrepancy no carrier owed, lots to sleep in that do not exist. §11.7 is the law all
// of them broke — the product asserting something it does not know — and it is the
// pattern behind six of the eight criticals across both audits.
//
// The fixtures could not simply be deleted, which is why this took an owner decision
// rather than a session: with no `loading` state, removing them traded a §11.7
// violation for a §8 one — a blank screen on every cold start. The skeleton primitive
// (`components/Skeleton{Card,Row,Pin}.vue`) and the four-state model (`load-state.js`)
// are the prerequisite that made the deletion possible.
//
// WHAT TO DO INSTEAD, depending on what you actually need:
//
//   · a surface with nothing to show yet ..... `LoadState.LOADING` + a Skeleton shape
//   · a surface whose fetch failed ........... `LoadState.FAILED` + §15.4's inline line
//   · a surface with a real empty result ..... §15.3: one sentence + one action
//   · test data .............................. a constant in the TEST file, shaped to
//                                              the endpoint it stands in for
//   · something to demo `/dev` against ....... `make seed`, against a real account
//
// The distinction that decides all five: a placeholder EXPORTED FROM `src/` is one
// import away from a driver's screen. §23 entry 81 removed the corridor fixture on
// exactly that argument — "an exported placeholder is one import away from being back
// on the screen a driver cannot verify" — and this file proved the point on its own:
// `SAMPLE_FUEL_ANALYTICS` was exported here and imported by NOTHING, a fixture already
// halfway back.
//
// Held by `test/loading-state.test.js`, which asserts this module exports nothing and
// that no file under `src/` imports it. That test was written first and watched failing.
export {};
