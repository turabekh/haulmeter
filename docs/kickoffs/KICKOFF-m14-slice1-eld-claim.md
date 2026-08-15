# KICKOFF — M14 slice 1: one ELD-derived detention claim, end to end

> **This file is a STUB, and says so rather than pretending otherwise.** The full kickoff
> was delivered to the session in the prompt and was never written to the tree; PRD
> Extension E2 and the D8 log entry both reference it by this name, so the name exists here
> with the corrections that matter. Reproducing the owner's document from a transcript
> would put a paraphrase in the repo under a title that claims to be the original.
>
> **The slice it scopes is BUILT** — see `docs/handoffs/HANDOFF-127.md` and §23 of
> `design-prd.md`. Its validation is open: `docs/validation/m14-slice1.md`.

---

## CORRECTION — the F-01 precondition in the original is STALE

The kickoff's **Precondition 3** reads:

> *"F-01 status is known. Production email goes to Mailpit on the VM until the owner's
> `.env` edit."*

**That was true when the kickoff was written and is false now.** F-01 was closed in
session 124: the SMTP block was placed on the VM with the owner's authorization and
production has sent real mail with a real Gmail Message-ID since. Verified again at the
start of session 127 — the box has `SMTP_HOST=smtp.gmail.com`, not `mailpit`.

**This raises the stakes rather than lowering them, and the direction is what matters.**
The kickoff treated F-01 as a thing blocking validation. It is now the opposite: a
guard that no longer exists. Dev and production both point at the same live Gmail
account, so **every environment is live-fire for email**.

**Owner decision, 2026-08-15: Gmail stays as the SMTP target in every environment.** The
owner has weighed this and accepted it. No session may "helpfully" restore Mailpit, add an
environment guard, or change SMTP configuration as a tidy-up — that would be reversing a
decision as a drift. What binds instead is behavioural and permanent:

> Any action that could trigger a send — approving a claim, exercising a notification
> path, running a demo — is production-grade wherever it runs. Nothing is ever addressed
> to an inbox the owner does not control, in any environment.

---

## The order the session actually followed

The kickoff's six steps, and where each landed:

| Step | Outcome |
|---|---|
| 0 · re-grep the seams | All three claims confirmed on the tree; `evaluate_ping` is account-centric, M3 arms through `f05.arm_stop` alone |
| 1 · scaffold, flag, contract | `m14_recovery`; **import-linter 31/31 in the first commit**; `m14_overlay` with no `default_on` |
| 2 · migrations | `0078` (f03 `source`, f04 `evidence_class`), `0079` (m14 schema), `0080` (`held_claim`) — additive, backfilled, apply→downgrade→re-apply verified by query |
| 3 · connector + poller | Worker job at 60 s behind the flag; fake mirrors the provider's nulls; `make m14-poll-once` |
| **4 · prove events fire** | **ENTER / DWELL_TICK×3 / EXIT from `source='eld:motive'`.** First run returned ZERO events over six correctly-ingested pings — swapped coordinates. A unit test would not have caught it |
| 5 · draft, hold, approve | Drafts through `m03.start_claim`, holds unconditionally, approve records the decision and the gate refuses the send |
| 6 · evidence-class wording | Written first, watched fail twice, then green |

## What the original got right, and it is worth keeping

> *"ELD traces that provably produce ENTER/EXIT are a complete increment; a half-built
> claim path that can reach a send button is a hazard, not progress."*

The session stopped at step 4 on the first pass and shipped it. Steps 5–6 followed in a
second commit once there was time to do them whole.

> *"A deferral that cannot fail is indistinguishable from a finished feature."*

This is why `make m14-poll-once` exists: the connector's proof against the real provider
is a human running a command with a real key, not a green suite over a fake.
