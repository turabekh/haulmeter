"""AI-CONTEXT: Operating-authority verification seam for F1 (PRD §7.1, Decision 190).

Backs the self-declared authority a driver picks at onboarding with a real FMCSA
lookup. Same key-gated shape as the F9 model provider: the deterministic
FakeAuthorityVerifier runs everywhere without a key (and in every test); the real
FmcsaVerifier hits the FMCSA QCMobile REST API only when a webKey is configured;
StubAuthorityVerifier fails loud until wired. Verification STRENGTHENS a claim's
credibility (verified legal name + MC# on the invoice) — it never gates the right
to invoice, which stays self-declared so onboarding stays under 60 s.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class VerificationResult:
    found: bool
    allowed_to_operate: bool
    legal_name: str | None = None
    dot_number: str | None = None
    mc_number: str | None = None
    raw: dict = field(default_factory=dict)


class AuthorityVerifier(Protocol):
    def verify(self, mc_number: str | None, dot_number: str | None) -> VerificationResult: ...


def _digits(value: str | None) -> str | None:
    if not value:
        return None
    kept = "".join(ch for ch in value if ch.isdigit())
    return kept or None


class FakeAuthorityVerifier:
    """Deterministic test double. Any lookup carrying at least one identifier
    resolves to an active carrier whose legal name is derived from the number, so
    tests are fully reproducible with no network. `deny` forces a not-authorized
    result so the failed path is exercisable without special-casing an identifier."""

    def __init__(self, deny: bool = False) -> None:
        self._deny = deny

    def verify(self, mc_number: str | None, dot_number: str | None) -> VerificationResult:
        mc, dot = _digits(mc_number), _digits(dot_number)
        if mc is None and dot is None:
            return VerificationResult(found=False, allowed_to_operate=False)
        anchor = mc or dot
        return VerificationResult(
            found=True,
            allowed_to_operate=not self._deny,
            legal_name=f"CARRIER {anchor} LLC",
            dot_number=dot,
            mc_number=mc,
            raw={"source": "fake", "allowedToOperate": "N" if self._deny else "Y"},
        )


class StubAuthorityVerifier:
    def verify(self, mc_number: str | None, dot_number: str | None) -> VerificationResult:
        raise NotImplementedError("FMCSA verifier is a seam; wired at activation")


# --- Real adapter: FMCSA QCMobile REST (the F1 verification activation) ---
_FMCSA_BASE = "https://mobile.fmcsa.dot.gov/qc/services/carriers"


def _fmcsa_lookup(webkey: str, mc_number: str | None, dot_number: str | None) -> dict:
    # single HTTP GET to QCMobile; kept as a module function so tests monkeypatch it
    # without touching the network. Prefers the DOT lookup (canonical carrier
    # record); falls back to the docket (MC#) endpoint. Returns the carrier dict.
    import httpx

    mc, dot = _digits(mc_number), _digits(dot_number)
    if dot is not None:
        url = f"{_FMCSA_BASE}/{dot}"
    elif mc is not None:
        url = f"{_FMCSA_BASE}/docket-number/{mc}"
    else:
        return {}
    resp = httpx.get(url, params={"webKey": webkey}, timeout=30.0)
    resp.raise_for_status()
    body = resp.json()
    content = body.get("content")
    if isinstance(content, list):  # docket lookup returns a list of matches
        content = content[0] if content else None
    if isinstance(content, dict):
        return content.get("carrier", content)
    return {}


class FmcsaVerifier:
    """Live FMCSA adapter. Maps the QCMobile carrier record onto VerificationResult;
    an unreachable API or a carrier not cleared to operate resolves to a `failed`
    (not-authorized) result the service records without blocking the driver."""

    def __init__(self, webkey: str) -> None:
        self._webkey = webkey

    def verify(self, mc_number: str | None, dot_number: str | None) -> VerificationResult:
        try:
            carrier = _fmcsa_lookup(self._webkey, mc_number, dot_number)
        except Exception:  # network / 4xx / 5xx -> unverified, never a hard error
            return VerificationResult(found=False, allowed_to_operate=False)
        if not carrier:
            return VerificationResult(found=False, allowed_to_operate=False)
        allowed = str(carrier.get("allowedToOperate", "")).strip().upper() == "Y"
        dot = carrier.get("dotNumber")
        return VerificationResult(
            found=True,
            allowed_to_operate=allowed,
            legal_name=carrier.get("legalName") or carrier.get("dbaName"),
            dot_number=str(dot) if dot is not None else _digits(dot_number),
            mc_number=_digits(mc_number),
            raw=carrier,
        )


def resolve_verifier() -> AuthorityVerifier:
    # the live FMCSA verifier when a webKey is set (F1 verification activated), else
    # the deterministic Fake — the same shape the app has always run on without a key.
    from app.core.config import get_settings

    settings = get_settings()
    if settings.fmcsa_webkey:
        return FmcsaVerifier(settings.fmcsa_webkey)
    return FakeAuthorityVerifier()
