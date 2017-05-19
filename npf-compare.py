#! /usr/bin/env python3
"""
NPF Program to compare multiple software against the same testie

A specific version is needed because tags may influence the testie according to the repo, so some tricks to find
common variables must be used. For this reason also one testie only is supported in comparator.
"""
import argparse

from npf import npf
from npf.regression import *
from pathlib import Path

from npf.testie import Testie


class Comparator():
    def __init__(self, repo_list: List[Repository]):
        self.repo_list = repo_list

    def run(self, testie_name, options, tags):
        graphs_series = []
        for repo in self.repo_list:
            regressor = Regression(repo)
            testies = Testie.expand_folder(testie_name, options=options, tags=repo.tags + tags)
            testies = npf.override(options, testies)
            for testie in testies:
                build, datasets = regressor.regress_all_testies(testies=[testie], options=options)
                if not build is None:
                    build._pretty_name = repo.name
                    graphs_series.append((testie, build, datasets[0]))

        if len(graphs_series) == 0:
            print("No valid tags/testie/repo combination.")
            return

        return graphs_series


def main():
    parser = argparse.ArgumentParser(description='NPF cross-repository comparator')

    npf.add_verbosity_options(parser)

    parser.add_argument('repos', metavar='repo', type=str, nargs='+', help='names of the repositories to watch')

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

    series = comparator.run(testie_name=args.testie, tags=args.tags, options=args)

    if series is None:
        return

    if args.graph_filename is None:
        filename = 'compare/' + os.path.splitext(os.path.basename(args.testie))[0] + '_' + '_'.join(
            ["%s" % repo.reponame for repo in repo_list]) + '.pdf'
    else:
        filename = args.graph_filename[0]

    dir = Path(os.path.dirname(filename))
    if not dir.exists():
        os.makedirs(dir.as_posix())

    # We must find the common variables to all repo, and change dataset to reflect only those
    all_variables = []
    for testie, build, dataset in series:
        v_list = set()
        for name, variable in testie.variables.vlist.items():
            v_list.add(name)
        all_variables.append(v_list)
    common_variables = set.intersection(*map(set, all_variables))

    for i, (testie, build, dataset) in enumerate(series):
        ndataset = {}
        for run, results in dataset.items():
            ndataset[run.intersect(common_variables)] = results
        series[i] = (testie, build, ndataset)

    grapher = Grapher()
    g = grapher.graph(series=series,
                      filename=filename,
                      options=args)


if __name__ == "__main__":
    main()
