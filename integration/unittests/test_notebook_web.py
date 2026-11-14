"""--web and --notebook on test scripts of integration/ that cover the different cases: no variable with several
values, one, two, a covariable and an aggregate, missing results, and a CDF"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import nbformat

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
SCRIPTS = {
    "single": "simple_bar",
    "math": "line",
    "heatmap": "heatmap",
    "experimental": None,
    "scarce": None,
    "cdf": "cdf",
}


def has_ipykernel():
    try:
        import ipykernel  # noqa: F401
        return True
    except ImportError:
        return False


class TestNotebookWeb(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder)
        self.env = dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in (ROOT, os.environ.get("PYTHONPATH")) if p))
        if has_ipykernel():
            # A kernel running the python of the tests, whatever the kernels of the user
            kernels = os.path.join(self.folder, "jupyter", "kernels", "npf-test")
            os.makedirs(kernels)
            with open(os.path.join(kernels, "kernel.json"), "w") as f:
                json.dump({"argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                           "display_name": "NPF test", "language": "python"}, f)
            self.env["JUPYTER_PATH"] = os.path.join(self.folder, "jupyter")

    def npf(self, script, execute):
        out = os.path.join(self.folder, script)
        args = [sys.executable, os.path.join(ROOT, "npf.py"), "local", "--test",
                os.path.join(ROOT, "integration", script + ".npf"), "--force-retest", "--config", "n_runs=2",
                "--experiment-folder", self.folder, "--graph-filename", out + ".pdf",
                "--web", out + ".html", "--notebook", out + ".ipynb"]
        args += ["--nb-kernel", "npf-test"] if execute else ["--disable-nb-exec"]
        p = subprocess.run(args, cwd=self.folder, env=self.env, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=600)
        self.assertEqual(p.returncode, 0, p.stdout[-2000:] + p.stderr[-2000:])
        return out, p.stdout

    def check(self, execute):
        for script, graph_type in SCRIPTS.items():
            with self.subTest(script=script):
                out, stdout = self.npf(script, execute)
                with open(out + ".html") as f:
                    self.assertIn("parameters", f.read())
                with open(out + ".ipynb") as f:
                    nb = nbformat.read(f, as_version=4)
                nbformat.validate(nb)
                code = [c for c in nb.cells if c.cell_type == "code"]
                self.assertTrue(code[0].source.startswith("data = ["))
                if graph_type:
                    self.assertTrue(any(c.source.startswith("# " + graph_type.replace("simple_bar", "MEAN").upper())
                                        for c in code), "no %s cell" % graph_type)
                if execute:
                    self.assertNotIn("ERROR", stdout)
                    outputs = [o for c in code for o in c.get("outputs", [])]
                    errors = [o["ename"] + ": " + o["evalue"] for o in outputs if o.get("output_type") == "error"]
                    self.assertEqual(errors, [])
                    self.assertTrue(any("image/png" in o.get("data", {}) for o in outputs), "no plot")

    def test_outputs(self):
        """The web page and the notebook are written. With ipykernel, the notebook runs without errors and draws its
        plots."""
        self.check(execute=has_ipykernel())
