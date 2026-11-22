# Handoff — AK980 Manager

Last updated: 2026-11-22 (third long session: key functions, macros, profiles, screen editor, lighting schemes, 2.4G dongle finished, v1.0.6 + v1.0.7 released).
Repository: https://github.com/j0p3s/AK980-Manager · License: GPL-3.0-or-later · latest release **v1.0.7**.

## What this is
English control software for the user's **AJAZZ AK980 V2 PRO** keyboard (Sonix `0C45:8009` wired, `0C45:FEFE` 2.4G dongle), because the official app is Chinese-only.
Python + Tkinter (dark custom theme, no GUI package), talks to the keyboard through the Windows HID API with `ctypes`. Packages: Pillow (screen), numpy + soundcard (Music Rhythm);
`bootstrap.py` installs and updates them by itself. Protocol reverse engineered from the official app: [docs/PROTOCOL.md](docs/PROTOCOL.md).
The user is Portuguese (**Portuguese Windows layout**, ANSI keyboard, no Print Screen/Insert/End/Right Alt), prefers spartan answers, always says "Commit only" or
"Release x" explicitly: **never commit/push/release unasked**.

## State (all verified on the real keyboard unless noted)
| Area | Status |
|---|---|
| Lighting effects / colour / brightness / speed | works; effect ids 1, 8, 9, 11 seen from the app, the rest inferred; direction byte and "LED Off" untested |
| Keys page | Key (+modifiers), characters of the **active Windows layout** (`layout.py`: AltGr, ISO key, dead accents), Media, Mouse (buttons, wheel), Macro with play modes (once / N times / toggle / hold), Special (Disable key, Show Desktop, Lock, Close Window, Switch Windows, My Computer, Copy, Paste, Cut), PC action, Sequence (Multi-Key, up to 3 tapped keys), Modifiers. RESULT box says what a key will type |
| PC actions (`pcactions.py`) | Open program / website / file, Send text: key entry `[05 02 N]`, keyboard sends report `05 00 N 00` on the vendor interface, the running manager acts. Works elevated and not |
| Macros | text typed like the user's layout (capitals, symbols, AltGr, accents), `{click} {rightclick} {middleclick}`, `{wait 500}`; macro table must be >= 10 packets (mouse events are ignored otherwise) |
| Profiles (`profiles.py`) | PC-side .json (keymap + macros + lighting + per-key); the official app has NO keyboard-side config slots (its 3 configs live in its SQLite db) |
| Per-key lighting + scheme import/export | works; scheme file = official XML `<userlight>` (key_code = HID usage, key_rgb = R+G*256+B*65536) |
| Screen (`screen_page.py`) | frame editor (brush/eraser/text/fill/undo), per-frame delays, reorder, GIF import/export, "load original animation" (from the official app folder), upload (16-bit chunk count fixed for >16 frames) |
| Reactive: key glow, Music Rhythm | glow verified; equalizer verified by eye from CLI; GUI audio path only checked for "no error"; bass pulse never eyeballed |
| System: sleep, key response, clock | sent byte-identical to the app, effect not observable by eye |
| Start with Windows (admin task), tray icon, single instance, centred window | verified by the user (sign-in start, tray, PC actions as admin); self-update of the exe verified on real releases |
| **2.4G dongle** (`ak980.DongleKeyboard`, `connect()`) | lighting + Top-layer keys **verified with the cable unplugged** (dongle alone, 2026-11-22). **Fn layer, Fn Toggle (system packet), macros, per-key colours** verified over the dongle alone (`research/logs/_dongle_fn_test.py`, `_dongle_toggle_test.py`, `_dongle_macro_perkey_test.py` record the typed text per phase); clock packet acked but not observable. **Music Rhythm "Bars"** verified over the dongle with live audio (`0b` frames of 19 column levels, the keyboard draws it). Key glow, Bass pulse (per-key colours) need the cable; screen upload over 2.4G: the official app has no LCD tab on the dongle, so not available |
| **Fn layer / Fn Momentary-Toggle** (cable) | **verified** with our own code (Fn+A->B, Fn+J->K; Momentary and Toggle). Fn+Q and Fn+1 do NOT work, even when the official app writes them (firmware-reserved) |

## How to run
Double-click `Start AK980 Manager.bat` (installs Python via winget if missing; the program then installs its own packages and updates itself from GitHub, see `bootstrap.py`;
skipped in a git checkout). By hand: `pip install -r requirements.txt` then `python ak980_gui.py`. Packaged exe: `python tools/build_exe.py` -> `dist/` zip + sha256
(`gh release create vX.Y.Z dist/AK980-Manager-windows.zip dist/AK980-Manager-windows.zip.sha256`, bump `version.py` first; gh is logged in as j0p3s).
**Close the official app first** (the GUI shows a banner with a "Close it" button).

## Where the last session stopped (read this first)
* Everything is committed, pushed and released: **v1.0.7** (2026-11-22). `main` == `origin/main`. Never commit/push/release unasked (the user says "Commit only" / "Release x").
* This session finished **2.4G**: Fn layer, Fn Toggle, macros, per-key colours, system settings, Music Rhythm "Bars" verified on hardware with the cable unplugged (tests in `research/logs/_dongle_*_test.py`, they record what the user types per phase in a small Tk window - the user cannot see the console, never ask them to time keypresses against console output). The clock packet is acked but its effect was never observed.
* The GUI was clicked through over the dongle (screenshots via computer-use): Lighting, Per-key, Keys (Fn remap A->B + reset), System Apply, Reactive Equalizer with music, Macros/Screen/Profiles render. Found + fixed: pages taller than the window were cut off -> `ScrollHost` (v1.0.7).
* Added in 1.0.6: X-button setting (System > Window, `appsettings.py`), offline tests (`python -m unittest discover -s tests`), selftest recognises the dongle.
* Not available over 2.4G and **not offered by the official app either** (its sidebar has no LCD tab on the dongle): screen editor/upload, Key glow, Bass pulse. The GUI says so.
* State left behind: keyboard reset to defaults (both layers empty, macros cleared, Fn Momentary, lighting Glittering `(77,107,255)` colourful, brightness 3, speed 3); official app closed and its db cleared (backup `.bak-*` next to it); keyboard is in **2.4G mode with the cable out**.

## 2.4G dongle (all verified 2026-11-22, details in docs/PROTOCOL.md)
Commands are 33-byte output reports on the dongle's `MI_03` (usage page FF60), byte 31 = checksum (sum of bytes 0-30). Single key `03 04 <idx> <type b1 b2>` (Top) and `0d 04 ...` (Fn) are **acknowledged**
(retried until acked; the link sleeps when idle, the first packets after a pause can be lost: ask the user to tap a key if everything times out). Lighting `05 10 00 <16 bytes>`, system `07 10 00 <wired body[0:14]> aa 55`
(wait ~0.6 s after a table write), clock `0c 10 00 ...`. Bulk tables in 28-byte chunks `[cmd, len, seq] + data`, no replies: cmd `10` Top, `12` Fn, `14` per-key colours, `09` macros.
**Fn layer needs an empty `12` bulk table first (chunks ~25 ms apart, then wait ~1.4 s) and only then the `0d 04` keys** - without it the keys are acked but do nothing (this cost an hour). Per-key: user-mode packet
`05 10 00 80 00*8 <brightness> ...` (brightness byte at index 9; I once put it at 12 = black keys) then the `14` table. Macro length rule: `end//28 + 2` chunks. Music Rhythm: `0b 1c 00 04 00 64` + 19 column levels (0-6) at ~30 fps,
the keyboard draws it (`DongleKeyboard.stream_music`, used by `effects.Runner` for the Equalizer "Bars" mode only). Bluetooth: the official app does not support settings there, nothing to do.

## Things that bite (read before touching the keyboard)
* **Always reset the keyboard after any test that writes to it** (the user's standing rule, also in memory): `set_macros([])`, `set_keymap({}, 'top')`, `set_keymap({}, 'fn')`,
  `set_system(2, 2, False)`, restore lighting. Wrap test scripts so it runs on failure. Over the dongle `set_keymap({})` restores keys listed in `%APPDATA%\AK980Manager\dongle_touched.json`.
* **After any capture with the official app**: close it and the Frida logger, run `research/logs/clear_official_keys.py` (backs up its db, clears key/macro tables), then reset the keyboard.
  The official app re-applies what is stored in `%LOCALAPPDATA%\Device Driver Files\db\*_datav1.db` every time it starts and breaks any other writer (polls ~12 Hz).
* Keep dangerous assignments off typable keys during captures; the app's Windows Shortcut menu has only 8 entries (no Log Off/Sleep/Shutdown/Restart) and Multimedia only the usual 6.
* After a table write the keyboard is **busy** (echo byte 3 = `FF`) -> `Keyboard.wait_ready()`. Macro tables < 10 packets silently ignore mouse events.
* Screen upload faster than ~140 ms/chunk stalls at 93 %; the keyboard is sluggish during the ~5 minute upload of a long animation (135 frames = 2136 chunks).
* A Static effect with an empty user table is dark. **Never** send "Reset Keyboard" / "Factory Reset" / firmware commands.
* Writing a wired keymap replaces the whole table of that layer; the GUI writes both layers.
* `research/` is in `.gitignore` (raw captures, Frida logs, decoders `analyze_*.py`, `clear_official_keys.py`, `inspect_db.py`): local only, **not in git**.
* Tool-output truncation by hooks in this environment (big Read/Bash outputs come back as stubs): read files in small chunks (`sed -n a,bp`), print only what you need; PowerShell has no heredocs, use the Bash tool for `python - <<'EOF'`; to test the GUI use computer-use (grant "Python 3.15"), bring it forward with `(New-Object -ComObject WScript.Shell).AppActivate('AK980 Manager')`, never `open_application` (it starts a Python console) and never kill python processes by window title (it took the GUI down once); Frida logger must be started detached (`Start-Process -WindowStyle Hidden`, `python -u`).

## Code map
* `ak980.py` — `Keyboard` (wired: `set_lighting`, `set_keymap`, `set_macros`, `macro_table`, `set_user_lighting`, `set_system`, `set_time`, `upload_screen`, real-time stream, `wait_ready`),
  `DongleKeyboard` (2.4G: `_send` with acks, `_bulk_table`, `set_keymap` both layers, `set_macros`, `set_user_lighting`, `set_system`, `set_time`, `stream_music`), `connect()`, `find_path(iface, pid)`.
* `ak980_gui.py` — main window (`ScrollHost` wraps every page), nav, connection pill (auto-reconnect 2 s), official-app banner, `post()` queue (never call Tk from other threads), `run(job, msg)`, tray, PC-action listener.
* `pages.py` — Lighting, Per-key (+scheme import/export), Reactive, Keys, Macros, System pages; `screen_page.py`; `profiles.py`; `layout.py` (Windows layout -> keys); `pcactions.py`;
  `autostart.py` (Task Scheduler); `tray.py` (ctypes tray + single instance); `effects.py` (Equalizer, KeyGlow); `keyboard_view.py`; `theme.py`; `keys.py` (generated from the official layout xml).
* `appsettings.py` — small per-user settings (`settings.json`, currently `close_to_tray`). `tests/test_tables.py` — offline tests of the table/packet builders.
* `bootstrap.py` — first-run pip install, self-update (git-less zip of main, or the GitHub Release for the frozen exe), `tools/build_exe.py` (PyInstaller), `tools/frida_hid_logger.py`, `tools/hid_listen.py`.

## How the reverse engineering is done (repeat for new features)
Official app = `C:\Program Files (x86)\AJAZZ AK980 V2 ...\DeviceDriver.exe` (Frida attaches to the running process; `tools/frida_hid_logger.py <pid> <log>`), start it, start the logger, ask
the user to make **specific assignments** in its UI and Apply once, then decode the last tables (`research/logs/analyze_*.py` show the pattern: 04 11 top / 04 27 fn key tables, 04 15 macros).
Its English strings: `research/ak980_extract/en_strings.txt`. Always rebuild the captured bytes offline, then verify on hardware (the user presses keys and reports).

## Open work / ideas
1. GUI over the dongle was clicked through 2026-11-22 (Lighting, Per-key, Keys Fn remap + reset, System Apply, Reactive Equalizer with music, Macros/Screen/Profiles render). Still to eyeball: Fn Toggle via the System page on the cable, Macros page assign flow over the dongle.
2. **2.4G leftovers**: none planned (key glow / Bass pulse / screen are not offered by the official app over the dongle). Unobserved: the clock packet's effect on the screen time; mouse events inside macros over the dongle (length rule only confirmed for keyboard events).
3. Real-time Lighting scheme export (only the per-key scheme was captured), more Music Rhythm modes of the official app.
4. Still unverified on hardware: effect ids 2-7, 10, 12+, "LED Off", direction byte, key response level 1, the screen clock, My Computer/Copy/Paste/Cut shortcuts, bass pulse (cable). Music Rhythm Equalizer in the GUI is verified over the dongle only.
5. Pages now scroll (ScrollHost in ak980_gui.py) when taller than the window, e.g. Keys on small screens. Polish left: high-DPI scaling was deliberately NOT done (fixed-size widgets; the program runs DPI-virtualised, fine but slightly soft - needs a visual pass on a scaled screen), on-screen keycap legends are ANSI, the GUI's look was never seen by the assistant (ask the user for feedback). Done in 1.0.6: X-button setting (System > Window, `appsettings.py`), tests (`python -m unittest discover -s tests`).
