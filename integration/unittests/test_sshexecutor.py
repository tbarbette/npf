import argparse
import os
import shlex
import tempfile
import unittest
from unittest import mock

import npf.globals


class TestSSHExecutorProxyCommand(unittest.TestCase):
    def setUp(self):
        saved = npf.globals.options
        self.addCleanup(setattr, npf.globals, "options", saved)
        npf.globals.options = argparse.Namespace(color=False, sshconfig=True)
        self.home = tempfile.mkdtemp(prefix="npf-ut-home-")
        os.mkdir(os.path.join(self.home, ".ssh"))
        with open(os.path.join(self.home, ".ssh", "config"), "w") as f:
            f.write("Host *.example.org\n  Port 2200\n  ProxyCommand ssh -W %h:%p -o 'ProxyJump gw0' gw\n")

    def test_through_a_shell(self):
        from npf.executor.sshexecutor import SSHExecutor
        with mock.patch.dict(os.environ, {"HOME": self.home}), \
                mock.patch("paramiko.SSHClient.connect"), mock.patch("paramiko.ProxyCommand") as proxy:
            SSHExecutor(None, "n1.example.org", "/tmp/x", 22).get_connection(cache=False)
        # As ssh does, so quotes, $(...) and pipes work: paramiko would give ssh "'ProxyJump" and "gw0'"
        self.assertEqual(shlex.split(proxy.call_args.args[0]),
                         ["/bin/sh", "-c", "ssh -W n1.example.org:2200 -o 'ProxyJump gw0' gw"])


class TestSSHExecutorSharedConnection(unittest.TestCase):
    """The scripts of a node share one connection, each in its own channel."""

    def setUp(self):
        saved = npf.globals.options
        self.addCleanup(setattr, npf.globals, "options", saved)
        npf.globals.options = argparse.Namespace(color=False, sshconfig=False, quiet=True, show_cmd=False,
                                                 cwd="/tmp/", experiment_folder="/tmp/")
        from npf.executor.sshexecutor import SSHExecutor
        self.ex = SSHExecutor("root", "n1", "/tmp/x", 22)
        self.clients = []
        p = mock.patch.object(SSHExecutor, "_connect", side_effect=self._client)
        p.start()
        self.addCleanup(p.stop)

    def _client(self):
        c = mock.Mock(name="client%d" % len(self.clients))
        c.get_transport.return_value.is_active.return_value = True
        c.exec_command.side_effect = self._command
        self.clients.append(c)
        return c

    @staticmethod
    def _command(cmd, get_pty=False):
        out = mock.Mock()
        out.channel.exit_status_ready.return_value = True
        out.channel.recv_ready.return_value = False
        out.channel.recv_exit_status.return_value = 0
        err = mock.Mock()
        err.channel.recv_ready.return_value = False
        return mock.Mock(), out, err

    def run_script(self):
        from npf.tests.eventbus import EventBus
        return self.ex.exec("true", event=mock.Mock(spec=EventBus, is_terminated=mock.Mock(return_value=False)))

    def test_one_connection(self):
        self.run_script()
        self.run_script()
        self.assertEqual(len(self.clients), 1)
        self.assertEqual(self.clients[0].exec_command.call_count, 2)
        self.clients[0].close.assert_not_called()

    def test_reconnects_when_closed(self):
        self.run_script()
        self.clients[0].get_transport.return_value.is_active.return_value = False
        self.run_script()
        self.assertEqual(len(self.clients), 2)
        self.clients[0].close.assert_called_once()

    def test_channel_refused(self):
        import paramiko
        shared = self.ex.get_connection()
        # Seen as a plain SSHException when other threads open channels at the same time
        shared.exec_command.side_effect = paramiko.ssh_exception.SSHException("Unable to open channel.")
        self.run_script()
        self.assertEqual(len(self.clients), 2, "a connection of its own when sshd's MaxSessions is reached")
        self.clients[1].close.assert_called_once()
        shared.close.assert_not_called()
        self.assertIs(self.ex.get_connection(), shared)

    def kill_script(self, data, **kwargs):
        """Runs a script that prints data, killed once it is read. :return: the commands sent after the script"""
        shared = self.ex.get_connection()
        read = []
        script = self._command(None)
        script[1].channel.exit_status_ready.return_value = False
        script[1].channel.recv_ready.side_effect = lambda: not read
        script[1].channel.recv.side_effect = lambda n: read.append(1) or data
        shared.exec_command.side_effect = [script] + [self._command(None) for _ in range(3)]
        before = shared.exec_command.call_count
        self.ex.exec("iperf -s", event=mock.Mock(is_terminated=lambda: bool(read)), **kwargs)
        return [c.args[0] for c in shared.exec_command.call_args_list[before + 1:]]

    def test_kill_process_group(self):
        self.assertEqual(self.kill_script(b"4242\n"), ["kill -- -4242 2>/dev/null; kill 4242 2>/dev/null; true"])
        self.ex.user = "bob"
        self.assertEqual(self.kill_script(b"4242\n", sudo=True, testdir="t"),
                         ["sudo -n sh -c 'kill -- -4242 2>/dev/null; kill 4242 2>/dev/null; true'"])

    def test_no_kill_before_the_pid(self):
        # "kill -1" would signal every process of the user
        self.assertEqual(self.kill_script(b"42"), [])

    def stream(self, chunks, **kwargs):
        """Runs a script whose output comes in chunks, None being a pause. :return: the script's channel, the events"""
        shared = self.ex.get_connection()
        script = self._command(None)
        chunks = list(chunks)
        ch = script[1].channel

        def recv_ready():
            # A pause lasts one check
            if chunks and chunks[0] is None:
                chunks.pop(0)
                return False
            return bool(chunks)
        ch.exit_status_ready.side_effect = lambda: not chunks
        ch.recv_ready.side_effect = recv_ready
        ch.recv.side_effect = lambda n: chunks.pop(0)
        shared.exec_command.side_effect = [script]
        event = mock.Mock(is_terminated=mock.Mock(return_value=False))
        self.ex.exec("x", event=event, **kwargs)
        return script, shared.exec_command.call_args, [c.args[0] for c in event.post.call_args_list]

    def test_pty(self):
        script, call, _ = self.stream([b"4242\n", b"out\n"], stdin="input")
        self.assertTrue(call.kwargs["get_pty"])
        self.assertTrue(call.args[0].startswith("stty -echo 2>/dev/null; echo $$;"))
        # Sent once the pid is read, so after stty disabled the echo
        script[0].write.assert_called_once_with("input")

    def test_raw_has_no_pty(self):
        _, call, _ = self.stream([b"4242\n"], raw=True)
        self.assertFalse(call.kwargs["get_pty"])
        self.assertTrue(call.args[0].startswith("echo $$;"))

    def test_event_without_newline(self):
        # printf "EVENT ready", then a pause: posted once, not again when the line ends
        _, _, events = self.stream([b"4242\n", b"EVENT ready", None, None, b" EVENT done\n"])
        self.assertEqual(events, ["ready", "done"])


if __name__ == '__main__':
    unittest.main()
