import argparse
import os
import shutil
import tempfile
import unittest

import npf.parsing
from npf import cmdline
from npf.repo import repository
from npf.tests.test_driver import Comparator


class TestPreserveTemporaries(unittest.TestCase):
    def test_preserved_outputs(self):
        """With --preserve-temporaries, the output of each script is kept in the test folder, run after run"""
        import glob
        parser = argparse.ArgumentParser(description='NPF test')
        cmdline.add_verbosity_options(parser)
        cmdline.add_building_options(parser)
        cmdline.add_testing_options(parser, regression=False)
        cmdline.add_graph_options(parser)
        parser.add_argument('repo', metavar='repo name', type=str, nargs='?', default=None)
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'outputs.npf')
        args = parser.parse_args(["--test", script, '--force-retest', '--experiment-folder', folder,
                                  '--preserve-temporaries', 'kept', '--config', 'n_runs=2'])
        npf.parsing.initialize(args)
        npf.parsing.create_local()
        Comparator([repository.Repository.get_instance("local", options=args)]).run(
            test_name=args.test_files, tags=args.tags, options=args)

        def read(name):
            files = glob.glob(os.path.join(folder, "kept", "*", name))
            self.assertEqual(len(files), 1, "%s not kept" % name)
            with open(files[0]) as f:
                return f.read().splitlines()

        out = read("0.stdout")
        self.assertEqual(len(out), 8)
        self.assertRegex(out[0], r"^===== %script \[0\], N = 1 \[run 1/2\] on localhost: exited with code 0 after ")
        self.assertEqual(out[1], "RESULT-X 1")
        self.assertRegex(out[6], r"N = 2 \[run 2/2\]")
        self.assertEqual(read("0.stderr")[1], "an error line")
        self.assertEqual(read("init-0.stdout")[1:], ["init done"])
        exits = read("exit-0.stdout")
        self.assertEqual(exits[1::3], ["exit of the run"] * 4)
        # %exit runs in the test folder, where the scripts of the run wrote value.txt
        self.assertEqual(exits[2::3], ["RESULT-EXITFILE 1"] * 2 + ["RESULT-EXITFILE 2"] * 2)
