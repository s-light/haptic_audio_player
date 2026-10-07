import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="PR_SET_PDEATHSIG is Linux only")
def test_child_dies_when_parent_is_killed_hard():
    parent = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(f"""
            import subprocess, sys, time
            sys.path.insert(0, {str(ROOT)!r})
            from haptic_player.proc import die_with_parent
            child = subprocess.Popen(["sleep", "60"], preexec_fn=die_with_parent)
            print(child.pid, flush=True)
            time.sleep(60)
        """)],
        stdout=subprocess.PIPE, text=True,
    )
    child_pid = int(parent.stdout.readline())
    os.kill(child_pid, 0)  # alive
    parent.send_signal(signal.SIGKILL)  # no chance to clean up
    parent.wait()
    for _ in range(50):
        try:
            os.kill(child_pid, 0)
            # zombie (not reaped by init yet) counts as dead
            if Path(f"/proc/{child_pid}/stat").read_text().split()[2] == "Z":
                break
        except (ProcessLookupError, FileNotFoundError):
            break
        time.sleep(0.1)
    else:
        os.kill(child_pid, signal.SIGKILL)
        pytest.fail("child survived its parent")
