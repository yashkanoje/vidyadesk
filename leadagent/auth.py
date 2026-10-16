"""Dashboard passwords and the limit on failed logins."""
import threading
import time
from collections import deque
from functools import lru_cache
import secrets

import bcrypt

MIN_LENGTH = 10
MAX_BYTES = 72  # bcrypt only uses the first 72 bytes of a password


class PasswordError(ValueError):
    """The new password is not acceptable. The message is safe to show."""


def check_new_password(password) -> None:
    if len(password) < MIN_LENGTH or len(password.encode()) > MAX_BYTES:
        raise PasswordError(f"A password needs at least {MIN_LENGTH} characters and at most {MAX_BYTES} bytes.")


def hash_password(password, rounds=12) -> str:
    check_new_password(password)
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=rounds)).decode()


def password_matches(password, password_hash) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:MAX_BYTES], password_hash.encode())
    except ValueError:  # not a bcrypt hash
        return False


@lru_cache
def dummy_hash() -> str:
    """Checked against when the email is unknown, so a wrong email takes as long as a wrong password."""
    return hash_password(secrets.token_urlsafe(32))


class LoginThrottle:
    """At most `limit` failed logins per key in `window` seconds.

    shortcut: kept in memory, so it resets on restart and works for one process only; move to the database before
    running more than one process.
    """

    def __init__(self, limit=5, window=900, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self._failures: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _recent(self, key):
        failures = self._failures.setdefault(key, deque())
        now = self.clock()
        while failures and now - failures[0] > self.window:
            failures.popleft()
        return failures

    def blocked(self, key) -> bool:
        with self._lock:
            return len(self._recent(key)) >= self.limit

    def failed(self, key) -> None:
        with self._lock:
            self._recent(key).append(self.clock())

    def succeeded(self, key) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
