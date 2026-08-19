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
prod   alembic 0094_f03_attested_presence · m15_roadside ON · m11_voice ON · m03_detention ON
prod   m01_map OFF — the D21 ops flip is DONE; /api/map/* answers 404
prod   Perth Test Dock at the owner's own location (0 m) — the detention loop is testable
local  gates 2632 pytest · 1125 vitest · 355/355 layout (18 map states dormant) · 32/32 contracts
git    ALL PUSHED — turabekh/haulmeter at 36798ba, 0 unpushed
local  stack DOWN (owner on a break); outbound queue was 0 unsent at shutdown
```

**Everything through entry 228 is deployed, flipped and pushed.** Nothing is outstanding
that a session can do on its own.

## 2. THE OPS FLIP IS DONE — and the order it needed, recorded for next time

`m01_map` carried `enabled = true` on production, a real operator decision that correctly
beat the code's new `default_on=False`, so the code change alone did not switch it off.

**The UI was deployed FIRST, then the flag flipped.** The other order leaves a live Map tab
in front of 404ing endpoints. Verified after: `enabled=false`, `/api/map/overlay` → 404,
`m11_voice` / `m03_detention` / `m15_roadside` untouched, 0 tracebacks, 0 unsent outbound.

**Reversal is one toggle** — `flags.enable(db, "m01_map")` — plus `MAP_DORMANT = false`.

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
| `BookingSurface.vue:131`, `FuelSurface.vue:125` | done buttons pushing `'/map'` — **single-quoted**, so the double-quoted census missed both | → `push('/')`; found in the shipped BUNDLE after deploy, guarded by a quote-agnostic test |

**Six dead pointers in total** — four the kickoff's §1 had not listed, two my own first census
missed. The last two surfaced only because I re-read the shipped bundle instead of trusting
the grep: minification normalises quote style, so `'/map'` and `"/map"` look identical there
and different in source. **A census is only as good as the spelling it assumed**, which is
why the guard is now a test rather than a grep run once.

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


## 7. Two facts about the repo that CLAUDE.md gets wrong

Found while pushing, and both will trip the next session:

- **The repo is PRIVATE, not public.** Rule 3 says "`git push` (github.com/turabekh/haulmeter,
  **public**)" and rule 9 leans on it ("check a diff for secrets before it leaves"). An
  unauthenticated fetch 404s and the push challenged for credentials — it is private.
  The diff-scanning discipline is still right; its stated reason is not.
- **This machine's default GitHub key authenticates as `turaboyenco`, not `turabekh`**, and
  GitHub refuses one key on two accounts. A second key was generated and an SSH alias added
  (`~/.ssh/config`, `Host github-turabekh`); `origin` now points at it, so `git push` works
  with no token and nothing to expire.

## 8. What was published, and what was deliberately coarsened

The 31 unpushed commits carried the owner's device coordinates to ~100 m, labelled as
theirs, in decision entries 220/227 and a test constant. Editing the tip would have left
them in the history that was about to be pushed, so **the unpushed range was rewritten**
(tree and one commit message) before anything left the machine: the prose keeps "Perth,
Western Australia" and every distance, and the test constant is deliberately coarse.
**Verified zero occurrences on the remote.** The emails in the entries were already public
as the commit author and were left alone.
