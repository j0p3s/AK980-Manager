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


if __name__ == '__main__':
    unittest.main()
