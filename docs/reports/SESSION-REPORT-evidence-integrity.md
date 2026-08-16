# SESSION-REPORT — evidence integrity

2026-08-11 · branch `main` · nothing pushed, nothing deployed, stack left running.
Baseline commit `4e368f4`; five commits. Fourth of four; the prior three reports are
unmodified.

**No migration, no `.env` change, no history mutated, no new alert channel, no knob turned.**

---

## 1. T1 verification

| ID | Verdict | Evidence |
|---|---|---|
| **F4-1** | REPRODUCES | `sharing.py open_share` appended `pack_opened` on the first GET; metadata columns already updated beside it |
| **F4-2** | REPRODUCES | `verify_chain` never read `ChainAnchor` (`_latest_anchor` existed, uncalled from it); `anchor_chain(db, log)` called with no `external_ref` while the PDF printed "Anchored: yes" |
| **F4-3** | REPRODUCES | `share_pack` pinned → minted a token → appended `pack_shared` with **no verification check anywhere on the path** |
| **F4-4** | REPRODUCES | `append_record` = read head → `seq+1` → insert, no `IntegrityError` handling |
| **F4-5** | Risk reproduces; **probe says STABLE** | see §2 |
| **F3-5** | REPRODUCES | 5 counterparty strings in m03 (`open_receivable` default, `_notice_body` ×2, `_dunning_body` ×2) **+ 1 driver catalogue key** (`claim.evidence`) **+ the module's own docstring** |
| **carried** | **DID-NOT-REPRODUCE as stated** | the notice control was already offered in `failed` — `notice_sent` is false there, so the CTA ladder reaches the notice rung. It was **mislabelled**, not missing. See §4 |

### The flow map (it had moved twice since the prompt's snapshot)

- **notice**: `POST /load/{stop}/notice` → pre-detention warning (own column, no evidence
  event) → else start notice → the wedge session's five-case resend rule → the route
  appends `notice_sent` only when `sent AND fresh AND not warned`.
- **share**: `m3.generate_pack` → accrue → anchor → compose (verification computed) →
  render → `share_pack` (pin + token + `pack_shared`) → `_notice_body(link)` → email.
- **open**: `GET /pack/s/{token}` → `open_share` → metadata (+ `pack_opened`, until now).

### Routes pinned
extend `POST /protection/share/{id}/extend` · revoke `DELETE /protection/share/{id}` ·
**list: did not exist** → D8 added `GET /protection/share?log_ref=`.

### Numeric payload readers (for D5's coerce branch)
`render.py:_located_points` (`payload["lat"]/["lon"]`), `render.py` artifact `gps`,
`service.py` composing `gps` from artifact columns. Not needed — see §2.

### Gates

| | Baseline (T1) | Final | |
|---|---|---|---|
| pytest | 1714 | **1766** | +52 |
| vitest | 769 (42 files) | **777 (43)** | +8 |
| layout | 289 | **289** | unchanged |
| ruff + import-linter | clean · 30/30 | **clean · 30/30** | |

---

## 2. The D5 probe verdict: **STABLE** → the probe *is* the fix

18 adversarial floats written through real Postgres and re-verified: long fractions,
`0.1 + 0.2`, `1e-7`, `1e16`, float max, the smallest subnormal, **negative zero**,
17-digit values, `2.675`. All verify. `_canonical` is untouched, so every existing record
verifies exactly as before, and the corpus is now a permanent test that goes red the day a
dependency upgrade or a column-type change breaks the assumption.

**The probe's own honesty took two attempts, and that is the useful part.** The first
version used `db.expire_all()` to force a re-read — and a revert-check showed that deleting
it changed nothing, because SQLAlchemy can serve the payload from the identity map and
never ask Postgres at all. Every test would have passed while testing nothing. The guard
now reads the stored JSONB back with **raw SQL**, bypassing the ORM entirely, and
sabotaging that stored value turns it red. Verified by doing exactly that.

---

## 3. Task status

| Task | Status |
|---|---|
| T1 Verify, map, probe | CLOSED |
| T2 The chain checks itself (D2+D4) | CLOSED |
| T3 Broken packs don't travel (D3) | CLOSED |
| T4 Nothing false about the record (D1+D5) | CLOSED |
| T5 The basis and the words (D6+D7) | CLOSED |
| T6 The driver's side (D8) | CLOSED — **except screenshots**, see below |
| T7 Finish line | CLOSED |

**T6's screenshots were not taken.** The three states (shares list, failed-with-Send-again,
the D3 blocked state) are covered by component tests and the layout suite is green, but the
`OBSERVE_SHOTS` spec was not extended. That is an unfinished piece of T6's acceptance,
recorded rather than glossed: the work is one spec addition following the pattern the
wedge session established, and nothing blocks it.

---

## 4. What the findings turned out to be

**F4-3 was the worst of them.** The render has printed "HASH CHAIN BROKEN — do not rely on
this pack" since it was written, and nothing stopped that PDF being pinned, given a link,
and emailed to a broker under the driver's name. The document said *do not rely on me* and
the product sent it anyway. The gate is at `share_pack`, the chokepoint M3, M5 and A1 all
cross, so one check covers three modules and any fourth that arrives.

**F4-2's anchor gap is subtle and total.** Everything `verify_chain` did was recompute
hashes from the records — and self-consistency is exactly what a competent rewrite
produces. Doctor a payload, re-link every record after it, and every check passed. The
anchor is the one row a rewriter cannot fix from inside the table.

**The `pack_opened` append was a claim about a person.** Mail-security scanners prefetch
links before a human sees the mail, and Starlette runs handlers for HEAD — so the chain was
immortalising automated fetches as human acts, and later packs carried "they opened it" to
the broker. In an append-only log that cannot be withdrawn.

**The carried finding did not reproduce.** The `failed`-state control was present all
along; it read "Send notice" to a driver who had already tapped it and watched it fail.
Fixed as wording, not as an affordance — and `retrying` deliberately keeps the plain
wording, because the sweep owns that row and tapping produces no new message.

**"GPS-verified" was in the module's own docstring too**, which the grep test caught. A
phrase the code repeats to its next reader is how it gets back into a string a broker sees.

---

## 5. Decisions under §3 authority

| Decision | Reasoning |
|---|---|
| **The gate lives in `share_pack`, not in each caller** | One chokepoint covers M3, M5 and A1. Callers translate; F4 refuses. |
| **Dunning does NOT raise on a refused pack** | The invoice is owed either way, so the chaser still goes — it simply carries no link rather than a link to a pack that failed its own check. Raising would silence a legitimate follow-up. |
| **The claim stays `open` when the pack is refused** | Marking it filed over a document nobody received would freeze the Meter on money never claimed. |
| **409, not 500, at all three routes** | The request is fine; the evidence is not. |
| **ERROR log, no second alert channel** | A12 has exactly one and adding another is an owner decision — stated in an `AI-CONTEXT` at the log site, and in §6. |
| **`anchor_mismatch` is its own reason, not `tampered`** | They mean different things to whoever reads the PDF: one says a record disagrees with its own hash, the other says the records agree with each other and disagree with what we recorded earlier. |
| **Only the latest anchor is cross-checked** | An older anchor legitimately describes a shorter chain; checking all of them would fail every log that was anchored and then appended to — which is every log this product makes. |
| **One retry on append, not a loop** | The second read sees a committed head. A third collision would mean sustained parallel writers on one stop's log, which a loop would hide. |
| **The basis section is supplied via `PackContext`** | F4 may not reach sideways to F3. `None` omits the section rather than inventing an answer. |
| **`IMPLAUSIBLE_SPEED_MPS` is a constant, not an F13 knob** | It labels a report; last session's two knobs gate a clock. Change this and a PDF line reads differently and not one cent moves. |
| **The grep test checks whole files, comments included** | It caught the module docstring, which is how the phrase would have returned. |
| **The module docstring was re-phrased** | Beyond D7's literal scope (counterparty artifacts + driver catalogues), but it is the same overclaim and leaving it would have meant teaching the test to ignore it. |

---

## 6. Revert-checks

| # | Reverted | Went red |
|---|---|---|
| T2-a | The anchor cross-check | `test_a_consistently_rewritten_chain_no_longer_passes` |
| T2-b | Provenance collapsed to "a row exists" | `test_an_internal_only_anchor_does_not_claim_an_external_timestamp` |
| T2-c | The append retry | `test_two_racing_appends_both_survive_with_consecutive_seqs` — **second attempt** |
| T3 | The `share_pack` gate | the three broken-chain tests |
| T4-a | The `pack_opened` append restored | `test_the_share_is_in_the_chain_and_the_open_is_not` |
| T4-b | The probe's stored value sabotaged | `test_the_probe_is_not_vacuous` — **second attempt** |
| T5-a | The basis section removed | the two basis render tests |
| T5-b | Honest absence collapsed to zeros | `test_a_pack_with_no_trail_says_so_and_asserts_nothing` |
| T6-a | The revoke wiring | `test_revokes_a_link_and_shows_it_as_revoked` |
| T6-b | The failed-state framing | `test_says_Send_again_not_Send_notice` |
| D7 | (the grep test is its own revert-check) | — |

**Two needed a second attempt, both for the same reason: the test wasn't exercising the
thing.** The race test planted the winner and called append in the same session, so the
head read already saw it and no collision happened. The probe leaned on `expire_all()`,
which the identity map made irrelevant. Fifth consecutive session in which a revert-check
has caught a test proving nothing — the practice is earning its cost.

---

## 7. Self-review

- **No history mutated.** Checked by grepping the app-code diff for writes to
  `record_hash` / `prev_hash` / `seq` / `payload` / `head_hash` / `storage.put` / `delete(`.
  Two hits, both benign: a local variable inside `append_record` computing a hash for a
  **new** row, and a read comparison in the cross-check. Legacy `pack_opened` records are
  untouched and render with a caveated label.
- **No migration files**, **no `.env`**, **no real addresses** (all `@*.example`).
- **One removed assertion**: `events.count("pack_opened") == 1` — the test D1 explicitly
  replaces, per §2.5, with one asserting the share is chained and the open is not.
- **Six-locale parity**: 1038 keys in each of the six files, no blanks.

---

## 8. Follow-ups

1. **External anchoring — the owner's decision, with two options.** Every anchor this
   product writes is internal; the PDF now says so rather than claiming a third-party
   timestamp. The two ways to make "Anchored: yes" true:
   - **An OpenTimestamps-style calendar.** Publishes a commitment to a public blockchain;
     verification is independent of us forever, and free. Costs: an outbound dependency at
     anchor time, confirmation latency measured in hours, and an explanation a broker's
     clerk will not have heard of.
   - **A signed daily digest to an owner-controlled archive.** Sign the day's chain heads
     and deposit them somewhere append-only (object storage with retention lock). Simpler,
     instant, no third party to explain — but the attestation is still *ours*, so it
     answers "did we alter this later" and not "was it us all along".
   The first is stronger evidence; the second is stronger operationally. Neither is
   activated, and the render is honest until one is.
2. **Client mock-location capture.** Android and iOS both expose a mock-provider flag and
   the client does not read it. That, plus teleport detection at capture time, is what
   would let the basis section say something about *how* a fix was produced rather than
   only how it looked. The F4-session item this session deliberately left alone.
3. **The alert-channel decision.** A refused pack logs at ERROR and nothing else. A12 has
   one alert channel; whether evidence failures deserve it is the owner's call.
4. **T6's screenshots** (§3).
5. **`compose_grouped_pack` verification.** The grouped/multi-stop composers merge
   `anchored` across parts with `any(...)`; the cross-check runs per log, so a grouped pack
   is as strong as its weakest part but reports optimistically on provenance. Not touched —
   no caller ships a grouped pack to a counterparty today.
6. **The two f03 knobs remain off**, still the owner's, unchanged by this session.
