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

# how far the two clocks may drift before the row discloses both (see
# `_divergence_note` for why this number and why it lives here rather than in config)
DISCLOSE_DIVERGENCE_S = 300

def template_title(template) -> str:
    return TEMPLATE_TITLES.get(template, "Evidence pack")


TEMPLATE_TITLES = {
    PackTemplate.detention_claim: "Detention claim",
    PackTemplate.tonu: "Truck ordered, not used",
    PackTemplate.on_time_proof: "On-time arrival proof",
    PackTemplate.cargo_condition: "Cargo condition report",
    PackTemplate.incident: "Incident report",
    PackTemplate.stop_record: "Stop record",
    PackTemplate.load_record: "Load record",
    PackTemplate.stop_packet: "Stop paperwork packet",
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
    # AI-CONTEXT: what the location data IS (D6). Supplied by the caller, because F3 sits
    # below F4's callers and F4 may not reach sideways for it. None omits the section
    # entirely — a pack composed by something that never asked should not invent an answer.
    location_basis: dict | None = None
    # AI-CONTEXT: M14-FR3. WHAT the location trail rests on, and WHO reported it.
    # Supplied by the caller for the same reason `location_basis` is: F4 owns the chain
    # and refuses to infer the provenance of data it did not produce. Defaulting to
    # `phone_verified` is a statement of fact about every pack that existed before M14.
    evidence_class: str = "phone_verified"
    evidence_providers: list[str] = field(default_factory=list)
    # AI-CONTEXT: THIS VISIT — arrived, departed, how long, and where the departure came
    # from. Supplied by the caller for the same reason `location_basis` is: F4 owns the
    # chain and will not infer a visit from data it did not produce. None omits the
    # section entirely, per this class's own rule — "Arrived: —" tells a clerk we do not
    # know, which is worse than not asking.
    #
    # `departure_source` is the honest half. A stop the driver ended in the app produces
    # no geofence EXIT, so the pack says the DRIVER stated it. That reads weaker to an AP
    # clerk than "observed", and it is what happened; a pack that overstates its own basis
    # is the one thing §11.7 forbids outright.
    visit: dict | None = None
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

    def paragraph(self, value, font=SANS, size=CAPTION, color=TEXT_3, leading=None):
        """Prose that WRAPS at the right margin, and breaks pages while doing it.

        AI-CONTEXT: `text()` is a bare `drawString`, so a caption longer than the column
        ran off the page and was clipped by it. Found by rendering a pack and LOOKING at
        it — no test could see it, because every assertion the suite makes about these
        sentences is made against the string, and the string was always correct. What the
        clerk read was "...it does not attest h".

        The sentences it truncated are the pack's HONESTY text: the location-basis
        paragraph explaining that the hash chain attests storage rather than capture, and
        the visit paragraph naming who says the truck left. A document that clips exactly
        the sentences qualifying its own evidence overstates itself by omission, which is
        §11.7's failure arriving through the typesetter.
        """
        step = leading if leading is not None else size + 4
        words, line = str(value).split(), ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if pdfmetrics.stringWidth(candidate, font, size) <= (self.right - self.left):
                line = candidate
                continue
            self.need(step)
            self.text(line, font, size, color)
            self.space(step)
            line = word
        if line:
            self.need(step)
            self.text(line, font, size, color)
            self.space(step)


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
    # A pack spanning a route sorts by STOP first (§23 entry 78). Time alone would
    # interleave two docks the moment a driver doubles back, and the section headings
    # would then repeat and contradict the order they announce.
    return sorted(
        records, key=lambda r: (r.get("group_order", 0), r.get(key) is None, r.get(key))
    )


def _divergence_note(record) -> str:
    """AI-CONTEXT: where the two clocks disagree, the row SAYS SO.

    Sorting the timeline by capture time was right and is not sufficient. The chain's
    hashes commit to `seq`, which is filing order, so a counterparty who obtains the
    chain can show that our rendered order differs from the order the hashes cover.
    "Your PDF reordered our evidence" is a bad sentence to be answering, and the
    answer is already in the data: F12 records both clocks precisely so the gap can
    be disclosed. Recording it and then hiding it wastes the capture.

    Five minutes: comfortably above ordinary drift and sync latency, comfortably
    below the case a counterparty would actually probe — a photo taken at the dock
    with no signal and filed hours later, which is the normal life of this product.
    Disclosing sub-minute jitter on every row would bury the rows that mean
    something. The threshold lives here, in the open, rather than in config: it is a
    statement about evidence, not a tuning knob.
    """
    occurred, received = record.get("occurred_at"), record.get("received_at")
    if occurred is None or received is None:
        return ""
    occurred = occurred if occurred.tzinfo else occurred.replace(tzinfo=UTC)
    received = received if received.tzinfo else received.replace(tzinfo=UTC)
    if abs((received - occurred).total_seconds()) < DISCLOSE_DIVERGENCE_S:
        return ""
    return f"filed {received.astimezone(UTC):%H:%M}"


def _timeline(cur, pack):
    """§17: event timeline, Mono timestamps, hairline rules."""
    if not pack.timeline:
        return
    cur.need(S6)
    cur.text("Event timeline", SANS_SEMI, TITLE)
    cur.space(S4 + S2)
    group = None
    for record in _chronological(pack.timeline):
        # AI-CONTEXT: a pack spanning a ROUTE says which dock each row happened at
        # (§23 entry 78). Without it, two stops' events run together as one confused
        # visit, and the broker cannot tell the pickup's four photos from the
        # delivery's. A single-stop pack carries no group and renders exactly as before.
        if record.get("group") and record["group"] != group:
            group = record["group"]
            cur.need(BODY_LINE + S4)
            cur.space(S2)
            cur.text(group, SANS_SEMI, BODY, TEXT_1)
            cur.space(BODY_LINE)
        cur.need(BODY_LINE + S2)
        # T-2: time is ALWAYS Mono + tabular, in every surface including this one
        filed = _divergence_note(record)
        captured = _fmt_ts(record.get("occurred_at"))
        cur.text(f"{captured} · {filed}" if filed else captured, MONO, CAPTION, TEXT_2)
        stamp_w = pdfmetrics.stringWidth("0000-00-00 00:00:00 UTC · filed 00:00", MONO, CAPTION)
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
    """AI-CONTEXT: a prompt is ATTRIBUTED, never asserted.

    Putting the guided-capture prompt into the chained record was right — it is a
    claim about what an image shows and belongs hashed with it. Rendering the row as
    `Photo  seals` was not: to a clerk that reads as *this photograph shows the
    seals*, which is the platform asserting image content in its own voice. If the
    driver photographed a mud flap at step two, the document states something false
    and we are the ones who said it.

    What actually happened is that we prompted for seals and this is what arrived.
    `prompted: seals` says who is speaking — the same discipline as "Vendor says
    halal" never being a bare "Halal", `documents_on_file` rendering neutral, and a
    vendor's own presence claim never appearing as a driver count. Same rule, applied
    to the AP clerk instead of the driver.
    """
    if not isinstance(payload, dict):
        return ""
    if payload.get("prompt"):
        return f"prompted: {str(payload['prompt']).replace('_', ' ')}"
    # AI-CONTEXT: `pack_opened` is a LEGACY record and must not read as a human act
    # (finding F4-1). It is no longer written — a link open is a URL being fetched, and
    # mail-security scanners fetch URLs before anyone reads the mail — but chains already
    # carrying it are append-only and are never rewritten. So the row renders as what was
    # actually measured: the link was reached, by someone or something.
    if (payload or {}).get("event") == "pack_opened":
        return "link first accessed (may include automated scanners)"
    for key in ("event", "kind", "status"):
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
    group = None
    for artifact in pack.artifacts:
        # AI-CONTEXT: which dock each photo came from (§23 entry 78). A route's pack
        # showed eight thumbnails in one grid, four from the pickup and four from the
        # delivery, with nothing separating them — so a clerk arguing about damage
        # found at the receiver could not tell which four were taken there.
        if artifact.get("group") and artifact["group"] != group:
            group = artifact["group"]
            if column:  # close the part-filled row before starting a new section
                cur.space(thumb + CAPTION_LINE + S4)
                column = 0
            cur.need(BODY_LINE + thumb + CAPTION_LINE + S4)
            cur.space(S2)
            cur.text(group, SANS_SEMI, BODY, TEXT_1)
            cur.space(BODY_LINE)
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


def _anchor_line(v) -> str:
    """What the anchor row actually proves — three states, not two.

    AI-CONTEXT: this printed "yes" whenever an anchor ROW existed, and every anchor this
    product writes is internal (`anchor_chain` is called with no `external_ref`). So the
    document a broker reads asserted third-party timestamping that nothing outside our own
    database supported — the single strongest-sounding line in the verification block, and
    the one with the least behind it. External anchoring is not activated; until it is,
    this says so in the clerk's own terms rather than in ours.
    """
    if v.get("anchored"):
        return "yes — externally timestamped"
    if v.get("anchor_recorded"):
        return "head recorded internally; no external timestamp"
    return "not yet anchored"


# AI-CONTEXT: the phone sentence, UNCHANGED and named so it cannot drift (M14-FR3).
# Every pack this product has ever sent a broker says exactly this, so altering it would
# alter documents already in AP inboxes. New classes are added beside it, never over it.
_PHONE_BASIS = (
    "Location data as reported by the driver's device. The hash chain shows these "
    "records are unaltered since capture; it does not attest how they were produced."
)
_TRAIL_ABSENT = (
    "Position trail not available for this period — it was not recorded, or has passed "
    "the retention window. No further claim is made about it."
)


def _provider_label(providers) -> str:
    """`motive` → `Motive`. Named, because §11.7 is state WHO said what: a pack that says
    "a telematics provider" gives a clerk nothing they can check."""
    names = [str(p).replace("_", " ").title() for p in (providers or []) if p]
    if not names:
        return "the vehicle's telematics provider"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def location_basis_text(context) -> str:
    """What the pack says about where its positions came from (M14-FR3).

    Extracted from the renderer so the WORDING can be asserted without rendering a PDF
    and grepping bytes — the sentence is the thing under test, not the layout.

    §11.7 AIMED AT A COUNTERPARTY. The pack must never imply a chain of custody it does
    not have. An AP clerk who catches one pack overclaiming distrusts every pack after
    it, and this product's whole argument to a broker is that its documents are worth
    more than a screenshot — so the strongest sentence available is the one that must be
    earned, not the one that is easiest to justify.

    WHAT EACH CLASS MAY CLAIM:
      · `phone_verified` — capture on the driver's device, hash-chained since capture.
      · `eld_derived`    — the PROVIDER's own timestamps and positions, provider NAMED,
        and explicitly NOT covered by the capture chain. There was no capture: the chain
        attests that OUR COPY is unaltered since we received it, which is a strictly
        weaker statement and is written as one.
      · `mixed`          — both, saying which side each sits on.
    """
    basis = (context.location_basis if context else None) or {}
    evidence_class = getattr(context, "evidence_class", "phone_verified") or "phone_verified"
    providers = getattr(context, "evidence_providers", []) or []
    who = _provider_label(providers)

    if evidence_class == "eld_derived":
        text = (
            f"Location data as reported by {who} from the vehicle's telematics unit. "
            "These are the provider's own timestamps and positions. They are not covered "
            "by this pack's capture chain, which attests only that our copy is unaltered "
            "since we received it — it does not attest how the readings were produced."
        )
    elif evidence_class == "mixed":
        text = (
            f"{_PHONE_BASIS} Some positions in this period were instead reported by {who} "
            "from the vehicle's telematics unit; those are the provider's own timestamps "
            "and are not covered by the capture chain."
        )
    else:
        text = _PHONE_BASIS

    # HONEST ABSENCE survives every class. A trail that is gone asserts nothing at all,
    # and a zero rendered as "0 implausible movements" would be the strongest sentence on
    # the page and completely unearned.
    if not basis.get("pings"):
        return f"{text} {_TRAIL_ABSENT}"
    return text


def _fmt_duration(seconds) -> str:
    """"3h 20m" — the shape §9's Meter uses, so the pack and the driver's screen say
    the same thing about the same stop."""
    total = int(seconds)
    hours, minutes = divmod(total // 60, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


# WHO SAYS the truck left, in the clerk's own terms. Two provenances, two sentences —
# rendering them identically would make the distinction invisible, which is the same as
# not drawing it.
_DEPARTURE_SOURCE = {
    "geofence": (
        "Arrival and departure are taken from this device's geofence record for the visit; "
        "both crossings were observed."
    ),
    "driver": (
        "Arrival is taken from this device's geofence record for the visit. The departure "
        "is the driver's own statement that they left, recorded at the time — the geofence "
        "did not observe the exit."
    ),
}
_DEPARTURE_OPEN = (
    "Arrival is taken from this device's geofence record for the visit. No departure has "
    "been recorded: at the time this document was produced the visit was still open."
)


def visit_window_text(context) -> str:
    """AI-CONTEXT: the sentence under the window, naming who is speaking (§11.7).

    Exported because it is asserted directly by tests: the difference between an observed
    departure and a driver-stated one is the whole honesty of the section, and a test that
    only checked the section existed would pass with both rendered the same.
    """
    visit = (context.visit if context else None) or {}
    if visit.get("departed_at") is None:
        return _DEPARTURE_OPEN
    return _DEPARTURE_SOURCE.get(visit.get("departure_source"), _DEPARTURE_OPEN)


def _visit_window(cur, context):
    """§17: what this visit WAS — stated as a figure, not left to be inferred.

    AI-CONTEXT: the pack showed a timeline and expected an AP clerk to reconstruct the
    visit from it. For a stop ended through the app that meant reading a `Geofence ENTER`
    row and, further down, a `User Action departed` row of a different type, and doing the
    subtraction. The visit was never in doubt — `visit_window` has read it from the
    presence record since entry 73 — it simply was never SAID.

    No EXIT event is synthesised to make this section possible; the section exists so that
    none has to be.
    """
    visit = (context.visit if context else None) or None
    if visit is None:
        return
    cur.need(S6)
    cur.text("This visit", SANS_SEMI, TITLE)
    cur.space(S4 + S2)
    rows = [("Arrived", _fmt_ts(visit.get("arrived_at")))]
    if visit.get("departed_at") is not None:
        rows.append(("Departed", _fmt_ts(visit.get("departed_at"))))
        if visit.get("seconds") is not None:
            rows.append(("On site", _fmt_duration(visit["seconds"])))
    else:
        # honest absence, the same branch `_location_basis` takes: state that it is open
        # rather than printing a dash a clerk would read as a missing value
        rows.append(("Departed", "still on site when this document was produced"))
    for label, value in rows:
        cur.need(BODY_LINE)
        cur.text(label, SANS_MEDIUM, BODY, TEXT_1)
        cur.right_text(value, MONO, BODY, TEXT_1)
        cur.space(BODY_LINE)
    cur.space(S2)
    cur.paragraph(visit_window_text(context))
    cur.space(S2)
    cur.rule()


def _location_basis(cur, context):
    """§17: what the location data IS — stated, not implied (D6).

    AI-CONTEXT: the counterparty copy used to call this "GPS-verified". The chain proves a
    reading has not been altered since it was recorded; it proves nothing about how the
    reading was produced. So the pack says so in the clerk's own terms, and gives them the
    shape of the trail to judge for themselves.

    HONEST ABSENCE is the important branch. When the window's pings are gone — purged past
    the retention window, or never recorded — this says the trail is not available and
    asserts NOTHING. A zero rendered as "0 implausible movements" would be the strongest
    sentence on the page and completely unearned.
    """
    basis = (context.location_basis if context else None) or None
    if basis is None:
        return
    cur.need(S6)
    cur.text("Location basis", SANS_SEMI, TITLE)
    cur.space(S4 + S2)
    cur.paragraph(location_basis_text(context))
    cur.space(S2)

    if not basis.get("pings"):
        # the absence sentence is part of `location_basis_text` now, so it has already
        # been printed above — printing it again would say it twice
        cur.space(S5)
        cur.rule()
        return

    def _m(value):
        return f"{value:.0f} m" if isinstance(value, int | float) else "—"

    rows = [("Position fixes", str(basis["pings"]))]
    if basis.get("accuracy_reported"):
        rows.append(
            (
                "Reported accuracy",
                f"best {_m(basis['accuracy_min_m'])} · "
                f"typical {_m(basis['accuracy_median_m'])} · "
                f"worst {_m(basis['accuracy_max_m'])}",
            )
        )
    else:
        rows.append(("Reported accuracy", "not reported by the device"))
    rows.append(("Device clock disagreed", str(basis.get("divergent_clock_pings", 0))))
    rows.append(("Implausible movements", str(basis.get("implausible_moves", 0))))
    for label, value in rows:
        cur.need(BODY_LINE)
        cur.text(label, SANS, BODY, TEXT_2)
        cur.right_text(value, SANS_MEDIUM, BODY, TEXT_1)
        cur.space(BODY_LINE)
    cur.space(S5)
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
        ("Anchored", _anchor_line(v)),
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
    # BEFORE the timeline: the clerk should read what the visit WAS before reading the
    # rows it is made of, rather than reconstructing it from them
    _visit_window(cur, context)
    _timeline(cur, pack)
    _trace(cur, pack, context)
    _artifacts(cur, pack, context)
    _location_basis(cur, context)
    _verification(cur, pack)

    canvas.save()
    return buffer.getvalue()
