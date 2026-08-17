"""AI-CONTEXT: officer lines get a voice, and the four things that must stay true.

M15 shipped to production with 8 released lines and zero audio: the Azure adapter worked,
and nothing had ever called it for content. A driver read a silent screen in a simulation
whose entire premise is an officer talking to them. These tests are the guard against that
returning, and against the three ways giving it a voice could go wrong.
"""

from app.foundation.f06_documents import public as documents
from app.modules.m15_roadside.domain import audio as m15_audio
from app.modules.m15_roadside.domain import models as m


class _Tts:
    """A stand-in for Azure. Named, never returned by `resolve_tts` (E3 §E3.4.5)."""

    name = "fake"

    def __init__(self, fail_on: str | None = None):
        self.calls: list[str] = []
        self.fail_on = fail_on

    def synthesize(self, text: str, *, locale: str, voice: str | None = None) -> bytes:
        self.calls.append(text)
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("azure said no")
        return b"ID3" + text.encode()


class _Storage:
    def __init__(self):
        self.objects = {}

    def put(self, key, content, content_type=None):
        self.objects[key] = content

    def get(self, key):
        return self.objects[key]


def _intent(db, key="hos_hours_driven"):
    intent = m.Intent(key=key, domain="paperwork", canonical_meaning="hours driven")
    db.add(intent)
    db.flush()
    return intent


def _variant(db, intent, text, *, status=m.ContentStatus.released, holdout=False, version=1):
    variant = m.PhraseVariant(
        intent_id=intent.id,
        text=text,
        difficulty=m.Difficulty.clear,
        status=status,
        holdout=holdout,
        version=version,
    )
    db.add(variant)
    db.flush()
    return variant


def test_a_released_line_gets_a_voice(db, monkeypatch):
    """The whole point. Without this the officer is a silent text prompt."""
    tts = _Tts()
    storage = _Storage()
    monkeypatch.setattr(m15_audio.ai, "resolve_tts", lambda: tts)
    intent = _intent(db)
    variant = _variant(db, intent, "How many hours have you been driving today?")

    summary = m15_audio.synthesize_missing(db, storage=storage)

    assert summary["synthesized"] == 1
    assert variant.audio_ref is not None
    doc = db.get(documents.Document, variant.audio_ref)
    assert doc.content_type == "audio/mpeg"
    # permanent, which is the DEFAULT — a driver's recording expires in 30 days and an
    # officer's line is content. The retention sweep selects on this column alone.
    assert doc.retention_class is documents.RetentionClass.permanent


def test_a_draft_line_is_never_synthesized(db, monkeypatch):
    """Q-6 reaches spending too. Unreviewed text has no path to a driver, so paying to
    give it a voice is both a leak risk and money for nothing."""
    tts = _Tts()
    monkeypatch.setattr(m15_audio.ai, "resolve_tts", lambda: tts)
    intent = _intent(db)
    _variant(db, intent, "still a draft", status=m.ContentStatus.draft)

    summary = m15_audio.synthesize_missing(db, storage=_Storage())

    assert summary["synthesized"] == 0
    assert tts.calls == []


def test_a_holdout_is_never_synthesized(db, monkeypatch):
    """Q-5. A voice does not leak a holdout by itself, but it spends money on lines that
    must never be taught and is the first step toward serving them."""
    tts = _Tts()
    monkeypatch.setattr(m15_audio.ai, "resolve_tts", lambda: tts)
    intent = _intent(db)
    _variant(db, intent, "held out", holdout=True)

    summary = m15_audio.synthesize_missing(db, storage=_Storage())

    assert summary["synthesized"] == 0
    assert tts.calls == []


def test_a_line_that_already_speaks_is_not_paid_for_twice(db, monkeypatch):
    """The job runs every fifteen minutes forever. Re-synthesizing what already exists
    would bill Azure on a timer for the life of the product."""
    tts = _Tts()
    storage = _Storage()
    monkeypatch.setattr(m15_audio.ai, "resolve_tts", lambda: tts)
    intent = _intent(db)
    _variant(db, intent, "How many hours have you been driving today?")

    m15_audio.synthesize_missing(db, storage=storage)
    second = m15_audio.synthesize_missing(db, storage=storage)

    assert second["synthesized"] == 0
    assert len(tts.calls) == 1


def test_one_failing_line_does_not_mute_the_rest(db, monkeypatch):
    """A quota or a bad character on one string must not leave every later line silent
    for as long as the first keeps failing."""
    tts = _Tts(fail_on="poison")
    monkeypatch.setattr(m15_audio.ai, "resolve_tts", lambda: tts)
    intent = _intent(db)
    bad = _variant(db, intent, "a poison line")
    good = _variant(db, intent, "May I see your logbook?", version=2)

    summary = m15_audio.synthesize_missing(db, storage=_Storage())

    assert summary["failed"] == 1
    assert summary["synthesized"] == 1
    assert bad.audio_ref is None
    assert good.audio_ref is not None


def test_no_speech_key_is_reported_not_raised(db, monkeypatch):
    """The job runs on every box. A dev machine without an Azure key is not a fault, and
    a raising job would show up as a crashing worker rather than as an absence."""

    def _refuse():
        raise m15_audio.ai.SpeechUnavailable("no key")

    monkeypatch.setattr(m15_audio.ai, "resolve_tts", _refuse)
    intent = _intent(db)
    _variant(db, intent, "How many hours have you been driving today?")

    summary = m15_audio.synthesize_missing(db, storage=_Storage())

    assert summary["tts"] == "unavailable"
    assert summary["synthesized"] == 0


def test_the_content_account_cannot_sign_in(db, monkeypatch):
    """It exists to satisfy an ownership column, not to be a user. An account that could
    authenticate would be a credential nobody rotates owning every officer line."""
    tts = _Tts()
    monkeypatch.setattr(m15_audio.ai, "resolve_tts", lambda: tts)
    intent = _intent(db)
    _variant(db, intent, "How many hours have you been driving today?")
    m15_audio.synthesize_missing(db, storage=_Storage())

    from sqlalchemy import select

    from app.foundation.f01_identity.domain.models import AuthMethod

    account = m15_audio.content_account(db)
    assert account.email == "content@haulmeter.online"
    methods = list(db.scalars(select(AuthMethod).where(AuthMethod.account_id == account.id)))
    assert methods == [], "a content-owning account with a credential is one nobody rotates"
    # and it is the same row on a second call — the job runs forever
    assert m15_audio.content_account(db).id == account.id


def test_the_synthesized_bytes_are_actually_served(db, monkeypatch):
    """The audio is only real if it comes back out. This is the half that a row with an
    id but no object would otherwise pass."""
    tts = _Tts()
    storage = _Storage()
    monkeypatch.setattr(m15_audio.ai, "resolve_tts", lambda: tts)
    intent = _intent(db)
    variant = _variant(db, intent, "May I see your logbook?")

    m15_audio.synthesize_missing(db, storage=storage)

    doc = db.get(documents.Document, variant.audio_ref)
    assert storage.get(doc.storage_key) == b"ID3May I see your logbook?"
