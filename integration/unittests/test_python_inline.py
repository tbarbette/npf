import argparse
import contextlib
import io
import os
import shutil
import tempfile
import unittest

import npf.globals
from npf.tests.section import SectionFactory
from npf.tests.test import Test
from npf.tests.variable import replace_variables


class TestPythonInline(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.options = argparse.Namespace(show_files=False, quiet=True, debug=False, experiment_folder=self.dir,
                                          search_path=[], cwd=os.getcwd(), python_inline=False)
        saved = npf.globals.options
        self.addCleanup(setattr, npf.globals, "options", saved)
        npf.globals.options = self.options
        saved_warned = set(Test._warned_python_inline)
        self.addCleanup(setattr, Test, "_warned_python_inline", saved_warned)

    def load(self, content):
        """:return: the test and the warnings printed while loading it"""
        path = os.path.join(self.dir, "t%d.npf" % len(os.listdir(self.dir)))
        with open(path, "w") as f:
            f.write(content)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            test = Test(path, self.options)
        return test, [l for l in out.getvalue().splitlines() if "python-inline" in l]

    def test_engines_anywhere_in_script_header(self):
        for header in ["script python-inline sudo=true", "script sudo=true autokill=false python-inline",
                       "script@client jinja python-inline waitfor=X"]:
            m = SectionFactory.namePattern.match(header)
            self.assertIsNotNone(m, header)
            self.assertTrue(SectionFactory.engines(m.group("scriptParams"))[1], header)
        m = SectionFactory.namePattern.match("script title=jinja")
        self.assertEqual(SectionFactory.engines(m.group("scriptParams")), (False, False))

    def test_sections(self):
        test, _ = self.load("%script sudo=true python-inline\necho\n%script jinja\necho\n"
                            "%file f.click python-inline\nx\n%require python-inline\ntrue\n")
        self.assertEqual([s.python_inline for s in test.scripts], [True, False])
        self.assertEqual([s.jinja for s in test.scripts], [False, True])
        self.assertTrue(test.files[0].python_inline)
        self.assertTrue(test.requirements[0].python_inline)

    def test_replace(self):
        v = {"N": 3}
        self.assertEqual(replace_variables(v, "$(( $N * 2 ))", python_inline=True), "6")
        self.assertEqual(replace_variables(v, "$(( $N * 2 ))", python_inline=False), "$(( 3 * 2 ))")
        # An escaped one is for the shell in both cases
        self.assertEqual(replace_variables(v, "\\$(( a + $N ))", python_inline=False), "$((a + 3))")

    def test_warn_python_in_script(self):
        _, warnings = self.load("%script\necho $(( $X + 1 ))\necho $(( log($X) ))\n")
        self.assertEqual(len(warnings), 1)
        self.assertIn("t0.npf:3: $(( log($X) )) looks like Python", warnings[0])

    def test_shell_arithmetic_not_reported(self):
        _, warnings = self.load("%script\necho $(( $X * ($Y - 1) % 2 ))\necho $(( ${A} << 2 ))\n"
                                "%file get.sh\nt=$(( $a / $n ))\n")
        self.assertEqual(warnings, [])

    def test_warn_float_once_replaced(self):
        test, warnings = self.load("%variables\nX={1.5}\n%script\necho $(( $X + 1 ))\n")
        self.assertEqual(warnings, [])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for _ in range(2):
                test.warn_python_inline(test.scripts[0], replace_variables({"X": 1.5}, test.scripts[0].content, python_inline=False))
        self.assertEqual(out.getvalue().count("$(( 1.5 + 1 )) looks like Python"), 1, out.getvalue())

    def test_warn_any_in_non_shell_file(self):
        _, warnings = self.load("%file conf.click\nStaticThreadSched(x $(( $T - 1 )))\n")
        self.assertEqual(len(warnings), 1)
        self.assertIn("is not evaluated by NPF anymore", warnings[0])

    def test_not_reported_when_enabled(self):
        _, warnings = self.load("%script python-inline\necho $(( log($X) ))\n%file conf.click noparse\n$(( $T ))\n")
        self.assertEqual(warnings, [])
        self.options.python_inline = True
        _, warnings = self.load("%script\necho $(( log($X) ))\n")
        self.assertEqual(warnings, [])


if __name__ == '__main__':
    unittest.main()
