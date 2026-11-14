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

    def test_pdf_metadata(self):
        """The PDF files of the graphs hold what is needed to draw them again"""
        import npf.parsing
        from npf import cmdline
        from npf.output.grapher import Grapher
        from npf.repo import repository
        from npf.tests.test_driver import Comparator

        parser = argparse.ArgumentParser()
        cmdline.add_verbosity_options(parser)
        cmdline.add_building_options(parser)
        cmdline.add_testing_options(parser, regression=False)
        cmdline.add_graph_options(parser)
        parser.add_argument('repo', nargs='?', default=None)
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'sections.npf')
        args = parser.parse_args(["--test", script, "--force-retest"])
        npf.parsing.initialize(args)
        npf.parsing.create_local()
        series, _ = Comparator([repository.Repository.get_instance("local", options=args)]).run(
            test_name=args.test_files, tags=args.tags, options=args)

        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        Grapher().graph(series=series, filename=os.path.join(folder, "graph.pdf"), options=args)
        pdfs = sorted(f for f in os.listdir(folder) if f.endswith(".pdf"))
        self.assertTrue(pdfs)
        with open(os.path.join(folder, pdfs[0]), "rb") as f:
            pdf = f.read()
        for key in (b"/Title", b"/Subject", b"/NPF-Command", b"/NPF-Series", b"/NPF-Results"):
            self.assertIn(key, pdf)
        self.assertIn(b"echo \"RESULT-SCRIPT $V\"", pdf)  # The test script
        self.assertIn(b"y_SCRIPT", pdf)  # The results
