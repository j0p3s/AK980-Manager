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
