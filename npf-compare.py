#! /usr/bin/env python3
"""
NPF Program to compare multiple software against the same testie

A specific script for that purpose is needed because tags may influence
the testie according to the repo, so some tricks to find
common variables must be used. For this reason also one testie only is
supported in comparator.
"""
import argparse

from npf import npf
from npf.regression import *
from pathlib import Path

from npf.testie import Testie


class Comparator():
    def __init__(self, repo_list: List[Repository]):
        self.repo_list = repo_list
        self.graphs_series = []

    def build_list(self, on_finish, testie, build,datasets):
        on_finish(self.graphs_series + [(testie,build,datasets[0])])

    def run(self, testie_name, options, tags, on_finish=None):
        for repo in self.repo_list:
            regressor = Regression(repo)
            testies = Testie.expand_folder(testie_name, options=options, tags=repo.tags + tags)
            testies = npf.override(options, testies)
            for testie in testies:
                build, datasets = regressor.regress_all_testies(testies=[testie], options=options, on_finish=lambda b,d: self.build_list(on_finish,testie,b,d) if on_finish else None)
            if len(testies) > 0 and not build is None:
                build._pretty_name = repo.name
                self.graphs_series.append((testie, build, datasets[0]))
        if len(self.graphs_series) == 0:
            print("No valid tags/testie/repo combination.")
            return

        return self.graphs_series

def do_graph(filename,args,series):

    if series is None:
        return

    # We must find the common variables to all repo, and change dataset to reflect only those
    all_variables = []
    for testie, build, dataset in series:
        v_list = set()
        for name, variable in testie.variables.vlist.items():
            v_list.add(name)
        all_variables.append(v_list)
    common_variables = set.intersection(*map(set, all_variables))

    #Remove variables that are totally defined by the series, that is
    # variables that only have one value inside each serie
    # but have different values accross series
    useful_variables=[]
    for variable in common_variables:
        all_values = set()
        all_alone=True
        for i, (testie, build, dataset) in enumerate(series):
            serie_values = set()
            for run, result_types in dataset.items():
                val = run.variables[variable]
                all_values.add(val)
                serie_values.add(val)
            if len(serie_values) > 1:
                all_alone = False
                break
        if all_alone and len(all_values) > 1:
            pass
        else:
            useful_variables.append(variable)

    for v in series[0][0].config.get_list("graph_hide_variables"):
        if v in useful_variables:
            useful_variables.remove(v)
    #Keep only the variables in Run that are usefull as defined above
    for i, (testie, build, dataset) in enumerate(series):
        ndataset = {}
        for run, results in dataset.items():
            ndataset[run.intersect(useful_variables)] = results
        series[i] = (testie, build, ndataset)

    grapher = Grapher()
    g = grapher.graph(series=series,
                      filename=filename,
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


    if args.graph_filename is None:
        filename = 'compare/' + os.path.splitext(os.path.basename(args.testie))[0] + '_' + '_'.join(
            ["%s" % repo.reponame for repo in repo_list]) + '.pdf'
    else:
        filename = args.graph_filename[0]

    dir = Path(os.path.dirname(filename))
    if not dir.exists():
        os.makedirs(dir.as_posix())

    series = comparator.run(testie_name=args.testie, tags=args.tags, options=args, on_finish=lambda series:do_graph(filename,args,series) if args.iterative else None)

    do_graph(filename,args,series)

if __name__ == "__main__":
    main()
