"""Child processes (mpv, arecord) must never outlive the backend - even when it is killed hard (SIGKILL), an
orphaned mpv would keep playing."""

from __future__ import annotations

import ctypes
import signal
import sys

PR_SET_PDEATHSIG = 1


def die_with_parent() -> None:
    """preexec_fn: ask the kernel to SIGTERM this child when the parent process dies (Linux only)."""
    if sys.platform.startswith("linux"):
        ctypes.CDLL(None).prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
