import unittest
from unittest import mock

from npf.tests.build import Build


def _repo():
    repo = mock.Mock(url="https://example.org/r.git", build_info=None, configure="", clean="", make="", env={},
                     packages="", bin_name="click", reponame="r")
    repo.get_remote_build_path.return_value = "build/r"
    repo.get_remote_bin_folder.return_value = "build/r/bin/"
    return repo


def _node(ret=0, out=""):
    node = mock.Mock()
    node.get_name.return_value = "n1"
    node.executor.exec.return_value = (1, out, "", ret)
    return node


class TestRemoteCompileNeeded(unittest.TestCase):
    """Like a local build, a remote build (--remote-build) is only needed if the node does not have the binary of
    this version"""

    def test_missing_binary(self):
        node = _node(ret=3)
        reason = Build(_repo(), "abc1234").is_remote_compile_needed(node)
        self.assertEqual(reason, "could not find build/r/bin/click on n1")
        cmd = node.executor.exec.call_args.kwargs["cmd"]
        self.assertIn("test -e build/r/bin/click", cmd)
        self.assertIn("cat build/r/.build_version", cmd)

    def test_other_version(self):
        reason = Build(_repo(), "abc1234").is_remote_compile_needed(_node(out="0123456\n"))
        self.assertEqual(reason, "the version built on n1 is 0123456, the newest is abc1234")

    def test_unknown_version(self):
        reason = Build(_repo(), "abc1234").is_remote_compile_needed(_node(out=""))
        self.assertEqual(reason, "the version built on n1 is unknown")

    def test_up_to_date(self):
        self.assertIsNone(Build(_repo(), "abc1234").is_remote_compile_needed(_node(out="abc1234\n")))

    def test_compile_writes_the_version(self):
        node = _node()
        node.executor.env = {}
        with mock.patch("builtins.print"):
            self.assertTrue(Build(_repo(), "abc1234").compile(node=node))
        self.assertEqual(node.executor.exec.call_args.kwargs["cmd"], "cd build/r && echo abc1234 > .build_version")


if __name__ == '__main__':
    unittest.main()
