"""haptic_player entry point.

    python -m haptic_player --data-dir /srv/haptic
    python -m haptic_player --simulate --data-dir /tmp/haptic     # no hardware needed (UI/dev)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import tempfile
from pathlib import Path

from aiohttp import web

from .audio import init_mixer
from .buttons import Buttons
from .config import load_config
from .controller import Controller
from .display import make_display
from .library import Library
from .nfc import NfcReader
from .player import make_player
from .recorder import Recorder
from .storage import FakeBackend, Storage, SysfsBackend
from .tags import TagStore
from .web import create_app

log = logging.getLogger("haptic")


async def run(args: argparse.Namespace) -> None:
    cfg = load_config(args.data_dir, simulate=args.simulate or None, port=args.port, host=args.host)
    if cfg.simulate:
        cfg.runtime_dir = Path(tempfile.gettempdir()) / "haptic-run"
    try:
        cfg.ensure_dirs()
    except OSError as e:
        log.error("data dir %s not usable (%s) - is the HAPTIC partition mounted? continuing without library", cfg.data_dir, e)
    loop = asyncio.get_running_loop()

    library = await asyncio.to_thread(Library, cfg.music_dir)
    tags = TagStore(cfg.tags_file)
    player = make_player(cfg)
    recorder = Recorder(cfg)
    ctl = Controller(cfg, player, recorder, library, tags)

    await player.start(cfg.volume)
    await init_mixer(cfg)

    png = cfg.runtime_dir / "display.png"
    display = make_display(cfg.display, cfg.simulate, png)
    if display:
        ctl.view_sink = display.update
        ctl.notify()

    def call(coro):
        asyncio.run_coroutine_threadsafe(coro, loop)

    nfc = buttons = None
    if not cfg.simulate:
        if cfg.nfc.enabled:
            nfc = NfcReader(cfg.nfc, lambda uid: call(ctl.handle_tag(uid)), lambda: call(ctl.handle_tag_removed()))
            nfc.start()

            async def watch_nfc():
                while True:
                    if ctl.nfc_ok != nfc.ok:
                        ctl.nfc_ok = nfc.ok
                        ctl.notify()
                    await asyncio.sleep(2)

            asyncio.create_task(watch_nfc())
        pins = {"play_pause": cfg.pins.play_pause, "record": cfg.pins.record, "prev": cfg.pins.prev, "next": cfg.pins.next}
        buttons = Buttons(pins, cfg.long_press_s, lambda n, k: call(ctl.handle_button(n, k)))
        buttons.start()

    storage = Storage(cfg.usb, FakeBackend() if cfg.simulate else SysfsBackend(), before_computer=ctl.stop,
                      after_player=ctl.reload_data, on_change=ctl.notify)
    ctl.storage = storage
    storage_task = asyncio.create_task(storage.watch())

    runner = web.AppRunner(create_app(cfg, ctl, png))
    await runner.setup()
    await web.TCPSite(runner, cfg.host, cfg.port).start()
    log.info("web UI on http://%s:%d  (data: %s%s)", cfg.host, cfg.port, cfg.data_dir, ", SIMULATE" if cfg.simulate else "")

    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()

    log.info("shutting down")
    storage_task.cancel()
    if storage.mode == "computer":
        await storage.to_player()  # leave the stick mounted for the next boot
    if recorder.active:
        await recorder.stop()
    for t in (nfc, buttons):
        if t:
            t.stop()
    if display:
        display.stop()
    await runner.cleanup()
    await player.close()


def main() -> None:
    ap = argparse.ArgumentParser(prog="haptic_player")
    ap.add_argument("--data-dir", default=None, help="writable data partition (default /srv/haptic)")
    ap.add_argument("--simulate", action="store_true", help="no GPIO/I2C/SPI/ALSA: fake tag scans via /api/dev/*, display as PNG")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
