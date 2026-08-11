import threading
from contextlib import contextmanager

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


# AI-CONTEXT: the concurrency bound lives WITH the expensive operation (finding F1-6).
#
# It used to be acquired in `authenticate`, which meant it protected the one call site that
# remembered to — and `build_secret_ref` on the registration path, at a cost per request at
# least equal to a verify, ran with no bound at all. A limit a caller has to remember is a
# limit the next caller forgets.
#
# TWO POOLS, NOT ONE, and the split is the whole point. A shared pool means a registration
# flood sheds LOGINS: every honest driver trying to reach their detention clock during an
# attack is turned away by the attacker's traffic. Separate pools mean the flood sheds only
# registrations, and existing drivers keep signing in.
#
# Creation gets the SMALLER pool deliberately. Verification is the operation the product
# depends on minute to minute; account creation is rare, and rationing it harder costs a
# handful of would-be signups during an attack rather than everyone's access.
#
# Both shed IMMEDIATELY (`blocking=False`) and never queue: a queued request holds a
# threadpool worker, which is the resource being protected.
VERIFY_SLOTS = threading.BoundedSemaphore(8)
HASH_SLOTS = threading.BoundedSemaphore(4)


class VerifierBusy(Exception):
    """Every slot for this operation is in use — shed load rather than fall over."""


@contextmanager
def slot(pool: threading.BoundedSemaphore):
    if not pool.acquire(blocking=False):
        raise VerifierBusy()
    try:
        yield
    finally:
        pool.release()
