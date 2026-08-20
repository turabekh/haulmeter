"""AI-CONTEXT: N-02's last mile — the language a driver PICKS reaches their alerts.

N-02 localized every driver notification: six modules' message tables, the fallback to
compiled English, the tests. It resolves the language from `f01.driver_profile.locale`.

Nothing ever wrote that column. `f15.set_user_locale` existed and was exported and was
called by tests and by nothing else; the UI's `setLocale` wrote `localStorage` and stopped
there. So every profile on production read `en`, and a driver running the app in Uzbek got
their detention alert in English — the whole catalogue built, shipped and never once
reached by a real driver, with nothing failing to say so.

These tests are the seam that was missing. The end-to-end one is the point: it asserts a
DISPATCHED notification comes out in the language the driver chose through the API they
actually use, rather than one a test set by calling the service function itself.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f08_notifications import public as notify
from app.foundation.f15_localization import public as localization
from app.main import app


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _register(client, email="locale-driver@example.com"):
    resp = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    assert resp.status_code == 201, resp.text
    return resp.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_a_driver_can_tell_the_server_which_language_they_chose(client):
    token = _register(client)

    resp = client.patch("/auth/locale", json={"locale": "uz"}, headers=_auth(token))

    assert resp.status_code == 200, resp.text
    assert resp.json()["locale"] == "uz"


def test_me_reports_it_back_so_a_new_device_can_adopt_it(client):
    token = _register(client, "locale-newphone@example.com")
    client.patch("/auth/locale", json={"locale": "ru"}, headers=_auth(token))

    me = client.get("/auth/me", headers=_auth(token))

    assert me.status_code == 200, me.text
    assert me.json()["locale"] == "ru"


def test_a_fresh_account_reports_the_default_rather_than_nothing(client):
    # a new device with no stored choice adopts what the server says, so the server must
    # always say something a client can use
    token = _register(client, "locale-fresh@example.com")

    assert client.get("/auth/me", headers=_auth(token)).json()["locale"] == (
        localization.DEFAULT_LOCALE
    )


def test_a_language_outside_the_six_is_refused(client):
    token = _register(client, "locale-bad@example.com")

    resp = client.patch("/auth/locale", json={"locale": "fr"}, headers=_auth(token))

    assert resp.status_code == 422, resp.text


def test_it_needs_a_session(client):
    assert client.patch("/auth/locale", json={"locale": "uz"}).status_code in (401, 403)


def test_the_alert_a_driver_receives_is_in_the_language_they_picked(client, db):
    """THE ONE THAT WOULD HAVE CAUGHT IT.

    Every existing localization test sets the locale by calling `set_user_locale` itself,
    which is why they all passed over a product where nothing called it. This one goes
    through the endpoint a driver's app uses, then dispatches, then reads the text.
    """
    from app.modules.m03_detention.domain import messages as m03_messages

    reg = client.post(
        "/auth/register",
        json={"email": "locale-alert@example.com", "password": "pw-123456"},
    )
    token = reg.json()["token"]
    account_id = uuid.UUID(reg.json()["account_id"])
    client.patch("/auth/locale", json={"locale": "uz"}, headers=_auth(token))

    # the catalogue reaches the DB at module registration on boot; production carries all
    # six locales (verified: 64 strings each). This test DB has not booted a module, so it
    # registers the same table the same way rather than asserting against an empty catalog
    localization.register_catalogue(db, m03_messages.KEY_PREFIX, m03_messages.ALERT_MESSAGES)

    key = next(iter(m03_messages.ALERT_MESSAGES))
    english = m03_messages.ALERT_MESSAGES[key]["en"]
    uzbek = m03_messages.ALERT_MESSAGES[key]["uz"]

    text = notify.localized_text(db, account_id, f"{m03_messages.KEY_PREFIX}{key}", english)

    assert text == uzbek, "the driver chose Uzbek through the app; the alert must follow"
    assert text != english


def test_a_counterparty_never_receives_the_drivers_language(client, db):
    """A broker's inbox is English whatever the driver chose (F15). The same column now
    moves, so this pins the boundary it must not cross."""
    assert localization.resolve_locale(localization.LocaleAudience.counterparty, "uz") == "en"
    assert localization.resolve_locale(localization.LocaleAudience.driver, "uz") == "uz"
