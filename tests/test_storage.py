import json

import pytest

from haptic_player import usbgadget
from haptic_player.config import UsbConfig
from haptic_player.storage import FakeBackend, Storage


@pytest.fixture
def env():
    backend, calls = FakeBackend(), []

    async def before():
        calls.append("before")

    async def after():
        calls.append("after")

    st = Storage(UsbConfig(debounce_s=2.0), backend, before, after, lambda: calls.append("changed"))
    return st, backend, calls


async def test_auto_switch_after_debounce_and_back_on_unplug(env):
    st, backend, calls = env
    await st.tick(0)
    assert st.mode == "player" and st.available
    backend.state.host = True
    await st.tick(10.0)
    assert st.mode == "player"  # not stable yet
    await st.tick(11.0)
    assert st.mode == "player"
    await st.tick(12.5)
    assert st.mode == "computer" and backend.state.attached and "before" in calls
    backend.state.host = False
    await st.tick(13.0)
    assert st.mode == "player" and not backend.state.attached and calls[-2:] != ["before"] and "after" in calls


async def test_user_switch_back_sticks_until_reconnect(env):
    st, backend, _ = env
    backend.state.host = True
    await st.tick(0)
    await st.tick(3)
    assert st.mode == "computer"
    assert await st.to_player(user=True)
    for t in (4, 8, 20):  # still connected, but the user said "player"
        await st.tick(t)
        assert st.mode == "player"
    backend.state.host = False
    await st.tick(21)
    backend.state.host = True
    await st.tick(22)
    await st.tick(25)
    assert st.mode == "computer"  # new connection -> auto again


async def test_eject_on_computer_gives_stick_back(env):
    st, backend, _ = env
    backend.state.host = True
    await st.tick(0)
    await st.tick(3)
    assert st.mode == "computer"
    backend.state.attached = False  # kernel clears the medium when the computer ejects
    await st.tick(4)
    assert st.mode == "player"
    await st.tick(9)
    assert st.mode == "player"  # no immediate re-attach


async def test_attach_failure_does_not_loop_and_manual_needs_host(env):
    st, backend, _ = env
    assert not await st.to_computer(user=True)
    assert "Computer" in st.error
    backend.state.host = True
    backend.fail_attach = "cannot unmount /srv/haptic: busy"
    await st.tick(0)
    await st.tick(3)
    assert st.mode == "player" and "busy" in st.error
    backend.fail_attach = ""
    await st.tick(10)
    assert st.mode == "player"  # override: no retry loop
    assert await st.to_computer(user=True)  # manual retry works


async def test_not_set_up_and_disabled(env):
    st, backend, _ = env
    backend.state.function = False
    backend.state.host = True
    await st.tick(0)
    await st.tick(5)
    assert st.mode == "player" and not st.available
    backend.state.function = True
    st.cfg.auto_switch = False
    await st.tick(10)
    assert st.mode == "player"


async def test_attached_before_start_is_adopted(env):
    st, backend, _ = env
    backend.state.host = backend.state.attached = True
    await st.tick(0)
    assert st.mode == "computer"


def test_usbgadget_state_reading(tmp_path):
    root, udc = tmp_path / "usb_gadget", tmp_path / "udc"
    (root / "g_multi" / "functions" / usbgadget.FUNCTION / "lun.0").mkdir(parents=True)
    (root / "g_multi" / "UDC").write_text("fe200000.usb\n")
    (root / "other").mkdir()
    (root / "g_multi" / "functions" / usbgadget.FUNCTION / "lun.0" / "file").write_text("\n")
    (udc / "fe200000.usb").mkdir(parents=True)
    (udc / "fe200000.usb" / "state").write_text("configured\n")
    assert usbgadget.find_gadget(root).name == "g_multi"  # the one owning the UDC
    st = usbgadget.read_state(root, udc)
    assert st == {"function": True, "host": True, "udc": "configured", "attached": False}
    (root / "g_multi" / "functions" / usbgadget.FUNCTION / "lun.0" / "file").write_text("/dev/sda1\n")
    (udc / "fe200000.usb" / "state").write_text("powered\n")
    st = usbgadget.read_state(root, udc)
    assert st["attached"] and not st["host"]
    assert usbgadget.read_state(tmp_path / "none", tmp_path / "none2") == {"function": False, "host": False, "udc": "none", "attached": False}
    json.dumps(st)
