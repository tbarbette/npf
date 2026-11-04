import argparse
import os
import shutil
import subprocess
import time
import unittest
import unittest.mock
import uuid

import npf.globals
from npf.cluster.factory import nodePattern
from npf.executor.dockerexecutor import DockerExecutor, SSHDockerSocket

IMAGE = "debian:bookworm-slim"


def docker_available():
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


class TestDockerPattern(unittest.TestCase):
    def test_docker_scheme(self):
        m = nodePattern.match("client=docker://GNS3.client-1")
        self.assertEqual(m.group("role"), "client")
        self.assertTrue(m.group("docker"))
        self.assertEqual(m.group("addr"), "GNS3.client-1")

    def test_ssh_unchanged(self):
        m = nodePattern.match("server=user@host.example.com:/tmp/npf")
        self.assertFalse(m.group("docker"))
        self.assertEqual(m.group("user"), "user")
        self.assertEqual(m.group("addr"), "host.example.com")
        self.assertEqual(m.group("path"), "/tmp/npf")


# Like python's print, perl's print fills a buffer when stdout is a pipe, but flushes each line in a terminal
BUFFERED_EVENT = "perl -e 'print \"EVENT ready\\n\"; sleep 3'"


def event_delay(ex):
    """Runs BUFFERED_EVENT with ex. :return: how long after the start its EVENT was seen"""
    seen = []
    event = unittest.mock.Mock(is_terminated=unittest.mock.Mock(return_value=False))
    event.post.side_effect = lambda ev: seen.append(time.time())
    start = time.time()
    ex.exec(BUFFERED_EVENT, event=event)
    return seen[0] - start if seen else None


@unittest.skipUnless(docker_available(), "docker daemon not available")
class TestDockerExecutor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "npf-ut-" + uuid.uuid4().hex[:8]
        cwd = os.getcwd()
        r = subprocess.run(["docker", "run", "-d", "--rm", "--name", cls.name, "-v", f"{cwd}:{cwd}", IMAGE, "sleep", "600"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise unittest.SkipTest("could not start %s: %s" % (IMAGE, r.stderr))
        cls.addClassCleanup(subprocess.run, ["docker", "rm", "-f", cls.name], capture_output=True)
        cls.saved_options = npf.globals.options
        npf.globals.options = argparse.Namespace(color=False)
        cls.addClassCleanup(setattr, npf.globals, "options", cls.saved_options)
        cls.ex = DockerExecutor(cls.name)


    def _in_container(self, cmd):
        return subprocess.run(["docker", "exec", self.name, "sh", "-c", cmd], capture_output=True, text=True).stdout

    def test_output_and_cwd(self):
        pid, out, err, ret = self.ex.exec("pwd; echo ERR >&2")
        # In the terminal of docker exec -t, stderr is merged with stdout
        self.assertEqual(out.split(), [os.getcwd(), "ERR"])
        self.assertEqual(ret, 0)

    def test_exit_code(self):
        _, _, _, ret = self.ex.exec("exit 3")
        self.assertEqual(ret, 3)

    def test_event_seen_when_printed(self):
        self.assertLess(event_delay(self.ex), 2)

    def test_env_not_inherited_from_host(self):
        _, out, _, _ = self.ex.exec("echo $MYVAR; echo $PATH", env={"MYVAR": "x y"})
        lines = out.splitlines()
        self.assertEqual(lines[0], "x y")
        self.assertNotIn("/Users", lines[1])

    def test_sudo_as_root(self):
        _, out, _, ret = self.ex.exec("id -u", sudo=True)
        self.assertEqual(out.strip(), "0")
        self.assertEqual(ret, 0)

    def test_timeout_kills_in_container(self):
        marker = "sleep 7%d" % (os.getpid() % 1000 + 100)
        self.ex.exec("echo start; %s" % marker, timeout=2)
        self.assertEqual(self._in_container("for p in /proc/[0-9]*; do tr '\\0' ' ' < $p/cmdline 2>/dev/null; echo; done | grep -c '^%s'" % marker).strip(), "0")


@unittest.skipUnless(docker_available(), "docker daemon not available")
class TestDockerNotShared(unittest.TestCase):
    """A container without the experiment folder, like a GNS3 node"""

    @classmethod
    def setUpClass(cls):
        cls.name = "npf-ut-ns-" + uuid.uuid4().hex[:8]
        r = subprocess.run(["docker", "run", "-d", "--rm", "--name", cls.name, IMAGE, "sleep", "600"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise unittest.SkipTest("could not start %s: %s" % (IMAGE, r.stderr))
        cls.addClassCleanup(subprocess.run, ["docker", "rm", "-f", cls.name], capture_output=True)
        cls.saved_options = npf.globals.options
        npf.globals.options = argparse.Namespace(color=False, cwd=os.getcwd(), experiment_folder="./")
        cls.addClassCleanup(setattr, npf.globals, "options", cls.saved_options)
        cls.root = "/tmp/npf-ut-root"
        cls.ex = DockerExecutor(cls.name, path=cls.root)
        cls.ex.run_raw("mkdir -p " + cls.root)

    def test_not_shared(self):
        self.assertFalse(self.ex.shared)
        _, out, _, _ = self.ex.exec("test -e %s && echo yes || echo no" % os.getcwd())
        self.assertEqual(out.strip(), "no")

    def test_runs_in_remote_root(self):
        _, out, _, ret = self.ex.exec("pwd")
        self.assertEqual(ret, 0)
        self.assertTrue(out.strip().startswith(self.root), out)

    def test_write_file(self):
        self.ex.writeFile("hello.txt", self.root, "hi there\n", sudo=False)
        _, out, _, _ = self.ex.exec("cat %s/hello.txt" % self.root)
        self.assertEqual(out.strip(), "hi there")

    def test_timeout_kills(self):
        marker = "sleep 8%d" % (os.getpid() % 1000 + 100)
        self.ex.exec("echo start; %s" % marker, timeout=2)
        _, out = self.ex.run_raw("for p in /proc/[0-9]*; do tr '\\0' ' ' < $p/cmdline 2>/dev/null; echo; done | grep -c '^%s'" % marker)
        self.assertEqual(out.strip(), "0")


class TestSSHDockerSocket(unittest.TestCase):
    def test_command(self):
        cmd = SSHDockerSocket.command("ssh://bob@lab.example.com:2222", "/tmp/x/docker.sock", "/var/run/docker.sock")
        self.assertEqual(cmd[0], "ssh")
        self.assertIn("-N", cmd)
        self.assertEqual(cmd[cmd.index("-L") + 1], "/tmp/x/docker.sock:/var/run/docker.sock")
        self.assertEqual(cmd[cmd.index("-p") + 1], "2222")
        self.assertEqual(cmd[-2:], ["--", "bob@lab.example.com"])
        self.assertNotIn("-p", SSHDockerSocket.command("ssh://lab", "/tmp/x", "/y"))

    def test_unreachable_falls_back(self):
        SSHDockerSocket._tunnels.pop("ssh://nonexistent.invalid", None)
        self.addCleanup(SSHDockerSocket._tunnels.pop, "ssh://nonexistent.invalid", None)
        with unittest.mock.patch("builtins.print"):
            self.assertEqual(SSHDockerSocket.endpoint("ssh://nonexistent.invalid"), "ssh://nonexistent.invalid")


def ssh_localhost_available():
    if not shutil.which("ssh"):
        return False
    return subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=3", "localhost", "true"],
                          capture_output=True).returncode == 0


@unittest.skipUnless(docker_available() and ssh_localhost_available(), "needs docker and passwordless ssh to localhost")
class TestDockerOverSSH(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "npf-ut-ssh-" + uuid.uuid4().hex[:8]
        r = subprocess.run(["docker", "run", "-d", "--rm", "--name", cls.name, IMAGE, "sleep", "600"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise unittest.SkipTest("could not start %s: %s" % (IMAGE, r.stderr))
        cls.addClassCleanup(subprocess.run, ["docker", "rm", "-f", cls.name], capture_output=True)
        cls.saved_options = npf.globals.options
        npf.globals.options = argparse.Namespace(color=False, cwd=os.getcwd(), experiment_folder="./")
        cls.addClassCleanup(setattr, npf.globals, "options", cls.saved_options)
        SSHDockerSocket._tunnels.pop("ssh://localhost", None)

    def test_one_shared_connection(self):
        a = DockerExecutor(self.name, host="ssh://localhost", path="/tmp/npf-ut-ssh")
        b = DockerExecutor(self.name, host="ssh://localhost", path="/tmp/npf-ut-ssh")
        for ex in (a, b, a):
            _, out, _, ret = ex.exec("echo hello")
            self.assertEqual((out.strip(), ret), ("hello", 0))
        tunnel = SSHDockerSocket._tunnels["ssh://localhost"]
        self.assertIsNotNone(tunnel, "forwarding failed, fell back to docker's ssh transport")
        self.assertIsNone(tunnel.proc.poll())
        self.assertEqual(a._docker("ps")[1:3], ["-H", "unix://" + tunnel.sock])
        self.assertEqual(oct(os.stat(tunnel.dir).st_mode & 0o777), "0o700")

    def test_tunnel_removed_at_close(self):
        tunnel = SSHDockerSocket._tunnels.get("ssh://localhost") or SSHDockerSocket("ssh://localhost")
        d = tunnel.dir
        tunnel.close()
        self.assertFalse(os.path.exists(d))
        SSHDockerSocket._tunnels.pop("ssh://localhost", None)


if __name__ == '__main__':
    unittest.main()
