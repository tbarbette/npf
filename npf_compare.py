#!/usr/bin/env python3
"""
NPF Program to compare multiple software against the same test

A specific script for that purpose is needed because tags may influence
the test according to the repo, so some tricks to find
common variables must be used. For this reason also one test only is
supported in comparator.
"""
import argparse
from typing import Dict

from npf import npf
from npf.test_driver import Comparator
from npf.regression import *

from npf.test import Test

import multiprocessing

from npf import npf

from npf.types.series import Series

from npf.test_driver import group_series

def main():
    """
    The main function for running the NPF cross-repository comparator.
    """
    parser = argparse.ArgumentParser(description='NPF cross-repository comparator')

    npf.add_verbosity_options(parser)

    parser.add_argument('repos', metavar='repo', type=str, nargs='+', help='names of the repositories to compare. Use a format such as repo+VAR=VAL:Title to overwrite variables and serie name.')
    parser.add_argument('--graph-title', type=str, nargs='?', help='Graph title')

    b = npf.add_building_options(parser)
    t = npf.add_testing_options(parser)
    g = npf.add_graph_options(parser)
    args = parser.parse_args()

    # Parse the cluster options
    npf.parse_nodes(args)

    # Parsing repo list and getting last_build
    repo_list = []
    for repo_name in args.repos:
        repo = Repository.get_instance(repo_name, args)
        repo_list.append(repo)

    comparator = Comparator(repo_list)

    # Create a proper file name for the output
    filename = npf.build_output_filename(args, repo_list)

    filename = npf.ensure_folder_exists(filename)

    series, time_series = comparator.run(test_name=args.test_files,
                                        tags=args.tags,
                                        options=args,
                                        on_finish=
                                            lambda series,time_series:
                                                group_series(filename,args,series,time_series,options=args) if args.iterative else None
                                        )

    group_series(filename, series, time_series, options=args)

if __name__ == "__main__":
    multiprocessing.set_start_method('forkserver')
    main()
