#!/usr/bin/python3
import argparse

import errno

from src import npf
from src.regression import *
from src.statistics import Statistics


def main():
    parser = argparse.ArgumentParser(description='NPF Regression test')
    v = npf.add_verbosity_options(parser)

    b = parser.add_argument_group('Click building options')
    bf = b.add_mutually_exclusive_group()
    bf.add_argument('--build-folder',
                    help='Overwrite build folder to use a local version of the program',dest='build_folder',default=None)
    bf.add_argument('--no-build',
                    help='Do not build the last master', dest='no_build', action='store_true', default=False)
    bf.add_argument('--force-build',
                    help='Force to rebuild Click even if the git current version is matching the regression versions '
                         '(see --version or --history).', dest='force_build',
                    action='store_true', default=False)
    b.add_argument('--allow-old-build',
                   help='Re-build and run test for old versions (compare-version and graph-version) without results. '
                        'By default, only building for the regression versions (see --history or --version) is done',
                   dest='allow_oldbuild', action='store_true', default=False)
    b.add_argument('--force-old-build',
                   help='Force to rebuild the old versions. Ignored if allow-old-build is not set', dest='force_oldbuild',
                   action='store_true', default=False)

    t = npf.add_testing_options(parser, True)

    g = parser.add_argument_group('Versioning options')
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
                   help='A version to compare against the last version. Default is the first parent of the last version containing some results.');
    g.add_argument('--no-compare',
                    help='Do not run regression comparison, just do the tests', dest='compare', action='store_false',
                    default=True)

    s = parser.add_argument_group('Statistics options')
    s.add_argument('--statistics',
                   help='Give some statistics output', dest='statistics', action='store_true',
                   default=False)
    s.add_argument('--statistics-maxdepth',
                   help='Max depth of learning tree', dest='statistics_maxdepth', type=int, default=None)

    a = npf.add_graph_options(parser)
    af = a.add_mutually_exclusive_group()
    af.add_argument('--graph-version', metavar='version', type=str, nargs='*',
                    help='versions to simply graph');
    af.add_argument('--graph-num', metavar='N', type=int, nargs='?', default=8,
                    help='Number of olds versions to graph after --compare-version, unused if --graph-version is given');
    # a.add_argument('--graph-allvariables', help='Graph only the latest variables (usefull when you restrict variables '
    #                                             'with tags)', dest='graph_newonly', action='store_true', default=False)
    # a.add_argument('--graph-serie', dest='graph_serie', metavar='variable', type=str, nargs=1, default=[None],
    #                 help='Set which variable will be used as serie when creating graph');

    parser.add_argument('repo', metavar='repo name', type=str, nargs=1, help='name of the repo/group of builds');

    args = parser.parse_args();

    if args.force_oldbuild and not args.allow_oldbuild:
        print("--force-old-build needs --allow-old-build")
        parser.print_help()
        return 1

    repo = Repository(args.repo[0])
    tags = args.tags
    tags += repo.tags


    #Overwrite config if a build folder is given
    if args.build_folder:
        repo.url = None
        repo._build_path = args.build_folder + '/'
        versions = ['local']
    else:
        versions = repo.method.get_last_versions(limit=args.history,branch=args.branch)

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
        if args.graph_num > 0 and not args.build_folder:
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

    testies = Testie.expand_folder(testie_path=args.testie, options=args, tags=tags)
    if not testies:
        sys.exit(errno.ENOENT)

    npf.override(args,testies)

    for b in last_rebuilds:
        print("Last version %s had no result. Re-executing tests for it." % b.version)
        b.build(args.force_build,args.no_build)
        for testie in testies:
            print("Executing testie %s" % testie.filename)
            all_results = testie.execute_all(b,options=args)
            b.writeversion(testie, all_results)
        b.writeResults()

    returncode = 0

    for build in reversed(builds):
        print("Starting regression test for %s" % build.version)

        nok = 0
        ntests = 0
        for testie in testies:
            print("Executing testie %s" % testie.filename)

            regression = Regression(testie)

            print(testie.get_title())

            old_all_results = None
            if last_build:
                try:
                    old_all_results = last_build.load_results(testie)
                except FileNotFoundError:
                    print("Previous build %s could not be found, we will not compare !" % last_build.version)
                    last_build = None

            try:
                prev_results = build.load_results(testie)
            except FileNotFoundError:
                prev_results = None

            if testie.has_all(prev_results, build) and not args.force_test:
                all_results = prev_results
            else:
                if not build.build(args.force_build,args.no_build):
                    continue
                all_results = testie.execute_all(build, prev_results=prev_results, do_test=args.do_test, options=args)

            if args.compare:
                variables_passed,variables_passed = regression.compare(testie, testie.variables, all_results, build, old_all_results, last_build)
                if variables_passed == variables_passed:
                    nok += 1
                else:
                    returncode += 1
                ntests += 1

            if all_results and len(all_results) > 0:
                build.writeResults()

            #Filtered results are results only for the given current variables
            filtered_results = {}
            for v in testie.variables:
                run = Run(v)
                if run in all_results:
                    filtered_results[run] = all_results[run]

            if args.statistics:
                Statistics.run(build,filtered_results, testie, max_depth=args.statistics_maxdepth)

            grapher = Grapher()

            graph_variables_names=[]
            for k,v in testie.variables.statics().items():
                val = v.makeValues()[0]
                if type(val) is tuple:
                    val = val[1]
                if k and v and val != '':
                    graph_variables_names.append((k,val))

            if args.graph_filename is None:
                filename = build.result_path(testie,'pdf','_'.join(["%s=%s" % (k,val) for k,val in graph_variables_names]))
            else:
                filename = args.graph_filename[0]

            g_series = []
            if last_build and old_all_results and args.compare:
                g_series.append((testie, last_build, old_all_results))

            for g_build in graph_builds:
                try:
                    g_all_results = g_build.load_results(testie)
                    if (g_all_results and len(g_all_results) > 0):
                        g_series.append((testie, g_build, g_all_results))
                except FileNotFoundError:
                    print("Previous build %s could not be found, we will not graph it !" % g_build.version)
            grapher.graph(series=[(testie, build, all_results)] + g_series, title=testie.get_title(),
                          filename=filename,
                          graph_variables=[Run(x) for x in testie.variables])
        if last_build:
            graph_builds = [last_build] + graph_builds[:-1]
        last_build = build
        if args.compare:
            print("[%s] Finished run for %s, %d/%d tests passed" % (repo.name, build.version, nok, ntests))

    sys.exit(returncode)


if __name__ == "__main__":
    main()
