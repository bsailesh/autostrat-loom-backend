"""
Password hashing.

New hashes use bcrypt (via the `bcrypt` package — not a hand-rolled scheme).
`verify_password` also still accepts the earlier stdlib PBKDF2 format
(`<salt_hex>$<hash_hex>`) so any pre-Phase-2 rows keep working; those verify
against the legacy path and are transparently left as-is until the user next
sets a password. Every caller only ever touches hash_password/verify_password,
so the algorithm behind them can change again without rippling outward.
"""
import hashlib
import hmac

import bcrypt

# bcrypt only considers the first 72 bytes of the input. That's plenty for a
# real password; we encode to bytes and let bcrypt do its own truncation rather
# than pre-hashing (which would be "rolling our own" again).
_BCRYPT_ROUNDS = 12

# Legacy PBKDF2 parameters — only used to verify old stored hashes.
_PBKDF2_ITERATIONS = 100_000


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(_BCRYPT_ROUNDS))
    return hashed.decode("utf-8")


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("$2"):  # bcrypt hashes start with $2a$ / $2b$ / $2y$
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
        except ValueError:
            return False
    return _verify_legacy_pbkdf2(password, stored)


def _verify_legacy_pbkdf2(password: str, stored: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return hmac.compare_digest(derived.hex(), hash_hex)
