#!/usr/bin/env python3
"""
NPF Program to compare multiple software against the same test

A specific script for that purpose is needed because tags may influence
the test according to the repo, so some tricks to find
common variables must be used. For this reason also one test only is
supported in comparator.
"""
import argparse

from npf import npf
from npf.regression import *
from pathlib import Path

from npf.test import Test

from npf.statistics import Statistics

class Comparator():
    def __init__(self, repo_list: List[Repository]):
        self.repo_list = repo_list
        self.graphs_series = []
        self.kind_graphs_series = []

    def build_list(self, on_finish, test, build, data_datasets, kind_datasets):
         on_finish(self.graphs_series + [(test,build,data_datasets[0])], self.kind_graphs_series + [(test,build,kind_datasets[0])])

    def run(self, test_name, options, tags, on_finish=None):
        for irepo,repo in enumerate(self.repo_list):
            regressor = Regression(repo)
            tests = Test.expand_folder(test_name, options=options, tags=repo.tags + tags)
            tests = npf.override(options, tests)
            for itest,test in enumerate(tests):
                build, data_dataset, kind_dataset  = regressor.regress_all_tests(tests=[test], options=options, on_finish=lambda b,dd,td: self.build_list(on_finish,test,b,dd,td) if on_finish else None,iserie=irepo,nseries=len(self.repo_list) )
            if len(tests) > 0 and not build is None:
                build._pretty_name = repo.name
                self.graphs_series.append((test, build, data_dataset[0]))
                self.kind_graphs_series.append((test, build, kind_dataset[0]))
        if len(self.graphs_series) == 0:
            print("No valid tags/test/repo combination.")
            return None, None

        return self.graphs_series, self.kind_graphs_series

def do_graph(filename,args,series,kind_series,options):

    if series is None:
        return

    #Group repo if asked to do so
    if options.group_repo:
        repo_series=OrderedDict()
        for i, (test, build, dataset) in enumerate(series):
            repo_series.setdefault(build.repo.reponame,(test,build,OrderedDict()))
            for run, run_results in dataset.items():
                run.variables['SERIE'] = build.pretty_name()
                repo_series[build.repo.reponame][2][run] = run_results
        series = []
        for reponame, (test, build, dataset) in repo_series.items():
            build._pretty_name = reponame
            build.version = reponame
            series.append((test, build, dataset))

    # Merge series with common name
    if options.group_series:
        merged_series = OrderedDict()
        for test, build, dataset in series:
            #Group series by serie name
            merged_series.setdefault(build.pretty_name(), []).append((test, build, dataset))

        series = []
        for sname,slist in merged_series.items():
                if len(slist) == 1:
                    series.append(slist[0])
                else:
                    all_r = {}
                    for results in [l[2] for l in slist]:
                        all_r.update(results)
                    series.append((slist[0][0], slist[0][1], all_r))

    # We must find the common variables to all series, and change dataset to reflect only those
    all_variables = []
    for test, build, dataset in series:
        v_list = set()
        for run, results in dataset.items():
            v_list.update(run.variables.keys())
        all_variables.append(v_list)

        if args.statistics:
            Statistics.run(build,dataset, test, max_depth=args.statistics_maxdepth, filename=args.statistics_filename if args.statistics_filename else npf.build_output_filename(args, [build.repo for t,build,d in series]))

    common_variables = set.intersection(*map(set, all_variables))

    #Remove variables that are totally defined by the series, that is
    # variables that only have one value inside each serie
    # but have different values accross series
    useful_variables=[]
    for variable in common_variables:
        all_values = set()
        all_alone=True
        for i, (test, build, dataset) in enumerate(series):
            serie_values = set()
            for run, result_types in dataset.items():
                if variable in run.variables:
                    val = run.variables[variable]
                    serie_values.add(val)
            if len(serie_values) > 1:
                all_alone = False
                break
        if all_alone:
            pass
        else:
            useful_variables.append(variable)

    if options.group_repo:
        useful_variables.append('SERIE')

    for v in series[0][0].config.get_list("graph_hide_variables"):
        if v in useful_variables:
            useful_variables.remove(v)

    #Keep only the variables in Run that are usefull as defined above
    for i, (test, build, dataset) in enumerate(series):
        ndataset = OrderedDict()
        for run, results in dataset.items():
            ndataset[run.intersect(useful_variables)] = results
        series[i] = (test, build, ndataset)

    #Keep only the variables in Time Run that are usefull as defined above
    if options.do_time:
      n_kind_series=OrderedDict()
      for i, (test, build, kind_dataset) in enumerate(kind_series):
        for kind, dataset in kind_dataset.items():
          ndataset = OrderedDict()
          n_kind_series.setdefault(kind,[])
          for run, results in dataset.items():
            ndataset[run.intersect(useful_variables + [kind])] = results
          if ndataset:
            n_kind_series[kind].append((test, build, ndataset))

    grapher = Grapher()
    print("Generating graphs...")
    g = grapher.graph(series=series,
                      filename=filename,
                      options=args,
                      title=args.graph_title)
    if options.do_time:
        for kind,series in n_kind_series.items():
            print("Generating graph for time serie '%s'..." % kind)
            g = grapher.graph(series=series,
                          filename=filename,
                          fileprefix=kind,
                          options=args,
                          title=args.graph_title)

def main():
    parser = argparse.ArgumentParser(description='NPF cross-repository comparator')

    npf.add_verbosity_options(parser)

    parser.add_argument('repos', metavar='repo', type=str, nargs='+', help='names of the repositories to watch')


    parser.add_argument('--graph-title', type=str, nargs='?', help='Graph title')

    b = npf.add_building_options(parser)
    t = npf.add_testing_options(parser)
    g = npf.add_graph_options(parser)
    args = parser.parse_args()

    npf.parse_nodes(args)

    # Parsing repo list and getting last_build
    repo_list = []
    for repo_name in args.repos:
        repo = Repository.get_instance(repo_name, args)
        repo.last_build = None
        repo_list.append(repo)

    comparator = Comparator(repo_list)

    filename = npf.build_output_filename(args, repo_list)

    savedir = Path(os.path.dirname(filename))
    if not savedir.exists():
        os.makedirs(savedir.as_posix())

    if not os.path.isabs(filename):
        filename = os.getcwd() + os.sep + filename

    series, time_series = comparator.run(test_name=args.test_files, tags=args.tags, options=args, on_finish=lambda series,time_series:do_graph(filename,args,series,time_series,options=args) if args.iterative else None)

    do_graph(filename, args, series, time_series, options=args)

if __name__ == "__main__":
    main()
