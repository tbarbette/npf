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
from npf.pipeline import pypost
from npf.pipeline import export_pandas


from npf.regression import *

from npf.test import Test

from npf.statistics import Statistics

import multiprocessing

from npf import npf

from npf.types.series import Series

class Comparator():

    def __init__(self, repo_list: List[Repository]):
        self.repo_list = repo_list
        self.graphs_series = []
        self.kind_graphs_series = []

    def build_list(self, on_finish, test, build:Build, data_datasets:Dataset, kind_datasets):
         on_finish(self.graphs_series + [(test,build,data_datasets[0])], self.kind_graphs_series + [(test,build,kind_datasets[0])])

    def run(self, test_name, options, tags, on_finish=None):
        for i_repo, repo in enumerate(self.repo_list):
            build = None
            regressor = Regression(repo)
            tests = Test.expand_folder(test_name, options=options, tags=repo.tags + tags)
            tests = npf.override(options, tests)
            for test in tests:
                build, data_dataset, kind_dataset  = regressor.regress_all_tests(tests=[test], options=options, on_finish=lambda b,dd,td: self.build_list(on_finish,test,b,dd,td) if on_finish else None,iserie=i_repo,nseries=len(self.repo_list) )
            if len(tests) > 0 and build is not None:
                build._pretty_name = repo.name
                self.graphs_series.append((test, build, data_dataset[0]))
                self.kind_graphs_series.append((test, build, kind_dataset[0]))
        if len(self.graphs_series) == 0:
            print("No valid tags/test/repo combination.")
            return None, None

        return self.graphs_series, self.kind_graphs_series


def export_output(filename: str, series: Series , kind_series:Series,options):
    """
    The function handles output modules, like graph, statistics and CSV generation

    :param filename: The name of the file to which the output will be exported
    :param series: The "series" parameter refers to the data series that you want to export. It could be
    a list, array, or any other data structure that contains the data you want to export
    :param kind_series: The `kind_series` parameter is used to specify the type of series to be
    exported. It can take values such as "line", "bar", "scatter", etc., depending on the type of chart
    or graph you want to export
    :param options: The "options" parameter is a dictionary that contains various options for exporting
    the output. These options can include things like the file format, the delimiter to use, whether or
    not to include headers, etc
    """

    if series is None:
        return

    pypost.execute_pypost(series)
    export_pandas.export_pandas(options, series)

    if options.do_time:
        print(kind_series)
        for test, build, kind_dataset in kind_series:
            for kind, dataset in kind_dataset.items():
                try:
                    pypost.execute_pypost(dataset)
                    export_pandas.export_pandas(options, dataset, fileprefix=kind)
                except Exception as e:
                    print(f"While exporting dataset for kind {kind}:")
                    print(dataset)
                    print("Error:")
                    print(e)

    #Group repo if asked to do so
    if options.group_repo:
        repo_series=OrderedDict()
        for test, build, dataset in series:
            repo_series.setdefault(build.repo.reponame,(test,build,OrderedDict()))
            for run, run_results in dataset.items():
                run.write_variables()['SERIE'] = build.pretty_name()
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
                    all_r |= results
                series.append((slist[0][0], slist[0][1], all_r))

    if options.statistics:
        for test, build, dataset in series:
            Statistics.run(build,dataset, test, max_depth=options.statistics_maxdepth, filename=options.statistics_filename or npf.build_output_filename(options, [build.repo for t,build,d in series]))



    # We must find the common variables to all series, and change dataset to reflect only those
    all_variables = []
    for test, build, dataset in series:
        v_list = set()
        for run, results in dataset.items():
            v_list.update(run.read_variables().keys())
        all_variables.append(v_list)

    common_variables = set.intersection(*map(set, all_variables))

    #Remove variables that are totally defined by the series, that is
    # variables that only have one value inside each series
    # but have different values across series
    useful_variables=[]
    for variable in common_variables:
        all_alone=True
        for test, build, dataset in series:
            serie_values = set()
            for run, _ in dataset.items():
                if variable in run.read_variables():
                    val = run.read_variables()[variable]
                    serie_values.add(val)
            if len(serie_values) > 1:
                all_alone = False
                break
        if not all_alone:
            useful_variables.append(variable)

    if options.group_repo:
        useful_variables.append('SERIE')

    for v in series[0][0].config.get_list("graph_hide_variables"):
        if v in useful_variables:
            useful_variables.remove(v)

    #Keep only the variables in Run that are useful as defined above
    for i, (test, build, dataset) in enumerate(series):
        new_dataset: Dict[Run,List]  = OrderedDict()
        for run, results in dataset.items():
            m = run.intersect(useful_variables)
            if m in new_dataset:
                print(f"WARNING: You are comparing series with different variables. Results of series '{build.pretty_name()}' are merged.")
                for output, data in results.items():
                    if output in new_dataset[m]:
                        new_dataset[m][output].extend(data)
                    else:
                        new_dataset[m][output] = data
            else:
                new_dataset[m] = results
        series[i] = (test, build, new_dataset)

    #Keep only the variables in Time Run that are useful as defined above
    if options.do_time:
        n_kind_series=OrderedDict()
        for test, build, kind_dataset in kind_series:
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
                      options=options,
                      title=options.graph_title)
    if options.do_time:
        for kind,series in n_kind_series.items():
            print(f"Generating graph for time serie '{kind}'...")
            g = grapher.graph(series=series,
                          filename=filename,
                          fileprefix=kind,
                          options=options,
                          title=options.graph_title)

def main():
    parser = argparse.ArgumentParser(description='NPF cross-repository comparator')

    npf.add_verbosity_options(parser)

    parser.add_argument('repos', metavar='repo', type=str, nargs='+', help='names of the repositories to watch')

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
        repo.last_build = None
        repo_list.append(repo)

    comparator = Comparator(repo_list)

    # Create a proper file name for the output
    filename = npf.build_output_filename(args, repo_list)

    filename = npf.ensure_folder_exists(filename)

    series, time_series = comparator.run(test_name=args.test_files,
                                         tags=args.tags, options=args,
                                         on_finish=lambda series,
                                         time_series:export_output(filename,series,time_series,options=args) if args.iterative else None)

    export_output(filename, series, time_series, options=args)

if __name__ == "__main__":
    multiprocessing.set_start_method('forkserver')
    main()