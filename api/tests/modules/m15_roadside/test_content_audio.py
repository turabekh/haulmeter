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

    def synthesize(self, text, **kw) -> bytes:
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


def test_a_released_model_answer_gets_a_voice_too(db, monkeypatch):
    """FR5's step is "hear a clear model answer, repeat it". A model answer a driver can
    only READ cannot be shadowed — that turns an ear-and-mouth exercise into a reading
    test, which is the one thing this module is not."""
    tts = _Tts()
    storage = _Storage()
    monkeypatch.setattr(m15_audio.ai, "resolve_tts", lambda: tts)
    intent = _intent(db)
    answer = m.ModelAnswer(
        intent_id=intent.id,
        text="I have been driving six hours today.",
        status=m.ContentStatus.released,
    )
    db.add(answer)
    db.flush()

    summary = m15_audio.synthesize_missing(db, storage=storage)

    assert summary["synthesized"] == 1
    assert answer.audio_ref is not None


def test_a_draft_model_answer_gets_no_voice(db, monkeypatch):
    """Q-6 reaches spending here too — paying to synthesize unreviewed text is money for
    something that must not be heard."""
    tts = _Tts()
    monkeypatch.setattr(m15_audio.ai, "resolve_tts", lambda: tts)
    intent = _intent(db)
    db.add(m.ModelAnswer(
        intent_id=intent.id, text="a drafted answer", status=m.ContentStatus.draft
    ))
    db.flush()

    assert m15_audio.synthesize_missing(db, storage=_Storage())["synthesized"] == 0
    assert tts.calls == []


def test_the_coach_speaks_the_drivers_language_not_the_officers(db, monkeypatch):
    """AI-CONTEXT: the one place this module stops speaking English, and it must.

    The officer speaks US English at a driver. The coaching explanation explains, in the
    DRIVER'S language, why an answer missed. Reading an Uzbek paragraph in `en-US-Ethan` is
    not accented Uzbek — it is English phonemes applied to Uzbek words, which is worse than
    silence because it teaches a pronunciation nobody uses.

    Asserted on the VOICE ARGUMENT actually passed to the adapter, because the failure is
    silent: a wrong voice still returns valid mp3, still sets `audio_ref`, and still reports
    `synthesized: 1`. Nothing anywhere would go red.
    """
    from app.modules.m15_roadside.domain import audio as m15_audio
    from app.modules.m15_roadside.domain import models as m

    intent = m.Intent(key="destination", domain="stop", canonical_meaning="where to")
    db.add(intent)
    db.flush()
    db.add(
        m.CoachingContent(
            intent_id=intent.id, locale="uz",
            explanation="Bu savolda inspektor qayerga ketayotganingizni so'rayapti.",
            review_status=m.ContentStatus.released,
        )
    )
    db.flush()

    seen = []

    class _Tts:
        def synthesize(self, text, **kw):
            seen.append((text, kw.get("locale"), kw.get("voice")))
            return b"AUDIO"

    monkeypatch.setattr(m15_audio.ai, "resolve_tts", lambda: _Tts())
    m15_audio.synthesize_missing(db)

    uz = [s for s in seen if s[1] == "uz"]
    assert uz, "the released Uzbek explanation was never offered to the synthesizer"
    assert uz[0][2] == "uz-UZ-SardorNeural"
    assert uz[0][2] != m15_audio.VOICE_DEFAULT, "the coach borrowed the officer's voice"


def test_a_language_with_no_voice_keeps_its_text_and_is_not_a_failure(db, monkeypatch):
    """Tajik has NO Azure voice at all — checked against the vendor, not assumed.

    A locale we cannot speak must leave its explanation as text rather than counting as a
    synthesis failure, or the job would report a fault on every tick forever and the real
    failures would be lost in it.
    """
    from app.modules.m15_roadside.domain import audio as m15_audio
    from app.modules.m15_roadside.domain import models as m

    intent = m.Intent(key="destination", domain="stop", canonical_meaning="where to")
    db.add(intent)
    db.flush()
    db.add(
        m.CoachingContent(
            intent_id=intent.id, locale="tg", explanation="matni tojiki",
            review_status=m.ContentStatus.released,
        )
    )
    db.flush()

    class _Tts:
        def synthesize(self, text, **kw):
            raise AssertionError("a language with no voice must never reach the synthesizer")

    monkeypatch.setattr(m15_audio.ai, "resolve_tts", lambda: _Tts())
    summary = m15_audio.synthesize_missing(db)

    assert summary["failed"] == 0


# --- the repair for a synthesis pass that wrote its bytes to nowhere (TRAPS 85) ---------


def test_a_row_whose_bytes_are_gone_is_queued_again(db, monkeypatch):
    """THE WORST STATE THIS MODULE CAN BE IN, and it has happened twice.

    A synthesis pass run without object storage wired writes its mp3s into an in-memory
    dict that dies with the process, and commits the `audio_ref` regardless. The database
    then says every line is voiced, so `variants_needing_audio` returns nothing and the
    worker has no work forever — while every play button fetches a key that was never
    written. Nothing is red; a person has to tap a button to find it.
    """
    tts = _Tts()
    storage = _Storage()
    monkeypatch.setattr(m15_audio.ai, "resolve_tts", lambda: tts)
    intent = _intent(db)
    variant = _variant(db, intent, "How many hours have you been driving today?")
    m15_audio.synthesize_missing(db, storage=storage)
    assert variant.audio_ref is not None

    # the bytes vanish; the row still claims a voice
    storage.objects.clear()
    assert m15_audio.variants_needing_audio(db) == []

    summary = m15_audio.heal_missing_audio(db, storage=storage)

    assert summary == {"checked": 1, "healed": 1}
    assert variant.audio_ref is None
    assert variant in m15_audio.variants_needing_audio(db)


def test_healing_leaves_a_healthy_row_alone(db, monkeypatch):
    """Safe to run on a good box: a blunt "clear everything released" would re-spend TTS
    on every line that is perfectly fine."""
    tts = _Tts()
    storage = _Storage()
    monkeypatch.setattr(m15_audio.ai, "resolve_tts", lambda: tts)
    intent = _intent(db)
    variant = _variant(db, intent, "How many hours have you been driving today?")
    m15_audio.synthesize_missing(db, storage=storage)
    ref = variant.audio_ref

    summary = m15_audio.heal_missing_audio(db, storage=storage)

    assert summary == {"checked": 1, "healed": 0}
    assert variant.audio_ref == ref


def test_a_coaching_explanation_is_healed_too(db, monkeypatch):
    """The row that `m15_revoice` forgot. Its column is `review_status` rather than
    `status`, which is exactly how it gets left out of sweeps."""
    tts = _Tts()
    storage = _Storage()
    monkeypatch.setattr(m15_audio.ai, "resolve_tts", lambda: tts)
    intent = _intent(db)
    row = m.CoachingContent(
        intent_id=intent.id,
        locale="uz",
        explanation="faqat bugungi haydash soatlari",
        review_status=m.ContentStatus.released,
        version=1,
    )
    db.add(row)
    db.flush()
    m15_audio.synthesize_missing(db, storage=storage)
    assert row.audio_ref is not None

    storage.objects.clear()
    summary = m15_audio.heal_missing_audio(db, storage=storage)

    assert summary["healed"] == 1
    assert row.audio_ref is None
