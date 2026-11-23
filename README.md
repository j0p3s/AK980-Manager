# Ajazz AK980 V2 Manager

An English, open-source replacement for the Chinese-only software of the **AJAZZ AK980 (V2) PRO** keyboard
(USB `0C45:8009`). Written by reverse engineering the official app's USB/HID traffic — see [docs/PROTOCOL.md](docs/PROTOCOL.md).
Windows, Python 3.10+ (Tkinter), Pillow. Licensed under the **GNU GPL v3 or later**. Not affiliated with AJAZZ.

> **Use at your own risk.** This talks to your keyboard directly. It only sends the lighting, key map, macro, screen and
> settings commands the official app also sends; it has no firmware update and no factory reset. Still, it is unofficial.

## Features

| Tab | What it does |
|---|---|
| **Lighting** | built-in effects (all 19 verified), colour, "colorful" rainbow, brightness (0 = LEDs off), speed, direction |
| **Per-key** | paint every key with its own colour; import / export the official app's lighting scheme files |
| **Reactive** | keys that glow when pressed; Music Rhythm equalizer (bar colours, background, amplitude over 2.4G), bass pulse, and system gauges (CPU on the top row, memory on the number row, cable only) |
| **Keys** | remap keys on the **Top** and **Fn** layer to a key, characters of your Windows layout, media, mouse, macro, special function (Show Desktop, Copy, Paste...), PC action (open program / website / file, send text) or key sequence |
| **Macros** | record keys and mouse clicks, type text, edit the steps (waits, speed), duplicate, import / export; assign on the Keys page |
| **Screen** | frame editor and GIF import / export for the TFT screen (240x135, up to 140 frames); sync the clock |
| **Profiles** | save keymap, macros and lighting under a name and switch with one click |
| **System** | sleep time, key response level, Fn key Momentary / Toggle, sync the keyboard clock, Bluetooth battery level (read-only), start with Windows, tray, updates |

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

1. Plug the keyboard in with the **USB cable** (wired mode), or use the **2.4G dongle** (lighting, keys incl. the Fn layer, macros, per-key colours, system settings and Music Rhythm "Bars" work over it).
2. **Close the official AJAZZ app first** (also its tray icon). It polls the keyboard about 12 times a second, which breaks
   writes, and it re-applies its own saved profile every time it starts — overwriting what you set here.
3. Settings are remembered in `%APPDATA%\AK980Manager` (`keymap.json`, `macros.json`, `perkey.json`).

Use as a library: `import ak980; kb = ak980.Keyboard(); kb.set_lighting('Spectrum')` — see `ak980.py`.

## Limitations

* Over the 2.4G dongle the screen editor, key glow and Bass pulse are not available (the official app does not offer them there either); Bluetooth is not supported.
* Macros: text is typed the way your Windows layout types it; recorded macros replay the exact keys and clicks (mouse movement is not recorded). The keyboard holds about 2700 bytes of macros (8 bytes per step); the page shows how much is used. PC actions work while the manager is running.
* Real-time lighting over the cable (key glow, bass pulse) is implemented from captures; Music Rhythm "Bars" over 2.4G uses the keyboard's own equaliser.
* Key response level 1 and the keyboard clock's effect on the screen time were not checked by eye.
* Profiles are stored on the PC (Profiles page), not in the keyboard.
* Not implemented: firmware update, Reset / Factory Reset (deliberately).
* Writes take time: a per-key / macro / keymap update needs a few seconds; a screen upload with many frames can take minutes.

## Credits

Protocol notes (macro memory size, the Fn-key rule, the clock weekday byte, the firmware-update guard) come from the open-source
[Keymotion](https://github.com/cebersaban44-rgb/keymotion) project (Apache-2.0 / MIT); see `NOTICE`.

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
