#!/usr/bin/python3

import argparse
import os

import subprocess
from src.regression import *
import git

def main():
    parser = argparse.ArgumentParser(description='Click Performance Executor')
    parser.add_argument('--show-full', help='Show full execution results', dest='show_full', action='store_true')
    parser.add_argument('--quiet', help='Quiet mode', dest='quiet', action='store_true')
    parser.add_argument('--no-build',
                        help='Do not build the last master', dest='no_build', action='store_true', default=False)
    parser.add_argument('--force-build', help='Force to rebuild the last master, even if the git current uuid is matching'
                                              ' the last uuid. Ignored if no-build is set', dest='force_build', action='store_true', default=False)
    parser.add_argument('--allow-old-build',
                        help='Re-build and run test for old UUIDs without results', dest='allow_oldbuild', action='store_true', default=False)
    parser.add_argument('--no-supplementary', help='Do not run supplementary tests if the new value is rejected',
                        dest='allow_supplementary', action='store_false')
    parser.add_argument('--force-test', help='Force re-doing all tests even if data for the given uuid and '
                                             'variables is already known', dest='force_test', action='store_true')
    parser.add_argument('--tags', metavar='tag', type=str, nargs='+', help='list of tags');
    parser.add_argument('--script', metavar='script', type=str, nargs='?', default='tests',
                        help='script or script folder. Default is tests');
    parser.add_argument('--branch', help='Branch', type=str, nargs='?', default='')
    parser.add_argument('--n_runs', help='Override test n_runs', type=int, nargs='?', default=-1)
    parser.add_argument('--n_supplementary_runs', help='Override test n_supplementary_runs', type=int, nargs='?', default=-1)
    parser.add_argument('--uuid', metavar='uuid', type=str, nargs='?',
                        help='Uuid to checkout and test. Default is master''s HEAD uuid.');
    parser.add_argument('--last-uuid', metavar='last_uuid', type=str, nargs='?',
                        help='Last uuid. Default is master''s previous uuid containing some results.');
    parser.add_argument('--graph-uuid', metavar='graph_uuid', type=str, nargs='*',
                        help='Uuids to simply graph. If number, the last N master uuids with results.');
    parser.add_argument('--graph-num', metavar='graph_num', type=int, nargs='?', default=8,
                        help='Number of olds UUIDs to graph');
    parser.add_argument('--graph-allvariables', help='Graph only the latest variables (usefull when you restrict variables '
                                                'with tags)', dest='graph_newonly', action='store_true',default=False)
    parser.add_argument('repo', metavar='repo name', type=str, nargs=1, help='name of the repo/group of builds');
    parser.set_defaults(show_full=False)
    parser.set_defaults(quiet=False)
    parser.set_defaults(force_test=False)
    parser.set_defaults(force_oldbuild=False)
    parser.set_defaults(allow_supplementary=True)
    parser.set_defaults(tags=[])
    args = parser.parse_args();

    repo=Repository(args.repo[0])
    tags = args.tags
    tags += repo.tags

    if not os.path.exists(repo.reponame):
        os.mkdir(repo.reponame)

    clickpath=repo.reponame+"/build"
    need_rebuild = False

    if args.branch:
        branch = args.branch
    else:
        branch = repo.branch

    if os.path.exists(clickpath):
        gitrepo = git.Repo(clickpath)
        current_commit = gitrepo.head.commit
        o = gitrepo.remotes.origin
        o.fetch()
        if gitrepo.commit('origin/'+branch) != current_commit:
            need_rebuild = True
    else:
        print("Cloning from repository %s",repo.url)
        gitrepo = git.Repo.clone_from(repo.url,clickpath)
        need_rebuild = True

    if args.force_build:
        need_rebuild = True
    if not os.path.exists(clickpath + '/bin/click'):
        need_rebuild = True
        if args.no_build:
            print("%s does not exist but --no-build provided. Cannot continue without Click !" % clickpath+'/bin/click')
            return 1
    if args.no_build:
        need_rebuild = False

    if args.uuid:
        uuid = args.uuid
    else:
        uuid = gitrepo.commit('origin/'+branch).hexsha[:7]
        print("%s UUID is %s" % (repo.branch,uuid));

    build = Build(repo, uuid)

    last_rebuilds=[]

    if args.last_uuid and len(args.last_uuid):
        last_uuid=args.last_uuid
        last_build=Build(repo,last_uuid)
    else:
        last_build = None
        for i,commit in enumerate(next(gitrepo.iter_commits(uuid)).iter_parents()):
            last_build=Build(repo,commit.hexsha[:7])
            if last_build.hasResults():
                break
            elif args.allow_oldbuild:
                last_rebuilds.append(last_build)
                break

            if i > 100:
                last_build = None
                break
        if last_build:
            print("Last UUID is %s" % last_build.uuid)

    graph_builds=[]
    if args.graph_uuid and len(args.graph_uuid):
        for g in args.graph_uuid:
            graph_builds.append(Build(repo,g))
    else:
        if last_build:
            for commit in gitrepo.commit(last_build.uuid).iter_parents():
                g_build = Build(repo, commit.hexsha[:7])
                if g_build == build or g_build == last_build:
                    continue
                i+=1
                if g_build.hasResults() and not args.force_oldbuild:
                    graph_builds.append(g_build)
                elif args.allow_oldbuild:
                    last_rebuilds.append(g_build)
                    graph_builds.append(g_build)
                if i > 100:
                    break
                if len(graph_builds) > args.graph_num:
                    break

    scripts=[]
    if os.path.isfile(args.script):
        scripts.append(args.script)
    else:
        for root, dirs, files in os.walk(args.script):
            for file in files:
                if file.endswith(".conf"):
                    scripts.append(os.path.join(root, file))

    for b in last_rebuilds:
        print("Last UUID %s had no result. Re-executing tests for it." % b.uuid)
        b.build_if_needed()
        for script_path in scripts:
            print("Executing script %s" % script_path)
            testie = Testie(script_path, clickpath, quiet=args.quiet, tags=tags, show_full=args.show_full)
            all_results = testie.execute_all(build)
            b.writeUuid(testie, all_results)
        b.writeResults()
        need_rebuild = True

    if need_rebuild:
        if not build.build_if_needed():
            print("Could not build Click for UUID %s !",build.uuid)
            return 1

    returncode=0



    for script_path in scripts:
        print("Executing script %s" % script_path)
        testie = Testie(script_path, clickpath, quiet=args.quiet, tags=tags, show_full=args.show_full)

        if args.n_runs != -1:
            testie.config["n_runs"] = args.n_runs

        if args.n_supplementary_runs != -1:
            testie.config["n_supplementary_runs"] = args.n_supplementary_runs

        regression = Regression(testie)

        print(testie.info.content.strip())

        returncode,all_results,old_all_results = regression.run(build, last_build, force_test=args.force_test, allow_supplementary=args.allow_supplementary);
        build.writeResults()

        grapher = Grapher()
        graphname = build.repo.reponame + '/results/' + build.uuid + '/'+ os.path.splitext(testie.filename)[0] + '.pdf'

        series = [(testie,build,all_results)]
        if last_build:
            series.append((testie,last_build,old_all_results))
        for g_build in graph_builds:
            try:
                g_all_results = g_build.readUuid(testie)
                series.append((testie,g_build,g_all_results))
            except FileNotFoundError:
                print("Previous build %s could not be found, we will not graph it !" % g_build.uuid)

        grapher.graph(series=series, title=testie.get_title(), filename=graphname)

    sys.exit(returncode)



if __name__ == "__main__":
    main()
