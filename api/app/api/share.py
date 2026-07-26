"""AI-CONTEXT: the counterparty's door — the second unauthenticated surface.

design-prd §17: counterparty mail is plain, short, professional, ONE link, no
images. This is that link. An accounts-payable clerk will not create an account to
read a document a driver sent them, so there is no session here — the token IS the
authorisation, and it is scoped to exactly one pack and nothing else.

It serves the PINNED bytes. If it re-rendered from the chain, a clerk refreshing an
old link would silently see a document that had grown new evidence since they were
sent it, and neither side could say which version the argument was about.

Unknown, revoked and expired all return the same 404 on purpose: a caller must not
be able to distinguish "never existed" from "revoked" by probing tokens.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.foundation.f04_evidence import public as evidence

router = APIRouter(prefix="/pack", tags=["share"])


@router.get("/s/{token}")
def open_shared_pack(token: str, db: Session = Depends(get_db)):
    try:
        content = evidence.open_share(db, token)
    except evidence.ShareNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "link not available") from exc
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="evidence-pack.pdf"'},
    )
