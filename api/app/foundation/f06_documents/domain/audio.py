"""AI-CONTEXT: audio in F6 — what may be stored, and how a browser fetches part of it.

F6 grew up serving photographs, where the whole object is the unit: a contact sheet wants
every byte of a thumbnail and nothing less. Audio is not like that. An `<audio>` element
issues a Range request before it will show a duration or let anyone scrub, and a server
that answers 200-with-everything makes the element download a whole recording to play the
last four seconds of it — on a driver's data plan, in a truck stop.

TWO SEPARATE THINGS LIVE HERE and it is worth not confusing them:

· **the MIME allowlist** — what F6 will accept as audio at all. An allowlist rather than a
  pattern match, because `audio/*` would accept whatever a client claimed, and the
  content type is what the browser trusts when it decides how to decode bytes.
· **range parsing** — turning one `Range:` header into a byte slice, or refusing it.
  Deliberately narrow: a single range only. Multi-range responses need multipart encoding
  and no audio element asks for one, so supporting it would be code with no caller, which
  is code nobody will notice going wrong.
"""

# AI-CONTEXT: an allowlist, not a prefix check. Opus and webm are what a browser records
# in practice; wav and mp4/m4a are what a synthesis provider returns; mpeg is what
# everything else on earth produces. Anything else is refused at the door rather than
# stored and discovered later by a player that will not decode it.
AUDIO_CONTENT_TYPES = frozenset(
    {
        "audio/webm",
        "audio/ogg",
        "audio/opus",
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp4",
        "audio/aac",
    }
)


class UnsupportedAudioType(ValueError):
    """A content type F6 will not accept as audio."""


class InvalidRange(ValueError):
    """A Range header that cannot be satisfied — the caller answers 416."""


def is_audio(content_type: str | None) -> bool:
    return bool(content_type) and content_type.split(";")[0].strip().lower() in AUDIO_CONTENT_TYPES


def require_audio(content_type: str | None) -> str:
    if not is_audio(content_type):
        raise UnsupportedAudioType(
            f"{content_type!r} is not an accepted audio type; "
            f"accepted: {sorted(AUDIO_CONTENT_TYPES)}"
        )
    return content_type


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """`Range: bytes=start-end` -> inclusive (start, end), or None when absent.

    Raises `InvalidRange` for a syntactically fine header that cannot be satisfied, which
    is a 416 rather than a 400 — the distinction matters to a player deciding whether to
    retry or give up.

    The three forms that actually occur:
      bytes=0-       an element asking for everything, but willing to be given a slice
      bytes=0-1023   a probe for the header of the file
      bytes=-1024    the LAST n bytes; some formats keep their index at the end
    """
    if not header:
        return None
    header = header.strip()
    if not header.startswith("bytes="):
        raise InvalidRange(f"unsupported range unit in {header!r}")
    spec = header[len("bytes=") :].strip()
    if "," in spec:
        # a single range only — see the module docstring on code with no caller
        raise InvalidRange("multiple ranges are not supported")
    if size <= 0:
        raise InvalidRange("cannot satisfy a range against an empty object")

    start_s, _, end_s = spec.partition("-")
    if not start_s and not end_s:
        raise InvalidRange(f"malformed range {header!r}")

    if not start_s:
        # suffix form: the last N bytes
        suffix = int(end_s)
        if suffix <= 0:
            raise InvalidRange("suffix range must be positive")
        start = max(0, size - suffix)
        end = size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s else size - 1

    if start >= size:
        raise InvalidRange(f"range start {start} is beyond the object ({size} bytes)")
    # a client asking past the end gets what exists, which is what RFC 9110 requires and
    # also what every player expects — clamping here rather than refusing
    end = min(end, size - 1)
    if end < start:
        raise InvalidRange(f"range end {end} precedes start {start}")
    return start, end


def content_range_header(start: int, end: int, size: int) -> str:
    return f"bytes {start}-{end}/{size}"
