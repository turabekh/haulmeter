# KICKOFF — M15 Session D: the teaching loop (FR5)

**Status: DRAFT, awaiting owner approval.** D14 is signed at scope (b), which authorizes
sessions one at a time against their own kickoffs. Session C's was entry 179; this is D's.

---

## 1. What FR5 actually asks for

Every meaningful failure runs a sequence, and E3 names all eight steps:

> replay the missed question → native-language explanation of the intent and the idiom →
> phrase-family exposure (hear 3–6 equivalents) → listen drill → respond-aloud →
> **model-answer shadowing** → variation → mini-sim retest

Plus two rules with teeth: vocabulary the baseline shows as unknown is **taught before it
is ever tested**, and a driver whose language has no released coaching sees an honest
"not yet in your language" — **never silent English** (Q-9).

**Its validation is the module's north star:** *a driver who failed an intent at baseline
passes its **holdout** variant after completing the loop — observed in `skill_state`.*

## 2. What exists, checked rather than assumed

| piece | state |
|---|---|
| `skill_state` table | exists · **written by nothing** — the north-star measurement has no writer |
| `coaching_content` table | exists · referenced only by the publish-transition helpers |
| released English phrasings | **2 per intent** (E3 wants 5–8) |
| officer audio | synthesized and serving, since entry 183 |
| the publish pipeline | built and used in anger — this is what makes content shippable now |
| holdout variants | 3, released-status `draft`, correctly withheld from teaching |

## 3. The trap this kickoff exists to avoid

Session C shipped an engine with no content and the owner found a silent screen. **FR5 is
the same shape, only larger**: a teaching loop with nothing to teach is a worse version of
the same mistake.

So the scope below is drawn along one line — **what can reach a driver this session** — and
the answer turns on a fact worth stating plainly:

**Most of the loop is ENGLISH, and English does not need a native reviewer.** Replaying the
missed question, hearing 3–6 equivalents, shadowing a model answer and the mini-sim retest
are all English content. The owner is the named human Q-6 wants for it. Only the
*explanation of the idiom* is native-language, and that is the one step that waits.

## 4. Scope

1. **`skill_state` gets its writer.** Exposure, success, and the per-variant record that
   makes "improved" mean anything. Without this FR5 cannot be validated at all, and FR6's
   spaced repetition has nothing to schedule from.
2. **The teaching loop**, driven by the failure tags already produced: replay → phrase
   family → model answer → shadow → retest on a **different released variant**, never the
   holdout (Q-5 keeps holdouts for reassessment, which is FR7).
3. **Model answers** as content through the **existing** publish pipeline — drafted by F9,
   reviewed and released by the owner, exactly as the officer lines were.
4. **More English phrasings per intent** — 2 is not a phrase family. Drafted, then owner-
   reviewed. This is the content pass that makes step 2 mean something.
5. **The Q-9 state**: where native-language coaching has not been released, the surface
   says so in the driver's language rather than falling back to English.
6. **The coaching surface**, composed from Session C's patterns — same §22.3 DoD, same
   layout-harness and DRIVE.md rules, same commits.

## 5. Not in scope

- **FR6 (the 30-day drill plan, SRS scheduling, offline packs)** — it needs P-1
  `readiness_reminder` to be signed before a daily habit has a mechanism, and that is
  still an unsigned owner fork (entry 177).
- **FR7 (reassessment, the Training & Improvement Record, `/verify`)** — the holdouts stay
  reserved for it.
- **Uzbek coaching text.** Drafting it is cheap and worthless without review; it ships when
  a native speaker has read it. The engine treats its absence as the designed state.
- No new notification class. No flag flip beyond what is already on. No new nav structure.

## 6. Definition of done

- A driver who fails an intent is **taught it** and then retested on a different released
  phrasing, in a browser at 360 × 800 — observed, not asserted.
- `skill_state` rows exist and change, and the before/after is visible in the database.
- Model answers and the extra phrasings are **released through the admin surface** by the
  owner, so the loop has real content behind it.
- The Q-9 state renders for a locale with no released coaching.
- Layout harness, DRIVE.md and locale completeness updated in the same commits; `make ci`
  green; `m15_roadside` unchanged.

## 7. What I need from you

1. **Approve or cut the scope**, particularly item 4 — I draft extra English phrasings and
   model answers, you review and release them. Without that the loop teaches from a pool
   of two.
2. **Confirm the retest rule:** after coaching, retest on a *different released variant*
   and keep holdouts for FR7's reassessment. That is what E3 says; it is worth a nod
   because it means the retest is slightly easier than the real reassessment will be.
