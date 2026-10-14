import threading

# shortcut: one lock per lead, kept for the life of the process and valid for a single process only;
# move to a PostgreSQL advisory lock before running more than one worker
_locks: dict[int, threading.Lock] = {}
_guard = threading.Lock()


def lock_for(lead_id) -> threading.Lock:
    """The lock that serialises everything that writes one lead's conversation: replies, nudges and deletion."""
    with _guard:
        return _locks.setdefault(lead_id, threading.Lock())
