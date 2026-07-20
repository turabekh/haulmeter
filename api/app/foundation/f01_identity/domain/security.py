from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(secret_ref: str, plain: str) -> bool:
    try:
        return _hasher.verify(secret_ref, plain)
    except VerifyMismatchError:
        return False


def needs_rehash(secret_ref: str) -> bool:
    return _hasher.check_needs_rehash(secret_ref)
