"""AI-CONTEXT: derivatives, because "thumbnail" was a variable name and never a file.

`EvidenceSurface` and `LoadRecordSurface` both hold a map called `thumbs` and render it
into a box a few dozen dp across — and what they put in it is the ORIGINAL, at whatever
resolution the camera produced. A driver opening a past load downloaded every full-size
photograph of every stop to draw a contact sheet. There was no resize anywhere in this
product, on either side.

The derivative key is DERIVED, not stored: `<storage_key>.thumb.jpg`. One column records
whether we have tried, and that is the only schema this needs — a second column holding a
key that can always be computed is a second thing to keep in step with the first.

Everything here is pure over bytes so it tests without MinIO, without Postgres and
without a job runner. `make_thumbnail` returns None rather than raising for anything it
cannot read: a PDF rate con, a corrupt frame, a format Pillow was not built with. The
caller records "we tried, there is nothing" and never asks again, which is what keeps a
scanned contract from being re-decoded every five minutes forever.
"""

import io

# The long edge of the derivative. §10.3 and §15.2 render these into rows and contact
# sheets on a 360 dp screen; 320 px covers a full-width row at 2x without being a second
# copy of the photograph. Quality is lower than the capture's 0.85 deliberately — nobody
# reads a BOL at this size, they recognise which photograph it is.
THUMB_EDGE = 320
THUMB_QUALITY = 72

THUMB_SUFFIX = ".thumb.jpg"
THUMB_CONTENT_TYPE = "image/jpeg"


def thumbnail_key(storage_key: str) -> str:
    return f"{storage_key}{THUMB_SUFFIX}"


def make_thumbnail(data: bytes, max_edge: int = THUMB_EDGE) -> bytes | None:
    """A JPEG derivative, or None when there is no image here to derive one from."""
    if not data:
        return None
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None

    try:
        with Image.open(io.BytesIO(data)) as img:
            # a phone writes the sensor's orientation into EXIF rather than rotating the
            # pixels, so a portrait BOL decodes on its side. The full-size original is
            # served as the camera wrote it and browsers honour the tag; a re-encoded
            # derivative loses it, so the rotation has to be baked in here or every
            # portrait capture appears sideways in the contact sheet.
            img = ImageOps.exif_transpose(img)
            # RGB because JPEG has no alpha: a PNG screenshot of a rate con would
            # otherwise raise on save, and "cannot write mode RGBA" is not a reason to
            # leave a driver without a thumbnail.
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.thumbnail((max_edge, max_edge))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=THUMB_QUALITY, optimize=True)
            return out.getvalue()
    except Exception:
        # Pillow raises a wide family — UnidentifiedImageError, OSError, DecompressionBomb
        # — and every one of them means the same thing to the caller. A document that is
        # not an image is the NORMAL case here, not an error worth propagating.
        return None
