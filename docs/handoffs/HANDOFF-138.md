# HANDOFF-138 — M15 Session E: the officer answers in two seconds, and eight things were built and never wired

Session D made the stop teach. This session made it a **conversation a person would sit
through** — and found, repeatedly, that the thing standing between the product and working
was not missing code but code that had been written, wired to nothing, and believed.

Owner-directed throughout; decisions **190–204**.

---

## 1. What a driver gets now, measured on production

```
 2.85s  OFFICER : "Good morning. License and registration, please…"
        DRIVER  : "i have been driving five hours today"
 2.57s  OFFICER : "Five hours. Let me see your logbook, please."
        DRIVER  : "i am headed to dallas texas"
 2.63s  OFFICER : "Dallas. But I have here that your destination is Chicago. Which…"
        DRIVER  : "sorry could you say that again"
 1.79s  OFFICER : "Your destination is Chicago. Are you headed to Chicago or Dallas?"
```

**≈5.5s → ≈1.8s** between turns, with a human sound at ~0.3s. He echoes your facts, catches
a wrong city, and repeats himself when asked. Every stop is now **recorded and replayable**,
and the coaching explains itself **in Uzbek, in an Uzbek voice**.

## 2. The eight things that existed and were reachable by nothing

This is the section to read. It is the same defect eight times.

| what | how it presented | entry |
|---|---|---|
| `Prompt.model_hint` | stored, used as the cost-log **label**, never in the request — a hint made `AiCall` name a model that never ran | 193 |
| the officer kill switch | `set_config` worked; the key was **undeclared**, so `/admin` could not list it and nobody could find it | 191 |
| `_M15_KINDS` | review/release handled 2 of 7 publishable kinds — **coaching was not one**, so Q-6 and Q-9 were unreachable by a human | 201 |
| `coaching_content.audio_ref` | the column did not exist; "Uzbek with voice" was a **schema** gap | 201 |
| coaching in the synthesis job | never queried, so the new column would have been a promise nothing kept | 201 |
| `Turn.audio_ref` | existed since migration 1, its docstring naming the 30-day class; **nothing ever wrote it**, while the consent screen promised a recording | 202 |
| STT failure handling | a vendor 400 escaped the handler and **killed the whole session** | 203 |
| object storage in scripts | a bare `exec` writes bytes to memory; **31 audio objects existed only in a dead process** | 204 |

**None of them was red anywhere.** Six were found by the owner using the product or by a
live probe with bad input.

## 3. Where the latency actually was, after three wrong readings

- **Not thinking depth.** `effort=low` vs none: 2.91s vs 3.07s — inside the noise.
- **Not TTS.** 1.2s measured from a laptop in Tashkent; **0.25s from the box**, which is
  next door to Azure. The first fix was built around the wrong number and corrected in
  public (entry 192).
- **Not the frame.** Every server number said 1.93s while the driver waited 3.0s — the
  browser spent **1050ms fetching the mp3** after the frame arrived (entry 199).
- **It was the scoring rubric**, a second LLM call nobody had counted, at **3.41s of every
  exchange**, computing what a driver reads on the *result* screen (entry 194).

**The rule this session earned: instrument where the person is, not where the server ends.**

## 4. Decisions taken, and their costs

- **The officer speaks on Haiku 4.5** (owner's call), 1.24s against Opus's 3.0s. The
  guardrails were **re-earned on the new model, not assumed**: Haiku on the old prompt said
  *"Good. I'll need to see your logbook to verify…"* — Q-1 and the regulation rule broken in
  one line. Prompt v2→v5; 0 violations in 9 live samples.
- **Scoring is deferred off the conversation.** `scoring_state` exists because `scores == {}`
  already means "excluded from the band" under Q-2 — conflating that with "not yet scored"
  would band a driver on whichever turns happened to have finished.
- **Voice is `en-US-Ethan:MAI-Voice-2-Flash`**, chosen by the owner **by ear** from a
  published page of clips. It renders slower than Guy (0.54s vs 0.24s) and produces 3.0s of
  speech where Guy produced 5.3s — *faster to listen to* beat *faster to synthesize*.
- **Uzbek coaching is DRAFTED, NOT RELEASED**, and the asymmetry is deliberate: a clumsy
  English officer line is an odd sentence from a simulated policeman; a wrong Uzbek
  explanation teaches something false in a language the driver cannot check.

## 5. Gates

| gate | value |
|---|---|
| pytest | **2382** |
| vitest | **1066** |
| layout harness | **397** (+8 new states: transcript ×2, drill ×2 re-verified) |
| import-linter | **32 kept, 0 broken** |
| alembic (both boxes) | **0093_m15_coaching_voice** |
| m15 audio in MinIO | **40 objects, 0 missing** |
| outbound queue | 0 unsent, across six deploys |

## 6. What is still not true

- **The pilot day is untouched.** All seven Journey-1 lines remain open, and it is still the
  top-ranked item by the validation law. Nothing this session moved it.
- **`/session/{id}/result` has no ownership check** — anyone with a session id can read its
  band. Found while adding one to `/transcript` (entry 202) and deliberately not widened.
- **Three Uzbek explanations sit in `/admin/roadside` awaiting the owner's review.** They
  get a voice within 15 minutes of release.
- **The speaking indicator is not in the layout harness** — it lives on the session surface
  (never harnessed; socket-driven) and in the drill's in-flight state (unreachable with a
  static mock).
- **No offline drill** (F12 prefetch unbuilt, so FR6's validation cannot be run), **nothing
  reminds a driver anything exists** (P-1/P-2 unsigned), **FR7 not started**.
- **`make ci` still not verified repeatable** — two clean runs, not five.

## 7. Next

1. **The pilot day.** Unchanged in rank and untouched for three sessions.
2. **Release the Uzbek coaching**, or it stays drafted and Q-9 keeps protecting a gap.
3. **The `/result` ownership check.**
4. **FR7** — reassessment, the Training & Improvement Record, `/verify`. Needs its own
   kickoff against D14, as C/D/E did.

## 8. The habit worth keeping

Every real defect this session lived in a seam — between our code and a vendor, between a
process and its wiring, between a frame and the ear. A suite that always hands the code a
working dependency tests the happy path of the integration and nothing else. **TRAPS 79–85**
were all written this session; 83 (a killed pytest wedges every later run) and 85 (a bare
`exec` writes bytes to nowhere) each cost an hour and two confident wrong diagnoses.
