"""AI-CONTEXT: the detention notice promised an attachment that does not exist.

M3 is the product's wedge — "real-time notice is the claims-stickiness requirement"
(M3-FR3) — and its outbound body reads:

    "Please find attached the GPS-verified detention evidence and invoice per the
     rate confirmation."

Nothing is attached. `send_email(to_ref, subject, body)` is the whole F8 gateway
protocol, across all four implementations: **there is no attachment parameter
anywhere**, and the notice carried no link either. A broker receiving that email had
no way to reach the evidence being claimed against them.

Every piece needed already existed and had never been connected on this path: F4's
`share_pack` pins the rendered bytes and issues a token, and `/pack/s/{token}` serves
the PDF. M5 uses both. M3 composed a pack and then described it in prose.

This is the same defect class as §23 entry 116's "quiet hours defer" — prose asserting
a behaviour nobody had checked — with the difference that this prose is addressed to a
COUNTERPARTY rather than to a developer, and it is the document the whole contingency
model rests on.
"""

from datetime import timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify
from app.modules.m03_detention import public as m3

from .test_m03 import T0, _arrive_and_leave, _setup


def _claim(db, authority=None):
    kwargs = {"authority": authority} if authority is not None else {}
    account, broker, load, stop = _setup(db, **kwargs)
    claim = m3.start_claim(db, stop, started_at=T0)
    _arrive_and_leave(db, account, T0, T0 + timedelta(minutes=240))
    return claim


def _with_base_url(monkeypatch, value):
    from app.core import config

    monkeypatch.setenv("PUBLIC_BASE_URL", value)
    config.get_settings.cache_clear()
    return config


def test_the_notice_carries_a_link_the_broker_can_actually_open(db, monkeypatch):
    cfg = _with_base_url(monkeypatch, "https://haulmeter.online")
    try:
        gateway = notify.RecordingNotificationGateway()
        result = m3.generate_pack(db, _claim(db), now=T0 + timedelta(minutes=240), gateway=gateway)

        # delivery is the `outbound_mail` sweep's job now, not the request path's
        notify.retry_unsent_messages(db, gateway)
        assert gateway.sent, "no counterparty message was sent at all"
        body = gateway.sent[-1].body
        assert "attached" not in body.lower(), (
            "the notice still claims an attachment, and F8 has no attachment parameter"
        )
        assert f"https://haulmeter.online/pack/s/{result['shared'].token}" in body, (
            f"the pack link is not in the body a broker receives:\n{body}"
        )
    finally:
        cfg.get_settings.cache_clear()


def test_with_no_public_url_it_says_so_instead_of_printing_a_dead_link(db, monkeypatch):
    """A deployment that cannot address itself must not print half a URL. §12.4: say
    what happened and what to do — "available on request" is true and actionable, and a
    link to nowhere is neither."""
    cfg = _with_base_url(monkeypatch, "")
    try:
        gateway = notify.RecordingNotificationGateway()
        m3.generate_pack(db, _claim(db), now=T0 + timedelta(minutes=240), gateway=gateway)
        # delivery is the `outbound_mail` sweep's job now, not the request path's
        notify.retry_unsent_messages(db, gateway)
        body = gateway.sent[-1].body
        assert "attached" not in body.lower()
        assert "/pack/s/" not in body
        assert "available on request" in body.lower()
    finally:
        cfg.get_settings.cache_clear()


def test_the_shared_pack_is_the_one_that_was_composed(db):
    """A link to a DIFFERENT rendering would be worse than no link — the hash chain in
    the document is what makes it dispute-resistant, and a second render is a second
    document."""
    gateway = notify.RecordingNotificationGateway()
    result = m3.generate_pack(db, _claim(db), now=T0 + timedelta(minutes=240), gateway=gateway)
    assert result["shared"].template == result["pack"].template.value


def test_a_notify_only_claim_still_gets_its_evidence_shared(db):
    """Company-driver mode (M3-FR9) exports a pack for the carrier and opens no
    receivable. The evidence still has to be reachable, or the export is a PDF nobody
    outside the phone can open."""
    gateway = notify.RecordingNotificationGateway()
    result = m3.generate_pack(
        db,
        _claim(db, authority=identity.AuthorityType.company),
        now=T0 + timedelta(minutes=240),
        gateway=gateway,
    )
    assert result["shared"] is not None
