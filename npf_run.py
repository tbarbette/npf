#!/usr/bin/env python3
"""
Main NPF test runner program
"""
import argparse
import errno

import sys

from npf import npf
from npf.regression import *
from npf.statistics import Statistics
from npf.test import Test, ScriptInitException


def main():
    parser = argparse.ArgumentParser(description='NPF Test runner')
    v = npf.add_verbosity_options(parser)

    b = npf.add_building_options(parser)
    b.add_argument('--allow-old-build',
                   help='Re-build and run test for old versions (compare-version and graph-version) without results. '
                        'By default, only building for the regression versions (see --history or --version) is done',
                   dest='allow_oldbuild', action='store_true', default=False)
    b.add_argument('--force-old-build',
                   help='Force to rebuild the old versions. Ignored if allow-old-build is not set', dest='force_oldbuild',
                   action='store_true', default=False)

    t = npf.add_testing_options(parser, True)

    g = parser.add_argument_group('Versioning options')
    g.add_argument('--regress',
                    help='Do a regression comparison against old version of the software', dest='compare', action='store_true',
                    default=False)
    gf = g.add_mutually_exclusive_group()
    gf.add_argument('--history',
                    help='Number of commits in the history on which to execute the regression tests. By default, '
                         'this is 1 meaning that the regression test is done on HEAD, and will be compared '
                         'against HEAD~1. This parameter allows to '
                         'start at commits HEAD~N as if it was HEAD, doing the regression test for each'
                         'commits up to now. Difference with --allow-old-build is that the regression test '
                         'will be done for each commit instead of just graphing the results, so error message and'
                         'return code will concern any regression between HEAD and HEAD~N. '
                         'Ignored if --version is given.',
                    dest='history', metavar='N',
                    nargs='?', type=int, default=1)
    g.add_argument('--branch', help='Branch', type=str, nargs='?', default=None)
    g.add_argument('--compare-version', dest='compare_version', metavar='version', type=str, nargs='?',
                   help='A version to compare against the last version. Default is the first parent of the last version containing some results.')


    a = npf.add_graph_options(parser)
    af = a.add_mutually_exclusive_group()
    af.add_argument('--graph-version', metavar='version', type=str, nargs='*',
                    help='versions to simply graph')
    af.add_argument('--graph-num', metavar='N', type=int, nargs='?', default=-1,
                    help='Number of olds versions to graph after --compare-version, unused if --graph-version is given. Default is 0 or 8 if --regress is given.')
    # a.add_argument('--graph-allvariables', help='Graph only the latest variables (usefull when you restrict variables '
    #                                             'with tags)', dest='graph_newonly', action='store_true', default=False)
    # a.add_argument('--graph-serie', dest='graph_serie', metavar='variable', type=str, nargs=1, default=[None],
    #                 help='Set which variable will be used as serie when creating graph');

    parser.add_argument('repo', metavar='repo name', type=str, nargs='?', help='name of the repo/group of builds', default=None)

    args = parser.parse_args()


    npf.parse_nodes(args)


    if args.force_oldbuild and not args.allow_oldbuild:
        print("--force-old-build needs --allow-old-build")
        parser.print_help()
        return 1

    if args.repo:
        repo = Repository.get_instance(args.repo, args)
    else:
        if os.path.exists(args.test_files) and os.path.isfile(args.test_files):
            tmptest = Test(args.test_files,options=args)
            if "default_repo" in tmptest.config and tmptest.config["default_repo"] is not None:
                repo = Repository.get_instance(tmptest.config["default_repo"], args)
            else:
                print("This npf script has no default repository")
                sys.exit(1)
        else:
            print("Please specify a repository to use to the command line or only a single test with a default_repo")
            sys.exit(1)

    if args.graph_num == -1:
        args.graph_num = 8 if args.compare else 0


    tags = args.tags
    tags += repo.tags

    #Overwrite config if a build folder is given
    if args.use_local:
        repo.url = None
        repo._build_path = args.use_local + '/'
        versions = ['local']
    elif repo.url:
        versions = repo.method.get_last_versions(limit=args.history,branch=args.branch)
    else:
        versions = ['local']

    # Builds of the regression versions
    builds = []

    for version in versions:
        builds.append(Build(repo, version))

    last_rebuilds = []

    last_build = None
    if args.compare:
        if args.compare_version and len(args.compare_version):
            compare_version = args.compare_version
            last_build = Build(repo, compare_version)
        else:
            old_versions = repo.method.get_history(versions[-1],100)
            for i, version in enumerate(old_versions):
                last_build = Build(repo, version)
                if last_build.hasResults():
                    break
                elif args.allow_oldbuild:
                    last_rebuilds.append(last_build)
                    break
                if i > 100:
                    last_build = None
                    break
            if last_build:
                print("Comparaison version is %s" % last_build.version)

    graph_builds = []
    if args.graph_version and len(args.graph_version) > 0:
        for g in args.graph_version:
            graph_builds.append(Build(repo, g))
    else:
        if args.graph_num > 1 and repo.url:
            old_versions = repo.method.get_history(last_build.version if last_build else builds[-1].version, 100)
            for i, version in enumerate(old_versions):
                g_build = Build(repo, version)
                if g_build in builds or g_build == last_build:
                    continue
                i += 1
                if g_build.hasResults() and not args.force_oldbuild:
                    graph_builds.append(g_build)
                elif args.allow_oldbuild:
                    last_rebuilds.append(g_build)
                    graph_builds.append(g_build)
                if len(graph_builds) > args.graph_num:
                    break

    tests = Test.expand_folder(test_path=args.test_files, options=args, tags=tags)
    if not tests:
        sys.exit(errno.ENOENT)

    npf.override(args, tests)

    for b in last_rebuilds:
        print("Last version %s had no result. Re-executing tests for it." % b.version)
        did_something = False
        for test in tests:
            prev_results = b.load_results(test)
            print("Executing test %s" % test.filename)
            try:
                all_results, time_results, init_done = test.execute_all(b,options=args, prev_results=prev_results)

                if all_results is None and time_results is None:
                    continue
            except ScriptInitException:
                continue
            else:
                did_something = True
            b.writeversion(test, all_results, allow_overwrite=True)
        if did_something:
            b.writeResults()

    returncode = 0

    for build in reversed(builds):
        if len(builds) > 1 or repo.version:
            if build.version == "local":
                print("Starting tests")
            else:
                print("Starting tests for version %s" % build.version)

        nok = 0
        ntests = 0

        for test in tests:
            print("Executing test %s" % test.filename)

            regression = Regression(test)

            if test.get_title() != test.filename:
                print(test.get_title())

            old_all_results = None
            if last_build:
                try:
                    old_all_results = last_build.load_results(test)
                except FileNotFoundError:
                    print("Previous build %s could not be found, we will not compare !" % last_build.version)
                    last_build = None

            try:
                prev_results = build.load_results(test)
                prev_kind_results = build.load_results(test, kind=True)
            except FileNotFoundError:
                prev_results = None
                prev_kind_results = None

            all_results = None
            time_results = None
            try:
                if all_results is None and time_results is None:
                    all_results, time_results, init_done = test.execute_all(build, prev_results=prev_results, prev_kind_results=prev_kind_results, do_test=args.do_test, options=args)
                if not all_results and not time_results:
                    returncode+=1
                    continue
            except ScriptInitException:
                continue

            if args.compare:
                variables_passed,variables_passed = regression.compare(test, test.variables, all_results, build, old_all_results, last_build)
                if variables_passed == variables_passed:
                    nok += 1
                else:
                    returncode += 1
                ntests += 1

            if all_results and len(all_results) > 0:
                build.writeResults()

            #Filtered results are results only for the given current variables
            filtered_results = {}
            for v in test.variables:
                run = Run(v)
                if run in all_results:
                    filtered_results[run] = all_results[run]

            if args.statistics:
                Statistics.run(build,filtered_results, test, max_depth=args.statistics_maxdepth, filename=args.statistics_filename)

            grapher = Grapher()

            g_series = []
            if last_build and old_all_results and args.compare:
                g_series.append((test, last_build, old_all_results))

            for g_build in graph_builds:
                try:
                    g_all_results = g_build.load_results(test)
                    if (g_all_results and len(g_all_results) > 0):
                        g_series.append((test, g_build, g_all_results))
                except FileNotFoundError:
                    print("Previous build %s could not be found, we will not graph it !" % g_build.version)

            filename = args.graph_filename if args.graph_filename else build.result_path(test.filename, 'pdf')
            grapher.graph(series=[(test, build, all_results)] + g_series,
                          title=test.get_title(),
                          filename=filename,
                          graph_variables=[Run(x) for x in test.variables],
                          options = args)
            if time_results:
                for find, results in time_results.items():
                    if not results:
                        continue
                    grapher.graph(series=[(test, build, results)],
                          title=test.get_title(),
                          filename=filename,
                          options = args)
        if last_build and args.graph_num > 0:
            graph_builds = [last_build] + graph_builds[:-1]
        last_build = build
        if args.compare:
            print("[%s] Finished run for %s, %d/%d tests passed" % (repo.name, build.version, nok, ntests))

    sys.exit(returncode)


if __name__ == "__main__":
    main()
