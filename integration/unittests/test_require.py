import argparse
import os
import unittest

import npf.parsing
from npf import cmdline
from npf.repo import repository
from npf.tests.test_driver import Comparator


class TestRequire(unittest.TestCase):
    def test_require_internal_variables(self):
        """%require gets NPF_VERSION and the other internal variables, also when there is no %late_variables"""
        parser = argparse.ArgumentParser(description='NPF test')
        cmdline.add_verbosity_options(parser)
        cmdline.add_building_options(parser)
        cmdline.add_testing_options(parser, regression=False)
        cmdline.add_graph_options(parser)
        parser.add_argument('repo', metavar='repo name', type=str, nargs='?', default=None)
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'require.npf')
        args = parser.parse_args(["--test", script, '--force-retest'])
        npf.parsing.initialize(args)
        npf.parsing.create_local()

        series, _ = Comparator([repository.Repository.get_instance("local", options=args)]).run(
            test_name=args.test_files, tags=args.tags, options=args)
        runs = series[0][2]
        self.assertEqual([run.variables["N"] for run in runs], [1])
