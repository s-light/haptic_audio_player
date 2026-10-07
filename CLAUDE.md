# haptic_audio_player

Child-friendly haptic audio player on a PocketBeagle 2: RFID tag selects album/track/recording slot, push buttons
for play/pause/record/prev/next, optional ST7789 display, Vue/Quasar web UI, read-only root.
README.md = requirements, docs/PLAN.md = decisions + architecture, docs/reference/ = fetched reference material,
docs/BRING-UP.md = hardware checklist (**nothing here has run on real hardware yet**).

## Repo map
- `haptic_player/` — device software (Python 3.11+, asyncio). `controller.py` is the hub (tags/buttons/web →
  player/recorder); `player.py` (mpv JSON IPC + FakePlayer), `pn532.py`/`nfc.py` (own I²C driver, no Blinka),
  `buttons.py`/`gpio.py` (libgpiod v2), `display.py` (Renderer + ST7789 over spidev), `web.py` (aiohttp REST + `/ws`),
  `storage.py` (who owns the data stick: player or connected computer, auto-switch watcher) + `usbgadget.py` (root helper: adds a mass-storage function to the stock USB-network gadget), `config.py` (defaults < `<data_dir>/config.toml`).
- `webui/` — Quasar CLI (`@quasar/app-vite` 3) + Vue 3 + TypeScript + Pinia, filename-based routing (`src/pages/index.vue` =
  layout, `src/pages/index/*.vue` = pages). API types in `src/api.ts`, live state in `src/stores/player.ts`.
  `pnpm dev` (proxies `/api` + `/ws` to a local `--simulate` server on :8080), `pnpm build` → `webui/dist/spa` (served by
  `web.py`), `pnpm typecheck`, `pnpm lint`. Needs Node >= 22.12 → on the board deploy a PC build with `webui/deploy.sh`.
- `overlays/k3-am62-pocketbeagle2-haptic-player.dtso` — McASP0 + WM8960 + sound card, SPI0/spidev, GPIO pads.
- `setup_pb2.py` + `haptic_setup.py` — idempotent setup steps (`--list-steps`); `readonly-root` is opt-in; `usb-gadget` (mass-storage next to the USB network) is a default step.
  `readwrite.sh` / `readonly.sh` remount `/`.
- `hw/generate-wiring-diagram.py` → `hw/wiring-diagram.svg` (rerun after changing pins; keep in sync with the overlay,
  `config.py` pin defaults and PLAN.md section 2).
- `tests/` — pytest (`pip install -e .[dev]`; `pytest`). No hardware needed.

## Conventions
- Writable state only on the data partition (`/srv/haptic`: `music/`, `recordings/`, `tags.json`, `config.toml`);
  write files atomically (`config.atomic_write`). Never write below `/` at runtime (root is read-only in production).
- Hardware access only via Linux interfaces (i2c-dev, spidev, libgpiod, ALSA) – Blinka does not support the PB2.
- GPIO pins are written as `GPIOx_y` (official pin table); pad offset = table address − 0xF4000.
- Dev without hardware: `python -m haptic_player --simulate --data-dir /tmp/haptic` (fake tag scans via
  `POST /api/dev/scan`, display frame at `/api/display.png`).
