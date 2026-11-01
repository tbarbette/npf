import unittest
from npf.osutils import get_valid_filename

class TestOsUtils(unittest.TestCase):
    def test_get_valid_filename(self):
        self.assertEqual(get_valid_filename("test file"), "test_file")
        self.assertEqual(get_valid_filename("test/file"), "testfile")
        self.assertEqual(get_valid_filename("test.file"), "test.file")
        self.assertEqual(get_valid_filename("  test  "), "test")


class TestLocalExecutorPath(unittest.TestCase):
    def test_bin_paths(self):
        import argparse
        import os
        from npf.executor.localexecutor import LocalExecutor
        options = argparse.Namespace(cwd="/launch")
        self.assertEqual(LocalExecutor._absolute_paths(["/abs/bin/", "build/x/bin/"], options),
                         ["/abs/bin/", "/launch/build/x/bin/"])
        self.assertEqual(LocalExecutor._absolute_paths(None, options), [])

    def test_path_not_overridden(self):
        """The script must see the bin folders in PATH, not an exported copy of the original PATH."""
        import argparse
        import npf.globals
        from npf.executor.localexecutor import LocalExecutor
        npf.globals.options = argparse.Namespace(color=False, cwd="/", quiet=True, show_cmd=False)
        pid, out, err, ret = LocalExecutor().exec("echo $PATH; echo $NPF_X", bin_paths=["/npf-test-bin/"],
                                                  options=npf.globals.options, env={"NPF_X": "1"})
        self.assertTrue(out.startswith("/npf-test-bin/:"), out)
        self.assertEqual(out.split()[-1], "1")
