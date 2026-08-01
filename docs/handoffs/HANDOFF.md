# HANDOFF.md — pointer

This file is a **pointer**, not content. The current state, decisions, per-state
results, exact next task, and blockers always live in the latest numbered handoff:

➡️ **[HANDOFF-110.md](HANDOFF-110.md)** — read this first, every session.

> 110 is the **first session under PRD v2.0** (`docs/trucker-platform-prd-v2-amendment.md`,
> which is now build law alongside the v1.0 PRD). It builds **A5 — Service & repair
> discovery** end to end, and the finding underneath it is the session: **six of the eight
> OSM service rules had never fired once**, because the extract filter never passed the tags
> they read. The registry held 12 repair facilities, 0 tire shops, and **0 phone numbers on
> 4,869 facilities**. The obvious fix — extend the filter — would have produced exactly
> nothing, because a second unmeasured gate rejected all 2,638 candidates.
>
> **Stack is UP · six commits to push · this one NEEDS A DEPLOY (A5 is driver-facing) ·
> `make repair-contact DRY_RUN=0` must run on the box after it · §23 entry 117 is PROPOSED
> and needs the owner's yes/no · A5 has no validation observation and no way to make one
> (§7.2) · a push on a real handset is still the item four sessions old.**
>
> Read 109 for the measured-flake correction and the label test; 108 for the quiet-hours
> file/defer decision; 107 for the quiet-hours inversion; 101 for the detention P0 and the
> anchor rule; 099 §11 for the repo being public.

Each session ends by writing the next `HANDOFF-<n>.md` in this directory and updating
this pointer to it. Full history is here in `docs/handoffs/`; the Session-0 bootstrap
(ports, stack, working rules, target layout) is `HANDOFF-000.md`.
