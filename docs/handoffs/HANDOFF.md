# HANDOFF.md — pointer

This file is a **pointer**, not content. The current state, decisions, per-state
results, exact next task, and blockers always live in the latest numbered handoff:

➡️ **[HANDOFF-105.md](HANDOFF-105.md)** — read this first, every session.

> 105: the lot-status prompt's tray buttons were real and answering with one could never
> send anything — the session token was never written to the IndexedDB the service worker
> reads it from. Its §4 is the one to read: happy-dom implements no IndexedDB, so the
> mirror was a silent no-op in every test that has ever run here. **The deployed box is
> behind this fix.** Read 104 for the prompt itself and the trigger that could not fire;
> 103 for Web Push and the one-shot-prompt reasoning both depend on; 102 for "the events
> were missing, not the notifications"; 101 for the detention P0 and the anchor rule;
> 099 §11 for the repo being public.

Each session ends by writing the next `HANDOFF-<n>.md` in this directory and updating
this pointer to it. Full history is here in `docs/handoffs/`; the Session-0 bootstrap
(ports, stack, working rules, target layout) is `HANDOFF-000.md`.
