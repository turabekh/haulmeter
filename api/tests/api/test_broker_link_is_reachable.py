"""AI-CONTEXT: the link in a broker's email must reach the DOCUMENT, not the driver app.

Found by the owner asking whether the shared link required a sign-in. It did — not because
the route asks for one, but because the link never reached the route.

`PUBLIC_BASE_URL` + `/pack/s/<token>` is what goes into every counterparty email. The API
serves `/pack/s/{token}` with no session dependency, exactly as §23 specifies ("no session,
because an accounts-payable clerk will not make an account to read what a driver sent
them"). But the edge proxied only `/api/*`, so the link fell through to the SPA's
`try_files` catch-all and answered **HTTP 200 with index.html** — whose router guard sends
an unauthenticated visitor to sign-in. Measured against the live domain:

    https://haulmeter.online/pack/s/<token>      200  text/html   <- the driver app
    https://haulmeter.online/api/pack/s/<token>  404              <- the real route

A broker clicking the evidence behind a detention claim got a login screen for a trucking
app. It had never worked in production, and F-01 hid it: no counterparty email left the box
until the day this was found, so nobody had ever clicked one.

THIS IS THE THIRD INSTANCE OF ONE DEFECT CLASS IN THIS SESSION — a URL correct in the
process that mints it and wrong in the process that fetches it. `media_url` broke every
contact sheet the same way. A path is not a URL until something decides what host and
prefix it hangs off, and the code that mints it never sees that decision.

WHY A TEST AND NOT JUST A LINE IN THE CADDYFILE. The routing is invisible from the
application: nothing in Python or Vue changes when the edge stops forwarding a path, and
every test in this suite talks to the router directly, where the bug does not exist. The
invariant is therefore asserted against the edge config itself, the same way
`test_compose_migration_order.py` asserts an ordering no unit test could see.
"""

import pathlib
import re

import pytest

# AI-CONTEXT: the same resolution `test_compose_migration_order.py` uses — `infra/` is
# mounted at /repo/infra in the test container and sits beside `api/` on a laptop. It
# ASSERTS rather than skips when neither exists: a check that skips reports nothing while
# looking like it passed.
_MOUNTED = pathlib.Path("/repo/infra/Caddyfile")
_LOCAL = pathlib.Path(__file__).resolve().parents[3] / "infra" / "Caddyfile"
CADDYFILE = _MOUNTED if _MOUNTED.exists() else _LOCAL


@pytest.fixture(scope="module")
def caddy() -> str:
    assert CADDYFILE.exists(), f"the edge config moved: {CADDYFILE}"
    return CADDYFILE.read_text()


def test_the_pack_link_is_proxied_to_the_api(caddy):
    """Without this the link is answered by the SPA and the broker sees a login screen."""
    assert re.search(r"handle\s+/pack/\*\s*\{[^}]*reverse_proxy\s+api:", caddy), (
        "no /pack/* route to the API — every link in a counterparty email reaches the "
        "driver app instead of the document"
    )


def test_the_prefix_is_preserved(caddy):
    """`handle_path` would strip `/pack`, and the API's route really is `/pack/s/{token}`.

    The `/api` block above it strips deliberately — that prefix is ours and the routers
    know nothing about it. This one is the route's own path and must survive.
    """
    block = re.search(r"handle(_path)?\s+/pack/\*\s*\{", caddy)
    assert block is not None, "the /pack route is missing entirely"
    assert block.group(1) is None, (
        "handle_path strips the prefix, so the API would receive /s/<token> and 404"
    )


def test_the_broker_facing_link_carries_no_api_prefix(caddy):
    """§17 asks for one plain link, and this is the only URL in the product a stranger
    reads. Routing `/pack` directly is what keeps `/api` out of it."""
    from app.foundation.f04_evidence.domain import sharing

    source = pathlib.Path(sharing.__file__).read_text()
    assert "/pack/s/" in source
    assert "/api/pack" not in source, (
        "an /api prefix in a counterparty link would work and would be the wrong fix — "
        "the edge exists so the link a clerk reads does not have to describe our routing"
    )


def test_the_spa_catch_all_still_exists(caddy):
    """The other half: deep links into the app (§13.5 requires notifications to use them)
    must still be answered by index.html rather than a filesystem 404."""
    assert "try_files {path} /index.html" in caddy
