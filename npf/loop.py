from typing import List
from npf import npf
from npf.regression import Regression
from npf.repository import Repository
from npf.test import Test


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
