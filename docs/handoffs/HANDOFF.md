# HANDOFF.md — pointer

This file is a **pointer**, not content. The current state, decisions, per-state
results, exact next task, and blockers always live in the latest numbered handoff:

➡️ **[HANDOFF-112.md](HANDOFF-112.md)** — read this first, every session.

> **112** finishes **A1 requirement 1 — the capture checklist**, and the finding underneath
> it is that the requirement's own last clause was the hard part: "the checklist is
> configuration (F13), not code" was true in the code and **false in every interface an
> operator has**. `a01.capture_checklist` is the first config key any component in this
> product reads, and `/admin/config` listed only keys somebody had already set.
>
> **112 is pushed and deployed · haulmeter.online CURRENT at `0059_f13_config_decl`**,
> verified against the box, with the backup restored and verified at the new schema.
> **The local stack is DOWN** (owner on a break) — `make up` restores it; production is
> untouched and serving.
>
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
> **A12 is COMPLETE and validated** — restore performed and verified, alert fired
> deliberately and the owner confirmed it arrived. All nine covered states were re-extracted
> through the corrected filter: **repair facilities 12 → 458, callable phones 0 → 807.**
> **A5 is still unvalidated** — no driver who is not the owner has used it. A push on a real
> handset is five sessions old.
>
> Read 110 for the starved rules and the A5 measurements; 109 for the measured flake; 108
> for the quiet-hours decision; 099 §11 for the repo being public.

Each session ends by writing the next `HANDOFF-<n>.md` in this directory and updating
this pointer to it. Full history is here in `docs/handoffs/`; the Session-0 bootstrap
(ports, stack, working rules, target layout) is `HANDOFF-000.md`.
