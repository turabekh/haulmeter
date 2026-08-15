"""AI-CONTEXT: the pasted provider key, encrypted at rest (owner decision, 2026-08-15).

The kickoff put the key in a `connector` column and said explicitly that a better home is
a handoff note rather than an improvisation, so it was asked rather than chosen. What
settled it is not the public repo — the key was never going to be committed — it is
`scripts/backup_db.sh`: this database is dumped nightly and uploaded offsite to a GCS
bucket, and A12 made that upload a REQUIRED step. A plaintext column therefore ships a
working key to somebody else's fleet telematics into a bucket, every night, forever.

AES-GCM, because the key must come back out (it is presented to Motive on every poll) and
because GCM authenticates: a tampered ciphertext fails rather than decrypting to garbage
that gets sent to a provider as a credential.

THE SECRET LIVES IN `infra/.env` AND NOWHERE ELSE. `0600 root:root` on the VM, excluded by
`deploy.sh` so a deploy cannot overwrite the box's copy, and present in `.env.example` only
as an empty placeholder. It is deliberately NOT derived from anything in the repo.

WHEN IT IS UNSET: encryption REFUSES rather than falling back to plaintext. A silent
fallback is how a security control becomes decorative — the same shape as
`register_flag(enabled=True)` bypassing the gates for six modules (audit F-02). A fleet
that cannot be connected is a visible problem; a fleet connected with an unprotected key
is an invisible one.
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SECRET_ENV = "M14_CONNECTOR_KEY"
_NONCE_BYTES = 12


class ConnectorKeyUnavailable(Exception):
    """`M14_CONNECTOR_KEY` is unset or unusable — refuse, never fall back to plaintext."""


def _cipher() -> AESGCM:
    raw = os.environ.get(SECRET_ENV, "").strip()
    if not raw:
        raise ConnectorKeyUnavailable(
            f"{SECRET_ENV} is not set — a connector key cannot be stored without it"
        )
    try:
        key = base64.urlsafe_b64decode(raw)
    except Exception as exc:  # noqa: BLE001 — any decode failure is the same refusal
        raise ConnectorKeyUnavailable(f"{SECRET_ENV} is not valid base64") from exc
    if len(key) not in (16, 24, 32):
        raise ConnectorKeyUnavailable(
            f"{SECRET_ENV} must decode to 16, 24 or 32 bytes (got {len(key)})"
        )
    return AESGCM(key)


def encrypt_key(plaintext: str) -> str:
    """Ciphertext as one base64 string: nonce ‖ ct. A fresh nonce per call — GCM's one
    unbreakable rule is never reusing a nonce under the same key."""
    aes = _cipher()
    nonce = os.urandom(_NONCE_BYTES)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def decrypt_key(stored: str) -> str:
    aes = _cipher()
    blob = base64.urlsafe_b64decode(stored.encode("ascii"))
    nonce, ct = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    return aes.decrypt(nonce, ct, None).decode("utf-8")


def last4(plaintext: str) -> str:
    """The only part of a key any screen may see. Four characters is enough for an
    operator to tell which key is installed and useless to anyone who reads it."""
    return plaintext[-4:] if len(plaintext) >= 4 else plaintext
