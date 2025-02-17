from typing import Tuple

from npf.globals import get_options
from npf.output.grapher import *
from npf.repo.repository import *
from npf.tests.test import Test, SectionScript, ScriptInitException
from npf.models.dataset import Dataset
import multiprocessing


"""Handles regression tests. That is, given an history of versions, execute tests for all previous versions
and ensure the last version has performance on par with previous ones.
"""
class Regression:

    def __init__(self, repo: Repository):
        self.repo = repo

    def accept_diff(self, test, result, old_result)->Tuple[bool,float]:
        """Compare two sets of results and tells if they difference is between a margin

        Args:
            test (Test): The test object
            result (_type_): The results of the last run
            old_result (_type_): The previous results

        Returns:
            [bool,float]: If the test passes and the difference
        """
        result = np.asarray(result)
        old_result = np.asarray(old_result)
        n = test.reject_outliers(result).mean()
        old_n = test.reject_outliers(old_result).mean()
        diff = abs(old_n - n) / old_n
        accept = test.config["acceptable"]
        accept += abs(result.std() * test.config["accept_variance"] / n)
        return diff <= accept, diff

    def compare(self,
                test:Test,
                variable_list,
                all_results: Dataset,
                build,
                old_all_results,
                last_build,
                allow_supplementary=True,
                init_done=False) -> Tuple[int,int]:
        """
        After the execution of all tests, compare two sets of results for the given list of variables and returns the amount of failing and passing test
        :param init_done: True if initialization for current test is already done (init sections for the test and its import)
        :param test: One test to get the config from
        :param variable_list:
        :param all_results:
        :param build:
        :param old_all_results:
        :param last_build:
        :param allow_supplementary:
        :return: the amount of failed tests (0 means all passed)
        """

        if not old_all_results:
            return 0, 0
        
        m = multiprocessing.Manager()

        tests_passed = 0
        tests_total = 0
        supp_done = False
        r = False
        tot_runs = test.config["n_runs"] + test.config["n_supplementary_runs"]
        for v in variable_list:
            tests_total += 1
            run = Run(v)
            results_types = all_results.get(run)
            
            # TODO : some config could implement acceptable range no matter the old value
            if results_types is None or len(results_types) == 0:
                continue

            need_supp = False
            diff = None
            for result_type, result in results_types.items():
                if run in old_all_results and not old_all_results[run] is None:
                    old_result = old_all_results[run].get(result_type, None)
                    if old_result is None:
                        continue

                    ok, diff = self.accept_diff(test, result, old_result)
                    r = True
                    if not ok and len(result) < tot_runs and allow_supplementary:
                        need_supp = True
                        break
                elif last_build:
                    if not test.options.quiet_regression:
                        print("No old values for %s for version %s." % (run, last_build.version))
                    if old_all_results:
                        old_all_results[run] = {}

            if r and need_supp and test.options.do_test and test.options.allow_supplementary:
                try:
                    if not test.options.quiet_regression:
                        print(
                            "Difference of %.2f%% is outside acceptable margin for %s. Running supplementary tests..." % (
                                diff * 100, run.format_variables()))

                    if not init_done:
                        test.do_init_all(build=build, options=test.options, do_test=test.options.do_test, m=m)
                        init_done = True
                    variables = v.copy()
                    for late_variables in test.get_late_variables():
                        variables.update(late_variables.execute(variables, test))

                    new_results_types, new_time_results_types, output, err, n_exec, n_err = test.execute(build, run, variables,
                                                                    m = m,
                                                                    n_runs=test.config["n_supplementary_runs"],
                                                                    allowed_types={SectionScript.TYPE_SCRIPT, SectionScript.TYPE_EXIT})

                    for result_type, results in new_results_types.items():
                        results_types[result_type] += results

                    if not test.options.quiet_regression:
                        print("Result after supplementary tests done :", results_types)

                    if new_results_types is not None:
                        supp_done = True
                        all_results[run] = results_types
                        for result_type, result in results_types.items():
                            old_result = old_all_results[run].get(result_type, None)
                            if old_result is None:
                                continue
                            ok, diff = self.accept_diff(test, result, old_result)
                            r = True
                            if ok is False:
                                break
                    else:
                        ok = True
                except ScriptInitException:
                    pass
            if r and len(results_types) > 0 and diff is not None:
                if not ok:
                    print(
                        "ERROR: Test %s is outside acceptable margin between %s and %s : difference of %.2f%% !" % (
                            test.filename, build.version, last_build.version, diff * 100))
                else:
                    tests_passed += 1
                    if not test.options.quiet_regression:
                        print("Acceptable difference of %.2f%% for %s" % ((diff * 100), run.format_variables()))

        if supp_done and all_results:
            build.writeversion(test, all_results, allow_overwrite = True)
        return tests_passed, tests_total

    def regress_all_tests(  self,
                            tests: List['Test'],
                            history: int = 1,
                            on_finish = None,
                            do_compare:bool = True,
                            i_serie=0, nseries=1) -> Tuple[Build, List[Dataset], List[Dataset]]:
        """
        Execute all experiments (tests) passed in argument for the last build of the regressor associated repository
        :param history: Start regression at last build + 1 - history
        :param tests: List of experiments
        
        :return: the lastbuild and one Dataset per tests or None if could not build
        """
        repo = self.repo
        data_datasets = []
        time_datasets = []

        if repo.url:
            build = repo.get_last_build(history=history)
        else:
            build = Build(repo, 'local', result_path=get_options().result_path )


        nok = 0

        for i_test, test in enumerate(tests):
            if build.version != "local":
                print(
                    f"[{repo.name}] Running test {test.filename} on version {build.version}..."
                )
            else:
                print(f"[{repo.name}] Running test {test.filename}...")

            if test.get_title() != test.filename:
                print(test.get_title())

            regression = self
            if repo.last_build:
                try:
                    old_all_results = repo.last_build.load_results(test)
                    old_time_all_results = repo.last_build.load_results(test, kind=True)
                except FileNotFoundError:
                    old_all_results = None
                    old_time_all_results = None
            else:
                old_all_results = None
                old_time_all_results = None
            try:
                if on_finish:
                    def early_results(all_data_results, all_time_results):
                        on_finish(build,(data_datasets + [all_data_results]),(time_datasets + [all_time_results]))
                else:
                    early_results = None
                all_results,time_results, init_done = test.execute_all(
                                                build,
                                                prev_results=build.load_results(test),
                                                prev_time_results=build.load_results(test, kind=True),
                                                options=get_options(),
                                                do_test=get_options().do_test,
                                                on_finish=early_results,
                                                iserie=i_serie*len(tests) + i_test,
                                                nseries=len(tests)*nseries)

                if all_results is None and time_results is None:
                    return None, None, None
            except ScriptInitException:
                return None, None, None

            variables_passed, variables_total = regression.compare( test, test.variables, all_results, build,
                                                                    old_all_results,
                                                                    repo.last_build,
                                                                    init_done=init_done, allow_supplementary=get_options().allow_supplementary)
            if variables_passed == variables_total:
                nok += 1
            data_datasets.append(all_results)
            time_datasets.append(time_results)
            test.n_variables_passed = variables_passed
            test.n_variables = variables_total

        build.writeResults()
        repo.last_build = build

        build.n_passed = nok
        build.n_tests = len(tests)

        return build, data_datasets, time_datasets
