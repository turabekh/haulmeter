"""AI-CONTEXT: ONE definition of "where does a counterparty open this pack".

F4 issues the token, so F4 answers where it lives. M3's detention notice needed it
first; A1's Stop Packet needs the identical thing, and M5's on-time proof is a third
caller waiting. Three modules building the same URL from the same token is the shape
of §23 entry 94's regression, and this session has now found nine mechanisms fixed in
one place and not the others.

The empty case is the interesting one. A deployment with no PUBLIC_BASE_URL cannot
address itself, and a half-formed URL in an email to a broker is worse than an honest
sentence saying the evidence is available on request (§12.4: what happened, what to do).
So this returns None rather than a broken string, and the caller writes the sentence.
"""

from app.foundation.f04_evidence import public as evidence


class _Shared:
    token = "abc123"


def test_it_builds_an_absolute_url_a_broker_can_open(monkeypatch):
    from app.core import config

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://haulmeter.online")
    config.get_settings.cache_clear()
    try:
        assert evidence.share_link(_Shared()) == "https://haulmeter.online/pack/s/abc123"
    finally:
        config.get_settings.cache_clear()


def test_a_trailing_slash_does_not_double(monkeypatch):
    from app.core import config

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://haulmeter.online/")
    config.get_settings.cache_clear()
    try:
        assert evidence.share_link(_Shared()) == "https://haulmeter.online/pack/s/abc123"
    finally:
        config.get_settings.cache_clear()


def test_no_base_url_returns_NOTHING_rather_than_half_a_link(monkeypatch):
    from app.core import config

    monkeypatch.setenv("PUBLIC_BASE_URL", "")
    config.get_settings.cache_clear()
    try:
        assert evidence.share_link(_Shared()) is None
    finally:
        config.get_settings.cache_clear()
