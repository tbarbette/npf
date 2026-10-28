import argparse
import os
import shutil
import subprocess
import unittest
import uuid

import npf.globals
from npf.cluster.factory import nodePattern
from npf.executor.dockerexecutor import DockerExecutor

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
        self.assertEqual(out.strip(), os.getcwd())
        self.assertEqual(err.strip(), "ERR")
        self.assertEqual(ret, 0)

    def test_exit_code(self):
        _, _, _, ret = self.ex.exec("exit 3")
        self.assertEqual(ret, 3)

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


if __name__ == '__main__':
    unittest.main()
