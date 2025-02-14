#!/usr/bin/env python3
"""
NPF Program to compare multiple software against the same test

A specific script for that purpose is needed because tags may influence
the test according to the repo, so some tricks to find
common variables must be used. For this reason also one test only is
supported in comparator.
"""

from npf.tests.main import main

if __name__ == "__main__":
    main()
