# AJAZZ AK980 (V2) PRO — USB/HID protocol notes

Reverse engineered from the official Windows app (`DeviceDriver.exe`, Inno Setup package "AJAZZ AK980 V2 ... Keyboard Driver
1.0.0.0", firmware version 120 in its layout file). Method: unpack the installer without running it, capture USB traffic
(USBPcap/Wireshark), then log the app's own `HidD_SetFeature` / `WriteFile` calls with Frida, and replay the packets.
Everything below was checked against captures; items marked **(unverified)** were inferred, not observed on hardware.

## Device

| | |
|---|---|
| USB (wired) | VID `0C45` (Sonix) PID `8009`, composite device, interfaces MI_00..MI_03 |
| 2.4G dongle | VID `0C45` PID `FEFE` (HID interface MI_03) — **not tested** |
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
* Modifier mask: LCtrl 01, LShift 02, LAlt 04, LWin 08, RCtrl 10, RShift 20, RAlt 40, RWin 80.

### Per-key lighting — header `04 23 …09`, then 9 packets = 576 bytes

* For every key (layout `light_index`) a 4-byte entry `[light_index, R, G, B]` at offset `4 * light_index`, `AA 55` trailer.
* Order that works: write the table → wait until ready → send the lighting packet with effect `0x80` (brightness at byte 9).

### Macros — header `04 15 00 00 00 00 00 00 N`, then N packets (N = len//64 + 2)

* Directory: 4-byte entries `[offset_lo, offset_hi, 0, 0]` at `4*n` (100 slots); macro data starts at offset 400.
* Each macro: 8-byte header `[2*events, 0 ×7]` followed by one 8-byte record per event:
  `[0, 0, hid_usage, flag, delay_lo, delay_hi, 0, 0x50]`, flag `0xB0` = key down, `0x30` = key up, delay = ms before the
  event (the app shows 0 for the last event but stores 10, so the minimum is 10). Total length = `(end//64 + 2) * 64`, `AA 55` last.
* A key runs macro *n* through keymap entry `[06, n]`. Repeat count (shown in the app) is **not** in these packets;
  mouse events and modifier events (capital letters) were **not captured**.

### System settings — header `04 17 01 00 00 00 00 00 01`, then one packet

```
[00, 01, 0, 0, 0, 0, sleep, 0, level, 0 …, AA, 55]      (positions 62-63)
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
   `<chunks> = len(stream) / 4096` (one frame = 16 chunks). The app uploads `04 18` + header only — no `04 F0` seen.
4. The layout file declares `gif_headlength=256`, `gif_maxframes=140`, 240×135.

## Not decoded / not covered

Mouse and modifier events and repeat count in macros, the second "Real-time Lighting" effect list, Music Rhythm (probably
streamed from the PC), 2.4G / Bluetooth modes, the firmware update path, lighting effect "LED Off", key response level 1.
