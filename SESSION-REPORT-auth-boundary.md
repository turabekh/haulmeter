# SESSION-REPORT — auth boundary integrity

2026-08-11 · branch `main` · nothing pushed, nothing deployed, stack left running.
Baseline commit `11c12c1`; six commits. Fifth of five; the prior four reports are unmodified.

**No `.env` change. No control weakened. No access widened. No retroactive enforcement.
No seed broken — verified by registering and signing in with each one.**

---

## 1. T1 verification — every finding REPRODUCES

Greps were uncapped and counted, per the brief's warning about the review's own first pass.

| ID | Evidence |
|---|---|
| **F1-1** | `AuthSession` appears 10× in `service.py`; **0×** inside `complete_credential_change`, **0×** inside `reset_credential`. `deactivate_account` loops and deletes, with a comment naming the exact 30-day consequence — the rule was known, understood, and applied to one site of three |
| **F1-2** | `grep -rn logout app/api/` → **0 matches**. No route at all; the only revocation anywhere was the impersonation path |
| **F1-3** | `grep -rn needs_rehash app/` → **2 matches, both its own definition**. Not exported, not called. Argon2 parameters could never rise for an existing account |
| **F1-6** | `register(body, db)` took no `Request` → could not throttle by IP even in principle; `build_secret_ref` → `hash_password` with no slot |
| **F1-7** | `/register` answered 409 unconditionally and for free |
| **F1-8** | No floor anywhere; `RegisterIn.password: str` |

### Pinned facts

**Every seed and bootstrap password clears a floor of 8 — measured before the number was
picked, not after:** `pw-123456` (9), `longhaul-dev-1` (14), `longhaul-admin-dev` (18),
and `_temp_password()` = `token_urlsafe(9)` (≥12 by construction). Re-verified at T7 by
registering and authenticating with each.

**Exactly one test registration was under the floor** — `test_dunning.py` used `pw-1234`
(7), written by me in an earlier session. Raised to `pw-12345` rather than lowering the
floor, per §2.1.

**Routes reaching a hashing call:** `/auth/register`, `/auth/login`, `POST /admin/accounts`
(which hashes **twice** — register + reset), `POST /admin/accounts/{id}/reset-credential`.
`VerifierBusy` was translated in exactly **one** of them.

**`complete_credential_change` has no HTTP route** — only tests call it. So D1's wiring
there is correct in advance of a caller, and the *absence of a driver-facing
change-password endpoint* is itself a gap (§6).

### Gates

| | Baseline (T1) | Final | |
|---|---|---|---|
| pytest | 1766 | **1799** | +33 |
| vitest | 777 (43 files) | **783 (44)** | +6 |
| layout | 289 | **289** | unchanged |
| ruff + import-linter | clean · 30/30 | **clean · 30/30** | |

---

## 2. Task status

| Task | Status |
|---|---|
| T1 Verify and baseline | CLOSED |
| T2 Migration (0069) | CLOSED |
| T3 Sessions that end (D1) | CLOSED |
| T4 Logout (D2) | CLOSED |
| T5 Bounded hashing, throttled registration (D3+D4) | CLOSED |
| T6 A floor, and hashes that age (D6+D7) | CLOSED |
| T7 Finish line | CLOSED |

Nothing BLOCKED.

---

## 3. Revert-checks

| # | Reverted | Went red |
|---|---|---|
| T3-a | The credential-change wiring | 3 tests |
| T3-b | The admin-reset wiring | `..._ends_every_session_with_no_exception` |
| T3-c | The deactivation wiring | `test_deactivation_still_ends_every_session` |
| T3-d | `except_token` honoured | 2 tests |
| T4-a | Route revocation | 3 tests |
| T4-b | The client call made blocking | 4 tests, incl. both offline cases |
| T5-a | Slots removed from `build_secret_ref` | 2 tests |
| T5-b | The two pools merged | `..._does_not_shed_LOGINS` — **second attempt** |
| T5-c | The `kind` discriminator dropped | `..._does_not_lock_anyone_out_of_LOGIN` — **second attempt** |
| T5-d | The registration throttle removed | 5 tests |
| T6-a | The floor at registration | `test_registration_refuses_a_short_password` |
| T6-b | The floor at credential change | `..._credential_change_refuses_a_short_password` |
| T6-c | **Retroactive** enforcement introduced | `test_an_existing_short_password_still_logs_in` |
| T6-d | The rehash made blocking | `..._full_creation_pool_skips_the_upgrade...` |
| T6-e | The rehash removed | `..._upgraded_on_the_next_successful_login` |

### The two that needed a second attempt — same mistake, two disguises

Both were tests that **sidestepped the mechanism they claimed to prove**:

- **The pool merge.** `test_a_registration_flood_does_not_shed_LOGINS` monkeypatched
  `HASH_SLOTS` with a fresh semaphore. A monkeypatch rebinds the **name**; a merge shares
  the **object** — so with `HASH_SLOTS = VERIFY_SLOTS` in source, the substitution left
  verification's permits untouched and the test passed while proving nothing. It now
  **drains the live pool**, which a merge cannot survive.
- **The `kind` discriminator.** The flood ran to `REGISTER_MAX_PER_IP` (10), which sits
  *under* login's per-IP ceiling of 20 — so removing `kind` changed nothing the test could
  see. The flood is now deliberately raised **above** that ceiling, so a shared counter
  bites.

Sixth consecutive session in which a revert-check has caught a test proving nothing. Both
failures here are the same shape as the location session's race and the evidence session's
`expire_all` — the test arranged the *appearance* of the condition rather than the
condition.

---

## 4. Decisions under §3 authority

| Decision | Reasoning |
|---|---|
| **Registration defaults MATCH login's (5 / 20), not tighter** | My first pass used 3 / 10 — rarer action, tighter number. That is numerically stricter than the existing throttle, which §2.1 forbids, and the realistic failure is a **fleet onboarding its drivers from one depot Wi-Fi**, which looks exactly like a script from behind a NAT. **The full suite confirmed it before I could argue it**: two  cases went red under 3 / 10 purely by registering several accounts from one client, and went green at 5 / 20. That is the fleet-onboarding shape, reproduced by accident. Tuning down on evidence is cheap; a lockout is not |
| **`revoke_sessions` expires in place rather than deleting** | `end_impersonation`'s shape. An in-flight request against a deleted row gets a confusing failure where an expired one gives a clean 401 — and a revocation is a security event that should stay legible rather than being a gap where rows used to be |
| **`revoke_sessions_for_token` is scoped to the account too** | The token already resolves to its owner; taking the account as well means a caller cannot end somebody else's session by mistake |
| **The pools moved to `security.py`, re-exported from `service.py`** | They belong beside the operations they bound, and every existing import path keeps working |
| **`auth_methods` resolves the pools through the module** | A live object a test (or a future config path) must be able to substitute — and it is what made the drain-not-substitute test possible |
| **`clear_failed_logins` clears only `kind='login'`** | A successful sign-in says nothing about how many accounts an address has been used to create |
| **The rehash catches `VerifierBusy` and returns False** | The pool is for people signing in; they come first |
| **The floor lives in `register_account`, not the Pydantic model** | `seed_admin` and `admin_create_account` call the service directly — a route-level constraint would have missed both |
| **`admin_create_account` inherits the floor** rather than re-checking | It calls `register_account`; a second check is a second thing to drift |

### Divergences from the prompt

- **Registration defaults raised to match login's** (above) rather than the tighter first
  guess.
- **The existing saturated-verifier test's patch target moved** (§2.3): its assertion is
  unchanged, but the slot is acquired in `PasswordHandler.verify` now, so patching
  `service.VERIFY_SLOTS` no longer reaches it.
- Everything else implemented as written. D5 required no code: the 409 stays.

---

## 5. Self-review

- **No control weakened, none widened.** Login's throttle semantics, `_client_ip`,
  impersonation and the OAuth/OTP seams are untouched — the only appearances of those names
  in the diff are prose and one *use* of the existing `_client_ip` helper.
- **No retroactive lockout**: the floor is checked where a password is set; a revert-check
  introducing it at verification turns the non-retroactivity test red.
- **No seed broken**: all three registered and authenticated successfully at T7.
- **No removed assertions** anywhere in the diff.
- **Six-locale parity**: 1039 keys in each file, no blanks.

---

## 6. Follow-ups

1. **There is no driver-facing change-password endpoint.** `complete_credential_change` is
   reachable only from tests. The revocation wiring is correct in advance, but a driver who
   believes they are compromised still has no way to act on it — the largest remaining gap
   in this area, and the one that makes D1's wiring matter in practice.
2. **"Sign out everywhere" and a session cap** — `revoke_sessions` makes both a few lines
   now (`revoke_sessions(db, account, except_token=current)` behind a route). Deliberately
   not built: it is a product decision about a control drivers will see.
3. **The enumeration oracle is downstream of the owner's verification decision.** The 409
   stays because the honest alternative ("we've emailed you if that address exists")
   requires an email-verification step, and no verification at signup is owner-LOCKED. A
   product that cannot send that email must not imply it did. The throttle makes
   enumeration cost attempts; closing it properly is not a code problem this session can
   solve.
4. **Session tokens are stored in plaintext at rest.** Bearer auth with no CSRF surface and
   the client transmits the token every request, so this is a hardening option rather than
   a finding — but a database read currently yields usable credentials.
5. **`login_attempt` is now two signals under one name.** Not renamed (churn); the docstring
   carries the truth. Worth revisiting if a third signal ever joins.

### A note to the owner — the registration throttle's numbers

**They are a first guess with no traffic behind them.** Nobody has watched real signup
volume, so I set them equal to login's existing limits (5 per identifier, 20 per IP, in a
15-minute sliding window) rather than inventing tighter ones — the failure mode that
worried me is a fleet signing its drivers up from one depot Wi-Fi, which is
indistinguishable from a script at the IP layer.

They are **F13 config keys** (`f01_register_max_per_identifier`, `f01_register_max_per_ip`)
for exactly this reason: once the first weeks of real signups show what normal looks like,
you can tighten them from the admin console **without a deploy**. The direction to tune is
almost certainly down — 20 registrations from one address in fifteen minutes is generous —
but tightening on evidence costs nothing and tightening on a guess can lock out a customer
on their first day.
