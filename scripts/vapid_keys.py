"""AI-CONTEXT: generate a VAPID keypair for Web Push (§23 entry 111).

This is why push needs no vendor account: the pair is SELF-generated. VAPID (RFC 8292)
identifies this application server to a push service by signing each request with a
P-256 key the service has never seen before — there is no registration step and nobody
to ask.

The encodings are the fiddly part and are not interchangeable:

  · PUBLIC  — the uncompressed EC point (65 bytes, X9.62), base64url, unpadded. This is
    the exact byte string a browser passes as `applicationServerKey`, so getting it
    wrong surfaces as an opaque DOMException in the client rather than as an error here.
  · PRIVATE — the raw 32-byte scalar, base64url, unpadded. `pywebpush` hands this to
    `Vapid01.from_string`.

It PRINTS rather than writing: the private key is a secret, infra/.env is never
generated over (rule 9), and an operator pasting it in deliberately is the point.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def generate() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    private = key.private_numbers().private_value.to_bytes(32, "big")
    return _b64(public), _b64(private)


def main() -> None:
    public, private = generate()
    print()
    print(f"VAPID_PUBLIC_KEY={public}")
    print(f"VAPID_PRIVATE_KEY={private}")
    print()
    print("Paste both into infra/.env, then restart the api and worker.")
    print("Rotating these INVALIDATES every stored subscription — drivers must re-enable.")


if __name__ == "__main__":
    main()
