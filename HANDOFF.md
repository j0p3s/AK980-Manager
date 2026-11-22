# Handoff — AK980 Manager

Last updated: 2026-11-22 (second long session: real-time lighting solved, Music Rhythm, auto-setup/updates, new GUI, .exe build). Repository: https://github.com/j0p3s/AK980-Manager · License: GPL-3.0-or-later.

## What this is
English control software for the user's **AJAZZ AK980 V2 PRO** keyboard (Sonix `0C45:8009`), because the official app is Chinese-only.
Python + Tkinter (dark custom theme, no GUI package), talks to the keyboard through the Windows HID API with `ctypes`. Packages: Pillow (screen tab), numpy + soundcard (Music Rhythm); `bootstrap.py` installs and updates them by itself.
The protocol was reverse engineered from the official app; the full description is in [docs/PROTOCOL.md](docs/PROTOCOL.md).

## State: working, tested on the real keyboard (USB cable)
| Feature | Status |
|---|---|
| Lighting effects, colour, brightness, speed | works (effect ids 1, 8, 9, 11 seen from the official app; the rest inferred from list order; direction byte and "LED Off" untested) |
| Keymap Top layer + Fn layer, media keys, modifiers, reset | works (Caps→Z, A→Volume+, B→Left Shift, Fn Q→W captured; Caps→Z and reset verified by typing) |
| Macros (text typing) assigned to a key | works, verified on hardware with the Portuguese layout: capitals, symbols, AltGr, dead-accent letters (`layout.py`); mouse clicks via text tokens `{click}` `{rightclick}` `{middleclick}` `{wait 500}` (verified); play modes + loop count live in the key entry `[06, slot, mode, count]` (verified); macro tables are padded to >= 10 packets (needed for mouse events) |
| Per-key RGB | works (verified by eye); needs "write table, wait until idle, then mode 0x80" |
| TFT screen: frame editor (`screen_page.py`: brush/eraser/text/fill, per-frame delays, reorder, GIF export, load original animation); upload (240×135 RGB565, ≤140 frames) | works (own image and a user image shown); must be paced ~140 ms per 4 KB chunk |
| System: sleep time, key response level | sent byte-identical to the app's packets; **effect not observable** by eye, so only matched to captures |
| Clock sync | sent like the app does; screen clock not checked visually |
| Fn key Momentary/Toggle (System tab, `set_system(..., fn_toggle)`) | byte 5 of the `04 17` packet decoded from the official app (0 = Momentary, 1 = Toggle); **not yet verified on hardware** |
| Real-time lighting stream (`04 20` frames) | works since 2026-11-22: fixed slot order + `04 02` + status reads (see docs/PROTOCOL.md); ~20 fps, verified by eye |
| Key glow (pressed keys light up and fade) | works, verified by eye, no noticeable delay (key state read on the PC) |
| Music Rhythm (equalizer / bass pulse from PC audio) | equalizer verified by eye from the CLI tool; in the GUI the audio-thread COM bug was fixed but only checked for "no error"; bass pulse not eyeballed |
| GUI (rebuilt 2026-11-22: sidebar, on-screen keyboard, Reactive tab) | every page builds, no clipped widgets, reactive modes start/stop, key assign / per-key paint work; **the user has not reviewed the look yet** |
| Auto-setup + auto-update (`bootstrap.py`, `Start AK980 Manager.bat`) | tested in a clean venv and on a copy without `.git`; the winget "install Python" path is untested |
| Packaged `AK980 Manager.exe` (`tools/build_exe.py`) | builds, runs, `--selftest` ok; exe auto-update tested only against a simulated release; **v1.0.0 published 2026-11-22, v1.0.1 adds start-with-Windows**; auto-update still untested against a real release (v1.0.0 -> v1.0.1 is the first real test) |

## How to run
Double-click `Start AK980 Manager.bat` (installs Python via winget if missing; the program then installs its own packages and updates itself from GitHub
every 6 h, see `bootstrap.py`; skipped in a git checkout, so this dev folder never overwrites itself). By hand: `pip install -r requirements.txt` then
`python ak980_gui.py`. **Close the official app first** (the GUI shows a banner with a "Close it" button when it is running).
A desktop shortcut "AK980 Manager.lnk" was created on the user's desktop (target: `pythonw.exe` of Python 3.15 + the .pyw).

## Pending / where the last session stopped
* **Verify the Fn switch on hardware:** close the official app, in the System tab choose "Toggle", Apply; remap Fn-layer Q→W
  on the Keys tab and Apply; then tap Fn once, release, press Q → should type `w` until Fn is tapped again. Set it back to
  Momentary afterwards.
* The old test remaps (A→Volume+, B→Left Shift, F/G macros, Fn Q→W) were **reset on 2026-11-22** (both layers) and verified by typing. If the official app is
  started again it re-applies its saved profile and they come back. The app keeps its 3 configs, key assignments and macros in
  `%LOCALAPPDATA%\Device Driver Files\db\*_datav1.db` (SQLite); on 2026-11-22 the key/macro tables were cleared with `research/logs/clear_official_keys.py`
  (backup next to the db). After any capture in the official app, close it, run that script, then reset the keyboard (empty keymaps + `set_macros([])`).
  The official app has NO keyboard-side config slots: a config switch only rewrites the 04 11 / 04 27 key tables (capture `config1.log`).
* **Releases**: v1.0.0 to v1.0.5 are published. Check that a v1.0.0 install really updates itself to v1.0.1. Ask before publishing further releases.
* **Tray icon + single instance** (`tray.py`, ctypes only, released in 1.0.2): X hides to the tray (effects keep running), tray menu Show/Quit, `--startup` starts hidden, a second launch shows the running window (works across elevation). Tested by script only (icon registration ok, show/hide, second-instance); not eyeballed in the notification area, not tested elevated.
* **Start with Windows** (`autostart.py`, System page > Startup): Task Scheduler task "AK980 Manager", logon trigger, highest privileges, `--startup` starts minimised. Create/remove tested on this PC (one UAC prompt each); a reboot/sign-in run not yet verified.
* **Wait for the user's feedback on the new GUI look** before polishing further.
* Real-time Lighting is solved and works from our code (see Open work 2 and docs/PROTOCOL.md). The official app's own Real-time
  page only sent black frames on this unit and turned the lights off; selecting any normal effect (Lighting tab) restores it.
* Key response levels 1-5 exist in the official app; the System tab only offers the verified 2 and 3.

## Things that bite (read before touching the keyboard)
* The official app (`DeviceDriver.exe`) polls ~12 Hz and **breaks any other writer**; it also **re-applies its saved profile at start-up**.
  Its profile still contains the **test remaps/macros from this session** (A→Volume+, B→Left Shift, F→macro "New Macro 1",
  G→"New Macro 2", Fn-layer Q→W, two test macros). If the user ever starts the official app, those come back — reset with
  the Keys tab "Reset all keys to default" afterwards, or clear them in the official app.
* After a table write the keyboard is **busy** (echo byte 3 = `FF`) and ignores commands for a while → `Keyboard.wait_ready()`.
  Several early "no change" results were this, not a wrong packet.
* Screen upload faster than ~140 ms/chunk stalls at 93 % (last chunk dropped); wait ~1.5 s before closing the handles.
* A Static effect with an empty user table is **dark** (Static shows the per-key table). Pick another effect or fill the Per-key tab.
* **Never** send "Reset Keyboard" / "Factory Reset" or firmware commands; they were never captured on purpose.
* Writing a keymap replaces the *whole* table of that layer; the GUI always writes both layers.

## Code map
* `ak980.py` — `Keyboard`: `set_lighting`, `set_keymap(entries, layer)`, `set_macros`, `set_user_lighting`, `set_system`, `set_time`,
  `upload_screen`, `wait_ready`; `find_path()` enumerates the HID interface with SetupAPI.
* `ak980_gui.py` — main window: sidebar nav, connection pill (auto-reconnect every 2 s), official-app banner, status bar, a thread-safe `post()` queue
  (never call Tk from other threads), `run(job, msg)` for keyboard writes, a latest-wins lighting worker. `pages.py` — the pages: `LightingPage`, `PerKeyPage`,
  `ReactivePage` (key glow / equalizer / bass pulse with live preview), `KeysPage` (click-a-key remapping, normal + Fn layer), `MacrosPage`, `ScreenPage`,
  `SystemPage` (+ software update card). `theme.py` — colours, ttk theme and custom widgets (`Btn`, `Chip`, `Seg`, `Slider`, `Toggle`, `Card`).
  `keyboard_view.py` — canvas keyboard (layout computed from `keys.KEYS`, paint/click callbacks). `effects.py` — `KeyGlow`, `Equalizer` (WASAPI loopback via
  soundcard; its recorder thread must call `CoInitializeEx` itself, the GUI main thread is an STA), `Runner` (stoppable stream thread).
  Settings in `%APPDATA%\AK980Manager\{keymap,macros,perkey,lighting,update}.json`; `bootstrap.log` there too.
* `bootstrap.py` — stdlib only: first-run pip install, weekly pip upgrade, GitHub self-update (zip of main, compile check, rollback; `.bat` rewritten with CRLF).
* `tools/keypress_glow.py`, `tools/music_rhythm.py` — command-line versions of the Reactive effects (thin wrappers over `effects.py`).
* `keys.py` — generated from the official `rgb-keyboard.xml` (97 keys: key_index, name, HID usage, light_index, row, col).
* `tools/frida_hid_logger.py`, `tools/usbpcap_capture.ps1` — how new commands were decoded.

## How the reverse engineering was done (to repeat for new features)
1. Unpacked the Inno Setup installer with `innoextract` (never ran the installer): config shows VID/PID/interfaces, layout xml has keys.
2. USBPcap + Wireshark only showed polling at first; the breakthrough was **Frida hooks on `HidD_SetFeature`/`WriteFile`**
   attached to the running official app (`tools/frida_hid_logger.py <pid>`), changing one setting at a time.
3. Verified every decoded format by rebuilding the captured bytes offline, then by sending them with the official app closed.

## Local-only material (not in git)
`D:\AK980-Manager\research\` — raw USB captures (contain other devices' traffic: mouse, camera, storage), Frida logs and the
unpacked vendor installer. It is in `.gitignore` on purpose; do not publish it.

## Tools installed on the user's machine during this work (safe to uninstall)
7-Zip, innoextract, USBPcap (driver + needs reboot to capture), Wireshark, and `pip install frida frida-tools`.

## Open work / ideas
0. DONE (v1.0.5 work): mouse-button key functions (captured with Frida, see docs/PROTOCOL.md; `research/logs/mouse.log`, `analyze_mouse.py`), verified on hardware.
1. Macros: DONE modifier events + layout-aware typing (capture `research/logs/macro2.log`, `analyze_macro2.py`). Mouse events DONE (insert menu capture `macro3.log`, `analyze_macro3.py`). The repeat count is not in any packet.
2. **Real-time Lighting** (SOLVED 2026-11-22, see docs/PROTOCOL.md): frames need the fixed slot order, a `04 02` packet and a status read (wait for `01`) after the header and after `04 02`. `tools/keypress_glow.py` (pressed keys light up and fade) works, verified on hardware. `tools/music_rhythm.py` (equalizer on the keys from the PC audio via WASAPI loopback, `soundcard` + numpy; `--mode pulse` = whole-keyboard bass flash, not yet eyeballed) works, verified on hardware (bars mode). Both are in the GUI's Reactive tab (done 2026-11-22; verified: modes start/stop, preview, no UI errors; the equalizer's audio thread COM fix is verified only for "no error" - hear it with music playing).
2a. Key functions DONE: macro play modes, Disable Key, Windows shortcuts (`research/logs/keyfn1.log`, `analyze_keyfn1.py`). PC actions DONE (`pcactions.py`, Keys page 'PC action', verified): Open Program/Website/File, Send Text - done by the running manager when the keyboard sends `05 00 N 00`. Multi-Key DONE as 'Sequence' (up to 3 tapped keys, verified). Still open: nothing: the app's Windows Shortcut and Multimedia menus are fully covered (no power or browser functions exist in this app version).
2b. From the app's English strings (`research/ak980_extract/en_strings.txt`): key response levels 1-5, Fn Momentary/Toggle,
   3 exclusive configs, lighting-scheme import/export, TFT frame editor + GIF export.
3. Verify the remaining effect ids, "LED Off", direction byte, key response level 1, and the clock on the screen by eye.
4. 2.4G dongle (`0C45:FEFE`, interface MI_03) and Bluetooth modes.
5. Profiles DONE (v1.0.5 work, `profiles.py`, app-side .json files, not the keyboard's own slots; load and apply verified on the real keyboard by the user). Polish: a proper installer or PyInstaller build, tests for the table builders.
6. **New GUI (2026-11-22) was checked by code only**: every page builds, no clipped widgets (geometry walk), reactive modes start/stop on the real keyboard,
   key assign/restore and per-key paint work. Nobody has looked at it yet (screenshots could not be viewed in that session) - ask the user for visual
   feedback (spacing, colours, the on-screen keyboard shapes in `keyboard_view.py`, which approximate the real key sizes).
7. **Single .exe** (asked by the user; BUILT and released 2026-11-22): `python tools/build_exe.py` -> `dist/AK980 Manager/AK980 Manager.exe` + `lib/`
   (PyInstaller 6.22, `--contents-directory lib`, ~11 MB exe, 44 MB zip) and `dist/AK980-Manager-windows.zip(.sha256)`. No driver is bundled: the keyboard uses
   Windows' built-in HID class driver. `AK980 Manager.exe --selftest` writes `%APPDATA%\AK980Manager\selftest.txt` (keyboard / Pillow / audio / glow) - all ok on
   the user's PC. Frozen mode in `bootstrap.py`: no pip; updates come from the latest GitHub Release (zip asset ending `-windows.zip`, optional `.sha256` is
   enforced, helper `apply.bat` swaps the folder after exit and restarts); tested only against a simulated release. Publishing: bump
   `version.py`, run the build, then `gh release create vX.Y.Z dist/AK980-Manager-windows.zip dist/AK980-Manager-windows.zip.sha256` (gh is logged in as j0p3s).
