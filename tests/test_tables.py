# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Offline tests for the table/packet builders (no keyboard needed). Run: python -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import ak980          # noqa: E402
import appsettings    # noqa: E402


class FakeDongle(ak980.DongleKeyboard):
    """DongleKeyboard that records what it would send instead of opening the USB dongle."""

    def __init__(self):                                   # no HID access
        import threading
        self.lock = threading.RLock()
        self.sent, self.written = [], []

    def _write32(self, body):
        b = bytearray(32)
        b[:len(body)] = body
        self.written.append(bytes(b))

    def _send(self, body, retries=10):
        self.sent.append(bytes(body))
        return bytes(body)


class MacroTable(unittest.TestCase):
    def test_directory_and_events(self):
        tab = ak980.Keyboard.macro_table([[(0x0B, True, 20), (0x0B, False, 20)]], min_packets=1)
        self.assertEqual(tab[0:4], bytes([0x90, 0x01, 0, 0]))              # first macro data starts at 400
        self.assertEqual(tab[400], 4)                                      # header: 2 * events
        self.assertEqual(tab[408:416], bytes([0, 0, 0x0B, 0xB0, 20, 0, 0, 0x50]))   # key down
        self.assertEqual(tab[416:424], bytes([0, 0, 0x0B, 0x30, 20, 0, 0, 0x50]))   # key up
        self.assertEqual(tab[-2:], bytes([0xAA, 0x55]))
        self.assertEqual(len(tab) % 64, 0)

    def test_mouse_flags_and_min_delay(self):
        tab = ak980.Keyboard.macro_table([[(1, True, 1, True), (1, False, 70000, True)]], min_packets=1)
        self.assertEqual(tab[408 + 3], 0x90)
        self.assertEqual(tab[416 + 3], 0x10)
        self.assertEqual(tab[408 + 4], 10)                                # delays are clamped to >= 10 ms
        self.assertEqual(tab[416 + 4:416 + 6], bytes([0xFF, 0xFF]))      # and to 16 bits


class DongleFrames(unittest.TestCase):
    def test_bulk_table_chunks(self):
        d = FakeDongle()
        tab = bytearray(576)
        tab[0:3] = b'\x01\x02\x03'
        tab[574:576] = b'\xAA\x55'
        d._bulk_table(0x12, tab)
        self.assertEqual(len(d.written), 21)
        self.assertEqual(d.written[0][:6], bytes([0x12, 0x1C, 0, 1, 2, 3]))
        self.assertEqual(d.written[19][:3], bytes([0x12, 0x1C, 19]))
        last = d.written[20]
        self.assertEqual(last[:3], bytes([0x12, 0x10, 20]))
        self.assertEqual(last[3 + 14:3 + 16], bytes([0xAA, 0x55]))
        self.assertEqual(last[19:23], bytes([0, 0x12, 0x10, 20]))

    def test_music_frame(self):
        d = FakeDongle()
        d.music_frame([0, 3, 6, 9, -2] + [1] * 14)
        w = d.written[0]
        self.assertEqual(w[:6], bytes([0x0B, 0x1C, 0, 0x04, 0, 0x64]))
        self.assertEqual(list(w[6:11]), [0, 3, 6, 6, 0])                   # clamped to 0..6
        self.assertEqual(w[6 + 19], 0)

    def test_system_and_clock_bodies(self):
        d = FakeDongle()
        import time
        sleep, time.sleep = time.sleep, lambda s: None
        try:
            d.set_system(2, 3, True)
        finally:
            time.sleep = sleep
        p = d.sent[0]
        self.assertEqual(p[:3], bytes([0x07, 0x10, 0]))
        self.assertEqual((p[3 + 1], p[3 + 5], p[3 + 6], p[3 + 8]), (1, 1, 2, 3))
        self.assertEqual(p[-2:], bytes([0xAA, 0x55]))
        import datetime
        d.set_time(datetime.datetime(2026, 11, 22, 10, 46, 4))
        self.assertEqual(d.sent[1][:12], bytes([0x0C, 0x10, 0, 0, 1, 0x5A, 26, 11, 22, 10, 46, 4]))


class Settings(unittest.TestCase):
    def test_roundtrip_and_bad_values(self):
        with tempfile.TemporaryDirectory() as t:
            path = os.path.join(t, 'settings.json')
            self.assertTrue(appsettings.get('close_to_tray', path))         # default
            appsettings.set('close_to_tray', False, path)
            self.assertFalse(appsettings.get('close_to_tray', path))
            with open(path, 'w') as f:
                f.write('{"close_to_tray": "no", "other": 1}')
            self.assertTrue(appsettings.get('close_to_tray', path))         # wrong type -> default
            with open(path, 'w') as f:
                f.write('not json')
            self.assertTrue(appsettings.get('close_to_tray', path))


class Recorder(unittest.TestCase):
    def test_collector(self):
        import recorder
        c = recorder.Collector()
        c.key(0x1E, False, True, 0.0)
        c.key(0x1E, False, True, 0.05)            # auto-repeat is ignored
        c.key(0x1E, False, False, 0.1)
        c.key(0x1D, True, False, 0.2)             # release of a key held before recording is ignored
        c.mouse(0x0201, 0.5)
        c.key(0x38, False, True, 0.75)            # still held when recording ends -> released automatically
        ev = c.finish(0.75)
        self.assertEqual(ev, [(4, True, 100, False), (4, False, 400, False), (1, True, 250, True),
                              (226, True, 10, False), (1, False, 10, True), (226, False, 10, False)])
        self.assertEqual(recorder.scan_to_usage(0x48, True), 82)       # Up arrow

    def test_full_recording_never_leaves_a_key_held(self):
        import recorder
        c = recorder.Collector(max_events=6)
        c.key(0x1D, False, True, 0.0)                                       # Ctrl held through the whole recording
        for i, s in enumerate((0x1E, 0x30, 0x2E)):                         # a, b, c tapped: only a fits next to Ctrl's release
            c.key(s, False, True, i + 0.1)
            c.key(s, False, False, i + 0.2)
        ev = c.finish(5.0)
        self.assertTrue(c.full)
        self.assertLessEqual(len(ev), 6)
        downs = [e[0] for e in ev if e[1]]
        self.assertEqual(sorted(downs), sorted(e[0] for e in ev if not e[1]))   # every press has its release
        self.assertEqual(ev[-1][:2], (224, False))
        self.assertEqual(recorder.scan_to_usage(0x48, False), 96)      # keypad 8

    def test_wait_extends_previous_event(self):
        import pages
        self.assertEqual(pages.macro_events('a{wait 500}b', 40),
                         [(4, True, 40, False), (4, False, 540, False), (5, True, 40, False), (5, False, 40, False)])

    def test_recorded_macro_events(self):
        import pages
        m = {'name': 'x', 'text': 'Recorded', 'delay': 40, 'events': [[4, True, 10, False], [4, False, 100, False]]}
        self.assertEqual(pages.events_of(m), [(4, True, 10, False), (4, False, 100, False)])
        self.assertTrue(len(ak980.Keyboard.macro_table([pages.events_of(m)])) >= 640)


class Safety(unittest.TestCase):
    def test_guard_blocks_bootloader_sequences(self):
        for bad in (bytes([0xAA, 0x42, 0x89, 0x5A, 0xFF, 0x71, 0x62, 0xCC]), bytes([0x05, 0xAA, 0x55, 0x00]),
                    bytes([0x00, 0xAA, 0x55, 0xA5, 0x5A, 0xFF, 0x00, 0x33, 0xCC])):
            with self.assertRaises(ValueError):
                ak980.guard(bad)
        for good in (bytes([0x04, 0x18]), bytes([0x0B, 0x1C, 0, 4, 0, 100]), bytes([0x07, 0x10, 0])):
            self.assertEqual(ak980.guard(good), good)

    def test_clock_packet_matches_capture(self):
        import datetime

        class K(ak980.Keyboard):
            def __init__(self):
                pass

            def transaction(self, *p):
                self.p = p
        k = K()
        k.set_time(datetime.datetime(2026, 10, 29, 15, 7, 32))                 # a Thursday
        self.assertEqual(k.p[2][:11].hex(), '00015a1a0a1d0f07200004')          # same bytes as a real capture (weekday 4)

    def test_macro_budget(self):
        import pages
        one = {'name': 'a', 'events': [[4, True, 10, False]] * 10}
        self.assertEqual(pages.macro_bytes([one]), (10 + 1) * 8)
        self.assertEqual(pages.MACRO_BUDGET, 2700)


class Misc(unittest.TestCase):
    def test_i18n_falls_back_to_english(self):
        import i18n
        i18n.set_language('Português')
        try:
            self.assertEqual(i18n.tr('Screen'), 'Ecrã')
            self.assertEqual(i18n.tr('Something new'), 'Something new')
        finally:
            i18n.set_language('English')

    def test_calibration(self):
        ak980.set_calibration(1.0, 0.5, 2.0)
        try:
            self.assertEqual(ak980.calibrate((200, 200, 100)), (200, 100, 150))        # blue gain is capped at 1.5
        finally:
            ak980.set_calibration(1, 1, 1)

    def test_diagnostics_has_no_personal_files(self):
        import diagnostics
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            p = diagnostics.save(os.path.join(d, 'd.zip'))
            names = zipfile.ZipFile(p).namelist()
        self.assertIn('report.txt', names)
        self.assertFalse(any(n in names for n in ('macros.json', 'keymap.json', 'live.json')))


class Extras(unittest.TestCase):
    def test_battery_parse(self):
        import battery
        self.assertEqual(battery.parse('{"name":"AK980 PRO","connected":true,"battery":87}'), [('AK980 PRO', True, 87)])
        self.assertEqual(battery.parse('[{"name":"x","connected":false,"battery":null}]'), [('x', False, None)])
        self.assertEqual(battery.parse('junk'), [])
        self.assertIn('No AK980', battery.summary([]))

    def test_focus_bar(self):
        import effects
        f = effects.FocusBar(1)
        self.assertEqual(len(f.frame(0)), 1)                       # just started: one key
        f.t0 -= 61                                                 # time is up: the whole keyboard flashes
        self.assertTrue(f.frame(0) == {} or len(f.frame(0)) == len(f.all_keys))
        self.assertIsNotNone(f.finished_at)

    def test_pomodoro_plan_and_bar(self):
        import effects
        plan = effects.make_plan(25, 5, 4, 15)
        self.assertEqual(plan[:3], [('focus', 25), ('break', 5), ('focus', 25)])
        self.assertEqual(plan[-1], ('break', 15))
        bar = effects.PomodoroBar([('focus', 1), ('break', 1)])
        self.assertEqual(bar.position(10)[:2], (0, 'focus'))
        self.assertEqual(bar.position(70)[:2], (1, 'break'))
        self.assertIsNone(bar.position(130))

    def test_decode_colors_hint(self):
        e = ak980.Keyboard.parse_colors(bytes([1, 200, 5, 6]))                           # red byte 200 = 2*100 or 2*228-256
        self.assertEqual(ak980.Keyboard.decode_colors(e)[1][0], 228)
        self.assertEqual(ak980.Keyboard.decode_colors(e, (100, 5, 6))[1][0], 100)
        self.assertEqual(ak980.Keyboard.decode_colors(e, {1: (230, 5, 6)})[1][0], 228)

    def test_decode_colors(self):
        d = ak980.Keyboard.decode_colors(ak980.Keyboard.parse_colors(bytes([1, 250, 253, 253, 2, 254, 0, 0, 3, 0x10, 5, 6])))
        self.assertEqual(d[1], (253, 253, 253))                      # static white at level 5 reads FA FD FD
        self.assertEqual(d[2], (255, 0, 0))
        self.assertEqual(d[3], (8, 5, 6))

    def test_gauges_frame(self):
        import effects
        g = effects.Gauges()
        out = g.frame(0)
        self.assertTrue(all(isinstance(k, int) and len(v) == 3 for k, v in out.items()))


class Backup(unittest.TestCase):
    def test_round_trip_and_refusals(self):
        import backup
        import zipfile
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            os.makedirs(os.path.join(src, 'profiles'))
            for rel, text in (('keymap.json', '{}'), ('profiles/p one.json', '[]'), ('notes.txt', 'ignored')):
                with open(os.path.join(src, rel), 'w') as f:
                    f.write(text)
            z = os.path.join(src, 'b.zip')
            self.assertEqual(backup.make(z, src), 2)                      # notes.txt is not a settings file
            self.assertEqual(backup.restore(z, dst), 2)
            self.assertTrue(os.path.exists(os.path.join(dst, 'profiles', 'p one.json')))
            evil = os.path.join(src, 'evil.zip')
            with zipfile.ZipFile(evil, 'w') as zz:
                zz.writestr('../evil.json', '{}')
            with self.assertRaises(ValueError):
                backup.check(evil)


if __name__ == '__main__':
    unittest.main()


class TestI18n(unittest.TestCase):
    def tearDown(self):
        import i18n
        i18n.set_language('English')

    def test_catalog_is_complete(self):
        import i18n_catalog
        for src, tr_ in i18n_catalog.ENTRIES.items():
            self.assertEqual(len(tr_), 4, src)
            self.assertTrue(all(tr_), src)
            for t in tr_:                                           # a translation keeps the same %-placeholders
                self.assertEqual(sorted(__import__('re').findall(r'%[-+ #0]?\d*(?:\.\d+)?[dsfi]', src)),
                                 sorted(__import__('re').findall(r'%[-+ #0]?\d*(?:\.\d+)?[dsfi]', t)), src)

    def test_translate_and_patterns(self):
        import i18n
        i18n.set_language('Français')
        self.assertEqual(i18n.tr('Brightness'), 'Luminosité')
        self.assertEqual(i18n.tr('%d slideshow frames added' % 4), '4 images de diaporama ajoutées')
        self.assertIn('(11%)', i18n.tr('Keyboard macro memory: 312 of 2700 bytes used (11%), 1 of 100 macros.'))
        self.assertEqual(i18n.tr('Some unknown text'), 'Some unknown text')
        i18n.set_language('English')
        self.assertEqual(i18n.tr('Brightness'), 'Brightness')

    def test_untr_round_trip(self):
        import i18n
        for lang in i18n.LANGUAGES[1:]:
            i18n.set_language(lang)
            for src in ('Once', 'Every day', 'Rainbow', 'Hide to the tray', 'Update automatically', 'Play once'):
                self.assertEqual(i18n.untr(i18n.tr(src)), src, (lang, src))



class ReleaseNotes(unittest.TestCase):
    def test_notes_in_the_chosen_language(self):
        import bootstrap
        nl = chr(10)
        body = nl.join(['Fixes.', '- **Lighting**: ok', '<!-- lang: Português -->', 'Correções.', '- **Iluminação**: ok',
                        '<!-- lang: Français -->', 'Corrections.'])
        self.assertEqual(bootstrap.notes_for_language(body, 'Português'), nl.join(['Correções.', '- Iluminação: ok']))
        self.assertEqual(bootstrap.notes_for_language(body, 'English'), nl.join(['Fixes.', '- Lighting: ok']))
        self.assertEqual(bootstrap.notes_for_language(body, 'Türkçe'), nl.join(['Fixes.', '- Lighting: ok']))   # no Turkish part: English
        self.assertEqual(bootstrap.notes_for_language('Plain notes', 'Português'), 'Plain notes')


class TestKeyboardV2(unittest.TestCase):
    """The firmware-769 cable protocol, with the transport replaced by a fake keyboard."""

    def fake(self):
        kb = ak980.KeyboardV2.__new__(ak980.KeyboardV2)
        kb.sent = []
        import json
        import os
        keylist = json.load(open(os.path.join(os.path.dirname(ak980.__file__), 'web_keylist.json'), encoding='utf-8'))
        top = bytearray(512)
        for pos, _n, usage, _k in keylist:
            top[pos * 4:pos * 4 + 4] = bytes([2, 0, usage, 0])
        top[96 * 4:96 * 4 + 4] = bytes([3, 0x92, 1, 0])                 # an entry outside the key list must be kept
        kb.top = top

        def ex(cmd, size, data=None, timeout=0.5, retries=3):
            if data is not None:
                kb.sent.append((cmd, bytes(data)))
                return b''
            return bytes(kb.top) if cmd == 0x12 else bytes(512)
        kb._exchange = ex
        return kb

    def test_frame_layout_and_whitelist(self):
        kb = ak980.KeyboardV2.__new__(ak980.KeyboardV2)
        f = kb._frame(0x22, 56, 112, bytes(range(56)), last=False)
        self.assertEqual(len(f), 64)
        self.assertEqual(f[:7], bytes([0xAA, 0x22, 56, 112, 0, 0, 0]))
        self.assertEqual(f[8:64], bytes(range(56)))
        self.assertEqual(kb._frame(0x22, 8, 504, bytes(8), last=True)[6], 1)
        for bad in (0x0F, 0x27, 0x01, 0x02, 0x33, 0x35, 0x36):
            with self.assertRaises(ValueError):
                kb._frame(bad, 1, 0)

    def test_set_macros_starts_a_write_on_each_flash_page(self):
        """The firmware erases a 1 KB page only for a frame that starts on it: macro data must be cut at 1024 and 2048."""
        kb = ak980.KeyboardV2.__new__(ak980.KeyboardV2)
        calls = []
        kb._exchange = lambda cmd, size, data=None, timeout=0.5, addr_start=0, last_flag=True: calls.append((cmd, size, addr_start, last_flag, data))
        ev = [(4, i % 2 == 0, 20) for i in range(600)]                    # 4 + 2400 bytes of data: ends at 2804
        kb.set_macros([ev])
        self.assertEqual([(c[1], c[2], c[3]) for c in calls], [(400, 0, False), (624, 400, False), (1024, 1024, False), (756, 2048, True)])
        index, data = ak980.KeyboardV2.macro_blocks([ev])
        self.assertEqual(b''.join(c[4] for c in calls[1:]), data)
        with self.assertRaises(ValueError):
            kb.set_macros([[(4, True, 20)] * 668])                         # 4 + 2672 bytes: one header too many

    def test_reset_frame(self):
        f = ak980.KeyboardV2.reset_frame()
        self.assertEqual((len(f), f[:3], f[3:]), (64, bytes([0xAA, 0x0F, 0xFF]), bytes(61)))

    def test_set_keymap_changes_only_listed_keys(self):
        import keys
        kb = self.fake()
        f12 = next(k[0] for k in keys.KEYS if k[1] == 'F12')
        kb.set_keymap({f12: (3, 0x92, 1)}, 'top')
        cmd, data = kb.sent[0]
        self.assertEqual(cmd, 0x22)
        self.assertEqual(len(data), 512)
        diff = [i for i in range(128) if data[i * 4:i * 4 + 4] != bytes(kb.top[i * 4:i * 4 + 4])]
        self.assertEqual(diff, [12])
        self.assertEqual(data[48:52], bytes([3, 0x92, 1, 0]))
        self.assertEqual(data[96 * 4:96 * 4 + 4], bytes([3, 0x92, 1, 0]))

    def test_unlisted_keys_return_to_default(self):
        kb = self.fake()
        kb.top[12 * 4:12 * 4 + 4] = bytes([3, 0x92, 1, 0])               # F12 was remapped earlier
        kb.set_keymap({}, 'top')
        self.assertEqual(kb.sent[0][1][48:52], bytes([2, 0, 0x45, 0]))

    def test_fn_layer_uses_fn_command(self):
        kb = self.fake()
        kb.set_keymap({}, 'fn')
        self.assertEqual(kb.sent[0][0], 0x26)

    def test_lighting_body(self):
        kb = self.fake()
        kb.set_lighting('Static', (10, 20, 30), True, 4, 2, 1)
        cmd, data = kb.sent[0]
        self.assertEqual((cmd, len(data)), (0x23, 16))
        self.assertEqual(data[:5], bytes([1, 10, 20, 30, 255]))
        self.assertEqual(data[8:12], bytes([1, 4, 2, 1]))
        self.assertEqual(data[14:], bytes([0xAA, 0x55]))

    def test_per_key_colours_and_time(self):
        import datetime
        import keys
        kb = self.fake()
        esc = next(k for k in keys.KEYS if k[1] == 'Esc')
        kb.set_user_lighting({esc[3]: (1, 2, 3)}, brightness=9)
        (c1, tab), (c2, eff) = kb.sent[0], kb.sent[1]
        self.assertEqual((c1, len(tab), c2), (0x24, 512, 0x23))
        self.assertEqual(tab[0:4], bytes([0, 1, 2, 3]))                       # Esc is position 0
        self.assertEqual(tab[4 * 5:4 * 5 + 4], bytes([5, 0, 0, 0]))           # every other led is off and keeps its own id
        self.assertEqual((eff[0], eff[9]), (0x80, 5))
        kb.sent.clear()
        kb.set_time(datetime.datetime(2026, 11, 22, 13, 45, 7))               # a Sunday
        c, body = kb.sent[0]
        self.assertEqual((c, body[:10]), (0x34, bytes([90, 1, 90, 26, 11, 22, 13, 45, 7, 0])))

    def test_macro_blocks(self):
        index, data = ak980.KeyboardV2.macro_blocks([[(4, True, 20), (4, False, 20)], [], [(1, True, 5, True), (1, False, 70000, True)]])
        self.assertEqual(len(index), 400)
        self.assertEqual(index[0:4], bytes([144, 1, 0, 0]))                  # first macro at 400
        self.assertEqual(index[4:8], bytes(4))                               # the empty one has no entry
        self.assertEqual(index[8:12], bytes([144 + 12, 1, 0, 0]))            # 4 header + 2 events * 4
        self.assertEqual(data[:12], bytes([4, 0, 0, 0, 20, 0, 4, 0xB0, 20, 0, 4, 0x30]))
        self.assertEqual(data[12:16], bytes([4, 0, 0, 0]))
        self.assertEqual(data[16:20], bytes([10, 0, 1, 0x90]))               # delay raised to the 10 ms minimum, mouse button down
        self.assertEqual(data[20:24], bytes([255, 255, 1, 0x10]))            # delay capped at 65535

    def test_frames_use_the_start_address(self):
        kb = ak980.KeyboardV2.__new__(ak980.KeyboardV2)
        f = kb._frame(0x25, 56, 400 + 56, bytes(56), last=True)
        self.assertEqual((f[3], f[4], f[6]), ((456) & 255, 456 >> 8, 1))

    def test_screen_payload(self):
        from PIL import Image
        imgs = [Image.new('RGB', (240, 135), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
        p = ak980.KeyboardV2.screen_payload(imgs, [100, 200, 300])
        self.assertEqual(len(p), 256 + 3 * 240 * 135 * 2)
        self.assertEqual(list(p[:5]), [3, 50, 100, 0, 255])                # count, 100/2, 200/2, last = 0, rest 0xFF
        self.assertEqual(p[256:258], (0xF800).to_bytes(2, 'little'))      # pure red in RGB565


class TestNowPlayingParse(unittest.TestCase):
    def test_accented_title_and_none(self):
        import live
        self.assertEqual(live.parse_nowplaying('{"title":"CORAÇÃO CIGANO","artist":"Luan Santana","status":"Playing"}'),
                         ('CORAÇÃO CIGANO', 'Luan Santana', 'Playing'))
        self.assertIsNone(live.parse_nowplaying(None))
        self.assertIsNone(live.parse_nowplaying('{}'))
