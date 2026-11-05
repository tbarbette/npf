import argparse
import multiprocessing
import os
import shlex
import tempfile
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
class TestEnoslibAnsibleExecutor(_ExecutorTest):
    """Scripts go through en.run_command, mocked here so no host is needed."""

    def setUp(self):
        super().setUp()
        self.ex = self.executor(en.Host("node-1.example.org", user="root", ))
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
        killer = enoslibexecutor.EnoslibKiller(self.ex.machine, "/tmp/npf-ut.pid")
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

    def test_sudo_decided_on_the_node(self):
        ok = CommandResult(host="node-1", task="t", status="OK", payload={"stdout": "", "stderr": "", "rc": 0})
        with self._run_command(ok):
            self.ex.exec("whoami", sudo=True, options=npf.globals.options)
            self.ex.exec("whoami", options=npf.globals.options)
        sudo, plain = self.cmds
        self.assertTrue(sudo.startswith('S=; [ "$(id -u)" != 0 ] && command -v sudo'))
        self.assertIn(" && $S  bash -c '", sudo)
        self.assertTrue(plain.startswith("S=; mkdir -p "))


    def test_timeout_applies_to_the_script(self):
        # Without it, a script waiting for an EVENT of a server (seen only when it ends) would wait forever
        ok = CommandResult(host="node-1", task="t", status="OK", payload={"stdout": "", "stderr": "", "rc": 0})
        with self._run_command(ok):
            self.ex.exec("iperf -s", queue=self.manager.Queue(), timeout=30, options=npf.globals.options)
            self.ex.exec("true", options=npf.globals.options)
        self.assertIn(" && timeout -k 5 30 $S ", self.cmds[0])
        self.assertNotIn("timeout", self.cmds[1])

@unittest.skipIf(en is None, "enoslib is not installed")
class TestEnoslibSSHParameters(unittest.TestCase):
    """enoslib_ssh=True: the parameters ansible would get, for NPF's SSH executor."""

    def params(self, host, **extra_vars):
        from npf.executor.enoslibexecutor import ssh_parameters
        return ssh_parameters(host, extra_vars)

    def test_gateway(self):
        p = self.params(en.Host("node-1.example.org", user="root", port=2222, keyfile="~/.ssh/k",
                                extra={"gateway": "access.example.org", "gateway_user": "me"}))
        self.assertEqual({k: p[k] for k in ("hostname", "username", "port", "identityfile")},
                         {"hostname": "node-1.example.org", "username": "root", "port": 2222, "identityfile": "~/.ssh/k"})
        self.assertTrue(p["proxycommand"].startswith("ssh -W %h:%p "))
        self.assertTrue(p["proxycommand"].endswith(" -l me access.example.org"))

    def test_no_gateway(self):
        p = self.params(en.Host("node-1"))
        self.assertEqual((p["hostname"], p["port"], p["proxycommand"], p["identityfile"]), ("node-1", 22, None, None))

    def test_two_gateways(self):
        p = self.params(en.Host("node-1", extra={"gateway": "a.org", "internal_gateway": "b.org"}))
        # The inner %% are for the second ssh: SSHExecutor expands one level, as ssh does
        self.assertRegex(p["proxycommand"], r"^ssh -W %h:%p .*-o ProxyCommand='ssh -W %%h:%%p .* a\.org' b\.org$")

    def test_extra_vars_win(self):
        p = self.params(en.Host("node-1", user="root"), ansible_user="bob", ansible_ssh_common_args="-o ProxyJump=a,b")
        self.assertEqual(p["username"], "bob")
        self.assertEqual(p["proxycommand"], "ssh -W %h:%p -J a b")

    def test_not_ssh(self):
        self.assertEqual(self.params(en.LocalHost()), "local")
        self.assertIsNone(self.params(en.Host("c", extra={"ansible_connection": "docker"})))


class TestSSHExecutorOverrides(unittest.TestCase):
    def setUp(self):
        saved = npf.globals.options
        self.addCleanup(setattr, npf.globals, "options", saved)
        npf.globals.options = argparse.Namespace(color=False, sshconfig=True)
        self.home = tempfile.mkdtemp(prefix="npf-ut-home-")
        os.mkdir(os.path.join(self.home, ".ssh"))
        with open(os.path.join(self.home, ".ssh", "config"), "w") as f:
            f.write("Host *.example.org\n  User alice\n  Port 2200\n  IdentityFile ~/.ssh/alice\n"
                    "  ProxyCommand ssh -W %h:%p config-gw\n")

    def connect(self, ex):
        with mock.patch.dict(os.environ, {"HOME": self.home}), \
                mock.patch("paramiko.SSHClient.connect") as connect, mock.patch("paramiko.ProxyCommand") as proxy:
            ex.get_connection(cache=False)
        return connect.call_args, proxy.call_args

    def test_ssh_config_without_overrides(self):
        from npf.executor.sshexecutor import SSHExecutor
        connect, proxy = self.connect(SSHExecutor(None, "n1.example.org", "/tmp/x", 22))
        self.assertEqual(connect.kwargs["port"], 2200)
        self.assertEqual(connect.kwargs["key_filename"], [os.path.join(self.home, ".ssh", "alice")])
        self.assertEqual(proxy.args[0], "/bin/sh -c 'ssh -W n1.example.org:2200 config-gw'")

    def test_overrides_win(self):
        from npf.executor.sshexecutor import SSHExecutor
        ex = SSHExecutor("root", "n1.example.org", "/tmp/x", 22)
        ex.overrides = {"username": "root", "port": 22, "identityfile": "~/.ssh/k", "hostname": "n1.example.org",
                        "proxycommand": "ssh -W %h:%p -l %r gw -o ProxyCommand='ssh -W %%h:%%p gw0'"}
        connect, proxy = self.connect(ex)
        self.assertEqual(connect.args[0], "n1.example.org")
        self.assertEqual((connect.kwargs["username"], connect.kwargs["port"]), ("root", 22))
        self.assertEqual(connect.kwargs["key_filename"], [os.path.join(self.home, ".ssh", "k")])
        # Run through a shell, as ssh does
        self.assertEqual(shlex.split(proxy.args[0]), ["/bin/sh", "-c", "ssh -W n1.example.org:22 -l root gw -o ProxyCommand='ssh -W %h:%p gw0'"])


@unittest.skipIf(en is None, "enoslib is not installed")
class TestEnoslibSSHMode(unittest.TestCase):
    def test_run_local_host(self):
        """A local host runs with the local executor: no ansible play per script."""
        from npf import run
        with mock.patch("npf.executor.enoslibexecutor.en.run_command") as run_command:
            results, _ = run('integration/sections.npf', roles={"localhost": en.LocalHost()}, enoslib_ssh=True)
        run_command.assert_not_called()
        self.assertEqual(len(results), 1)

    def test_ssh_host_uses_ssh_executor(self):
        from npf import run
        from npf.cluster.node import Node
        host = en.Host("node-1.example.org", user="root", extra={"gateway": "gw.example.org"})
        made = []

        def make_ssh(user, addr, path, port=22, nfs=None, overrides=None, mkdir=False):
            made.append(dict(user=user, addr=addr, path=path, port=port, nfs=nfs, overrides=overrides, mkdir=mkdir))
            raise RuntimeError("stop here")

        with mock.patch.object(Node, "makeSSH", side_effect=make_ssh), self.assertRaises(RuntimeError):
            run('integration/sections.npf', roles={"server": host}, enoslib_ssh=True)
        self.assertEqual(len(made), 1)
        m = made[0]
        self.assertEqual((m["user"], m["addr"], m["port"], m["nfs"], m["mkdir"]),
                         ("root", "node-1.example.org", 22, False, True))
        self.assertEqual(m["path"], npf.globals.options.experiment_folder, "the same folder as with ansible")
        self.assertIn("gw.example.org", m["overrides"]["proxycommand"])


class TestLiveOutputWarning(unittest.TestCase):
    def params(self, live, waitfor):
        from npf.tests.remote_params import RemoteParameters
        p = RemoteParameters()
        p.role, p.role_id, p.waitfor = "client" if waitfor else "server", 0, waitfor
        p.nodes = [mock.Mock(executor=mock.Mock(live_output=live))]
        return p

    def warn(self, test, *params):
        from npf.tests.test import Test
        with mock.patch("builtins.print") as p:
            Test._warn_no_live_output(test, list(params))
        return [c.args[0] for c in p.call_args_list]

    def test_warns_once(self):
        test = mock.Mock(spec=[])
        out = self.warn(test, self.params(False, None), self.params(True, "ready"))
        self.assertEqual(len(out), 1)
        self.assertIn("role(s) server", out[0])
        self.assertIn("enoslib_ssh=True", out[0])
        self.assertEqual(self.warn(test, self.params(False, None), self.params(True, "ready")), [])

    def test_no_warning(self):
        self.assertEqual(self.warn(mock.Mock(spec=[]), self.params(False, None), self.params(False, None)), [])
        self.assertEqual(self.warn(mock.Mock(spec=[]), self.params(True, None), self.params(True, "ready")), [])
