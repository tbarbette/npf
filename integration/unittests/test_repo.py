import unittest
import argparse
from npf.repo.repository import Repository
from npf import cmdline
import npf.globals
import npf.parsing

class TestRepo(unittest.TestCase):
    def get_args(self):
        parser = argparse.ArgumentParser(description='NPF Tester')
        cmdline.add_verbosity_options(parser)
        cmdline.add_building_options(parser)
        cmdline.add_graph_options(parser)
        cmdline.add_testing_options(parser)
        args = parser.parse_args(args = [])
        args.tags = {}
        npf.globals.set_args(args)
        npf.parsing.parse_nodes(args)
        return args

    def test_repo(self):
        args = self.get_args()
        r = Repository('click-2022', args)
        self.assertEqual(r.branch, '2022')
