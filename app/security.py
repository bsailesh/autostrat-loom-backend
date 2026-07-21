"""
Password hashing using only the Python standard library (PBKDF2-HMAC-SHA256,
100k iterations, random salt per password) — no extra dependency to install.
Good enough for a functioning demo/pilot; for a hardened production
deployment, swapping to passlib/bcrypt or argon2 here is a one-file change,
since every caller only ever uses hash_password/verify_password.
"""
import hashlib
import hmac
import os

_ITERATIONS = 100_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, hash_hex = stored.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return hmac.compare_digest(derived.hex(), hash_hex)
