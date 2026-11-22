# AJAZZ AK980 (V2) PRO — USB/HID protocol notes

Reverse engineered from the official Windows app (`DeviceDriver.exe`, Inno Setup package "AJAZZ AK980 V2 ... Keyboard Driver
1.0.0.0", firmware version 120 in its layout file). Method: unpack the installer without running it, capture USB traffic
(USBPcap/Wireshark), then log the app's own `HidD_SetFeature` / `WriteFile` calls with Frida, and replay the packets.
Everything below was checked against captures; items marked **(unverified)** were inferred, not observed on hardware.

## Device

| | |
|---|---|
| USB (wired) | VID `0C45` (Sonix) PID `8009`, composite device, interfaces MI_00..MI_03 |
| 2.4G dongle | VID `0C45` PID `FEFE`: MI_00 keyboard, MI_01 mouse, MI_02 consumer/system + vendor `Col05` (key events), **MI_03 vendor FF60 = commands (33-byte reports)**, MI_04 vendor FF59 (65-byte, unknown). See the 2.4G section. |
| MI_03 | vendor usage page `0xFF13`; 65-byte input/output/feature reports → **command channel** |
| MI_02 | vendor usage page `0xFF68`; 4097-byte output report (id 0 + 4096 data) → **bulk data (screen images)** |
| MI_00 / MI_01 | boot keyboard / mouse + consumer + system collections (normal typing) |

## Command channel (MI_03)

* All commands are **feature reports of 65 bytes**: report id `0x00` + 64 data bytes (`HidD_SetFeature`).
* After every SET the app reads the device with `HidD_GetFeature`; the keyboard **echoes the command**. Byte 3 of the echo is a
  status: `01` = ok, `FF` = **busy**. After a table write the keyboard stays busy for a while and **silently ignores** commands
  sent in that window — poll `04 18` until its echo has byte 3 = `01` before the next transaction (`Keyboard.wait_ready`).
* A command is a *transaction*: `04 18` (begin) → header → data packet(s) → `04 F0` (end). ~36 ms between packets is fine.
* The official app also sends `04 02` and `04 F5 .. 09` about 12 times a second (status polls). They interleave with other
  traffic and break foreign transactions, so **the official app must be closed** while using this software. The app also
  re-applies its saved profile (keymaps, lighting tables) every time it starts.

All multi-packet tables end with the two bytes `AA 55`.

### Lighting effect — header `04 13 00 00 00 00 00 00 01`, then one packet

```
[effect, R, G, B, 0, 0, 0, 0, colorful, brightness(0-5), speed(0-5), direction, 0, 0, AA, 55]
```

* Effect ids follow the app's list order starting at 1: Static=1, SingleOn, SingleOff, Glittering, Fluttering, Colourful,
  Breath, Spectrum=8, Outward=9, Scrolling, Rolling=11, Rotating, Explode, Launch, Ripples, Flowing, Pulsating, Tilt,
  Shuttle. Seen from the app: 1, 8, 9, 11; the others are inferred from the list order **(unverified)**; "LED Off" not captured.
* `effect = 0x80` selects **user (per-key) lighting**, see below. Colour bytes apply to effects with a colour picker;
  `colorful=1` uses rainbow colours. Static with an all-zero user table looks dark (Static shows the user table).

### Key remapping — headers `04 11 …09` (top layer) and `04 27 …09` (Fn layer), then 9 packets = 576 bytes

* 4 bytes per key at offset `4 * key_index` (indexes in `keys.py`, from the app's `rgb-keyboard.xml`; 97 keys incl. Fn=96,
  Ctrl_R=98), table ends with `AA 55` at bytes 574-575. Always write the **whole** table; an all-zero entry = default key.
* Entries: keyboard key `[02, modifier_mask, hid_usage, 0]` (modifier-only: usage 0), media/consumer key
  `[03, usage_lo, usage_hi, 0]` (Volume Up = `0x00E9`), macro `[06, macro_number, 0, 0]`.
* Macro key `[06, slot, mode, count]` (captured 2026-11-22, verified): mode 0 once, 1 multiple times (count 1-255 in byte 3),
  2 loop until the key is pressed again, 3 play while the key is held. Disable key `[05, 03, 0, 0]`. The app's Windows shortcuts are plain
  key combinations: Show Desktop = LWin+D, Lock Computer = LWin+L, Close Window = LCtrl+W, Switch Windows = LAlt+Tab, My Computer = LWin+E, Copy/Paste/Cut = LCtrl+C/V/X.
  The app's menus offer nothing else: its Windows Shortcut list has only these 8 entries (no Log Off/Sleep/Shutdown/Restart) and its Multimedia
  list is Play/Pause, Stop, Previous, Next, Volume +/- and Mute (all already in our Media list).
* PC-side actions (Open Program / Website / File, Send Text; captured + verified 2026-11-22): key entry `[05, 02, N, 0]` with N = 1..255
  chosen by the app. The keyboard stores nothing else: on a press it sends the input report `05 00 N 00` on the vendor interface
  (`MI_01&Col05`, usage page 0xFFFF, 4-byte reports, no release report) and the PC program acts (`pcactions.py`).
* Multi-Key = key sequence `[07, usage1, usage2, usage3]` (3rd optional; verified on hardware 2026-11-22: `07 04 05 06` types abc). The keys are
  **tapped one after another**, not held together, so modifiers do not combine (the app's Ctrl+V entry `07 e0 19` taps Ctrl, then V).
* Mouse function `[01, class, value, 0]` (captured 2026-11-22, verified on hardware): class 1 = button bits (Left `01`, Right `02`, Middle `04`,
  Double Click `03`, Button 4/Back `08`, Button 5/Forward `10`), class 3 = wheel (Scroll Up `01`, Scroll Down `ff`).
* Modifier mask: LCtrl 01, LShift 02, LAlt 04, LWin 08, RCtrl 10, RShift 20, RAlt 40, RWin 80.

### Per-key lighting — header `04 23 …09`, then 9 packets = 576 bytes

* For every key (layout `light_index`) a 4-byte entry `[light_index, R, G, B]` at offset `4 * light_index`, `AA 55` trailer.
* Order that works: write the table → wait until ready → send the lighting packet with effect `0x80` (brightness at byte 9).

### Macros — header `04 15 00 00 00 00 00 00 N`, then N packets (N = len//64 + 2)

* Directory: 4-byte entries `[offset_lo, offset_hi, 0, 0]` at `4*n` (100 slots); macro data starts at offset 400.
* Each macro: 8-byte header `[2*events, 0 ×7]` followed by one 8-byte record per event:
  `[0, 0, hid_usage, flag, delay_lo, delay_hi, 0, 0x50]`, flag `0xB0` = key down, `0x30` = key up, delay = ms before the
  event (the app shows 0 for the last event but stores 10, so the minimum is 10). Total length = `(end//64 + 2) * 64`, `AA 55` last.
* Modifier events (captured 2026-11-22, verified on hardware) are normal records with the modifier usage `E0`-`E7` (LShift `E1`, LCtrl `E0`,
  LAlt `E2`, RAlt `E6`): down, key down, key up, up. The app records AltGr as LCtrl+LAlt; we send RAlt, which also works.
* A key runs macro *n* through keymap entry `[06, n]`. A repeat count is **not** in these packets (the entry stayed `06 02 00 00`;
  unconfirmed whether the user had set one). Mouse events in macros (captured 2026-11-22, verified on hardware): record `[00 00 button flag delay_lo delay_hi 00 50]`, button = bit
  (Left `01`, Right `02`, Middle `04`), flag `90` = press, `10` = release (keys use `B0` / `30`). **The macro table must be at least 10 packets
  long**: an 8-packet table still typed the keys but silently ignored every mouse event. Setting a repeat count in the app changes no byte.

### System settings — header `04 17 01 00 00 00 00 00 01`, then one packet

```
[00, 01, 0, 0, 0, fn_switch, sleep, 0, level, 0 …, AA, 55]      (AA 55 at positions 62-63)
fn_switch: 0 = Momentary (hold Fn, default), 1 = Toggle (press Fn to switch layer) — captured from the app's switch, not yet
           checked on the keyboard by pressing Fn
sleep: 0 = No Sleep, 1 = 1 min, 2 = 5 min, 3 = 30 min          level: key response 2 and 3 verified (1 unverified)
```

"Disable Windows key / Alt+F4 / Alt+Tab" in the app send nothing to the keyboard (done on the PC). "Reset Keyboard" and
"Factory Reset" were never used or captured.

### Clock — `04 18`, `04 28 00 00 00 00 00 00 01`, then `[00 01 5A yy mm dd hh mm ss 0 … AA 55]` (year = last two digits)

Sent by the official app whenever it changes page; replayed by this software without visually checking the screen clock.

## TFT screen image upload (240×135, up to 140 frames)

1. MI_03: `04 18`, then `04 72 02 00 00 00 00 00 <chunks> 00`
2. MI_02: `<chunks>` × `WriteFile` of 4097 bytes (report id 0 + 4096 data), **~140 ms apart**, then wait ≈1.5 s before closing
   the handle. Sending faster stalls the keyboard at "93 %" (the last chunk is lost).
3. Stream = 256-byte header `[frame_count, delay_ms/2 for each frame …, FF padding]` + frames + `FF` padding to a multiple of
   4096. A frame is 240×135 pixels, **RGB565 little-endian**, row-major from the top-left corner (red `F800` → bytes `00 F8`).
   `<chunks> = len(stream) / 4096` (one frame = 16 chunks), sent as 16-bit little-endian in bytes 8-9 of the `04 72 02` header
   (a 135-frame upload = 2136 chunks was accepted and restored the original animation). The app uploads `04 18` + header only — no `04 F0` seen.
4. The layout file declares `gif_headlength=256`, `gif_maxframes=140`, 240×135.

## Real-time Lighting (decoded, works)

The PC drives the keyboard's lights directly, ~20 frames per second. One frame is:

1. `04 20 00 00 00 00 00 00 08` (SetFeature), then **read the status (GetFeature) ~6 ms later and wait until byte 3 is `01`**.
2. 8 packets of 64 bytes = 512 bytes of `[light_index, R, G, B]` entries, back to back (~3 ms apart).
3. `04 02`, then read the status again until byte 3 is `01`.

Three details decide whether the keyboard shows the frame (all found 2026-11-22 by comparing with a USBPcap capture of the official app):

* The entries must be in the official app's **fixed slot order** (`Keyboard.RT_SLOTS`, 97 entries + zero padding), not layout-row order.
* The keyboard answers the status read with `04 xx 00 01` when ready and `00` / `FF` while busy. A frame sent while busy is dropped
  (this looked like "the keyboard ignores the stream"). Reading the status *immediately* after a write (before ~6 ms) provoked
  long busy periods (0.5-1.5 s); reading it 6 ms later like the app does keeps the stream smooth.
* Send at about 20 fps (the app's rate, 48 ms median); faster only queues frames and adds visible lag.

The stream works over a built-in effect or the per-key mode; when streaming stops, the keyboard falls back to its own effect.
The keyboard does **not** report key presses to the PC (no input reports on the vendor interfaces, and the official app never reads
any), so a key-press effect is computed on the PC (global key state) and streamed: see `tools/keypress_glow.py`. On the tested
unit the official app's own Real-time page only ever sent black frames (and turned the lights off), so its effects there are not a
reference. Music Rhythm very likely uses the same stream.
Code: `Keyboard.realtime_frame`, `Keyboard.stream_realtime`.

## Other features seen in the official app's strings but not implemented

Key response levels 1-5 (the app's text: about 2-3 / 5-6 / 8-9 / 13-14 / 17-18 ms wired; only 2 and 3 were captured),
three "exclusive configs" and saved
nothing of the official app's key, macro, profile, screen or lighting-scheme features (see HANDOFF).

## Not decoded / not covered

Mouse and modifier events and repeat count in macros, Real-time Lighting and Music Rhythm (see above), 2.4G / Bluetooth modes,
the firmware update path, lighting effect "LED Off".

## 2.4G dongle (captured 2026-11-22, lighting + Top-layer keys verified on hardware)

* Commands are output reports of 33 bytes (report id 0 + 32 bytes) written with `WriteFile` to the dongle's `MI_03` (usage page `0xFF60`).
  Byte 31 = sum of bytes 0-30 (mod 256). The dongle answers on the same interface (input report, 33 bytes): for a key command `03 04 <key> 00`.
  The link sleeps when idle and **the first packet after a pause can be lost**: wait for the answer and resend (we retry up to 5 times).
* Set one key (Top layer): `03 04 <key_index> <type> <b1> <b2>`, same key indices and entry types as the wired tables. There is no
  whole-table write; restoring a key = writing its default entry (`02 00 <usage>`, modifiers `02 <mask> 00`).
* Lighting: `05 10 00` + the same 16-byte block as the wired lighting packet (`effect R G B 0 0 0 0 colorful brightness speed direction 0 0 AA 55`).
* Keep-alive from the official app: `20 01 ...` every 15 s.
* Not captured yet over the dongle: Fn layer, macros, per-key colours, screen upload, real-time lighting, system settings.
* Bluetooth: the official app does not support keyboard settings there, so nothing to implement.
