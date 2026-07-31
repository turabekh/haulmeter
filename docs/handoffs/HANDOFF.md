# HANDOFF.md — pointer

This file is a **pointer**, not content. The current state, decisions, per-state
results, exact next task, and blockers always live in the latest numbered handoff:

➡️ **[HANDOFF-109.md](HANDOFF-109.md)** — read this first, every session.

> 109 closes 108's deploy: **the box is CURRENT** and no longer tells drivers "Held
> until morning" about notifications that never arrive. It also **corrects 108 §5** —
> the map states' `ready` budget was never marginal (the slowest `ready` in the whole
> 181-state sweep is **80 ms** against 15 s), so the raise it proposed would have
> buried a real failure rather than fixed a flake; a timeout there now names its own
> cause. And it closes 108 §8's label-shape test, which turned up a **fourth** copy of
> the retired "quiet hours defer" claim in the test file for that very feature.
>
> **Stack is DOWN · two local commits to push (no deploy needed) · the one thing still
> needing the owner's hands is a push on a real handset** (§7.1).
>
> Read 108 for the quiet-hours file/defer decision and the copy correction; 107 for the
> quiet-hours inversion and the per-zone table; 106 for the prompt's opt-in; 105 for the
> token the tray answer never had; 104 for the trigger that could not fire; 103 for Web
> Push and the one-shot-prompt reasoning; 102 for "the events were missing, not the
> notifications"; 101 for the detention P0 and the anchor rule; 099 §11 for the repo
> being public.

Each session ends by writing the next `HANDOFF-<n>.md` in this directory and updating
this pointer to it. Full history is here in `docs/handoffs/`; the Session-0 bootstrap
(ports, stack, working rules, target layout) is `HANDOFF-000.md`.
