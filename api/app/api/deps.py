"""AI-CONTEXT: HTTP API layer dependencies. This package (app.api) is the
presentation/composition layer ABOVE modules — it may import module and
foundation public interfaces (never their internals; core/UI split keeps
app.core clean). Auth is F1 session tokens (email/password at launch, no
activation); the pluggable auth registry means OAuth/OTP slot in later without
touching this dependency.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f13_flags import public as flags


def get_db() -> Iterator[Session]:
    yield from get_session()


def canonical_facility_id(
    facility_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> uuid.UUID:
    """AI-CONTEXT: a merged facility_id resolves to the site it was merged INTO,
    everywhere, before any module sees it.

    A merge does not delete the duplicate — that is deliberate, so an id a driver
    already holds keeps working — but nothing on the READ side resolved it, so it
    "kept working" by answering with the shadow. `GET /public/facility/<merged>`
    returned the absorbed pump ("Pilot", fuel_station) rather than the site it now
    belongs to ("Flying J Travel Center", truck_stop), and the write paths were worse:
    a crowd report against a merged id returned a submission_id and wrote a belief
    onto a facility that no longer renders, so the driver was told their report landed
    and no one would ever see it. §11.7 forbids exactly that — an absence dressed as
    a result.

    Applied at the API layer rather than inside each module because the id is the
    thing that needs correcting, not the object: most callers pass the UUID on to
    tables of their own keyed by facility_id. 678 rows are merged today (239 from the
    scales repair, 439 from the fuel one) and `/admin/facilities/{id}/merge` makes
    more, so this cannot be a one-off backfill.

    Unknown ids pass through untouched — resolution is not existence, and each route
    still answers 404 in its own words.
    """
    resolved = facility.resolve_canonical(db, facility_id)
    return resolved.id if resolved is not None else facility_id


def bearer_token(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    return authorization[len("Bearer ") :]


def current_account(
    token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
) -> identity.Account:
    """Ordinary authentication. An IMPERSONATION token resolves to nothing here
    (F1 `resolve_session` refuses it), which is what structurally prevents a
    "view as vendor" session from reaching a driver endpoint — E-D5 approves
    impersonating vendors only, and this is where "only" is enforced."""
    account = identity.resolve_session(db, token)
    if account is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired session")
    return account


@dataclass
class PortalActor:
    """Who is acting, and whose portal they are in. For an ordinary vendor session
    the two are the same account. Under impersonation `actor` is the ADMIN and
    `subject` is the vendor — reads scope to the subject so the screen matches what
    the vendor sees, while every write attributes to the actor."""

    actor: identity.Account
    subject: identity.Account
    impersonated: bool

    @property
    def attribution(self) -> identity.Account:
        return self.actor


def portal_actor(
    token: str = Depends(bearer_token),
    db: Session = Depends(get_db),
) -> PortalActor:
    impersonation = identity.resolve_impersonation(db, token)
    if impersonation is not None:
        actor, subject = impersonation
        return PortalActor(actor=actor, subject=subject, impersonated=True)
    account = identity.resolve_session(db, token)
    if account is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired session")
    return PortalActor(actor=account, subject=account, impersonated=False)


def require_module(flag_key: str):
    """AI-CONTEXT: PRD §6's gate, as a router dependency (§23 entry 105).

    **404, not 403** — following M13, the one module that was already built to the law.
    A disabled module is not forbidden, it is NOT THERE: a driver whose fleet has not
    activated M12 should meet the same wall as a driver asking for a route that never
    existed, and a 403 would confirm the capability exists and is being withheld.

    Attached to the ROUTER rather than each route, so a new endpoint inside a module
    cannot be added ungated by forgetting a decorator — the failure mode that left
    twelve modules open in the first place.
    """

    def _gate(db: Session = Depends(get_db)) -> None:
        if flags.is_switched_off(db, flag_key):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not enabled")

    return _gate


def require_any_module(*flag_keys: str):
    """AI-CONTEXT: the same gate for a module built in HALVES (A6 / M13).

    A router whose flags are per-capability cannot ask one flag whether it is there:
    M13 serves food vendors and service centers from one prefix, and v2.0 §4 turns the
    first off while §3's A6 turns the second on. Refusing the router when `m13_vendor`
    is off would take the repair shops with it.

    So the ROUTER asks the weakest honest question — is any half live — and the routes
    inside it ask about a type. That division is the point: this gate is never
    sufficient on its own, and every route behind it names its own half.

    `is_switched_off` for the same fail-open reason `require_module` uses it: a
    bootstrap that never registered the flags must not take the module dark.
    """

    def _gate(db: Session = Depends(get_db)) -> None:
        if all(flags.is_switched_off(db, key) for key in flag_keys):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not enabled")

    return _gate
