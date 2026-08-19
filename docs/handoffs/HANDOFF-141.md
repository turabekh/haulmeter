# HANDOFF-141 — the map goes to sleep, and four dead pointers the kickoff had not seen

A long owner-directed day: **decisions 215–228 and owner decision D21.** The Money tab
grew the half of the pipeline it never showed, the Load tab stopped inventing money over
a finished stop, a driver's own attestation stopped being overruled by a GPS fix, and the
session closed on the map-dormancy flip.

The through-line, again: **the sweeps and the reports were right about the data and wrong
about the verdict.** A parallel audit returned "OBSERVABLE DEFECTS: NONE FOUND" over a
button labelled "Approve & send" whose entire handler was `sent.value = true`. A kickoff
listed the map's dead pointers and missed the one on the sign-in screen.

---

## 1. State at the break

```
prod   alembic 0094_f03_attested_presence · m15_roadside ON · m11_voice ON · m01_map ON (ops flip owed)
prod   Perth Test Dock created at the owner's own coordinates (0 m) — the loop is testable
local  gates 2632 pytest · 1124 vitest · 355/355 layout (18 map states dormant) · 32/32 contracts
local  17 commits unpushed; the map-dormancy slice is committed and NOT deployed
```

**Deployed through entry 227.** The map slice (D21 / 228) is **local only** — §4 of its
kickoff puts deploy out of scope.

## 2. THE OPS STEP THAT IS OWED, AND ITS ORDER

`m01_map` on production reads `enabled = true` — a real operator decision, which correctly
beats the code's new `default_on=False`. So the box still serves the map.

**Deploy the UI first, then flip the flag.** The other order leaves a live Map tab in front
of 404ing endpoints. One toggle in the admin console, or `flags.disable(db, "m01_map")`.

## 3. What the map slice did

Five tabs — Load · Money · Docs · Roadside · More — `/` is `/load`, and `MAP_DORMANT` in
`router.js` is the one greppable switch. **Dormant, not deleted:** every map component and
every one of its tests is still here and still green.

**Four dead pointers §1 of the kickoff had not listed**, each found by grepping rather than
by reading the list:

| where | what it did | disposition |
|---|---|---|
| `AuthSurface.vue:56` | `router.push("/map")` after **every sign-in** | → `push("/")`, so the router owns home |
| `PasswordSurface.vue:63` | the same `voice.unavailable` hint — and the ONLY thing it renders at speed | → `driving.paused`; standing it down would have left a blank screen at 60 mph |
| `roadside-tab.test.js`, `ui-components.test.js` | pinned six tabs and the login destination | updated |
| `layout.spec.js` ×**18** | map states rooted at `/` | skipped by PATH, all 18 named in the run output |
| `BookingSurface.vue:131`, `FuelSurface.vue:125` | done buttons pushing `'/map'` — **single-quoted**, so the double-quoted census missed both | → `push('/')`; found in the shipped bundle after deploy, guarded by a quote-agnostic test |

Left deliberately: **`DevIndexSurface.vue:65`** links `/map` — `/dev` ships only in
development builds (entry 51), it is not driver-visible, and it now lands on `/load`.
**`nav.map` and `voice.unavailable` stay in all six locales** — verified that
`locale-completeness.test.js` does not flag unused keys, so reactivation needs no
translation pass.

## 4. The reactivation recipe

`MAP_DORMANT = false` in `router.js` · `default_on=True` in `m01_map.register_module` (or
just the operator toggle on an existing box) · the `/map` entry back in `TabBar.vue`'s
array with its `Map` lucide import · `MapSurface` back in `App.vue`'s `KeepAlive` include ·
the voice hint back on Load. The tests invert themselves — `map-keepalive`, the SM-3
census and the layout sweep all read `MAP_DORMANT`, so nothing is hand-maintained.

## 5. The rest of the day, in one line each

- **215/216** — the Money tab's empty state had one cause and needed four; **216 corrects
  215**, which generalised from six of fourteen claims.
- **218** — "Approve & send" sent nothing and the next screen said "Sent". Reported to me
  as working.
- **219 + 225** — the Meter restarted its free-time clock on an ended stop, then kept
  accruing over one; both were the owner's "goes back and freezes".
- **220** — geofence exit detection investigated and found **correct**: the driver is in
  Perth, the docks are in America.
- **222** — three write paths failed in silence, including an empty catch on **filing a
  claim**, whose comment described an F12 queue that does not exist.
- **223/224** — food alerts still advertised after the half was switched off; the
  `require_any_module` half-rule is now an enforced test.
- **226** — the Money tab shows the whole pipeline: not sent yet · waiting · paid.
- **227** — an attested arrival is no longer overruled by an impossible fix, **and Perth
  Test Dock exists**.

## 6. For the next session

**The pilot day is still the largest gap between built and validated** — and for the first
time it is unblocked: a facility 0 m from the owner means the detention loop can actually
run. Arm a stop at Perth Test Dock, wait past free time, file, and watch the money land in
"Not sent yet" and then in "Waiting on brokers". **Nothing in this session's Money or Load
work has been seen accruing real money by a real person.**

Open: **N-06** (the server's `arrival or now`, corroborated by entry 107's five live
claims), **N-09** (the North Star renders nowhere), **N-10 PARTIAL**, **N-11** (three
MapSurface timer tests flake under the full parallel run — attempted, reverted, and the
finding carries why a longer wait is not the fix), **N-18** (the promotions route asks the
weak flag question).

Deferred by D21's kickoff, for future D-entries: the `m11_voice` → `m11_ghostwriter` split,
a list-based discovery surface for M6/M7/M13, and the map deletion-vs-return decision,
which is evidence-gated on the pilot.
