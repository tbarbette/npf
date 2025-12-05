import unittest
import argparse
from npf.cmdline import ArgListOrTrueAction
from npf import cmdline
import npf.globals
import npf.parsing

class TestCmdline(unittest.TestCase):
    def setUp(self):
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument('--statistics',
                           dest='statistics', default=False,
                           action=ArgListOrTrueAction)

    def test_arglist_or_true_no_flag(self):
        args = self.parser.parse_args([])
        self.assertFalse(args.statistics)

    def test_arglist_or_true_flag_only(self):
        args = self.parser.parse_args(['--statistics'])
        self.assertTrue(args.statistics)

    def test_arglist_or_true_one_arg(self):
        args = self.parser.parse_args(['--statistics', 'EXP'])
        self.assertEqual(args.statistics, ['EXP'])

    def test_arglist_or_true_multiple_args(self):
        args = self.parser.parse_args(['--statistics', 'EXP', 'LOG'])
        self.assertEqual(args.statistics, ['EXP', 'LOG'])

    def test_arglist_or_true_multiple_flags(self):
        args = self.parser.parse_args(['--statistics', 'EXP', '--statistics', 'LOG'])
        self.assertEqual(args.statistics, ['EXP', 'LOG'])

class TestArgs(unittest.TestCase):
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

    def test_args(self):
        self.assertTrue(self.get_args())
