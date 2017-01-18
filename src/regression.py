from typing import Tuple

from src.repository import *
from src.build import *
from src.grapher import *

class Regression:
    def __init__(self, repo):
        self.repo = repo

    def accept_diff(self, testie, result, old_result):
        result = np.asarray(result)
        old_result = np.asarray(old_result)
        n = testie.reject_outliers(result).mean()
        old_n = testie.reject_outliers(old_result).mean()
        diff=abs(old_n - n) / old_n
        accept =  testie.config["acceptable"]
        accept += abs(result.std() * testie.config["accept_variance"] / n)
        return diff <= accept, diff

    def compare(self, testie, variable_list, all_results, build, old_all_results, last_build, allow_supplementary=True) -> tuple:
        """
        Compare two sets of results for the given list of variables and returns the amount of failing test
        :param variable_list:
        :param all_results:
        :param build:
        :param old_all_results:
        :param last_build:
        :param allow_supplementary:
        :return: the amount of failed tests (0 means all passed)
        """

        tests_failed = 0
        tests_total = 0
        for v in variable_list:
            tests_total += 1
            run = Run(v)
            result = all_results[run]
            # TODO : some config could implement acceptable range no matter the old value
            if result is None:
                continue
            if old_all_results and run in old_all_results and not old_all_results[run] is None:
                old_result = old_all_results[run]
                ok, diff = self.accept_diff(testie, result, old_result)
                if not ok and testie.config["n_supplementary_runs"] > 0 and allow_supplementary:
                    if not testie.quiet:
                        print(
                            "Difference of %.2f%% is outside acceptable margin for %s. Running supplementary tests..." % (
                            diff * 100, run.format_variables()))
                    for i in range(testie.config["n_supplementary_runs"]):
                        n, output, err = testie.execute(build, v)
                        if n == False:
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
                        "ERROR: Test %s is outside acceptable margin between %s and %s : difference of %.2f%% !" % (testie.filename,build.uuid,last_build.uuid,diff * 100)  )
                    tests_failed += 1
                elif not testie.quiet:
                    print("Acceptable difference of %.2f%% for %s" % ((diff * 100), run.format_variables()))
            elif last_build:
                print("No old values for %s for uuid %s." % (run, last_build.uuid))
                if (old_all_results):
                    old_all_results[run] = [0]
        return tests_failed,tests_total

    def regress_all_testies(self, testies:List[Testie], quiet:bool, history:int = 0, force_test:bool = True) -> Tuple[Build,Dataset]:
        repo = self.repo
        gitrepo = repo.gitrepo()
        datasets = []
        commit = next(gitrepo.iter_commits('origin/' + repo.branch))
        uuid = commit.hexsha[:7]
        if repo.last_build and uuid == repo.last_build.uuid:
            if not quiet:
                print("[%s] No new uuid !" % (repo.name))
            return None,None

        if (history > 0 and repo.last_build):
            build = repo.last_build_before(repo.last_build)
        else:
            build = Build(repo, uuid)

        if repo.last_build:
            print("[%s] New uuid %s !" % (repo.name, build.uuid))

        if not build.build_if_needed():
            if (build.uuid != uuid):
                repo.last_build = build
            return None,None
        nok = 0

        for testie in testies:
            print("[%s] Running testie %s..." % (repo.name, testie.filename))
            regression = self
            if repo.last_build:
                try:
                    old_all_results = repo.last_build.readUuid(testie)
                except FileNotFoundError:
                    old_all_results = None
            else:
                old_all_results = None
            all_results = testie.execute_all(build, prev_results=(None if force_test else build.readUuid(testie)))
            tests_failed, tests_total = regression.compare(testie, testie.variables, all_results, build, old_all_results,
                                                           repo.last_build)
            if tests_failed == 0:
                nok += 1
            build.writeUuid(testie, all_results)
            datasets.append(all_results)

        build.writeResults()
        repo.last_build = build

        build.n_passed = nok
        build.n_tests = len(testies)

        return build,datasets
