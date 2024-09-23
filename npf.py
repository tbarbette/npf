#!/usr/bin/env python3
"""
NPF Program to compare multiple software against the same test

A specific script for that purpose is needed because tags may influence
the test according to the repo, so some tricks to find
common variables must be used. For this reason also one test only is
supported in comparator.
"""
import argparse

import npf
import npf.cmdline
import npf.osutils
from npf.tests import get_default_repository
from npf.tests.test_driver import Comparator
from npf.output import generate_outputs
from npf.tests.regression import *

import multiprocessing

def main():
    """
    The main function for running NPF.
    """

    # First, invoke cmdline parsing
    parser = argparse.ArgumentParser(description='NPF cross-repository comparator')

    npf.cmdline.add_verbosity_options(parser)

    parser.add_argument('repos', metavar='repo', type=str, nargs='*', help='names of the repositories to compare. Use a format such as repo+VAR=VAL:Title to overwrite variables and serie name. By default "local" is used, which means no repository is used and therefore versioning is disabled.')
    parser.add_argument('--graph-title', type=str, nargs='?', help='Graph title')

    b = npf.cmdline.add_building_options(parser)
    t = npf.cmdline.add_testing_options(parser)
    g = npf.cmdline.add_graph_options(parser)
    args = parser.parse_args()

    # Parse the cluster options
    npf.parse_nodes(args)

    # Parsing repo list and getting last_build
    repo_list = []
    for repo_name in args.repos:
        repo = Repository.get_instance(repo_name, args)
        repo_list.append(repo)
    if not repo_list:
        repo = get_default_repository(args)
        repo_list.append(repo)

    # Comparator will handle the comparison between each repo in the list
    comparator = Comparator(repo_list)

    # Create a proper file name for the output
    filename = npf.build_output_filename(repo_list)
    filename = npf.osutils.ensure_folder_exists(filename)

    # Launch the actual runs
    series, time_series = comparator.run(test_name=args.test_files,
                                        tags=args.tags,
                                        options=args,
                                        on_finish=
                                            lambda series,time_series:
                                                generate_outputs(filename,args,series,time_series,options=args) if args.iterative else None
                                        )

    generate_outputs(filename, series, time_series, options=args)

if __name__ == "__main__":
    multiprocessing.set_start_method('forkserver')
    main()
