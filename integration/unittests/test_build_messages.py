import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from npf.repo.repository import MethodGit
from npf.tests.build import Build


def _folder(test):
    folder = tempfile.mkdtemp()
    test.addCleanup(shutil.rmtree, folder)
    return folder


class TestBuildMessages(unittest.TestCase):
    """The build messages name the repository, why it would be built, and why it is not"""

    def build(self, never_build, checked_out=False):
        folder = _folder(self)
        if checked_out:
            with open(os.path.join(folder, ".checkout_version"), "w") as f:
                f.write("abc1234")
        repo = mock.Mock(url="https://example.org/r.git", reponame="fastclick-x", build_info=None, env={})
        repo.name = "FastClick"
        repo.get_build_path.return_value = folder + "/"
        repo.method.checkout.return_value = True
        repo.get_local_bin_path.return_value = folder + "/bin/click"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertTrue(Build(repo, "abc1234").build(never_build=never_build))
        return out.getvalue(), folder

    def test_remote_build(self):
        out, folder = self.build("--remote-build")
        self.assertIn("Checking out fastclick-x abc1234 (it is the first checkout)", out)
        self.assertIn("Not building fastclick-x here (it is the first checkout): with --remote-build, each node "
                      "builds it", out)
        self.assertNotIn("Warning", out)

    def test_no_build(self):
        out, folder = self.build("--no-build", checked_out=True)
        self.assertNotIn("Checking out", out)
        self.assertIn("Warning: not building fastclick-x (could not find %s/bin/click), as --no-build was given: the "
                      "test uses the build that is there, which may be outdated" % folder, out)

    def test_nothing_to_build(self):
        repo = mock.Mock(url=None, reponame="local")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertTrue(Build(repo, "local").build(never_build="--remote-build"))
        self.assertEqual(out.getvalue(), "")


class TestResetMessage(unittest.TestCase):
    """Moving a git build folder to the latest version tells it, and where its local changes went"""

    def test_dirty(self):
        folder = _folder(self)
        origin = os.path.join(folder, "origin")
        build = os.path.join(folder, "build")
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q", "-b", "main", origin], check=True)
        for content in ("1", "2"):
            with open(os.path.join(origin, "f"), "w") as f:
                f.write(content)
            subprocess.run(git + ["-C", origin, "commit", "-q", "-a", "-m", content] if content == "2" else
                           git + ["-C", origin, "add", "f"], check=True)
            if content == "1":
                subprocess.run(git + ["-C", origin, "commit", "-q", "-m", content], check=True)
        subprocess.run(["git", "clone", "-q", origin, build], check=True)
        subprocess.run(["git", "-C", build, "reset", "-q", "--hard", "HEAD~1"], check=True)
        old = subprocess.run(["git", "-C", build, "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True).stdout.strip()
        new = subprocess.run(["git", "-C", origin, "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True).stdout.strip()
        with open(os.path.join(build, "f"), "w") as f:
            f.write("local change")

        repo = mock.Mock(reponame="fastclick-x", branch="main", url=origin)
        repo.options.no_build = False
        repo.options.quiet_build = True  # Local changes are told anyway
        repo.get_build_path.return_value = build
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            MethodGit(repo).checkout()
        self.assertIn("Resetting fastclick-x in %s from %s to origin/main (%s)" % (build, old, new), out.getvalue())
        self.assertIn("Its local changes are saved with git stash: see git -C %s stash list" % build, out.getvalue())
        self.assertTrue(subprocess.run(["git", "-C", build, "stash", "list"], capture_output=True, text=True).stdout)


if __name__ == '__main__':
    unittest.main()
