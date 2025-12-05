import unittest

class TestEnoslib(unittest.TestCase):
    def test_enoslib(self):
        try:
            import enoslib as en
            from npf.enoslib import run
            run('integration/sections.npf', roles={"localhost":en.LocalHost()}, argsv=[])

        except ImportError as e:
            print("Enoslib test ignored as enoslib is not installed")
            pass  # module doesn't exist, deal with it.
