import unittest
from npf.osutils import get_valid_filename

class TestOsUtils(unittest.TestCase):
    def test_get_valid_filename(self):
        self.assertEqual(get_valid_filename("test file"), "test_file")
        self.assertEqual(get_valid_filename("test/file"), "testfile")
        self.assertEqual(get_valid_filename("test.file"), "test.file")
        self.assertEqual(get_valid_filename("  test  "), "test")
