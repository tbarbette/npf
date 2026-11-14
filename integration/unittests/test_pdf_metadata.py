import argparse
import os
import shutil
import tempfile
import unittest


class TestPDFMetadata(unittest.TestCase):
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
