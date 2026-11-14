import argparse
import os
import shutil
import tempfile
import unittest
from unittest import mock

import npf.globals
from npf.cluster.node import Node
from npf.executor.localexecutor import LocalExecutor
from npf.tests.build import Build


class TestNodeEnv(unittest.TestCase):
    """env=KEY=VALUE lines of a node file"""

    def setUp(self):
        saved = npf.globals.options
        self.addCleanup(setattr, npf.globals, "options", saved)
        npf.globals.options = argparse.Namespace(color=False, search_path=[], experiment_folder=".", cwd=os.getcwd())
        self.dir = tempfile.mkdtemp(prefix="npf-ut-")
        self.addCleanup(shutil.rmtree, self.dir)
        os.mkdir(os.path.join(self.dir, "cluster"))
        # Node files are found as cluster/<name>.node
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.dir)

    def node(self, content):
        name = "n%d" % len(os.listdir("cluster"))
        with open(os.path.join("cluster", name + ".node"), "w") as f:
            f.write(content)
        return Node(name, LocalExecutor(), tags=[])

    def test_env(self):
        n = self.node("path=/tmp/x\nenv=RTE_SDK=/opt/dpdk\nenv = PKG = $RTE_SDK/lib:${RTE_SDK}/lib64:$HOME:$RTE\n")
        self.assertEqual(n.executor.env, {"RTE_SDK": "/opt/dpdk", "PKG": "/opt/dpdk/lib:/opt/dpdk/lib64:$HOME:$RTE"})
        self.assertEqual(n.executor.path, "/tmp/x")
        self.assertEqual(LocalExecutor().env, {}, "the env of a node is its own")

    def test_bad_env(self):
        with self.assertRaisesRegex(Exception, ":2 : env node config expects env=KEY=VALUE"):
            self.node("path=/tmp/x\nenv=NOVALUE\n")

    def test_remote_build_gets_the_env(self):
        n = self.node("env=CC=gcc\nenv=RTE_SDK=/opt/dpdk\n")
        n.executor.exec = mock.Mock(return_value=(1, "", "", 0))
        repo = mock.Mock(url="https://example.org/r.git", build_info=None, configure="", clean="",
                         make="make CC=$CC", env={"CC": "clang"})
        repo.get_remote_build_path.return_value = "/remote/build"
        with mock.patch("builtins.print"):
            self.assertTrue(Build(repo, "local").compile(node=n))
        kwargs = n.executor.exec.call_args.kwargs
        # The repo wins over the node
        self.assertEqual(kwargs["env"], {"CC": "clang", "RTE_SDK": "/opt/dpdk"})
        self.assertEqual(kwargs["cmd"], "cd /remote/build && make CC=clang")


if __name__ == '__main__':
    unittest.main()
