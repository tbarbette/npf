import argparse
import os
import math
import numpy as np

from src.variable import *
from src.testie import *
from src.repository import *
from src.build import *
from src.grapher import *

class Regression:
    def __init__(self, testie):
        self.testie = testie

    def accept_diff(self, result, old_result):
        result = np.asarray(result)
        old_result = np.asarray(old_result)
        n = self.testie.reject_outliers(result).mean()
        old_n = self.testie.reject_outliers(old_result).mean()
        diff=abs(old_n - n) / old_n
        accept =  self.testie.config["acceptable"]
        accept += abs(result.std() * self.testie.config["accept_variance"] / n)
        return diff <= accept, diff

    def run(self, build, old_build = None, force_test=False, allow_supplementary=True, do_test=True):
        testie = self.testie
        returncode=0
        old_all_results=None
        if old_build:
            try:
                old_all_results = old_build.readUuid(testie)
            except FileNotFoundError:
                print("Previous build %s could not be found, we will not compare !" % old_build.uuid)
                old_build = None

        if force_test:
            prev_results = None
        else:
            try:
                prev_results = build.readUuid(testie)
            except FileNotFoundError:
                prev_results = None
        all_results = testie.execute_all(build,prev_results,do_test=do_test)
        for run,result in all_results.items():
            v = run.variables
            #TODO : some config could implement acceptable range no matter the old value
            if result is None:
                continue
            if old_all_results and run in old_all_results and not old_all_results[run] is None:
                old_result=old_all_results[run]
                ok,diff = self.accept_diff(result, old_result)
                if not ok and testie.config["n_supplementary_runs"] > 0 and allow_supplementary:
                        if not testie.quiet:
                            print("Difference of %.2f%% is outside acceptable range for %s. Running supplementary tests..." % (diff*100, run.format_variables()))
                        for i in range(testie.config["n_supplementary_runs"]):
                            n,output,err = testie.execute(build, v)
                            if n == False:
                                result = False
                                break
                            result += n

                        if result:
                            all_results[run] = result
                            ok,diff = self.accept_diff(result, old_result)
                        else:
                            ok = True

                if not ok:
                    print("ERROR: Test " + testie.filename + " is outside acceptable margin between " +build.uuid+ " and " + old_build.uuid + " : difference of " + str(diff*100) + "% !")
                    returncode += 1
                elif not testie.quiet:
                    print("Acceptable difference of %.2f%% for %s" % ((diff*100),run.format_variables()))
            elif old_build:
                print("No old values for this test for uuid %s." % (old_build.uuid))
                old_all_results[run] = [0]

#Finished regression comparison
        if all_results:
            if prev_results:
                prev_results.update(all_results)
                build.writeUuid(testie,prev_results)
            else:
                build.writeUuid(testie,all_results)

        return returncode,all_results,old_all_results