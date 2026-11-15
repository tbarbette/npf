"""waitfor= on an %import adds to the waitfor= of the scripts of the module"""
import argparse
import os
import shutil
import tempfile
import unittest

import npf.globals
from npf.tests.test import Test


class TestImportWaitfor(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.test_dir, 'modules'))
        with open(os.path.join(self.test_dir, 'modules', 'waiting.npf'), 'w') as f:
            f.write("%script waitfor=A\necho RESULT 1\n")
        self.options = argparse.Namespace(show_files=False, quiet=True, debug=False, no_build_deps=[],
                                          force_build_deps=[], ignore_deps=[], keep_env=[], rand_env=0,
                                          allow_mp=False, preserve_temp=False, design="full",
                                          experiment_folder=self.test_dir, search_path=[self.test_dir],
                                          cwd=os.getcwd())
        npf.globals.options = self.options

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_both_waitfor(self):
        path = os.path.join(self.test_dir, 'test.npf')
        with open(path, 'w') as f:
            f.write("%import waiting waitfor=B\n")
        test = Test(path, self.options)
        script = test.imports[0].test.scripts[0]
        self.assertEqual(script.params['waitfor'], ['A', 'B'])


if __name__ == '__main__':
    unittest.main()
