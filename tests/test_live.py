# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import live  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def make(plan='Balanced'):
    clock = Clock()
    log = {'up': [], 'back': 0, 'fail': False}
    s = live.load_settings(os.devnull)
    s.update({'enabled': False, 'plan': plan, 'hold_seconds': 60})

    def upload(img):
        if log['fail']:
            raise OSError('no cable')
        log['up'].append(live.fingerprint(img))

    def restore():
        log['back'] += 1
    w = live.Worker(s, upload, restore, clock=clock, save=lambda settings: None)         # never touch the real settings file
    w.budget.updated = clock.t
    return w, clock, log


class BudgetTests(unittest.TestCase):
    def test_burst_then_refill(self):
        b = live.Budget('Saver', updated=100.0)                      # 8 a day, 3 stored
        self.assertEqual([b.take(100.0) for _ in range(4)], [True, True, True, False])
        self.assertAlmostEqual(b.wait_seconds(100.0), 3 * 3600, delta=5)        # 8 a day = one every 3 hours
        self.assertTrue(b.take(100.0 + 3 * 3600 + 5))

    def test_forced_never_blocked(self):
        b = live.Budget('Saver', tokens=0.0, updated=5.0)
        self.assertTrue(b.take(5.0, force=True))
        self.assertEqual(b.tokens, 0.0)


class WorkerTests(unittest.TestCase):
    def test_same_card_is_not_uploaded_twice(self):
        w, c, log = make()
        img = live.reminder_card('hi')
        w.offer('reminder:a', img)
        w.step()
        w.offer('reminder:a', img)
        w.step()
        self.assertEqual(len(log['up']), 1)

    def test_budget_makes_cards_wait_and_newest_wins(self):
        w, c, log = make('Saver')                                    # 3 back to back
        for i in range(5):
            w.offer('nowplaying', live.song_card('song %d' % i, 'a', 'Playing'))
            w.step()
        self.assertEqual(len(log['up']), 3)
        self.assertIsNotNone(w.pending)                              # the 4th is waiting, the 5th replaced it
        self.assertEqual(live.fingerprint(live.song_card('song 4', 'a', 'Playing')), w.pending[4])
        c.t += 3 * 3600 + 10
        w.step()
        self.assertEqual(len(log['up']), 4)

    def test_higher_priority_card_replaces_lower_but_not_the_reverse(self):
        w, c, log = make()
        w.offer('reminder:x', live.reminder_card('r'))
        w.offer('clock', live.clock_card(datetime.datetime(2026, 1, 1, 9, 0)))
        self.assertEqual(w.pending[1], 'reminder:x')
        w.offer('reminder:y', live.reminder_card('later'))
        self.assertEqual(w.pending[1], 'reminder:y')

    def test_failed_upload_is_given_back(self):
        w, c, log = make()
        log['fail'] = True
        before = w.budget.tokens
        w.offer('reminder:x', live.reminder_card('r'))
        w.step()
        self.assertEqual(w.budget.tokens, before)
        self.assertIsNotNone(w.pending)
        log['fail'] = False
        w.step()
        self.assertEqual(len(log['up']), 1)

    def test_users_picture_comes_back_after_a_temporary_card(self):
        w, c, log = make()
        w.offer('reminder:x', live.reminder_card('r'), temporary=True)
        w.step()
        self.assertEqual(log['back'], 0)
        c.t += 61
        w.step()
        self.assertEqual(log['back'], 1)

    def test_send_now_bypasses_budget(self):
        w, c, log = make('Saver')
        w.budget.tokens = 0.0
        w.send_now(live.reminder_card('now'))
        w.step()
        self.assertEqual(len(log['up']), 1)


class LongRunTests(unittest.TestCase):
    def test_burst_plan_holds_over_days(self):
        """A new card every minute for two days: the first day may use the stored burst, every later day the plan's count."""
        from PIL import Image
        t, ups = [1_800_000_000.0], []
        w = live.Worker({'enabled': False, 'plan': 'Burst', 'hold_seconds': 120}, upload=lambda img: ups.append(t[0]),
                        restore=lambda: ups.append(t[0]), clock=lambda: t[0], save=lambda s: None)
        for n in range(2 * 24 * 60):
            w.offer('music:%d' % n, Image.new('RGB', (4, 4), (n % 256, n // 256 % 256, 1)), temporary=n % 5 == 0)
            w.step()
            t[0] += 60
        day2 = sum(1 for u in ups if u >= 1_800_000_000 + 86400)
        self.assertLessEqual(len(ups) - day2, 96 + 8)
        self.assertEqual(day2, 96)

    def test_failed_forced_upload_gives_nothing_back_extra(self):
        t = [1_800_000_000.0]

        def fail(img):
            raise OSError('unplugged')
        from PIL import Image
        w = live.Worker({'enabled': False, 'plan': 'Saver'}, upload=fail, restore=lambda: None, clock=lambda: t[0], save=lambda s: None)
        w.budget.tokens, w.budget.updated = 0.25, t[0]
        w.send_now(Image.new('RGB', (4, 4)))
        w.step()
        self.assertAlmostEqual(w.budget.tokens, 0.25)


class CalendarTests(unittest.TestCase):
    ICS = 'BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nDTSTART;TZID="(UTC+01:00) Amsterdam, Berlin":20261127T100000\r\nSUMMARY:Planning\\, Q4\\; budget \\\\ review\r\nBEGIN:VALARM\r\nTRIGGER:-PT15M\r\nDESCRIPTION:Reminder\r\nEND:VALARM\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nDTSTART:20261127T110000\r\nSUMMARY:Cancelled one\r\nSTATUS:CANCELLED\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'

    def test_outlook_quoted_tzid_escapes_and_cancelled(self):
        ev = live.parse_ics(self.ICS)
        self.assertEqual(ev, [(datetime.datetime(2026, 11, 27, 10, 0), 'Planning, Q4; budget ' + chr(92) + ' review')])

    def test_a_meeting_is_uploaded_once(self):
        """The card shows the start time, not a countdown: one upload per meeting, not one a minute."""
        import tempfile
        start = datetime.datetime(2026, 11, 27, 10, 0)
        f = tempfile.NamedTemporaryFile('w', suffix='.ics', delete=False, encoding='utf-8')
        f.write('BEGIN:VEVENT\nDTSTART:%s\nSUMMARY:Standup\nEND:VEVENT\n' % start.strftime('%Y%m%dT%H%M%S'))
        f.close()
        t = [(start - datetime.timedelta(minutes=50)).timestamp()]
        ups = []
        s = {'enabled': True, 'plan': 'Burst', 'ics': f.name, 'hold_seconds': 120, 'reminders': [],
             'sources': {'calendar': True, 'nowplaying': False, 'clock': False}}
        w = live.Worker(s, upload=lambda img: ups.append('up'), restore=lambda: ups.append('back'), clock=lambda: t[0], save=lambda s: None)
        for _ in range(60):
            w.step()
            t[0] += 60
        os.unlink(f.name)
        self.assertEqual(ups.count('up'), 1)

    def test_webcal_links_are_fetched_over_https(self):
        seen = []
        orig = live.urllib.request.urlopen
        live.urllib.request.urlopen = lambda req, timeout=0: seen.append(req.full_url) or (_ for _ in ()).throw(OSError())
        try:
            self.assertEqual(live.load_ics('webcal://calendar.example/basic.ics'), '')
        finally:
            live.urllib.request.urlopen = orig
        self.assertEqual(seen, ['https://calendar.example/basic.ics'])


class CounterTests(unittest.TestCase):
    def test_counts_per_day(self):
        import tempfile
        d = os.path.join(tempfile.mkdtemp(), 'u.json')
        day1, day2 = datetime.date(2026, 11, 23), datetime.date(2026, 11, 24)
        self.assertEqual(live.count_upload(d, day1), (1, 1))
        self.assertEqual(live.count_upload(d, day1), (2, 2))
        self.assertEqual(live.count_upload(d, day2), (3, 1))
        self.assertEqual(live.uploads(d, day1), (3, 2))


class ReminderTests(unittest.TestCase):
    def test_once_daily_and_every(self):
        dt = datetime.datetime(2026, 11, 23, 10, 5)
        once = {'at': '2026-11-23 10:00', 'text': 'a', 'repeat': 'Once'}
        self.assertIsNotNone(live.reminder_due(once, dt, set()))
        self.assertIsNone(live.reminder_due(once, datetime.datetime(2026, 11, 23, 11, 0), set()))
        fired = {live.reminder_due(once, dt, set())}
        self.assertIsNone(live.reminder_due(once, dt, fired))
        daily = {'at': '2026-01-01 10:00', 'text': 'd', 'repeat': 'Every day'}
        self.assertIsNotNone(live.reminder_due(daily, dt, set()))
        self.assertIsNotNone(live.reminder_due(daily, datetime.datetime(2027, 3, 4, 10, 2), set()))
        every = {'text': 'e', 'repeat': 'Every N minutes (work hours)', 'every': 30, 'from': '09:00', 'to': '18:00'}
        self.assertIsNotNone(live.reminder_due(every, datetime.datetime(2026, 11, 23, 10, 31), set()))
        self.assertIsNone(live.reminder_due(every, datetime.datetime(2026, 11, 23, 10, 45), set()))     # between slots
        self.assertIsNone(live.reminder_due(every, datetime.datetime(2026, 11, 23, 20, 0), set()))      # after work hours


class PomodoroTests(unittest.TestCase):
    def test_plan_advances_and_ends(self):
        w, c, log = make()
        w.s['enabled'] = True
        w.s['sources'] = {'clock': False, 'nowplaying': False, 'calendar': False}
        w.start_pomodoro([('focus', 1), ('break', 1)])
        w.step()
        self.assertEqual(len(log['up']), 1)                          # focus card
        c.t += 61
        w.step()
        self.assertEqual(len(log['up']), 2)                          # break card
        c.t += 61
        w.step()
        self.assertEqual(len(log['up']), 3)                          # done card
        self.assertIsNone(w.pomo)


class SourceTests(unittest.TestCase):
    def test_ics(self):
        text = 'BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nDTSTART:20261123T150000\r\nSUMMARY:Team\\, sync\r\nEND:VEVENT\r\nEND:VCALENDAR'
        ev = live.parse_ics(text)
        self.assertEqual(ev[0][1], 'Team, sync')
        self.assertIsNotNone(live.next_event(ev, datetime.datetime(2026, 11, 23, 14, 30)))
        self.assertIsNone(live.next_event(ev, datetime.datetime(2026, 11, 23, 9, 0)))

    def test_nowplaying_parse(self):
        self.assertEqual(live.parse_nowplaying('{"title":"S","artist":"A","status":"Playing"}'), ('S', 'A', 'Playing'))
        self.assertIsNone(live.parse_nowplaying('{}'))
        self.assertIsNone(live.parse_nowplaying('garbage'))

    def test_cards_are_screen_sized(self):
        for img in (live.clock_card(datetime.datetime.now(), 'MM/DD/YYYY'), live.song_card('x' * 200, 'y' * 200, 'Playing')):
            self.assertEqual(img.size, (240, 135))


if __name__ == '__main__':
    unittest.main()
