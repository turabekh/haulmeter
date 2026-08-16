"""AI-CONTEXT: the pack STATES the visit window, and says where the departure came from.

A claim pack is read by a broker's AP clerk deciding whether to pay. Until now it showed a
timeline and left the clerk to infer the visit from it — and for a stop the driver ended
through the app ("Leave this stop") the geofence chain shows an ENTER and no EXIT, because
the geofence genuinely never saw an exit. The departure IS in the pack, as a USER_ACTION
row, so the pack was never silent; it simply never said *this visit ran from X to Y, and
here is how we know*.

WHAT THIS DOES NOT DO, and the refusal is the point: it synthesises no EXIT event. Writing
one would assert the geofence observed something it did not, into the hash-chained stream
the claim is argued from — the same refusal the dwell-reader fix made, for the same reason.

So the window is derived from `visit_window` (the presence record, which both the detention
clock and dwell stats already trust) and its DEPARTURE PROVENANCE is stated honestly:
observed by the geofence where an EXIT event exists, stated by the driver where it does
not. The second reads weaker to a clerk. It is also true, and a pack that overstates its
own basis is the one thing §11.7 will not allow.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.modules.m03_detention import public as m3

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.7970)
T0 = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _claim(db, email, close_by, hours=3):
    account = identity.register_account(db, email, "pw-123456")
    fac = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    load = loads.create_load(db, account.id, counterparty_id=None, reference_number="L-1")
    stop = loads.add_stop(db, load, fac.id, sequence=0, stop_type=loads.StopType.delivery)
    loads.arm_stop(db, stop)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)
    claim = m3.start_claim(db, stop, started_at=T0)
    if close_by == "ping":
        location.evaluate_ping(db, account.id, *FAR, occurred_at=T0 + timedelta(hours=hours))
    elif close_by == "app":
        loads.depart_stop(db, stop, occurred_at=T0 + timedelta(hours=hours))
    db.flush()
    return claim


# --- the regression: a stop ended in the app states a complete window ---


def test_a_visit_the_driver_ended_in_the_app_states_both_ends(db):
    claim = _claim(db, "pack-app@example.com", "app")

    visit = m3.pack_context_for(db, claim).visit

    assert visit["arrived_at"] == T0
    assert visit["departed_at"] == T0 + timedelta(hours=3)
    assert visit["seconds"] == 10800


def test_that_departure_is_attributed_to_the_DRIVER_not_the_geofence(db):
    """The honest half. The geofence saw no exit; saying it did would be the pack
    overstating its own basis to an AP clerk."""
    claim = _claim(db, "pack-app-src@example.com", "app")

    assert m3.pack_context_for(db, claim).visit["departure_source"] == "driver"


def test_no_EXIT_event_is_invented_to_produce_that_window(db):
    """Same refusal as the dwell fix: nothing fabricated enters the stream a claim is
    argued from."""
    claim = _claim(db, "pack-no-invent@example.com", "app")

    events = location.list_events(db, claim.account_id, claim.facility_ref)
    kinds = [e.event_type.value for e in events]
    assert "EXIT" not in kinds
    assert m3.pack_context_for(db, claim).visit["departed_at"] is not None


# --- what must not change ---


def test_a_geofence_departure_is_attributed_to_the_geofence(db):
    claim = _claim(db, "pack-ping@example.com", "ping")

    visit = m3.pack_context_for(db, claim).visit
    assert visit["departure_source"] == "geofence"
    assert visit["seconds"] == 10800


def test_a_driver_still_at_the_dock_has_an_open_window_not_a_guessed_one(db):
    """An open visit renders as open. Closing it at render time would invent a
    departure — the same error as counting an open visit as a dwell sample."""
    claim = _claim(db, "pack-open@example.com", "none")

    visit = m3.pack_context_for(db, claim).visit
    assert visit["arrived_at"] == T0
    assert visit["departed_at"] is None
    assert visit["seconds"] is None
    assert visit["departure_source"] is None


def test_a_claim_with_no_visit_at_all_omits_the_section(db):
    """PackContext's rule: a section the caller cannot fill is OMITTED, never rendered
    as a blank row. "Arrived: —" tells a clerk we do not know, which is worse than not
    asking."""
    account = identity.register_account(db, "pack-novisit@example.com", "pw-123456")
    fac = facility.create_facility(db, facility.FacilityType.shipper_receiver, "D", *DALLAS)
    load = loads.create_load(db, account.id, counterparty_id=None, reference_number="L-2")
    stop = loads.add_stop(db, load, fac.id, sequence=0, stop_type=loads.StopType.delivery)
    loads.arm_stop(db, stop)
    claim = m3.start_claim(db, stop, started_at=T0)  # armed, never arrived

    assert m3.pack_context_for(db, claim).visit is None


def test_no_claim_means_no_window(db):
    assert m3.pack_context_for(db, None).visit is None


# --- what the clerk actually reads ---


def test_the_rendered_pack_states_the_window_and_its_source(db):
    """Rendered, not just computed — the figure has to survive into the PDF a clerk
    opens, and the wording has to name who is speaking (§11.7)."""
    from app.foundation.f04_evidence import public as evidence

    claim = _claim(db, "pack-render@example.com", "app")
    context = m3.pack_context_for(db, claim)
    pack = evidence.compose_stop_pack(db, claim.stop_ref, evidence.PackTemplate.detention_claim)

    text = evidence.visit_window_text(context)
    assert "driver" in text.lower()
    assert evidence.render_pack_pdf(pack, context).startswith(b"%PDF")


def test_the_geofence_wording_differs_from_the_driver_wording(db):
    """Two different provenances must not render the same sentence — that would make the
    honest distinction invisible, which is the same as not making it."""
    from app.foundation.f04_evidence import public as evidence

    app_claim = _claim(db, "w-app@example.com", "app")
    fence_claim = _claim(db, "w-fence@example.com", "ping")
    by_app = evidence.visit_window_text(m3.pack_context_for(db, app_claim))
    by_fence = evidence.visit_window_text(m3.pack_context_for(db, fence_claim))

    assert by_app != by_fence
