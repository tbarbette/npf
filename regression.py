#!/usr/bin/python3
import argparse

from src.regression import *
from src.statistics import Statistics


def main():
    parser = argparse.ArgumentParser(description='Click performance regression test')
    v = parser.add_argument_group('Verbosity options')
    v.add_argument('--show-full', help='Show full execution results', dest='show_full', action='store_true',
                   default=False)
    v.add_argument('--quiet', help='Quiet mode', dest='quiet', action='store_true', default=False)

    b = parser.add_argument_group('Click building options')
    bf = b.add_mutually_exclusive_group()
    bf.add_argument('--no-build',
                    help='Do not build the last master', dest='no_build', action='store_true', default=False)
    bf.add_argument('--force-build',
                    help='Force to rebuild Click even if the git current uuid is matching the regression uuids '
                         '(see --uuid or --history).', dest='force_build',
                    action='store_true', default=False)
    b.add_argument('--allow-old-build',
                   help='Re-build and run test for old UUIDs (compare-uuid and graph-uuid) without results. '
                        'By default, only building for the regression uuids (see --history or --uuid) is done',
                   dest='allow_oldbuild', action='store_true', default=False)
    b.add_argument('--force-old-build',
                   help='Force to rebuild the old uuids. Ignored if allow-old-build is not set', dest='force_oldbuild',
                   action='store_true', default=False)

    t = parser.add_argument_group('Testing options')
    tf = t.add_mutually_exclusive_group()
    tf.add_argument('--no-test',
                    help='Do not run any tests, use previous results', dest='do_test', action='store_false',
                    default=True)
    tf.add_argument('--force-test',
                    help='Force re-doing all tests even if data for the given uuid and '
                         'variables is already known', dest='force_test', action='store_true',
                    default=False)
    t.add_argument('--n_runs', help='Override test n_runs', type=int, nargs='?', metavar='N', default=-1)
    t.add_argument('--n_supplementary_runs', metavar='N', help='Override test n_supplementary_runs', type=int,
                   nargs='?', default=-1)

    t.add_argument('--tags', metavar='tag', type=str, nargs='+', help='list of tags');
    t.add_argument('--testie', metavar='path or testie', type=str, nargs='?', default='tests',
                   help='script or script folder. Default is tests');

    g = parser.add_argument_group('Commit choice')
    gf = g.add_mutually_exclusive_group()
    gf.add_argument('--history',
                    help='Number of commits in the history on which to excute the regression tests. By default, '
                         'this is 1 meaning that the regression test is done on HEAD, and will be compared '
                         'against HEAD~1. This parameter allows to '
                         'start at commits HEAD~N as if it was HEAD, doing the regression test for each'
                         'commits up to now. Difference with --allow-old-build is that the regression test '
                         'will be done for each commit instead of just graphing the results, so error message and'
                         'return code will concern any regression between HEAD and HEAD~N. '
                         'Ignored if --uuid is given.',
                    dest='history', metavar='N',
                    nargs='?', type=int, default=1)
    gf.add_argument('--uuid', metavar='uuid', type=str, nargs='*',
                    help='Uuid to checkout and test. Default is master''s HEAD uuid and its N "--redo-history" firsts parents.');
    g.add_argument('--branch', help='Branch', type=str, nargs='?', default=None)

    g.add_argument('--compare-uuid', dest='compare_uuid', metavar='uuid', type=str, nargs='?',
                   help='A uuid to compare against the last uuid. Default is the first parent of the last uuid containing some results.');
    g.add_argument('--no-compare',
                    help='Do not run regression comparison, just do the tests', dest='compare', action='store_false',
                    default=True)

    s = parser.add_argument_group('Statistics options')
    s.add_argument('--statistics',
                   help='Give some statistics output', dest='statistics', action='store_true',
                   default=False)
    s.add_argument('--statistics-maxdepth',
                   help='Max depth of learning tree', dest='statistics_maxdepth', type=int, default=None)

    a = parser.add_argument_group('Graphing options')
    af = a.add_mutually_exclusive_group()
    af.add_argument('--graph-uuid', metavar='uuid', type=str, nargs='*',
                    help='Uuids to simply graph');
    af.add_argument('--graph-num', metavar='N', type=int, nargs='?', default=8,
                    help='Number of olds UUIDs to graph after --compare-uuid, unused if --graph-uuid is given');
    a.add_argument('--graph-allvariables', help='Graph only the latest variables (usefull when you restrict variables '
                                                'with tags)', dest='graph_newonly', action='store_true', default=False)

    parser.add_argument('repo', metavar='repo name', type=str, nargs=1, help='name of the repo/group of builds');

    parser.set_defaults(tags=[])
    args = parser.parse_args();

    if args.force_oldbuild and not args.allow_oldbuild:
        print("--force-old-build needs --allow-old-build")
        parser.print_help()
        return 1

    repo = Repository(args.repo[0])
    tags = args.tags
    tags += repo.tags

    gitrepo = repo.checkout(args.branch)

    if args.uuid:
        uuids = args.uuid
    else:
        uuids = []
        for i, commit in enumerate(gitrepo.iter_commits('origin/' + repo.branch)):
            if i >= args.history: break
            short = commit.hexsha[:7]
            uuids.append(short)

    clickpath = repo.reponame + "/build"

    # Builds of the regression uuids
    builds = []
    for short in uuids:
        builds.append(Build(repo, short))
        compare_uuid = short

    last_rebuilds = []

    last_build = None
    if args.compare_uuid and len(args.compare_uuid):
        compare_uuid = args.compare_uuid
        last_build = Build(repo, compare_uuid)
    elif args.history <= 1:
        for i, commit in enumerate(next(gitrepo.iter_commits(compare_uuid)).iter_parents()):
            last_build = Build(repo, commit.hexsha[:7])
            if last_build.hasResults():
                break
            elif args.allow_oldbuild:
                last_rebuilds.append(last_build)
                break
            if i > 100:
                last_build = None
                break
        if last_build:
            print("Comparaison UUID is %s" % last_build.uuid)

    graph_builds = []
    if args.graph_uuid and len(args.graph_uuid) > 0:
        for g in args.graph_uuid:
            graph_builds.append(Build(repo, g))
    else:
        if last_build and args.graph_num > 0:
            for commit in gitrepo.commit(last_build.uuid).iter_parents():
                g_build = Build(repo, commit.hexsha[:7])
                if g_build in builds or g_build == last_build:
                    continue
                i += 1
                if g_build.hasResults() and not args.force_oldbuild:
                    graph_builds.append(g_build)
                elif args.allow_oldbuild:
                    last_rebuilds.append(g_build)
                    graph_builds.append(g_build)
                if i > 100:
                    break
                if len(graph_builds) > args.graph_num:
                    break

    testies = Testie.expand_folder(testie_path=args.testie, quiet=args.quiet, tags=tags, show_full=args.show_full)

    for b in last_rebuilds:
        print("Last UUID %s had no result. Re-executing tests for it." % b.uuid)
        b.build_if_needed()
        for testie in testies:
            print("Executing script %s" % testie.filename)
            all_results = testie.execute_all(b)
            b.writeUuid(testie, all_results)
        b.writeResults()

    returncode = 0

    for build in reversed(builds):
        print("Starting regression test for %s" % build.uuid)
        do_test = args.do_test
        need_rebuild = build.is_build_needed()

        if args.force_build:
            need_rebuild = True
        if not os.path.exists(clickpath + '/bin/click'):
            need_rebuild = True
            if args.no_build:
                print(
                    "%s does not exist but --no-build provided. Cannot continue without Click !" % clickpath + '/bin/click')
                return 1
        if args.no_build:
            if need_rebuild:
                print("Warning : will not do test because build is not allowed")
                do_test = False
                need_rebuild = False

        nok = 0
        ntests = 0
        for testie in testies:
            print("Executing testie %s" % testie.filename)
            regression = Regression(testie)
            if args.n_runs != -1:
                testie.config["n_runs"] = args.n_runs

            if args.n_supplementary_runs != -1:
                testie.config["n_supplementary_runs"] = args.n_supplementary_runs

            print(testie.info.content.strip())

            force_test = args.force_test
            old_all_results = None
            if last_build:
                try:
                    old_all_results = last_build.readUuid(testie)
                except FileNotFoundError:
                    print("Previous build %s could not be found, we will not compare !" % last_build.uuid)
                    last_build = None

            if force_test:
                prev_results = None
            else:
                try:
                    prev_results = build.readUuid(testie)
                except FileNotFoundError:
                    prev_results = None

            if testie.has_all(prev_results):
                all_results = prev_results
            else:
                if need_rebuild:
                    build.build()
                all_results = testie.execute_all(build, prev_results, do_test=do_test)

            if args.compare:
                tests_failed,tests_total = regression.compare(testie.variables, all_results, build, old_all_results, last_build)
                if tests_failed == 0:
                    nok += 1
                else:
                    returncode += 1
                ntests += 1

            build.writeResults()

            if args.statistics:
                filtered_results={}
                for v in testie.variables:
                    run = Run(v)
                    filtered_results[run] = all_results[run]
                Statistics.run(build,filtered_results, testie, max_depth=args.statistics_maxdepth)

            grapher = Grapher()

            graphname = build.result_path(testie,'pdf')

            g_series = []
            if last_build and args.compare:
                g_series.append((testie, last_build, old_all_results))

            for g_build in graph_builds:
                try:
                    g_all_results = g_build.readUuid(testie)
                    g_series.append((testie, g_build, g_all_results))
                except FileNotFoundError:
                    print("Previous build %s could not be found, we will not graph it !" % g_build.uuid)
            grapher.graph(series=[(testie, build, all_results)] + g_series, title=testie.get_title(),
                          filename=graphname,
                          graph_variables=list(testie.variables))
        if last_build:
            graph_builds = [last_build] + graph_builds
        last_build = build
        print("[%s] Finished run for %s, %d/%d tests passed" % (repo.name, build.uuid, nok, ntests))

    sys.exit(returncode)


if __name__ == "__main__":
    main()
