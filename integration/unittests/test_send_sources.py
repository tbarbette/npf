import argparse
import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import npf.globals
from npf.osutils import git_sources


def _folder(test):
    folder = tempfile.mkdtemp()
    test.addCleanup(shutil.rmtree, folder)
    return folder


def _write(path, content="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


class TestGitSources(unittest.TestCase):
    """git_sources() lists what a node needs to build a git repository itself: the tracked files, not the build products"""

    def test_sources(self):
        folder = _folder(self)
        repo = os.path.join(folder, "build", "sw")
        _write(os.path.join(repo, ".gitignore"), "*.o\nbin/\n")
        _write(os.path.join(repo, "src", "a.c"))
        _write(os.path.join(repo, "Makefile"))
        git = ["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q", repo], check=True)
        subprocess.run(git + ["add", "."], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "init"], check=True)
        _write(os.path.join(repo, "src", "a.c"), "changed")  # A local change: the file is still listed
        _write(os.path.join(repo, "src", "new.c"))  # Untracked and not ignored: often a build product
        _write(os.path.join(repo, "src", "added.c"))
        subprocess.run(git + ["add", "-N", "src/added.c"], check=True)  # A new source, added to git
        _write(os.path.join(repo, "src", "a.o"))  # Ignored build products
        _write(os.path.join(repo, "bin", "sw"))

        files = git_sources(repo)
        self.assertEqual(files, {os.path.join(repo, f) for f in (".gitignore", "Makefile", "src/a.c", "src/added.c")})

    def test_not_git(self):
        folder = _folder(self)
        _write(os.path.join(folder, "a.c"))
        self.assertIsNone(git_sources(folder))


class TestSendFolderOnly(unittest.TestCase):
    """sendFolder(only=...) sends only the given files, and does not walk the folders that have none of them"""

    def setUp(self):
        saved = npf.globals.options
        self.addCleanup(setattr, npf.globals, "options", saved)
        npf.globals.options = argparse.Namespace(color=False, sshconfig=False, quiet=True, show_cmd=False, debug=False)

    def send(self, local, only=None):
        from npf.executor.sshexecutor import SSHExecutor
        sftp = mock.MagicMock()
        sftp.listdir.return_value = []
        sent = []
        sftp.put.side_effect = lambda l, r: sent.append(os.path.normpath(r))
        ex = SSHExecutor("root", "n1", "/remote/", 22)
        out = io.StringIO()
        with mock.patch.object(ex, "get_connection"), \
                mock.patch("paramiko.SFTPClient.from_transport", return_value=sftp), \
                contextlib.redirect_stdout(out):
            ex.sendFolder("build", local=local, only=only)
        made = sorted(os.path.normpath(c.args[0]) for c in sftp.mkdir.call_args_list)
        return sorted(sent), made, out.getvalue()

    def test_only(self):
        folder = _folder(self)
        for f in ("build/src/a.c", "build/src/a.o", "build/Makefile", "build/objs/b.o"):
            _write(os.path.join(folder, f))
        only = {os.path.join(folder, f) for f in ("build/src/a.c", "build/Makefile")}
        sent, made, _ = self.send(folder, only)
        self.assertEqual(sent, ["/remote/build/Makefile", "/remote/build/src/a.c"])
        self.assertNotIn("/remote/build/objs", made, "a folder without sources is not made on the node")

    def test_all(self):
        folder = _folder(self)
        for f in ("build/src/a.c", "build/src/a.o"):
            _write(os.path.join(folder, f))
        sent, _, _ = self.send(folder)
        self.assertEqual(sent, ["/remote/build/src/a.c", "/remote/build/src/a.o"])

    def test_debug(self):
        npf.globals.options.debug = True
        folder = _folder(self)
        _write(os.path.join(folder, "build", "a.c"), "12345")
        _, _, out = self.send(folder)
        self.assertIn("[DEBUG] Sent %s (5 bytes) to n1" % os.path.join(folder, "build", "a.c"), out)
        self.assertTrue(out.startswith("\n"), "the first file starts a new line after 'Sending ...'")


if __name__ == '__main__':
    unittest.main()
