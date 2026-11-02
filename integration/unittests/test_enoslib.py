import argparse
import multiprocessing
import os
import shlex
import tempfile
import threading
import time
import unittest
from unittest import mock

import npf.globals

try:
    import enoslib as en
    from enoslib.api import CommandResult
except ImportError:
    en = None


class TestEnoslib(unittest.TestCase):
    def test_enoslib(self):
        try:
            import enoslib as en
            from npf.enoslib import run
            run('integration/sections.npf', roles={"localhost":en.LocalHost()}, argsv=[])

        except ImportError as e:
            print("Enoslib test ignored as enoslib is not installed")
            pass  # module doesn't exist, deal with it.


class _ExecutorTest(unittest.TestCase):
    def setUp(self):
        saved = npf.globals.options
        self.addCleanup(setattr, npf.globals, "options", saved)
        self.dir = tempfile.mkdtemp(prefix="npf-ut-")
        npf.globals.options = argparse.Namespace(color=False, experiment_folder=self.dir, cwd=self.dir,
                                                 quiet=True, show_cmd=False)
        # Killers go through a manager queue in Test.execute, so they must be picklable
        self.manager = multiprocessing.Manager()
        self.addCleanup(self.manager.shutdown)

    def executor(self, host, **extra_vars):
        from npf.executor.enoslibexecutor import EnoslibExecutor
        return EnoslibExecutor(host, extra_vars=extra_vars)


@unittest.skipIf(en is None, "enoslib is not installed")
class TestEnoslibSSHExecutor(_ExecutorTest):
    """ssh and local hosts are driven directly, with live output."""

    def test_ssh_command_like_ansible(self):
        ex = self.executor(en.Host("node-1.example.org", user="root", port=2222, keyfile="/k",
                                   extra={"gateway": "access.example.org", "gateway_user": "me"}))
        self.assertEqual(ex.connection, "ssh")
        cmd = ex.ssh_command(tty=True)
        self.assertEqual(cmd[-2:], ["--", "node-1.example.org"])
        self.assertIn("StrictHostKeyChecking=no", cmd)
        self.assertIn("-tt", cmd)
        for opt in (["-l", "root"], ["-p", "2222"], ["-i", "/k"]):
            self.assertIn(" ".join(opt), " ".join(cmd))
        proxy = [a for a in cmd if a.startswith("ProxyCommand=")]
        self.assertEqual(len(proxy), 1)
        self.assertIn("-l me access.example.org", proxy[0])

    def test_ssh_common_args_override_npf_defaults(self):
        # ssh keeps the first value of an option: user-given arguments must come before NPF's ControlPath
        ex = self.executor(en.Host("node-1"), ansible_ssh_common_args="-o ControlPath=none -o ProxyJump=gw")
        cmd = ex.ssh_command()
        self.assertLess(cmd.index("ControlPath=none"), cmd.index("ControlPath=/tmp/npf-cm-%C"))
        self.assertIn("ProxyJump=gw", cmd)
        self.assertNotIn("-tt", cmd)
        # The user handles multiplexing: no shared connection is opened
        with mock.patch("npf.executor.enoslibexecutor.subprocess.run") as run:
            ex._ensure_master()
        run.assert_not_called()

    def test_shared_connection_in_own_session(self):
        # A script's ssh must never become the master: its ProxyCommand would stay in the script's process group
        ex = self.executor(en.Host("node-1"))
        self.assertIn("ControlMaster=no", ex.ssh_command())
        down, up = mock.Mock(returncode=255), mock.Mock(returncode=0)
        with mock.patch("npf.executor.enoslibexecutor.subprocess.run", side_effect=[down, up]) as run:
            ex._ensure_master()
        check, master = run.call_args_list
        self.assertIn("check", check.args[0])
        self.assertTrue({"-M", "-N", "-f"} <= set(master.args[0]))
        self.assertTrue(master.kwargs["start_new_session"])
        with mock.patch("npf.executor.enoslibexecutor.subprocess.run", return_value=up) as run:
            ex._ensure_master()
        self.assertEqual(run.call_count, 1, "an existing master is reused")

    def test_local_environment_not_sent(self):
        ex = self.executor(en.Host("node-1"))
        with mock.patch.object(type(ex), "_run", return_value=(1, "", "", 0)) as run, \
                mock.patch.object(type(ex), "_ensure_master"), mock.patch.dict(os.environ, {"NPF_UT_SECRET": "s3cr3t"}):
            ex.exec("true", env={"NPF_REPO": "local"}, options=npf.globals.options)
        cmd = run.call_args.args[0]
        self.assertTrue(cmd.startswith("ssh "))
        self.assertIn("NPF_REPO=local", cmd)
        self.assertNotIn("s3cr3t", cmd)
        self.assertNotIn("export HOME=", cmd)

    def test_local_host_live_output_and_kill(self):
        from npf.tests.eventbus import EventBus
        ex = self.executor(en.LocalHost())
        self.assertEqual(ex.connection, "local")
        pid, out, err, ret = ex.exec("echo out; echo err >&2; pwd", options=npf.globals.options)
        self.assertEqual((ret, err), (0, "err\n"))
        self.assertEqual(out.splitlines()[0], "out")
        self.assertEqual(os.path.realpath(out.splitlines()[1]), os.path.realpath(self.dir))

        eb = EventBus()
        q = self.manager.Queue()
        result = {}
        t = threading.Thread(target=lambda: result.update(r=ex.exec("echo EVENT ready; sleep 30", queue=q, event=eb,
                                                                      options=npf.globals.options)))
        start = time.time()
        t.start()
        # The event must be seen while the script still runs
        eb.listen("ready")
        self.assertLess(time.time() - start, 10)
        killer = q.get(timeout=10)
        self.assertTrue(killer.is_alive())
        killer.kill()
        t.join(15)
        self.assertFalse(t.is_alive(), "the killed script must return")
        self.assertFalse(killer.is_alive())
        self.assertFalse(os.path.exists(killer.pid_file))

    def test_local_host_write_file(self):
        ex = self.executor(en.LocalHost())
        with mock.patch("builtins.print"):
            self.assertTrue(ex.writeFile("f.txt", "sub", "hello $X\n"))
        with open(os.path.join(self.dir, "sub", "f.txt")) as f:
            self.assertEqual(f.read(), "hello $X\n")


@unittest.skipIf(en is None, "enoslib is not installed")
class TestEnoslibAnsibleExecutor(_ExecutorTest):
    """Hosts with another ansible connection go through en.run_command, mocked here so no host is needed."""

    def setUp(self):
        super().setUp()
        self.ex = self.executor(en.Host("node-1.example.org", user="root", extra={"ansible_connection": "paramiko"}))
        self.cmds = []

    def _run_command(self, *results):
        def run_command(cmd, roles, **kwargs):
            self.cmds.append(cmd)
            return [results[min(len(self.cmds), len(results)) - 1]]
        return mock.patch("npf.executor.enoslibexecutor.en.run_command", side_effect=run_command)

    def test_output(self):
        ok = CommandResult(host="node-1", task="t", status="OK", payload={"stdout": "RESULT 1", "stderr": "", "rc": 0})
        with self._run_command(ok):
            pid, out, err, rc = self.ex.exec("echo RESULT 1", options=npf.globals.options)
        self.assertEqual((out, rc), ("RESULT 1", 0))

    def test_unreachable_is_a_failed_script(self):
        # With on_error_continue, enoslib returns unreachable hosts as a result without stdout/rc
        unreachable = CommandResult(host="node-1", task="t", status="UNREACHABLE",
                                    payload={"unreachable": True, "changed": False,
                                             "msg": "Failed to connect to the host via ssh: Shared connection to node-1 closed."})
        with self._run_command(unreachable), mock.patch("builtins.print"):
            pid, out, err, rc = self.ex.exec("iperf -s", options=npf.globals.options)
        self.assertEqual(rc, 255)
        self.assertEqual(out, "")
        self.assertIn("Shared connection", err)

    def test_killer_skips_finished_script(self):
        ok = CommandResult(host="node-1", task="t", status="OK", payload={"stdout": "", "stderr": "", "rc": 0})
        q = self.manager.Queue()
        with self._run_command(ok):
            self.ex.exec("true", queue=q, options=npf.globals.options)
            killer = q.get(block=False)
            self.assertFalse(killer.is_alive())
            killer.kill()
            killer.force_kill()
        self.assertEqual(len(self.cmds), 1, "no ansible play must be spent on a finished script")

    def test_killer_running_script(self):
        from npf.executor import enoslibexecutor
        killer = enoslibexecutor.EnoslibAnsibleKiller(self.ex.machine, "/tmp/npf-ut.pid")
        enoslibexecutor._running.add("/tmp/npf-ut.pid")
        self.addCleanup(enoslibexecutor._running.discard, "/tmp/npf-ut.pid")
        echoed = CommandResult(host="node-1", task="t", status="OK", payload={"stdout": "4242\n", "stderr": "", "rc": 0})
        with self._run_command(echoed):
            self.assertTrue(killer.is_alive())
            killer.kill()
            killer.force_kill()
        self.assertEqual(len(self.cmds), 2)
        self.assertIn("cat /tmp/npf-ut.pid", self.cmds[0])
        self.assertIn("kill -9", self.cmds[0])
        # The pid file is gone after the first kill, the second signal uses the pid echoed back
        self.assertIn("_p=4242;", self.cmds[1])
        self.assertIn("kill -15", self.cmds[1])

    def test_local_environment_not_sent(self):
        ok = CommandResult(host="node-1", task="t", status="OK", payload={"stdout": "", "stderr": "", "rc": 0})
        with self._run_command(ok), mock.patch.dict(os.environ, {"NPF_UT_SECRET": "s3cr3t"}):
            self.ex.exec("true", env={"NPF_REPO": "local"}, options=npf.globals.options)
        self.assertIn("NPF_REPO=local", self.cmds[0])
        self.assertNotIn("s3cr3t", self.cmds[0])
        self.assertNotIn("export HOME=", self.cmds[0])
