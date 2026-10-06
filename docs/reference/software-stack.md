# Software stack notes

| Need | Choice | Why / reference |
| :-- | :-- | :-- |
| Language | **Python 3** (asyncio) | README prefers Python; CircuitPython/Blinka has **no PocketBeagle 2 board support** (`import board` → `NotImplementedError`, confirmed in the sibling light-desk project). We use plain Linux interfaces instead: `/dev/i2c-N`, `/dev/spidev`, libgpiod, ALSA. |
| Audio playback | **mpv** (`--idle`, JSON IPC) | plays mp3/flac/ogg/wav/m4a, gap-less playlists, reports `time-pos`, `duration`, `pause`, `playlist-pos`, metadata. IPC: <https://mpv.io/manual/stable/#json-ipc> |
| Recording | `arecord -D plughw:CARD=haptic -f S16_LE -r 44100 -c 2` | tiny, robust; SIGINT finalises the WAV header |
| Volume/mixer | `amixer -c haptic sset …` | applied at start (root is read-only, `alsactl store` is impossible) |
| Buttons | libgpiod v2 (`python3-libgpiod`) edge events | package is a system package → venv uses `--system-site-packages` |
| NFC | own minimal PN532 I²C driver (`haptic_player/pn532.py`) | `adafruit-circuitpython-pn532` needs Blinka/`busio` |
| Display | own ST7789 driver on spidev + Pillow + numpy | no fbtft/DRM overlay needed |
| Metadata | `mutagen` (optional; falls back to file names) | ID3/Vorbis/MP4 tags + embedded cover art |
| Web server | `aiohttp` (REST + WebSocket + static files) | one process, one event loop, Debian package `python3-aiohttp` |
| Web UI | **Vue 3 + Quasar** (Vite build) | as requested in the README; `webui/` |
| Why not Node | audio/NFC/SPI/GPIO libs and the sibling projects are Python; one language for the whole device side | – |

### libgpiod line lookup
Lines are addressed as `GPIOx_y` (official table notation) → resolved to the chip whose label starts with
`600000.gpio` (x=0) / `601000.gpio` (x=1) (AM62x `main_gpio0/1`), falling back to the kernel's named lines
(`gpioinfo`, e.g. `P2.02`) if given as a header name.
