"""--build-folder: each repository is built in its own folder inside it, with or without a trailing slash"""
import argparse
import os
import shutil
import tempfile
import unittest

from npf import cmdline
import npf.globals
import npf.parsing
from npf.repo.repository import Repository


class TestBuildFolder(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.folder)

    def get_args(self, build_folder):
        parser = argparse.ArgumentParser(description='NPF Tester')
        cmdline.add_verbosity_options(parser)
        cmdline.add_building_options(parser)
        cmdline.add_graph_options(parser)
        cmdline.add_testing_options(parser)
        args = parser.parse_args(args=['--build-folder', build_folder])
        args.tags = {}
        npf.parsing.parse_nodes(args)
        return args

    def test_build_path(self):
        for folder in [self.folder, self.folder + '/']:
            r = Repository('click-2022', self.get_args(folder))
            self.assertEqual(r.get_build_path(), os.path.join(self.folder, 'click-2022', ''), "--build-folder " + folder)


if __name__ == '__main__':
    unittest.main()
