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
