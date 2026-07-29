"""AI-CONTEXT: the manual-settability boundary (Admin Console 2.0 decision 8).

The console's guiding principle is that anything legitimately settable by hand
should be reachable from it. The corollary is the more important half: some things
are **constitutionally not settable**, and "we didn't build an endpoint for that"
is not the same guarantee as "no endpoint for that can exist".

These are NEGATIVE tests. They assert the absence of a route, against the live
OpenAPI schema rather than against anyone's memory of the code, so a mutation added
later — however well-intentioned — turns this file red.

The four never-touchable classes and why:

· **F4 evidence and its hash chain.** The whole product promise is that a third
  party can verify a detention claim. An evidence record an admin could edit is
  worth nothing in a dispute, and a hash chain with an edit path is not a chain.
· **F7 ledger postings.** Money is append-only. A correction is a new entry, not a
  changed one, and none of those corrections are in admin scope.
· **F10 crowd submissions and beliefs.** Moderation hides M13 *content*; nobody
  edits what drivers reported. A belief an operator can set is not crowd data, it
  is an opinion wearing crowd data's clothes (§11.7).
· **Other people's words.** Review and report TEXT is never edited — it is hidden
  or removed as a whole, with the author's words intact either way.
· **The audit log itself.** An editable audit log is not an audit log.
· **Detention clock events** (F3 geofence events / pings). They are the evidence
  behind the money.
"""

import pytest

from app.main import app

MUTATING = ("post", "put", "patch", "delete")


def _mutating_paths() -> set[str]:
    spec = app.openapi()["paths"]
    return {
        path for path, methods in spec.items() for method in methods if method.lower() in MUTATING
    }


def _all_paths() -> set[str]:
    return set(app.openapi()["paths"])


# --- the four constitutional carve-outs ---
@pytest.mark.parametrize(
    "forbidden",
    [
        "evidence_record",
        "evidence_log",
        "evidence_artifact",
        "chain_anchor",
    ],
)
def test_no_route_can_mutate_f4_evidence(forbidden):
    # an evidence record an admin could edit is worth nothing in a dispute
    for path in _mutating_paths():
        assert forbidden not in path


# AI-CONTEXT: the one mutating route allowed to name a receivable, and why the
# carve-out is narrow rather than a relaxation of the rule (§23 entry 108).
#
# The principle above is about POSTINGS: money is append-only, a correction is a new
# entry. A receivable's STATE is a different object — F7 ships `transition_receivable`
# with an ALLOWED_TRANSITIONS table precisely because `invoiced -> recovered` is a
# transition the ledger is designed to make. The blanket ban on the word "receivable"
# was true only because nothing in the product had ever called it, so the guard was
# broader than the principle it was written to protect.
#
# The allowance is ONE exact path, so a route that edited a receivable's AMOUNT, or any
# other receivable mutation, still turns this file red and has to argue for itself here.
LEDGER_STATE_CARVE_OUT = {"/money/receivable/{receivable_id}/paid"}


@pytest.mark.parametrize("forbidden", ["ledger", "posting", "journal_entry", "receivable"])
def test_no_route_can_mutate_f7_ledger_postings(forbidden):
    # money is append-only; a correction is a new entry, not a changed one
    for path in _mutating_paths() - LEDGER_STATE_CARVE_OUT:
        assert forbidden not in path


def test_the_ledger_carve_out_is_exactly_one_known_route():
    """The carve-out must not quietly become a category. If the named path ever stops
    existing, this fails and the exception is deleted rather than left lying around."""
    assert LEDGER_STATE_CARVE_OUT <= _mutating_paths()
    assert len(LEDGER_STATE_CARVE_OUT) == 1


def test_no_route_can_change_what_a_receivable_is_worth():
    """The half of the ban that is NOT carved out: state may transition, amounts may
    not be edited. This is what the blanket rule was really protecting."""
    schema = app.openapi()
    for path in LEDGER_STATE_CARVE_OUT:
        for method, spec in schema["paths"][path].items():
            if method.lower() not in MUTATING:
                continue
            body = spec.get("requestBody")
            assert body is None, f"{method} {path} takes a body and could carry an amount"


@pytest.mark.parametrize("forbidden", ["belief", "submission", "contributor_trust"])
def test_no_route_can_mutate_f10_crowd_data(forbidden):
    # a belief an operator can set is an opinion wearing crowd data's clothes
    for path in _mutating_paths():
        assert forbidden not in path


def test_no_route_can_mutate_the_audit_log():
    # an editable audit log is not an audit log. Scoped to the ADMIN audit route —
    # /money/settlements/audit is a driver's settlement audit and unrelated.
    for path in _mutating_paths():
        assert "admin_action" not in path
        assert not path.startswith("/admin/audit")


@pytest.mark.parametrize("forbidden", ["geofence_event", "location_ping", "geofence_presence"])
def test_no_route_can_mutate_the_detention_clock_evidence(forbidden):
    for path in _mutating_paths():
        assert forbidden not in path


# --- others' words are hidden or removed, never edited ---
def test_moderation_hides_content_it_never_edits_the_text():
    """A moderator's verbs are uphold / dismiss / frivolous. None of them accept
    replacement text, because the author's words survive the verdict either way."""
    from app.api.admin import ResolveReportIn

    fields = set(ResolveReportIn.model_fields)
    assert fields == {"approve", "reason", "frivolous"}
    # `reason` is the MODERATOR's note about the decision, not the author's content
    assert "text" not in fields
    assert "body" not in fields


def test_the_review_moderation_path_carries_no_text_field():
    from app.api.admin import DecideIn

    assert set(DecideIn.model_fields) == {"approve", "reason"}


# --- the positive half of the principle: what IS settable is reachable ---
def test_everything_declared_settable_has_a_console_route():
    """The other half of decision 8 — a thing we call admin-settable must actually
    be reachable, or the classification is a fiction."""
    paths = _all_paths()
    expected = [
        "/admin/flags",  # feature flags
        "/admin/config",  # runtime config registry
        "/admin/moderation",  # moderation queue
        "/admin/vendors",  # vendor roster
        "/admin/claims",  # facility claims
        "/admin/ingest",  # source config + freshness
    ]
    for route in expected:
        assert route in paths, f"declared settable but unreachable: {route}"


def test_admin_mutations_are_confined_to_the_admin_surface():
    """Every mutating admin route lives under /admin. A console power that hides on
    another router is a power nobody reviews."""
    admin_mutations = {p for p in _mutating_paths() if "/admin" in p}
    assert admin_mutations
    for path in admin_mutations:
        assert path.startswith("/admin/")
