"""AI-CONTEXT: F4 evidence-pack PDF rendering (design-prd §17 — "the PDF is a screen").

This fills a seam that has been open since F4 was written: `render_pack_pdf` raised
`RenderNotEnabled` and PRD §7.16(b) asked the Foundation e2e for "a hash-chain-valid
evidence pack **PDF** offline" while the certifying test had quietly dropped the word.

**The reader is the whole spec.** §17 names the persona: a broker's accounts-payable
clerk, thirty seconds, deciding whether to pay. Everything here serves that — figures
first, one accent, no decoration, and a verification block that a sceptic can act on.

**Tokens, not CSS.** A PDF has no stylesheet, so §6 is transcribed rather than
imported. Two rules keep that from becoming improvisation:

· COLOUR is the LIGHT theme, already derived and owner-approved (§23, 2026-07-20)
  and contrast-verified in `ui/test/contrast.test.js`. §17 says "shield accent on
  white": white is light `--ink-2`. Nothing here is invented.
· SIZE is the §6.2/§6.3 dp scale multiplied by 0.75 — the CSS px (96 dpi) to
  PostScript point (72 dpi) conversion, not a redesign. Body 16 dp becomes 12 pt,
  which is exactly where a print body should land. Logged as a §23 entry.

**The trace is drawn from EVIDENCE, not from raw location pings.** Every plotted
point is a hash-chained record or a geotagged artifact, so the map cannot show a
position the verification block does not cover. That is also why there is no
basemap: an artifact that must survive years in a dispute cannot depend on a tile
server, an API key, or a network call at render time.

**Determinism.** Same chain in, same bytes out. The creation date comes from the
chain — never the clock — so a regenerated pack is byte-identical and its own hash
identifies it. PRD §11 requires packs "verifiable by a third party"; a document
whose bytes change on every render cannot be verified by anyone.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas

from .enums import PackTemplate

# --- §6.1 colour, light theme (§23 2026-07-20 — derived, approved, contrast-verified)
INK_2 = HexColor("#FFFFFF")  # the page. §17: "on white"
INK_1 = HexColor("#F7F9FB")  # the header strip
LINE_1 = HexColor("#CFD8E1")  # hairline rules
TEXT_1 = HexColor("#10161C")
TEXT_2 = HexColor("#47535F")
TEXT_3 = HexColor("#5C6B77")
SHIELD = HexColor("#2C5FC4")  # the ONLY accent (§6.1) — used at ≤10% of the page

# --- §6.2 type scale × 0.75 (96 dpi CSS px → 72 dpi points). No size is invented.
PX_TO_PT = 0.75
METER = 44 * PX_TO_PT
DISPLAY = 28 * PX_TO_PT
TITLE = 20 * PX_TO_PT
BODY = 16 * PX_TO_PT
LABEL = 14 * PX_TO_PT
CAPTION = 13 * PX_TO_PT
BODY_LINE = 24 * PX_TO_PT
CAPTION_LINE = 18 * PX_TO_PT

# --- §6.3 spacing, same conversion. 8 dp grid.
S2 = 8 * PX_TO_PT
S3 = 12 * PX_TO_PT
S4 = 16 * PX_TO_PT
S5 = 24 * PX_TO_PT
S6 = 32 * PX_TO_PT
S7 = 48 * PX_TO_PT

MARGIN = S7  # §17: "generous margins"

SANS = "PlexSans"
SANS_MEDIUM = "PlexSans-Medium"
SANS_SEMI = "PlexSans-SemiBold"
MONO = "PlexMono"
MONO_SEMI = "PlexMono-SemiBold"

_FONT_FILES = {
    SANS: "IBMPlexSans-Regular.ttf",
    SANS_MEDIUM: "IBMPlexSans-Medium.ttf",
    SANS_SEMI: "IBMPlexSans-SemiBold.ttf",
    MONO: "IBMPlexMono-Regular.ttf",
    MONO_SEMI: "IBMPlexMono-SemiBold.ttf",
}

# a pinned producer, because it lands in the PDF trailer and a changing one would
# make otherwise-identical renders differ
PRODUCER = "Haulmeter Evidence Pack 1"

TEMPLATE_TITLES = {
    PackTemplate.detention_claim: "Detention claim",
    PackTemplate.tonu: "Truck ordered, not used",
    PackTemplate.on_time_proof: "On-time arrival proof",
    PackTemplate.cargo_condition: "Cargo condition report",
}

_fonts_registered = False


def _font_dir():
    from pathlib import Path

    return Path(__file__).resolve().parents[1] / "assets" / "fonts"


def register_fonts() -> None:
    """§6.2: "no other families, ever". The faces are vendored beside this module
    (SIL OFL 1.1) and EMBEDDED in the document — a PDF cannot fall back to a system
    stack on the reader's machine, so substituting Helvetica would silently ship a
    typeface the constitution forbids."""
    global _fonts_registered
    if _fonts_registered:
        return
    directory = _font_dir()
    for name, filename in _FONT_FILES.items():
        pdfmetrics.registerFont(TTFont(name, str(directory / filename)))
    _fonts_registered = True


@dataclass
class PackContext:
    """What F4 cannot know about a pack and must be told.

    The parties and the money are not F4's business — the carrier and broker come
    from F5, and a detention total is M3's arithmetic. F4 owns the chain and refuses
    to compute either, so a caller supplies them and any section left empty is
    OMITTED rather than rendered as a blank row. A pack that shows "Broker: —" tells
    a clerk we do not know who they are, which is worse than not asking.
    """

    parties: list[tuple[str, str]] = field(default_factory=list)
    references: list[tuple[str, str]] = field(default_factory=list)
    # §9 The Meter: (label, figure) pairs. §17 puts "total detention · total $" here,
    # and §9 requires the same numbers, order and wording as every other surface.
    meter: list[tuple[str, str]] = field(default_factory=list)
    facility_name: str | None = None
    # artifact thumbnails, keyed by content_hash. Bytes are passed IN rather than
    # fetched here: F4 does not reach into object storage during a render, so a
    # missing image degrades to a labelled placeholder instead of an exception.
    images: dict = field(default_factory=dict)


def _fmt_ts(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _chain_time(pack) -> datetime:
    """The document's creation date, taken from the EVIDENCE rather than the clock.

    This is what makes a regenerated pack byte-identical. It also happens to be more
    honest: the meaningful date of an evidence pack is when the events happened, not
    when someone last pressed export."""
    stamps = [r.get("occurred_at") for r in pack.timeline if r.get("occurred_at")]
    if not stamps:
        return datetime(2000, 1, 1, tzinfo=UTC)
    latest = max(s if s.tzinfo else s.replace(tzinfo=UTC) for s in stamps)
    return latest.astimezone(UTC)


class _Cursor:
    """Bare-minimum flow: the layout is fixed and one-directional, so a full Platypus
    document template would be ceremony around four sections."""

    def __init__(self, canvas, width, height):
        self.c = canvas
        self.width = width
        self.height = height
        self.y = height - MARGIN

    @property
    def left(self):
        return MARGIN

    @property
    def right(self):
        return self.width - MARGIN

    def space(self, amount):
        self.y -= amount

    def rule(self):
        """§6.3: elevation is a hairline, never a shadow."""
        self.c.setStrokeColor(LINE_1)
        self.c.setLineWidth(0.5)
        self.c.line(self.left, self.y, self.right, self.y)
        self.y -= S3

    def need(self, amount) -> None:
        if self.y - amount < MARGIN:
            self.c.showPage()
            self.y = self.height - MARGIN

    def text(self, value, font=SANS, size=BODY, color=TEXT_1, x=None):
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        self.c.drawString(x if x is not None else self.left, self.y, value)

    def right_text(self, value, font=SANS, size=BODY, color=TEXT_1):
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        self.c.drawRightString(self.right, self.y, value)


def _header(cur, pack, context):
    """§17: header strip carrying The Meter figure (total detention · total $)."""
    strip_h = S6 + METER + S5 if context.meter else S6 + DISPLAY
    cur.c.setFillColor(INK_1)
    cur.c.rect(0, cur.y - strip_h + S5, cur.width, strip_h, stroke=0, fill=1)

    cur.text(TEMPLATE_TITLES.get(pack.template, "Evidence pack"), SANS_SEMI, DISPLAY)
    cur.right_text(pack.label or "", SANS, CAPTION, TEXT_3)
    cur.space(S5)

    # §9: label above, Mono figure below, fixed-width — identical composition to the
    # ON_SITE card, the Money tab and the detention push. Same numbers, same order.
    if context.meter:
        cur.space(S2)
        x = cur.left
        for label, figure in context.meter:
            cur.c.setFont(SANS, LABEL)
            cur.c.setFillColor(TEXT_2)
            cur.c.drawString(x, cur.y, label)
            cur.c.setFont(MONO_SEMI, METER)
            cur.c.setFillColor(TEXT_1)
            cur.c.drawString(x, cur.y - METER, figure)
            x += max(pdfmetrics.stringWidth(figure, MONO_SEMI, METER), 140) + S6
        cur.space(METER + S4)
    cur.space(S4)
    cur.rule()


def _pairs(cur, heading, rows):
    if not rows:
        return
    cur.need(S5 + len(rows) * BODY_LINE)
    cur.text(heading, SANS_SEMI, TITLE)
    cur.space(S4 + S2)
    for name, value in rows:
        cur.text(name, SANS, BODY, TEXT_2)
        cur.right_text(value, SANS_MEDIUM, BODY, TEXT_1)
        cur.space(BODY_LINE)
    cur.space(S3)
    cur.rule()


def _chronological(records, key="occurred_at"):
    """AI-CONTEXT: the chain is ordered by SEQ; a timeline is ordered by TIME, and
    the two are not the same list.

    Seq order is the hashing order — each record commits to the one before it — and
    it is insertion order, so a photo attached after the fact but stamped with its
    capture time lands late in the chain and early in the day. Rendering the chain
    order gave a document whose timestamps ran 07:58, 08:04, 09:58, 08:58 — which a
    clerk reads as sloppy at best and doctored at worst. Sorting for display changes
    nothing about the evidence: the verification block still covers the seq-ordered
    chain, and every row still carries the hash it was recorded under.
    """
    return sorted(records, key=lambda r: (r.get(key) is None, r.get(key)))


def _timeline(cur, pack):
    """§17: event timeline, Mono timestamps, hairline rules."""
    if not pack.timeline:
        return
    cur.need(S6)
    cur.text("Event timeline", SANS_SEMI, TITLE)
    cur.space(S4 + S2)
    for record in _chronological(pack.timeline):
        cur.need(BODY_LINE + S2)
        # T-2: time is ALWAYS Mono + tabular, in every surface including this one
        cur.text(_fmt_ts(record.get("occurred_at")), MONO, CAPTION, TEXT_2)
        stamp_w = pdfmetrics.stringWidth("0000-00-00 00:00:00 UTC", MONO, CAPTION)
        cur.text(
            str(record.get("type", "")).replace("_", " ").title(),
            SANS_MEDIUM,
            BODY,
            TEXT_1,
            x=cur.left + stamp_w + S4,
        )
        detail = _detail(record.get("payload"))
        if detail:
            cur.right_text(detail, SANS, CAPTION, TEXT_3)
        cur.space(BODY_LINE)
    cur.space(S2)
    cur.rule()


def _detail(payload) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("event", "prompt", "kind", "status"):
        if payload.get(key):
            return str(payload[key]).replace("_", " ")
    return ""


def _trace(cur, pack, context):
    """§17: map trace snapshot.

    Drawn from LOCATED EVIDENCE — geotagged artifacts and any timeline record
    carrying coordinates — so every plotted point is inside the chain the
    verification block covers. No basemap and no tile request: this artifact has to
    render identically, offline, years from now.
    """
    points = _located_points(pack)
    if len(points) < 2:
        return
    box_h = 150 * PX_TO_PT
    cur.need(box_h + S6)
    cur.text("Location trace", SANS_SEMI, TITLE)
    cur.space(S4 + S2)

    top = cur.y
    bottom = top - box_h
    width = cur.right - cur.left
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    span_lat = max(max(lats) - min(lats), 1e-5)
    span_lon = max(max(lons) - min(lons), 1e-5)
    pad = S4

    def place(lat, lon):
        x = cur.left + pad + (lon - min(lons)) / span_lon * (width - 2 * pad)
        y = bottom + pad + (lat - min(lats)) / span_lat * (box_h - 2 * pad)
        return x, y

    cur.c.setStrokeColor(LINE_1)
    cur.c.setLineWidth(0.5)
    cur.c.rect(cur.left, bottom, width, box_h, stroke=1, fill=0)

    cur.c.setStrokeColor(SHIELD)
    cur.c.setLineWidth(1.2)
    path = cur.c.beginPath()
    start = place(*points[0])
    path.moveTo(*start)
    for lat, lon in points[1:]:
        path.lineTo(*place(lat, lon))
    cur.c.drawPath(path)

    cur.c.setFillColor(SHIELD)
    for lat, lon in (points[0], points[-1]):
        x, y = place(lat, lon)
        cur.c.circle(x, y, 2.5, stroke=0, fill=1)

    # north arrow — without a basemap, orientation has to be stated. Top RIGHT: the
    # first plotted point is frequently the west-most and north-most one, and the
    # label sat on top of the start marker.
    cur.c.setFont(SANS, CAPTION)
    cur.c.setFillColor(TEXT_3)
    cur.c.drawRightString(cur.right - pad, top - pad - CAPTION, "N ↑")
    cur.y = bottom - S4

    # the caption carries what the missing basemap would have shown
    caption = context.facility_name or "Trace"
    cur.text(
        f"{caption} · {points[0][0]:.4f}, {points[0][1]:.4f} · {len(points)} located records",
        SANS,
        CAPTION,
        TEXT_3,
    )
    cur.space(S5)
    cur.rule()


def _located_points(pack) -> list[tuple[float, float]]:
    """A trace is a path THROUGH TIME, so the points are ordered by when they were
    recorded — not by which list they came from and not by chain order. Plotting the
    chain order drew a zig-zag between the same coordinates, which is not a route
    anyone drove."""
    located = []
    for record in pack.timeline:
        payload = record.get("payload") or {}
        if isinstance(payload, dict):
            lat, lon = payload.get("lat"), payload.get("lon")
            if isinstance(lat, int | float) and isinstance(lon, int | float):
                located.append((record.get("occurred_at"), float(lat), float(lon)))
    for artifact in pack.artifacts:
        gps = artifact.get("gps")
        if gps and gps[0] is not None and gps[1] is not None:
            located.append((artifact.get("captured_at"), float(gps[0]), float(gps[1])))
    located.sort(key=lambda p: (p[0] is None, p[0]))
    return [(lat, lon) for _, lat, lon in located]


def _artifacts(cur, pack, context):
    """§17: artifact thumbnails. A photo whose bytes we cannot load renders as a
    labelled placeholder carrying its hash — the hash is the evidence, the image is
    only the convenience, and a missing thumbnail must not cost a clerk the record."""
    if not pack.artifacts:
        return
    cur.need(S6)
    cur.text("Artifacts", SANS_SEMI, TITLE)
    cur.space(S4 + S2)

    thumb = 96 * PX_TO_PT
    per_row = 4
    gap = S4
    column = 0
    row_top = cur.y
    for artifact in pack.artifacts:
        if column == 0:
            cur.need(thumb + CAPTION_LINE + S4)
            row_top = cur.y
        x = cur.left + column * (thumb + gap)
        y = row_top - thumb
        data = context.images.get(artifact.get("content_hash"))
        drawn = False
        if data:
            try:
                cur.c.drawImage(
                    ImageReader(__import__("io").BytesIO(data)),
                    x,
                    y,
                    width=thumb,
                    height=thumb,
                    preserveAspectRatio=True,
                    anchor="c",
                    mask="auto",
                )
                drawn = True
            except Exception:
                drawn = False
        if not drawn:
            cur.c.setStrokeColor(LINE_1)
            cur.c.setLineWidth(0.5)
            cur.c.rect(x, y, thumb, thumb, stroke=1, fill=0)
            cur.c.setFont(SANS, CAPTION)
            cur.c.setFillColor(TEXT_3)
            cur.c.drawString(x + S2, y + thumb / 2, str(artifact.get("artifact_type", "")))
        cur.c.setFont(MONO, CAPTION * 0.8)
        cur.c.setFillColor(TEXT_3)
        cur.c.drawString(x, y - CAPTION_LINE + 2, (artifact.get("content_hash") or "")[:12])

        column += 1
        if column == per_row:
            column = 0
            cur.y = row_top - thumb - CAPTION_LINE - S4
    if column:
        cur.y = row_top - thumb - CAPTION_LINE - S4
    cur.space(S2)
    cur.rule()


def _verification(cur, pack):
    """§17: hash-verification block, monospace, quiet.

    Quiet, but never softened. If the chain is broken this says so in `flare` and
    names the record it broke at — an evidence pack that hid its own failure would
    be worse than no pack, because someone would rely on it.
    """
    v = pack.verification or {}
    cur.need(S7 + 6 * CAPTION_LINE)
    cur.text("Verification", SANS_SEMI, TITLE)
    cur.space(S4 + S2)

    valid = v.get("chain_valid")
    # C-1: colour never carries meaning alone — the words say it too
    cur.c.setFont(SANS_MEDIUM, BODY)
    cur.c.setFillColor(HexColor("#2E8A4B") if valid else HexColor("#C5343A"))
    cur.c.drawString(
        cur.left,
        cur.y,
        "Hash chain intact" if valid else "HASH CHAIN BROKEN — do not rely on this pack",
    )
    cur.space(BODY_LINE)

    rows = [
        ("Records", str(v.get("record_count", 0))),
        ("Head sequence", str(v.get("head_seq", "—"))),
        ("Head hash", v.get("head_hash") or "—"),
        ("Anchored", "yes" if v.get("anchored") else "not yet anchored"),
    ]
    if v.get("anchor_ref"):
        rows.append(("Anchor reference", str(v["anchor_ref"])))
    if v.get("broken_at") is not None:
        rows.append(("Broken at record", str(v["broken_at"])))
    if v.get("reason"):
        rows.append(("Reason", str(v["reason"])))

    for name, value in rows:
        cur.c.setFont(SANS, CAPTION)
        cur.c.setFillColor(TEXT_2)
        cur.c.drawString(cur.left, cur.y, name)
        cur.c.setFont(MONO, CAPTION)
        cur.c.setFillColor(TEXT_1)
        cur.c.drawString(cur.left + 110 * PX_TO_PT, cur.y, value)
        cur.space(CAPTION_LINE)

    cur.space(S3)
    cur.c.setFont(SANS, CAPTION)
    cur.c.setFillColor(TEXT_3)
    cur.c.drawString(
        cur.left,
        cur.y,
        "Each record's hash includes the previous record's hash. Altering any event "
        "changes every hash after it.",
    )


def render(pack, context: PackContext | None = None) -> bytes:
    import io

    context = context or PackContext()
    register_fonts()

    buffer = io.BytesIO()
    created = _chain_time(pack)
    canvas = pdfcanvas.Canvas(buffer, pagesize=LETTER, invariant=1)
    # determinism: a pinned producer and a chain-derived timestamp. `invariant=1`
    # alone would pin the date to ReportLab's own fixed epoch — deterministic, but it
    # would claim the document was made in 2000. Setting `_timeStamp` keeps the
    # determinism and makes the date mean something: the last event in the chain.
    canvas.setProducer(PRODUCER)
    canvas.setCreator(PRODUCER)
    canvas.setTitle(f"{TEMPLATE_TITLES.get(pack.template, 'Evidence pack')} · {pack.label or ''}")
    canvas.setSubject(str(pack.log_id))
    stamp = created.strftime("D:%Y%m%d%H%M%S+00'00'")
    canvas._doc.info._dateFormatter = lambda *_: stamp
    # streams stay UNCOMPRESSED on purpose. The fonts dominate the file size either
    # way, and an uncompressed pack can be read — timeline, hashes and all — with
    # `strings` and no PDF library at all. PRD §11 asks for packs "verifiable by a
    # third party"; this costs a few kilobytes and removes a tool from that job.
    canvas.setPageCompression(0)

    width, height = LETTER
    canvas.setFillColor(INK_2)
    canvas.rect(0, 0, width, height, stroke=0, fill=1)

    cur = _Cursor(canvas, width, height)
    _header(cur, pack, context)
    _pairs(cur, "Parties", context.parties)
    _pairs(cur, "References", context.references)
    _timeline(cur, pack)
    _trace(cur, pack, context)
    _artifacts(cur, pack, context)
    _verification(cur, pack)

    canvas.save()
    return buffer.getvalue()
