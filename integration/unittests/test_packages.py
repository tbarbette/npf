import argparse
import contextlib
import io
import shutil
import unittest
from unittest import mock

from npf.repo import packages


class Repo:
    reponame = "snort"

    def __init__(self, value):
        self.packages = value


class TestPackages(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(packages.parse("flex, deb:libdumbnet-dev rpm:libdnet-devel"),
                         {"deb": ["flex", "libdumbnet-dev"], "rpm": ["flex", "libdnet-devel"]})
        with self.assertRaises(Exception):
            packages.parse("arch:libdnet")

    def ensure(self, value, required=False, install=False, run=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            if run:
                with mock.patch.object(packages, "_run", side_effect=run) as r:
                    ok = packages.ensure(Repo(value), argparse.Namespace(install_packages=install), required=required)
                return ok, out.getvalue(), r.call_args_list
            ok = packages.ensure(Repo(value), argparse.Namespace(install_packages=install), required=required)
        return ok, out.getvalue(), []

    @unittest.skipUnless(shutil.which("dpkg-query"), "needs a Debian-based system")
    def test_check_debian(self):
        """On this system: bash is installed, the other is not, and NPF tells how to install it"""
        ok, out, _ = self.ensure("bash,deb:npf-no-such-package,rpm:bash-devel")
        self.assertTrue(ok)
        self.assertNotIn("bash ", out.split("Install")[0])
        self.assertIn("npf-no-such-package", out)
        self.assertIn("apt-get install -y npf-no-such-package", out)
        self.assertEqual(self.ensure("bash")[:2], (True, ""))
        # With method=package, the build cannot go on
        self.assertFalse(self.ensure("npf-no-such-package", required=True)[0])

    def test_install(self):
        """With --install-packages, the missing packages are installed with the package manager of the node"""
        ok, out, calls = self.ensure("deb:a,rpm:b", install=True, run=[("rpm\nb\n", True), ("", True)])
        self.assertTrue(ok)
        self.assertIn("install -y b", calls[1].args[0])
        self.assertIn("dnf", calls[1].args[0])
        ok, out, calls = self.ensure("a", required=True, install=True, run=[("deb\na\n", True), ("E: no a", False)])
        self.assertFalse(ok)
        self.assertIn("E: no a", out)

    def test_unknown_system(self):
        ok, out, _ = self.ensure("a", run=[("unknown\n", True)])
        self.assertTrue(ok)
        self.assertIn("neither dpkg nor rpm", out)
