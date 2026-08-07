# HANDOFF-118 — the stack came back up, the gates were re-measured, and a file four handoffs promised not to touch is in the public repo

> **Stack DOWN · six commits UNPUSHED · nothing deployed.** haulmeter.online still
> serves 112's code.
>
> A short session with **no source changes**. The owner asked for the stack to be
> restarted, then for a handoff and a shutdown. Both were done, and the four gates were
> **re-measured rather than carried forward** — they hold, identically to 117.
>
> One thing turned up that is not a code defect and not a leak: **`collect_files.py` is
> tracked and pushed.** Four handoffs (089, 098, 099, 117) describe it as untracked and
> deliberately left alone. It was swept into session 113's A6 commit on 2026-08-02 and is
> in the public repo. Left in place — it is the owner's file and the owner's call.

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, **six** commits ahead of `origin/main` — 117's four, 117's handoff commit `79b55dc`, and this file |
| `origin/main` | `113327e` — **carried from 117, NOT re-verified this session** (see §6) |
| This session | no commits but this handoff |
| Gates | **measured today: pytest 1391 · vitest 689 (35 files) · layout 225 checks · import-linter 30/30 · ruff clean** |
| Migrations | none. `alembic current` in the running container → `0059_f13_config_decl (head)` |
| Working tree | clean — and see §4, which is why that line reads differently than it did in 117 |
| Local stack | brought **UP** for the session, **DOWN** at the end at the owner's request |
| Dev data | Tampa `27.9506,-82.4572` intact. `make seed-where` prints it and the four DEV facilities |
| Email | **dev still points at live Gmail** — `smtp.gmail.com:587`, STARTTLS on. Mailpit is up in compose and unaddressed |
| Deploy | **not run.** A6, 114's preset fix, 115, 116 and 117 are all still absent from the box |

## 2. What this session did

Read 117. `make up` — preflight passed, all four images rebuilt (first up since 117 brought
the stack down), seven containers started, no migration ran. Then verified from **outside**
the containers rather than from compose's own opinion of itself:

- `/health` → **200** on 8008; UI → **200** on 9008
- postgres 5438, redis 6438, mailpit 1038/8038, minio 9018/9019 — all bound, all healthy
- `alembic current` → `0059_f13_config_decl (head)`, matching what 117 recorded for both dev and production
- `make seed-where` → origin `27.950600,-82.457200`, four DEV facilities at 88–125 m, geofence radius 150 m

Then the gates, then this file, then `make down`.

## 3. The gates were measured, not inherited

**pytest 1391 · vitest 689 across 35 files · 225 layout checks · 30/30 import-linter
contracts · ruff clean.** Every number is identical to 117's.

That is the expected result and it is worth the four minutes anyway: 117's numbers were
taken in the same session that produced the changes, on a stack that had been up for
hours. These were taken on a cold stack with freshly built images, days later, by a
session with no stake in the answer. Identical is what it should be, and now it is
observed rather than assumed.

**What this does not mean.** Green is not correctness — this project has now been taught
that five separate times, most sharply in 115, where four mechanisms were wrong at once
and the suite was green across all of them. Nothing here revalidates anything; it says
the tree is in the state 117 left it in.

## 4. `collect_files.py` — the record had gone stale

The working-tree line in the table above used to carry a caveat. It no longer does, and
the reason is worth recording rather than silently dropping.

**What the record says.** HANDOFF-089: *"`collect_files.py` sits untracked at the repo
root and is not ours to commit or delete."* HANDOFF-098 and 099 state tables: *"clean
except untracked `collect_files.py` (not mine, left alone)."* HANDOFF-117: *"clean apart
from untracked `collect_files.py` (pre-existing, not mine)."*

**What is true.** It is **tracked.** `git log` puts it in **`9cf9775`** — *feat(a06): the
claim reaches the card a driver calls from*, 2026-08-02, session 113 — alongside thirteen
files that genuinely belong to A6. `git merge-base --is-ancestor 9cf9775 113327e` confirms
it is an ancestor of `origin/main`, so it has been **in the public repo since 113 pushed.**

**What it contains**, read in full before saying any of this: 79 lines, no imports beyond
`os` and `sys`. It walks a directory, concatenates files matching a fixed extension tuple,
and prints them or writes them to a path given as `argv[2]`. No network, no credentials, no
write outside its output argument. Nothing in the repo imports or references it. It sits
outside `api/`, so ruff and import-linter have never seen it and never will.

**So this is not a leak and not a defect.** It is a `git add`-shaped accident: a file that
four handoffs explicitly promised to leave alone got swept into a feature commit, and every
state table since has described a working tree that does not exist.

One property of it is worth stating now that it ships publicly. Its `EXTENSIONS` tuple
includes `.example`, and `SKIP_DIRS` does not exclude `infra/`. Pointed at the repo root it
**will** read `infra/.env.example` — committed, safe — and will **not** read `infra/.env`,
which matches no extension in the tuple. The accident is therefore not one keystroke away
from dumping the live Gmail App Password into a paste buffer. That is luck, not design, and
it is luck that only holds while nobody adds `.env` or `.json` to that tuple.

**Not deleted, not ignored.** 089's rule was that this file is not ours to commit or
delete. Half of that has already been broken by accident; that is not a licence to break
the other half on purpose. Three options, all the owner's: leave it, `git rm --cached` it
and add a `.gitignore` line, or keep it deliberately and let it be a tool of the repo.

## 5. Exact next task

Unchanged from 117 — nothing this session did could move any of it.

1. **The handset background-sensor test** (v2.0 DoD #8), now ten-plus sessions old.
   Whether `/location/ping` fires unprompted while the app is backgrounded, screen off,
   over hours, **has still never been observed by anyone.** A desktop tab cannot answer it.
2. **Push, then decide on deploying.** A deploy needs production `SMTP_*` added to
   `infra/.env` on the VM — `deploy.sh:46` deliberately never ships it. Without it the box
   runs `SMTP_HOST` unset, falls back to the recording gateway, and is exactly where 116
   started. The box has none of 113–117, so production email needs the deploy before it
   needs the credentials.
3. **Two owner decisions still open, untouched:** claim-on-EXIT one-tap, and
   `register_flag`'s gate bypass (114 §7 — F13's central promise going unenforced).
4. **New, small, and the owner's:** what happens to `collect_files.py` (§4).
5. Then the v2.0 board, which has not moved: **A2←D5 · A4←D3 · A7←D1 · A8←D7 · A10←D4**,
   A11 gated on A2, all seven decisions D1–D7 open.

**Phase DoD: 2 of 8**, unchanged. Item 1 is still blocked only on a driver who is not the
owner.

## 6. What I did NOT do

- **No source file changed. Nothing pushed. Nothing deployed.**
- **`git fetch` did not run** — it failed with *"could not read Username for
  'https://github.com'"*, there being no GitHub credential in this environment. So
  *"five commits ahead of `113327e`"* is arithmetic against the last-known local ref, not
  a fresh observation. If anything was pushed to `main` from elsewhere since 117 fetched,
  this file does not know it. **Re-fetch before pushing.**
- **The box was never contacted.** *"haulmeter.online still serves 112"* is carried from
  117 and is unverified here.
- **ON_SITE still has not been walked in a browser.** 117 §7 flagged that distinction as
  load-bearing given what that session found; the stack was up for several minutes today
  and I did not spend them closing it, because the ask was a restart, not a walkthrough.
  The recipe is in §7 below and takes about two minutes.
- **`collect_files.py` was not deleted, untracked, or ignored** (§4).
- **Nothing decides what happens when Gmail is down or over quota** (117 §7). The gateway
  still swallows the failure by design, records `smtp-failed-*`, retries nothing, and tells
  nobody; free Gmail still caps near 500 recipients/day.
- **`StubNotificationGateway` (SMS) and `StubPaymentGateway` (F7) are still untouched** and
  should still be assumed inert until someone watches one work. After five inert engines,
  the prior is inert-until-observed, not correct-until-doubted.
- **The plain-language copy pass is still not done** (117 §7) — structure was fixed at the
  dock, vocabulary was not.
- **No layout-harness coverage for the new photos CTA** (117 §5), and the harness's wrong
  geolocation comment (116 §6) is still in place.

## 7. Restarting

```
make up                              # preflight, then the full stack
make seed-where                      # the Tampa origin is still seeded — paste into Sensors
make test                            # 1391 pytest + 689 vitest — do NOT pipe it
make lint                            # ruff + import-linter (30 contracts)
make ui-layout                       # 225 checks, ~3.3 min
make down                            # stop everything
```

`infra/.env` carries the live Gmail block; it is gitignored and has never been committed.
**A send from dev is a real send** — recipients are pre-filled and editable, so a live
broker address typed into a test load emails an actual broker. Seeded `@bolt.example`
counterparties are safe; that TLD does not resolve. To put dev back on Mailpit for a
session where you want to read message bodies quickly: `SMTP_HOST=mailpit`,
`SMTP_PORT=1038`, `SMTP_STARTTLS=false`, then recreate the api container.

To see the dock behaviour without a phone — the walkthrough §6 says nobody has done:
create a load at the DEV shipper with Free time 2, tap **I've arrived**, and the Primary
should read **"Take cargo photos 0/4"**. Reload the tab; it must come back within one ping.
That reload is the whole of 117 §3 — an edge is a fact about a moment, a state has to be
askable at any moment.

Nothing is waiting on a background job, an ingest, or a queue.
