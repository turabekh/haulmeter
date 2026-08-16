# HANDOFF-133 — M15 Session B: the loop runs on real speech, and two things it found

**Autonomous run**, authorized by the Session-B kickoff against D14 (entry 179 — no new
D-number, per the slice discipline D14 itself restated). Nothing pushed, nothing deployed.

**The headline is not the loop.** It is that running the loop against real providers found
a defect that would have told a driver they answered incompletely when they had answered
perfectly — and that a green suite had no opinion about it at all.

---

## 1. Gates

| gate | Session-B start | now |
|---|---|---|
| pytest | 2230 | **2279 passed, 0 failed** |
| vitest | 1028 / 64 files | **1028 / 64, exit 0** (no UI work this session) |
| import-linter | 32 kept | **32 kept, 0 broken** |
| ruff | clean | clean |
| alembic head (dev) | 0086_f06_retention | **0087_m15_hidden** |

Run directly rather than delegated — see §6 for why that mattered this time.

---

## 2. Step 0 and Step 2 — the keys are live, three remainders closed

All four keys load in **both** api and worker after `--force-recreate` (masked: Deepgram
len 40, Azure len 84 + region `eastus`, Telegram len 46). The loud-refusal seams still
refuse with real keys present — keys existing did not weaken the seam.

`make m15-key-smoke` (never in `make ci` — it reaches paid APIs; a suite that fails when
the wifi does is a suite people learn to ignore):

| provider | result |
|---|---|
| Telegram | `getMe` → **@HaulmeterBot**, id 8710197965. Read-only. No sends. |
| Azure TTS | three clips, incl. both Uzbek voices |
| Deepgram | **round trip on the Azure clip**: spoken *"Good afternoon. Where are you headed today?"* → heard *"good afternoon where are you headed today"*, confidence **1.000** |

Making STT transcribe the audio TTS had just produced turns two unrelated pings into the
real integration question — both work *and* they work on each other's formats.

Four F9 rows written and then **queried**: 3 tts + 1 stt, 4384 micros against m15's budget.

### For the owner: the Uzbek spot-check

**`docs/voice-samples/`** — `officer_en.mp3`, `coach_uz_sardor.mp3`, `coach_uz_madina.mp3`,
with a README stating what is actually being asked: not "is it understandable" but **would
a driver trust it**. A coach voice that sounds wrong teaches a driver to stop listening.

**No Uzbek is synthesized at scale until you confirm these.** They are deliberately not
stored in F6 — content audio is permanent-class and belongs to a released variant, and
storing spot-check output as content is how an unreviewed voice ends up on a driver-facing
line.

---

## 3. The defect worth reading

`make m15-session-probe` runs a full session as a **guest principal** against the DEV_SEED
scenario with both providers live: Azure speaks each driver answer, Deepgram hears it back.
So the transcripts scored were never typed.

First run:

```
spoke : 'I have been driving six hours today'
heard : 'i have been driving six hours today'  (conf 1.000)
slots : {}          answer_completeness: 0
```

A perfect answer, scored incomplete. The cause is a gap **between two halves of E3**:
§E3.1.2 says a `scenario_version` carries hidden state *"from which questions and expected
answers derive"*; §E3.1.4's table list has no column for it. So `expected_slots` was filled
from `intent.required_slots`, whose values name *which* facts are needed — the string
`"required"` — and the validator checked whether the driver had said the word "required".

**Every existing test passed**, because each supplied its expected slots directly and never
went near the resolution step. That is this codebase's oldest defect class, and only a real
session touched the seam.

Migration **0087** adds `hidden_state`; `expected_slots_for` resolves the two against each
other; the DEV_SEED scenario carries real facts. A slot the scenario has no fact for is
**dropped** — a question we cannot mark cannot be failed.

### And the false green it produced on the way

After the fix the probe reported 100 across the board — **for the wrong reason.** The box
was already seeded, so its scenario still had `hidden_state = {}`, which made
`expected_slots` empty, which scores 100 for having nothing to answer. It looked better and
proved less. Caught by noticing `slots : {}` was still empty beside a perfect score.

The seed now **backfills** rather than skipping, so the next person cannot hit it.

---

## 4. The loop, measured

With real facts in place, the observation is genuine — slots filled from the driver's
spoken words:

```
turn 1  hos_hours_driven  heard 'i have been driving six hours today'  slots {'hours': '6'}
turn 3  destination       heard 'i am going to chicago'                slots {'destination': 'Chicago'}
turn 5  logbook_request   heard 'yes here is my logbook'               slots {}
band=green  provisional=True  label_key=roadside.band.green_provisional
```

Guest claimed into an account afterwards: `sessions_moved=1`.

### Latency — reported as measured, not as hoped

| metric | measured | budget | verdict |
|---|---|---|---|
| p75 | **1403 ms** | ≤1300 | **MISSED** |
| p95 | 1403 ms | ≤1800 | MET |

Raw: `[1029, 1376, 1403]` ms. An earlier run of the same code measured `[700, 741, 1097]`
and would have reported p75 MET — the difference is network variance to Deepgram, not code.

**n=3, so p75 and p95 are both essentially "the maximum".** Quantiles over three samples
are close to meaningless, and the honest read is: *a single turn round-trips in roughly
0.7–1.4 s, which straddles the 1.3 s budget.* A real measurement needs a scenario with many
more turns, and Session C should build one before anyone claims the budget is met. The
clock covers transcribe + score only; synthesizing the driver's answer is excluded, because
a real driver's mouth is not on our latency budget.

---

## 5. What is built, and what is not

**Built and tested (93 m15 tests):** the four scored dimensions and ten failure tags; the
deterministic slot validator; the F9 rubric bridge; bands with Q-8's provisional label; the
transport-free session loop; the first **WebSocket** in this codebase.

**Quality laws, each written as the failure it prevents and each sabotage-checked:** Q-1
(accent is never a feature — *"I go Chicago"* outscores *"Yes."*), Q-2 (below the ASR floor
scores **nothing**, so an unheard turn cannot drag a band down), Q-4 (refuses to start AND
hard-pauses mid-turn), Q-6 (an empty released pool **raises** rather than falling back to
draft), Q-8 (there is no API that returns a bare band).

**NOT built — Session C's kickoff must carry or drop these deliberately:**

- **All UI surfaces.** No session screen, no consent screen, no result screen. The kickoff's
  step 10 was not reached, so **nothing is in the layout harness and no locale strings were
  added.** The `roadside.band.*` keys the API returns do not exist in any catalogue yet.
- **The teaching loop (FR5)** — step 9, not started.
- **The WebSocket is untested over the wire.** It has no integration test. Every route is
  gated on `require_module("m15_roadside")` and that flag must stay `enabled IS NULL`, so
  exercising it would mean switching the module on — the owner's decision, not a probe's.
  The loop underneath it is fully tested; the socket itself is **code that has never run**.
- **The five-run `make ci` verification** is still owed. §6.

---

## 6. Two process failures, both mine

**I invalidated the `make ci` verification twice.** The second time I told the agent the
tree was frozen and then kept writing files into it; the agent did what my instruction
implied, ran `git clean`, and **destroyed four modules and three test files** that had never
been staged. Git could not help. I rewrote them from context and now commit after every
file. Recorded as **TRAPS 73a** — a "frozen tree" instruction is a promise about your own
behaviour, and it is broken by `Write`, not only by `docker`.

**Run 1 of that verification was valid and green** (exit 0, pytest 2230, vitest 1028/64,
linter 32/0). So `make ci` is green; what is unproven is that it is *repeatably* green.

---

## 7. Owner questions

1. **The Uzbek voices** — `docs/voice-samples/`. Blocks Uzbek synthesis at scale.
2. **Band thresholds.** E3 names Green/Yellow/Red but not the numbers. They are F13 config
   keys (`m15.band_green_min` 80, `m15.band_yellow_min` 55) so you can tune them without a
   deploy — but the defaults are mine, and they decide what a driver is told they are.
3. **`m15.calibration_min_samples` = 30.** E3 states the 85% agreement rate; it does not
   state a sample floor. Without one the gate opens the first time three reviews agree, and
   every band silently drops "provisional". 30 is my number.
4. **P-1 / P-2 notification classes** remain unsigned owner forks (entry 177).
5. **D15, D18, D19** remain OPEN.
6. **Tajik native review** — `docs/i18n-drafts/tg.draft.json`, still needs a paid reviewer.
7. **Latency budget** — is 0.7–1.4 s per turn acceptable while a proper measurement is
   built? The budget as written is currently missed at p75 on a 3-sample run.

---

## 8. What to do first on return

1. **The pilot day still outranks all of this** — `docs/validation/j1-journey.md`, seven
   open lines, untouched by M15.
2. If M15 continues: **Session C needs its own kickoff against D14.** The honest first item
   is the UI, because everything above is currently reachable only from a probe — and the
   second is a latency scenario long enough for a quantile to mean something.
3. **Do not read §5's "built" list as "shipped".** No driver has seen any of it, the flag is
   `enabled IS NULL`, and the socket has never carried a frame.
