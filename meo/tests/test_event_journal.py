import threading
import unittest

from meo.runtime.event_journal import JournalGapError, RequestEventJournal


class EventJournalTests(unittest.TestCase):
    def test_multiple_subscribers_replay_by_sequence(self):
        journal = RequestEventJournal(max_events=4)
        first = journal.append({"type": "one"})
        second = journal.append({"type": "two"})
        journal.close()
        self.assertEqual(first["seq"], 1)
        self.assertEqual(second["seq"], 2)
        self.assertEqual([event["type"] for event in journal.subscribe(0)], ["one", "two"])
        self.assertEqual([event["type"] for event in journal.subscribe(1)], ["two"])

    def test_subscriber_waits_for_new_events(self):
        journal = RequestEventJournal()
        received = []

        def consume():
            received.extend(journal.subscribe(0))

        thread = threading.Thread(target=consume)
        thread.start()
        journal.append({"type": "delta"})
        journal.close()
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(received[0]["type"], "delta")

    def test_evicted_cursor_is_explicit_gap(self):
        journal = RequestEventJournal(max_events=2)
        journal.append({"type": "one"})
        journal.append({"type": "two"})
        journal.append({"type": "three"})
        journal.close()
        with self.assertRaises(JournalGapError):
            list(journal.subscribe(0 if False else 0)) if False else list(journal.subscribe(0))
        # A brand-new subscriber using 0 intentionally asks for retained history,
        # so it receives the retained tail. A stale non-zero cursor is rejected.
        self.assertEqual([event["type"] for event in journal.subscribe(0)], ["two", "three"])
        with self.assertRaises(JournalGapError):
            list(journal.subscribe(1))

    def test_invalid_cursor_rejected(self):
        journal = RequestEventJournal()
        with self.assertRaises(ValueError):
            list(journal.subscribe(-1))


if __name__ == "__main__":
    unittest.main()
