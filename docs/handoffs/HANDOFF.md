# HANDOFF.md — pointer

This file is a **pointer**, not content. The current state, decisions, per-state
results, exact next task, and blockers always live in the latest numbered handoff:

➡️ **[HANDOFF-111.md](HANDOFF-111.md)** — read this first, every session.

> 110 and 111 are one working session, the first under **PRD v2.0**
> (`docs/trucker-platform-prd-v2-amendment.md`, now build law beside the v1.0 PRD).
>
> **110** builds **A5 — Service & repair discovery**, and the finding underneath it is the
> session: **six of the eight OSM service rules had never fired once**, because the extract
> filter never passed the tags they read. 12 repair facilities, 0 tire shops, and **0 phone
> numbers on 4,869 facilities**. The obvious fix would have produced exactly nothing.
>
> **111** takes the owner's delegation of **design-prd rule 6** (agents may now dispose as
> well as propose — §23 entry 118, with two carve-outs) and builds **A12 — Operational
> floor**: offsite nightly backups, a **restore that is performed and verified** (v2.0 §7
> item 7, satisfied), an alert that lives outside the box, and a snapshot identifier so
> "what is the box running" has an answer.
>
> **Stack UP · everything pushed and deployed · haulmeter.online CURRENT.**
> **ONE THING NEEDS THE OWNER'S EYES: did the test alert email arrive? (111 §5.)** Until
> that is answered the alerting half of A12 is decorative. A5 and A12 are both still
> unvalidated under v2.0 §2 — no driver has used either. A push on a real handset is now
> five sessions old.
>
> Read 110 for the starved rules and the A5 measurements; 109 for the measured flake; 108
> for the quiet-hours decision; 099 §11 for the repo being public.

Each session ends by writing the next `HANDOFF-<n>.md` in this directory and updating
this pointer to it. Full history is here in `docs/handoffs/`; the Session-0 bootstrap
(ports, stack, working rules, target layout) is `HANDOFF-000.md`.
