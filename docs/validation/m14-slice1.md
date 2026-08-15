# M14 slice 1 — validation log

**Living checklist. The slice is BUILT; none of the four below has happened yet.**

PRD Extension E2's law, and v2.0's: *done = a paying party used it and the outcome is in
the database*. Everything in this file is the world, not the suite — the test suite is
green and proves nothing on this page.

**Nothing is ticked by a session.** A session may add an OBSERVED row with its evidence;
whether that clears a line is the owner's reading.

---

## The four

| # | Gate | State | What would clear it |
|---|---|---|---|
| 1 | **A real fleet's key is pasted and traces flow** | ☐ open | A fleet that is not the owner's completes `make m14-onboard`, and `pings_imported` for its connector is non-zero |
| 2 | **±3 min on ≥10 stops** | ☐ open | `make m14-validate` reports "is MET" — ten measured stops, zero failures, ground truth from a gate log / receiver sheet / driver's word, never the provider |
| 3 | **One ELD-derived claim reaches a broker** | ☐ open | draft → fleet-admin approve → **a real email that really left the box** → the broker has it |
| 4 | **Paid, and the fee is in the ledger** | ☐ open | The receivable moves to `recovered` and the platform fee posts. **This is Phase DoD #3** — the product's unproven central claim since v1.0 |

**Blocked on the owner, not on code:** #3 and #4 cannot start until **D13** has an answer.
`carrier_invoicing_counsel` and M3's inherited `legal_signoff` are both unsatisfied, so
`can_send` refuses in code and the approvals panel says so before an admin approves. One
counsel engagement clears both.

---

## How to record a run

Paste `make m14-validate` output straight in under a dated heading. It is formatted for it.

```
make m14-onboard  FLEET=<uuid>                     # ≤15 min, on the call
make m14-validate FLEET=<uuid> FILE=ground-truth.csv
```

`ground-truth.csv` — `stop_ref,arrived_at,departed_at,source,note`, ISO-8601 timestamps.
**`source` is required and may not name the provider.** Motive validating Motive proves
only that the poller copies faithfully, so the refusal is in code rather than in a note
here: `gate_log`, `receiver_sheet` or `driver` (weakest, and the report labels it).

---

## Observed so far

### 2026-08-15 · session 127 · production deploy — INERT, as intended

Slice 1 is on `haulmeter.online` and refusing to act, which is the whole point of this
entry. Verified by querying the box, never by reading an exit line:

```
alembic_head                     0080_m14_held_claim
f03.source col                   1        f04.evidence_class col   1
m14 tables                       4
pings backfilled 'device'        476 / 476
packs backfilled 'phone_verified' 51 / 51
m14_overlay enabled              NULL — no decision
m14_overlay default_on           false
m14 gates                        legal_signoff=false, carrier_invoicing_counsel=false
held_claim rows                  0        connector rows           0
```

And the refusal itself, run on the box:

```
m14_overlay is_enabled : False
can_activate           : False
can_send               : False | blocked by: legal_signoff
```

`M14_CONNECTOR_KEY` is installed on the VM (0600 root:root, distinct from dev) and
encryption round-tripped against a throwaway connector row, which was then deleted.

### 2026-08-15 · the provider endpoints are REACHABLE

Not a validation line, but worth recording because it is the first contact with the real
provider. `make m14-onboard` against a deliberately fake key reached
`api.gomotive.com` and got a genuine **401 Unauthorized** from both `/v1/vehicles` and
`/v3/vehicle_locations`. So the base URL, the paths, TLS and the auth header all work; what
is still unproven is the **response shape** on a 200, which only a real key can show.

**`/v1/vehicles` is the one call in the module never exercised against a real response.**
The onboarding script falls back to `/v3/vehicle_locations` — the endpoint the poller is
known to work against — if it fails or returns nothing.
