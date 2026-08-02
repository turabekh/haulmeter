# HANDOFF.md — pointer

This file is a **pointer**, not content. The current state, decisions, per-state
results, exact next task, and blockers always live in the latest numbered handoff:

➡️ **[HANDOFF-113.md](HANDOFF-113.md)** — read this first, every session.

> **113** builds **A6 — service-center vendors**, the only Group-2 requirement with no
> owner decision in front of it. The requirement asked for one thing (split `m13_vendor`
> so the food half can be deferred while repair shops run); two more were underneath it.
>
> **The shared endpoints made the split a label rather than a gate** — `/vendors/{id}`,
> review, report and confirm all take a `vendor_id`, and a `vendor_id` carries its half
> with it, so a deferred cook's whole sheet stayed readable. And **claiming was improving
> `/facility/<id>` while A6's own validation happens on the map card**: a shop could claim
> its site, enter the number it answers, and a driver tapping that pin still saw the OSM
> number — or, for 28 of 45 repair facilities, no call action at all.
>
> **Stack UP · three commits on local `main`, NOTHING pushed and NOTHING deployed.**
> haulmeter.online is still serving 112's code. **A6's validation is unmet by design** —
> it needs a real repair shop to claim a facility and take a call.
>
> 113 also carries an F13 fix with nothing to do with A6: **a flag's description was
> frozen after first boot**, so every box still called the food half "M13 Vendor Network".
> It refreshes now; `enabled` deliberately does not.
>
> **112** finishes **A1 requirement 1 — the capture checklist**, and the finding underneath
> it is that the requirement's own last clause was the hard part: "the checklist is
> configuration (F13), not code" was true in the code and **false in every interface an
> operator has**. `a01.capture_checklist` is the first config key any component in this
> product reads, and `/admin/config` listed only keys somebody had already set.
>
> *(112, still the deployed state)* **112 is pushed and deployed · haulmeter.online CURRENT at `0059_f13_config_decl`**,
> verified against the box, with the backup restored and verified at the new schema.
> (112 ended with the local stack down; 113 brought it back up and it is up now.)
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
