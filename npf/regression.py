from typing import Tuple

from npf.grapher import *
from npf.repository import *
from npf.testie import Testie
from npf.types.dataset import Dataset


class Regression:
    def __init__(self, repo: Repository):
        self.repo = repo

    def accept_diff(self, testie, result, old_result):
        result = np.asarray(result)
        old_result = np.asarray(old_result)
        n = testie.reject_outliers(result).mean()
        old_n = testie.reject_outliers(old_result).mean()
        diff = abs(old_n - n) / old_n
        accept = testie.config["acceptable"]
        accept += abs(result.std() * testie.config["accept_variance"] / n)
        return diff <= accept, diff

    def compare(self, testie, variable_list, all_results, build, old_all_results, last_build,
                allow_supplementary=True) -> tuple:
        """
        Compare two sets of results for the given list of variables and returns the amount of failing test
        :param testie: One testie to get the config from
        :param variable_list:
        :param all_results:
        :param build:
        :param old_all_results:
        :param last_build:
        :param allow_supplementary:
        :return: the amount of failed tests (0 means all passed)
        """

        tests_passed = 0
        tests_total = 0
        for v in variable_list:
            tests_total += 1
            run = Run(v)
            result = all_results.get(run)
            # TODO : some config could implement acceptable range no matter the old value
            if result is None:
                continue
            if old_all_results and run in old_all_results and not old_all_results[run] is None:
                old_result = old_all_results[run]
                ok, diff = self.accept_diff(testie, result, old_result)
                if not ok and testie.config["n_supplementary_runs"] > 0 and allow_supplementary:
                    if not testie.options.quiet:
                        print(
                            "Difference of %.2f%% is outside acceptable margin for %s. Running supplementary tests..." % (
                                diff * 100, run.format_variables()))
                    for i in range(testie.config["n_supplementary_runs"]):
                        n, output, err = testie.execute(build, v)
                        if not n:
                            result = False
                            break
                        result += n

                    if result:
                        all_results[run] = result
                        ok, diff = self.accept_diff(testie, result, old_result)
                    else:
                        ok = True

                if not ok:
                    print(
                        "ERROR: Test %s is outside acceptable margin between %s and %s : difference of %.2f%% !" % (
                        testie.filename, build.version, last_build.version, diff * 100))
                else:
                    tests_passed += 1
                    if not testie.options.quiet:
                        print("Acceptable difference of %.2f%% for %s" % ((diff * 100), run.format_variables()))
            elif last_build:
                print("No old values for %s for version %s." % (run, last_build.version))
                if (old_all_results):
                    old_all_results[run] = [0]
        return tests_passed, tests_total

    def regress_all_testies(self, testies: List['Testie'], options, history : int = 1) -> Tuple[Build, List[Dataset]]:
        """
        Execute all testies passed in argument for the last build of the regressor associated repository
        :param history: Start regression at last build + 1 - history
        :param testies: List of testies
        :param options: Options object
        :return: the lastbuild and one Dataset per testies or None if could not build
        """
        repo = self.repo
        datasets = []

        build = repo.get_last_build(history=history)

        nok = 0

        for testie in testies:
            print("[%s] Running testie %s..." % (repo.name, testie.filename))
            regression = self
            if repo.last_build:
                try:
                    old_all_results = repo.last_build.load_results(testie)
                except FileNotFoundError:
                    old_all_results = None
            else:
                old_all_results = None
            all_results = testie.execute_all(build, prev_results=build.load_results(testie), options=options,
                                             do_test=options.do_test)
            if all_results is None:
                return None
            variables_passed, variables_total = regression.compare(testie, testie.variables, all_results, build,
                                                                   old_all_results,
                                                                   repo.last_build)
            if variables_passed == variables_total:
                nok += 1
            datasets.append(all_results)
            testie.n_variables_passed = variables_passed
            testie.n_variables = variables_total

        build.writeResults()
        repo.last_build = build

        build.n_passed = nok
        build.n_tests = len(testies)

        return build, datasets
