import unittest
from collections import OrderedDict
from npf.models.dataset import Run
from npf.models.units import dtype, numeric_dict

class TestRun(unittest.TestCase):
    def test_run_equality(self):
        r1 = Run({'a': 1, 'b': 2})
        r2 = Run({'b': 2, 'a': 1})
        self.assertEqual(r1, r2)
        self.assertEqual(hash(r1), hash(r2))

    def test_run_inequality(self):
        r1 = Run({'a': 1, 'b': 2})
        r2 = Run({'a': 1, 'b': 3})
        self.assertNotEqual(r1, r2)

    def test_run_inside(self):
        r1 = Run({'a': 1})
        r2 = Run({'a': 1, 'b': 2})
        self.assertTrue(r1.inside(r2))
        self.assertFalse(r2.inside(r1))

    def test_run_format(self):
        r = Run({'a': 1, 'b': 2})
        self.assertIn('a = 1', r.format_variables())
        self.assertIn('b = 2', r.format_variables())

    def test_run_copy(self):
        r1 = Run({'a': 1, 'b': 2})
        r2 = r1.copy()
        self.assertEqual(r1, r2)
        self.assertIsNot(r1, r2)

    def test_run_intersect(self):
        r1 = Run({'a': 1, 'b': 2, 'c': 3})
        r1.intersect({'a', 'b'})
        self.assertEqual(r1.variables, {'a': 1, 'b': 2})

    def test_runequality_ordered(self):
        ra = OrderedDict()
        ra["A"] = 1
        ra["B"] = "2"
        self.assertTrue(type(numeric_dict(ra)["B"]) is int)
        a = Run(ra)
        rb = OrderedDict()
        rb["B"] = 2
        rb["A"] = 1
        b = Run(rb)
        self.assertEqual(a, b)
        self.assertTrue(a.inside(b))
        self.assertTrue(b.inside(a))
        self.assertEqual(a.__hash__(), b.__hash__())
        h = a.__hash__()
        a.write_variables()["A"] = 3
        self.assertNotEqual(a.__hash__(), h)
        self.assertNotEqual(a, b)

class TestType(unittest.TestCase):
    def test_type(self):
        self.assertEqual(dtype('0'), int)
        self.assertEqual(dtype(''), str)
        self.assertEqual(dtype('1'), int)
        self.assertEqual(dtype(' '), str)
