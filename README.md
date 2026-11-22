# AK980 Manager

An English, open-source replacement for the Chinese-only software of the **AJAZZ AK980 (V2) PRO** keyboard
(USB `0C45:8009`). Written by reverse engineering the official app's USB/HID traffic — see [docs/PROTOCOL.md](docs/PROTOCOL.md).
Windows, Python 3.10+ (Tkinter), Pillow. Licensed under the **GNU GPL v3 or later**. Not affiliated with AJAZZ.

> **Use at your own risk.** This talks to your keyboard directly. It only sends the lighting, key map, macro, screen and
> settings commands the official app also sends; it has no firmware update and no factory reset. Still, it is unofficial.

## Features

| Tab | What it does |
|---|---|
| **Lighting** | built-in effects, colour, "colorful" rainbow, brightness, speed, direction |
| **Keys** | remap keys on the **Top** and **Fn** layer to a key, media key, modifier or macro; reset to defaults |
| **Macros** | text-typing macros (letters, digits, space) with a delay; assigned on the Keys tab |
| **Per-key** | paint every key with its own colour (user lighting) |
| **Screen** | upload PNG/JPG/GIF frames (240×135, up to 140) to the TFT screen; sync the clock |
| **System** | sleep time, key response level, Fn key Momentary / Toggle |

## Install and run

**Easiest - the packaged program:** download `AK980-Manager-windows.zip` from the
[Releases](https://github.com/j0p3s/AK980-Manager/releases) page, unzip it anywhere and double-click `AK980 Manager.exe` (a few supporting
files sit in the `lib` subfolder). Nothing else to install: the keyboard works through Windows' built-in HID driver, so no driver is needed.
It checks GitHub Releases for a newer version every few hours and updates itself (download is verified with a SHA-256 checksum).

**From source:** double-click **`Start AK980 Manager.bat`**. On the first run it installs Python 3.12 if the PC has none (via winget),
and the program then installs the packages it needs (Pillow, numpy, soundcard) by itself, with a small "Setting up" window.
Afterwards it keeps itself up to date without asking: about every 6 hours it checks GitHub for a newer version (downloaded,
syntax-checked, swapped in, rolled back if anything fails) and about once a week it upgrades its packages.
Updates are skipped in a git checkout (a developer copy) or when the environment variable `AK980_NO_UPDATE` is set.
By hand: `pip install -r requirements.txt`, then `python ak980_gui.py`.

Your settings live in `%APPDATA%\AK980Manager` and are never touched by an update; everything is logged to
`%APPDATA%\AK980Manager\bootstrap.log`. Offline is fine (it tries again next start).

Building the `.exe` yourself: `python tools/build_exe.py` (PyInstaller), see the header of that file for publishing a release.

1. Plug the keyboard in with the **USB cable** (wired mode) and set it to USB mode.
2. **Close the official AJAZZ app first** (also its tray icon). It polls the keyboard about 12 times a second, which breaks
   writes, and it re-applies its own saved profile every time it starts — overwriting what you set here.
3. Settings are remembered in `%APPDATA%\AK980Manager` (`keymap.json`, `macros.json`, `perkey.json`).

Use as a library: `import ak980; kb = ak980.Keyboard(); kb.set_lighting('Spectrum')` — see `ak980.py`.

## Limitations

* USB cable only (2.4G dongle / Bluetooth not tested).
* Macros: typed the way your Windows layout types them (capitals, symbols, AltGr, accents); no mouse events, no repeat count.
* Lighting effect ids beyond Static, Spectrum, Outward and Rolling are inferred from the list order; "LED Off" is not
  implemented.
* **Real-time Lighting and Music Rhythm are not supported.** The stream format is known (`04 20`, per-key colours at ~20 fps,
  see docs/PROTOCOL.md) but on the tested keyboard even the official app's Real-time page only produced black frames, and
  streaming frames from here did not light the keyboard.
* The Fn Momentary/Toggle switch is implemented from a capture but was not yet checked by pressing Fn on the keyboard.
* Not implemented: multiple profiles, the screen frame editor,
  firmware update, Reset / Factory Reset (deliberately).
* Writes take time: a per-key / macro / keymap update needs a few seconds; a screen upload with many frames can take minutes.

## Repository layout

* `ak980.py` — driver (protocol commands) · `ak980_gui.py` — Tkinter interface · `keys.py` — key/light index table
  generated from the official app's layout file
* `tools/` — `frida_hid_logger.py` (log the official app's HID calls) and `usbpcap_capture.ps1` (USB capture helper) used for
  the reverse engineering
* `docs/PROTOCOL.md` — the decoded protocol · `HANDOFF.md` — project state for whoever continues the work
* `test_media/` — small test images used while developing the screen upload

## Contributing / extending the protocol

Open the official app, attach `tools/frida_hid_logger.py` (`pip install frida`), change **one** setting at a time, and read the
log (`hid_log.txt`): every setting is a few 64-byte feature reports. Verify on hardware before documenting it as verified.
Never replay Reset / Factory Reset or anything that touches firmware.

## License

Copyright (C) 2026 j0p3s. GNU General Public License v3.0 or later — see [LICENSE](LICENSE). "AJAZZ" is a trademark of its
owner. No code or assets of the official software are included; `keys.py` only contains the factual key-index / light-index
table (names, HID codes, grid positions) read from the official app's layout file so that every key can be addressed.
