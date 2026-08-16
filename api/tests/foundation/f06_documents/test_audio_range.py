"""AI-CONTEXT: audio types and Range parsing (E3 §E3.4.3).

Range parsing is the kind of code that looks obviously right and is off by one. These
tests spell out INCLUSIVE bounds everywhere, because that is the convention HTTP uses and
the convention a Python slice does not — `bytes=0-0` is one byte, and a reader who
mentally translates it to `data[0:0]` gets zero. Every expected value below is written as
the byte count it should produce.
"""

import pytest

from app.foundation.f06_documents.domain import audio

SIZE = 1000


# --- the allowlist -------------------------------------------------------------------


def test_accepted_audio_types_are_recognised():
    for content_type in ("audio/webm", "audio/mpeg", "audio/wav", "audio/mp4"):
        assert audio.is_audio(content_type) is True


def test_a_parameterised_content_type_still_matches():
    """Browsers send `audio/webm;codecs=opus`, and the parameter is not part of the type."""
    assert audio.is_audio("audio/webm;codecs=opus") is True
    assert audio.is_audio("audio/webm; codecs=opus") is True


def test_non_audio_is_refused_at_the_door():
    for content_type in ("image/jpeg", "application/pdf", "text/html", None, ""):
        assert audio.is_audio(content_type) is False
    with pytest.raises(audio.UnsupportedAudioType):
        audio.require_audio("image/jpeg")


def test_the_allowlist_is_not_a_prefix_match():
    """`audio/*` would accept whatever a client claimed. The browser trusts this value."""
    assert audio.is_audio("audio/x-made-up") is False


# --- range parsing -------------------------------------------------------------------


def test_no_range_header_means_no_range():
    assert audio.parse_range(None, SIZE) is None
    assert audio.parse_range("", SIZE) is None


def test_an_open_ended_range_runs_to_the_last_byte():
    assert audio.parse_range("bytes=0-", SIZE) == (0, 999)


def test_a_bounded_range_is_inclusive():
    """`bytes=0-1023` is 1024 bytes, not 1023. Inclusive on both ends."""
    assert audio.parse_range("bytes=0-99", SIZE) == (0, 99)
    start, end = audio.parse_range("bytes=0-99", SIZE)
    assert end - start + 1 == 100


def test_a_single_byte_range():
    """The case an off-by-one gets wrong: one byte, not zero."""
    start, end = audio.parse_range("bytes=0-0", SIZE)
    assert (start, end) == (0, 0)
    assert end - start + 1 == 1


def test_a_suffix_range_returns_the_last_n_bytes():
    """Some formats keep their index at the end, so players ask for the tail first."""
    assert audio.parse_range("bytes=-100", SIZE) == (900, 999)


def test_a_suffix_longer_than_the_object_clamps_to_the_whole_object():
    assert audio.parse_range("bytes=-5000", SIZE) == (0, 999)


def test_a_range_past_the_end_is_clamped_rather_than_refused():
    """RFC 9110 and every player expect what exists, not a refusal."""
    assert audio.parse_range("bytes=900-5000", SIZE) == (900, 999)


def test_a_start_beyond_the_object_is_unsatisfiable():
    with pytest.raises(audio.InvalidRange):
        audio.parse_range("bytes=1000-", SIZE)


def test_multiple_ranges_are_refused_rather_than_half_supported():
    """Multipart ranges need multipart encoding; no audio element asks for one."""
    with pytest.raises(audio.InvalidRange):
        audio.parse_range("bytes=0-99,200-299", SIZE)


def test_a_non_byte_unit_is_refused():
    with pytest.raises(audio.InvalidRange):
        audio.parse_range("items=0-99", SIZE)


def test_a_malformed_range_is_refused():
    with pytest.raises(audio.InvalidRange):
        audio.parse_range("bytes=-", SIZE)


def test_a_range_against_an_empty_object_is_unsatisfiable():
    with pytest.raises(audio.InvalidRange):
        audio.parse_range("bytes=0-", 0)


def test_the_content_range_header_states_the_whole_size():
    """A player computes duration from the total, so the slice must name the whole."""
    assert audio.content_range_header(0, 99, SIZE) == "bytes 0-99/1000"
