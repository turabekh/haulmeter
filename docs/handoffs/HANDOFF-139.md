# HANDOFF-139 — M15 Session F: the play button that was never broken

A short session with one owner-reported symptom — *"the play buttons not working"* — and
three genuinely different causes underneath it, only one of which was in the code that
draws the button. Owner-directed; decisions **205–206**; deployed and verified on
production.

The lesson worth carrying: **the symptom was reported against a screen, and the screen was
innocent every time.** One cause was a lookup that had quietly stopped matching, one was a
box nobody was looking at, and one was my own editing invalidating the owner's URLs in
real time while I investigated them.

---

## 1. State at the break

Deployed. Production at alembic head `0093_m15_coaching_voice`.

```
prod  coaching screen, 8 play buttons, every one HTTP 206 audio/mpeg, PLAYING, resolved
prod  m15_heal_audio: checked 40 released lines, 0 missing bytes   <- audio genuinely healthy
prod  outbound queue: 0 unsent / 63 sent (checked BEFORE deploy)
gates 2387 pytest passed · 1068 vitest passed · 32 import contracts kept
```

The eighth button is new: it is FR5 step 1, *replay the question you missed*, which had
been structurally absent since the officer started improvising and which nothing detected.

## 2. The three causes, in the order they were wrong

**(a) A lookup that matched content by its TEXT** — `missed_question_audio` was found by
matching the officer's transcript against the released `PhraseVariant` rows. Correct while
every line he spoke came out of that table; since entry 194 he composes his own, so the
match never succeeds, the value is always `None`, and `v-if` simply stops drawing the
button. **No error, no log, no red test — a button that was never there is not a failure.**
The audio had been on the officer's own `Turn.audio_ref` the whole time, which is a better
replay than a variant's separate rendering of the same sentence. (Entry 205, TRAPS 86.)

**(b) The screenshot was not production.** The reported screen showed a *released* Uzbek
explanation; production had those three `CoachingContent` rows as `draft`, which cannot
render one at all. Two states that cannot coexist means two boxes — it was the local
stack. **An hour went into proving production healthy, which it was, and which was never
the question.** On local, every M15 audio object was missing from MinIO: 13,674 objects in
the bucket, 83 mp3, and every one a runtime `fragment-*.mp3` — zero `m15-*.mp3`. That is
TRAPS 85, written after *production* hit it, never checked on dev. (Entry 206, TRAPS 89.)

**(c) `MEDIA_SIGNING_SECRET` was empty and dev runs `uvicorn --reload`.** An unset secret
mints a per-process signing key. That was documented as acceptable because URLs only break
across a restart and "the next render mints fresh ones" — **which assumes a surface that
re-renders.** The coaching screen mints its URLs on load and then sits there. `--reload`
respawns the process on every file edit, so every button on the owner's screen was 403ing
`bad signature` each time I touched a source file. (Entry 206, TRAPS 88.)

## 3. What was built

| thing | why |
|---|---|
| `coaching_for` reads `officer.audio_ref` | restores FR5 step 1; variant match kept as fallback |
| coach surface playback | one clip at a time, retained reference, `data-playing`, stops when driving — the pattern the transcript surface already had |
| `heal_missing_audio` + `make m15-heal-audio` | the repair TRAPS 85 never had: probes each object, clears only refs whose bytes are gone, safe on a healthy box |
| `m15_revoice` gained `CoachingContent` | it gates on `review_status`, not `status`, so it falls out of every table-loop sweep — a voice change would have left every explanation in the old voice |
| `scripts/gen_signing_secret.sh` at `make env` | per-box secret; **generated, never committed** — a shared signing secret is one anyone can mint URLs with |

Six new tests, all sabotage-checked against the old behaviour.

## 4. The exact next task

**Nothing is half-finished.** The queue is what it was before this session, minus one
defect:

1. **Owner-only, and now the only thing standing between a driver and Uzbek coaching on
   production:** release the three drafted Uzbek explanations in `/admin/roadside`. They
   are drafted and reviewed-by-nobody; Q-6 says a human releases them. The moment they are
   released the synthesis worker voices them on its own pass — **do not synthesize
   unreviewed text to save a step.**
2. The pilot day — all 7 Journey-1 lines in `docs/validation/j1-journey.md` still open.
   This remains the largest gap between "built" and "validated" on the whole platform.
3. FR7 reassessment, F12 offline drill prefetch, P-1/P-2 notification classes.
4. Five-run `make ci` for flake confidence.

## 5. Open, deliberately not closed

- **`/session/{id}/result` has no ownership check** — anyone with a session id can read its
  band. Found in Session E, still true, still deliberately not widened without the owner.
  `/coaching` is the same. Neither leaks a name; both leak a stranger's score.
- **Production's Uzbek coaching is `draft`**, so the coaching screen there correctly shows
  "not yet in your language". That is Q-9 working, not a defect — do not "fix" it.
- **Push was not requested and has not happened.** Two commits (`528e5a1`, `c12949c`) are
  local only. The repo is public; the diffs were scanned and carry no secrets.

## 6. For the next session

The three traps added here (86, 87, 88) plus 89 all say one thing: **when a surface is
reported broken, establish which box is on screen and whether the surface is even
involved, before reading the surface's code.** Two of this session's three causes were
invisible from the component and one of them was being caused by the investigation itself.

And the specific habit worth keeping: **drive the real screen with Playwright and
instrument `window.Audio`.** Proving all seven buttons played correctly is what redirected
the search to the button that was missing. A green suite would never have said that.
