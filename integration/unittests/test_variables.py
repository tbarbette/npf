import argparse
import os
import shutil
import tempfile
import unittest

import npf.globals
from npf.models.variables.DictVariable import DictVariable
from npf.models.variables.ListVariable import ListVariable
from npf.models.variables.ParentVariable import ParentVariable
from npf.models.variables.RangeVariable import RangeVariable
from npf.models.variables.SimpleVariable import SimpleVariable
from npf.models.variables.VariableFactory import VariableFactory
from npf.models.variables.grammar import VariableSyntaxError
from npf.tests.test import Test


def build(value, base_path=None):
    return VariableFactory.build("X", value, None, base_path)


class TestValueGrammar(unittest.TestCase):
    def test_ranges(self):
        v = build("[1-4]")
        self.assertIsInstance(v, RangeVariable)
        self.assertEqual(v.makeValues(), [1, 2, 3, 4])
        self.assertEqual(build("[10-30#10]").makeValues(), [10, 20, 30])
        self.assertEqual(build("[1*8]").makeValues(), [1, 2, 4, 8])
        self.assertEqual(build("[-2-1]").makeValues(), [-2, -1, 0, 1])
        self.assertTrue(build("[[0-1#0.5]]").force_int)
        self.assertEqual(build("[0-10#]").step, "")

    def test_list_and_dict(self):
        self.assertEqual(build("{a,b,c}").makeValues(), ["a", "b", "c"])
        self.assertEqual(build("{1,2,8}").makeValues(), [1, 2, 8])
        d = build("{1:Zero-copy,0:Copy}")
        self.assertIsInstance(d, DictVariable)
        self.assertEqual(d.makeValues(), [("1", "Zero-copy"), ("0", "Copy")])
        self.assertEqual(build("{:without,-S:with}").vdict, {"": "without", "-S": "with"})
        self.assertEqual(build("{}").vdict, {})

    def test_text_kept_verbatim(self):
        self.assertEqual(build("{RESULT: }").vdict, {"RESULT": " "})
        self.assertEqual(build("{TIME:Time (s),grid_color:#444444}").vdict,
                         {"TIME": "Time (s)", "grid_color": "#444444"})
        self.assertEqual(build("{a, b}").makeValues(), ["a", " b"])

    def test_urls(self):
        urls = ["https://www.debian.org/", "http://10.0.2.2:8080/x"]
        self.assertEqual(build("{https://www.debian.org/,http://10.0.2.2:8080/x}").makeValues(), urls)
        self.assertEqual(build('{"https://www.debian.org/", "http://10.0.2.2:8080/x"}').makeValues(), urls)
        labelled = build('{https://www.debian.org/:Debian,"http://10.0.2.2/a?b=1,2":Local}')
        self.assertEqual(labelled.makeValues(), [("https://www.debian.org/", "Debian"), ("http://10.0.2.2/a?b=1,2", "Local")])
        d = build('{debian:https://www.debian.org/,local:"http://10.0.2.2/a?b=1,2"}')
        self.assertEqual(d.vdict, {"debian": "https://www.debian.org/", "local": "http://10.0.2.2/a?b=1,2"})

    def test_quotes(self):
        self.assertEqual(build('{"a,b",\'c:d\',"say \\"hi\\""}').makeValues(), ["a,b", "c:d", 'say "hi"'])
        self.assertEqual(build("{it's,ok}").makeValues(), ["it's", "ok"])

    def test_variables_in_sets(self):
        self.assertEqual(build("{${A:b},$B}").makeValues(), ["${A:b}", "$B"])

    def test_mixed_entries_stay_a_list(self):
        self.assertEqual(build("{a:b,c}").makeValues(), ["a:b", "c"])

    def test_trailing_comment(self):
        self.assertEqual(build("{LOG} //Log may be \"0\", a valid number").makeValues(), ["LOG"])
        self.assertEqual(build("[1-2]   # two values").makeValues(), [1, 2])

    def test_not_parsed(self):
        for value in ["{{ LIMIT + 1 }}", "[0]", "Unqueue()", "Replay(STOP 0, QUICK_CLONE true)", " {a,b}", "abc"]:
            self.assertIsInstance(build(value), SimpleVariable, value)

    def test_invalid_set(self):
        with self.assertRaisesRegex(VariableSyntaxError, "column"):
            build('{"unterminated,b}')
        with self.assertRaises(VariableSyntaxError):
            build("{a,b} trailing")

    def test_concat(self):
        v = build("CONCAT({1,2},[4-5],{https://a.org/})")
        self.assertIsInstance(v, ParentVariable)
        self.assertEqual(v.makeValues(), [1, 2, 4, 5, "https://a.org/"])


class TestFileVariable(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        with open(os.path.join(self.dir, "sites.txt"), "w") as f:
            f.write("# sites to fetch\nhttps://www.debian.org/\n\n  https://example.com/a?b=1,2  \n#https://skipped/\n")

    def test_file(self):
        v = build("FILE(sites.txt)", self.dir)
        self.assertIsInstance(v, ListVariable)
        self.assertEqual(v.makeValues(), ["https://www.debian.org/", "https://example.com/a?b=1,2"])
        self.assertEqual(build('FILE("%s")' % os.path.join(self.dir, "sites.txt")).count(), 2)
        self.assertEqual(build("CONCAT(FILE(sites.txt),{https://c.org/})", self.dir).count(), 3)

    def test_relative_to_cwd(self):
        cwd = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, cwd)
        self.assertEqual(build("FILE(sites.txt)", "/nonexistent").count(), 2)

    def test_missing_or_empty(self):
        with self.assertRaisesRegex(VariableSyntaxError, "no such file"):
            build("FILE(nope.txt)", self.dir)
        open(os.path.join(self.dir, "empty.txt"), "w").write("# nothing\n")
        with self.assertRaisesRegex(VariableSyntaxError, "no value"):
            build("FILE(empty.txt)", self.dir)

    def test_in_a_test_file(self):
        """FILE() paths are relative to the test file, wherever NPF runs from."""
        sub = os.path.join(self.dir, "sub")
        os.mkdir(sub)
        shutil.move(os.path.join(self.dir, "sites.txt"), os.path.join(sub, "sites.txt"))
        path = os.path.join(sub, "web.npf")
        with open(path, "w") as f:
            f.write("%variables\nURL=FILE(sites.txt)\nTAG={a:\"http://x/\",b:http://y/}\n\n%script\necho $URL\n")
        options = argparse.Namespace(show_files=False, quiet=True, debug=False, no_build_deps=[], force_build_deps=[],
                                     ignore_deps=[], keep_env=[], rand_env=0, allow_mp=False, preserve_temp=False,
                                     design="full", experiment_folder=self.dir, search_path=[], cwd=os.getcwd())
        npf.globals.options = options
        test = Test(path, options)
        self.assertEqual(test.variables.vlist["URL"].makeValues(), ["https://www.debian.org/", "https://example.com/a?b=1,2"])
        self.assertEqual(test.variables.vlist["TAG"].vdict, {"a": "http://x/", "b": "http://y/"})


if __name__ == "__main__":
    unittest.main()
