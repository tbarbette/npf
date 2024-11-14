from typing import List
import npf.parsing
from npf.tests.build import Build
from npf.tests.regression import Regression, npf
from npf.repo.repository import Repository
from npf.tests.test import Test
from npf.models.dataset import Dataset


"""Runs all tests for a given list of experiment (or a folder to expand), and a series of repositories.
"""
class Comparator():
    def __init__(self, repo_list: List[Repository]):
        self.repo_list = repo_list
        self.graphs_series = []
        self.time_graphs_series = []

    def build_list(self, on_finish, test, build:Build, data_datasets:Dataset, time_datasets):
         on_finish(self.graphs_series + [(test,build,data_datasets[0])], self.time_graphs_series + [(test,build,time_datasets[0])])

    def run(self, test_name, options, tags:List, on_finish=None, do_regress=True):
        for i_repo, repo in enumerate(self.repo_list):
            build = None
            regressor = Regression(repo)
            tests = Test.expand_folder(test_name, options=options, tags=repo.tags + tags)
            tests = npf.parsing.override(options, tests)
            for test in tests:
                build, data_dataset, time_dataset = regressor.regress_all_tests(
                    tests=[test],
                    do_compare=do_regress,
                    on_finish=lambda b,dd,td: self.build_list(on_finish,test,b,dd,td) if on_finish else None,
                    i_serie=i_repo,
                    nseries=len(self.repo_list)
                    )


            if len(tests) > 0 and build is not None:
                build._pretty_name = repo.name
                self.graphs_series.append((test, build, data_dataset[0]))
                self.time_graphs_series.append((test, build, time_dataset[0]))
        if len(self.graphs_series) == 0:
            print("No valid tags/test/repo combination.")
            return None, None

        return self.graphs_series, self.time_graphs_series


