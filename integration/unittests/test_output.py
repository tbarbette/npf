import argparse
import os
import shutil
import tempfile
import unittest
from collections import OrderedDict

import numpy as np

from npf.models.dataset import Run, process_output_options


class TestOutput(unittest.TestCase):
    def test_web(self):
        from npf.output import web

    def test_notebook(self):
        from npf.output import notebook

    def test_csv_output(self):
        """--output writes one CSV per result type, with the --output-columns of each run."""
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        # As NPF gives them: one array of values (one per run) per result type
        results = OrderedDict()
        for n in (1, 2):
            results[Run(OrderedDict(N=n, STATIC=0))] = {"A": np.array([10 * n, 10 * n + 2]), "B": np.array([0, n])}
        options = argparse.Namespace(output=os.path.join(folder, "res.csv"), graph_filename=None, show_serie=False,
                                     output_columns=["x", "mean", "n", "mean(where(B>0))", "all"])
        process_output_options([(None, None, results)], {"STATIC": 0}, options, list(results.keys()))

        with open(os.path.join(folder, "A.csv")) as f:
            self.assertEqual(f.read().split("\n"), ["1 11.0 2 12.0 10 12", "2 21.0 2 22.0 20 22", ""])
        with open(os.path.join(folder, "B.csv")) as f:
            self.assertEqual(f.read().split("\n"), ["1 0.5 2 1.0 0 1", "2 1.0 2 2.0 0 2", ""])
