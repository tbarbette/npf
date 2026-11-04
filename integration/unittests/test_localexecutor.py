import argparse
import os
import pty
import time
import unittest
from unittest import mock

import npf.globals
from npf.executor.localexecutor import LocalExecutor

# Like python's print, perl's print fills a buffer when stdout is a pipe, but flushes each line in a terminal
BUFFERED_EVENT = "perl -e 'print \"EVENT ready\\n\"; sleep 3'"


class TestLocalLiveOutput(unittest.TestCase):
    def setUp(self):
        saved = npf.globals.options
        self.addCleanup(setattr, npf.globals, "options", saved)
        npf.globals.options = argparse.Namespace(color=False, cwd=os.getcwd(), experiment_folder=os.getcwd())

    def test_event_seen_when_printed(self):
        seen = []
        event = mock.Mock(is_terminated=mock.Mock(return_value=False))
        event.post.side_effect = lambda ev: seen.append(time.time())
        start = time.time()
        LocalExecutor().exec(BUFFERED_EVENT, event=event)
        self.assertTrue(seen, "EVENT not seen")
        self.assertLess(seen[0] - start, 2)

    def test_stderr_kept_apart(self):
        _, out, err, ret = LocalExecutor().exec("echo OUT; echo ERR >&2")
        self.assertEqual((out, err.strip(), ret), ("OUT\n", "ERR", 0))

    def test_last_output(self):
        # Printed just before the script ends, after a pause of the loop: macOS drops it if the terminal is closed
        cmd = "sleep 0.19; " + "; ".join("echo L%d" % i for i in range(7))
        for _ in range(5):
            _, out, _, _ = LocalExecutor().exec(cmd)
            self.assertEqual(out.split(), ["L%d" % i for i in range(7)])

    def test_read_lines(self):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        os.write(slave, b"one\ntwo\nthr")
        os.set_blocking(master, False)
        self.assertEqual([l.replace(b"\r", b"") for l in LocalExecutor._read_lines(master)], [b"one\n", b"two\n", b"thr"])
        self.assertEqual(LocalExecutor._read_lines(master), [])


if __name__ == '__main__':
    unittest.main()
