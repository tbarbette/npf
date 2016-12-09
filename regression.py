import argparse
import os
import math
import numpy as np

from src.variable import *
from src.script import *
from src.repository import *
from src.build import *
from src.grapher import *

class Regression:
    def __init__(self, script):
        self.script = script

    def reject_outliers(self, data):
        m = self.script.config["accept_outliers_mult"]
        mean = np.mean(data)
        std = np.std(data)
        data = data[abs(data - mean) <= m * std]
        return data

    def accept_diff(self, result, old_result):
        result = np.asarray(result)
        old_result = np.asarray(old_result)
        n = self.reject_outliers(result).mean()
        old_n = self.reject_outliers(old_result).mean()
        diff=abs(old_n - n) / old_n
        accept =  self.script.config["acceptable"]
        accept += abs(result.std() * self.script.config["accept_variance"] / n)
        return diff <= accept, diff

    def run(self, build, old_build = None, force_test=False):
        script = self.script
        returncode=0
        old_all_results=None
        if old_build:
            old_all_results = old_build.readUuid(script)

        if force_test:
            prev_results = None
        else:
            prev_results = build.readUuid(script)
        all_results = script.execute_all(build,prev_results)
        for run,result in all_results.items():
            v = run.variables
            #TODO : some config could implement acceptable range no matter the old value

            if old_all_results and run in old_all_results:
                old_result=old_all_results[run]
                ok,diff = self.accept_diff(result, old_result)
                if not ok and script.config["unacceptable_n_runs"] > 0:
                        if not script.quiet:
                            print("Difference of %.2f%% is outside acceptable range for %s. Running supplementary tests..." % (diff*100, run.format_variables()))
                        for i in range(script.config["unacceptable_n_runs"]):
                            n,output,err = script.execute(build, v)
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
                    print("ERROR: Test " + script.filename + " is outside acceptable margin between " +build.uuid+ " and " + old_build.uuid + " : difference of " + str(diff*100) + "% !")
                    returncode += 1
                else:
                    print("Acceptable difference of %.2f%%" % (diff*100))
            elif old_build:
                print("No old values for this test for uuid %s." % (old_build.uuid))

        build.writeUuid(script,all_results)
        if "title" in self.script.config:
            title = self.script.config["title"]
        elif hasattr(self.script,"info"):
            title = script.info.content.strip().split('\n', 1)[0]
        else:
            title = self.script.filename
        grapher = Grapher()
        graphname = build.repo.reponame + '/results/' + build.uuid + '/'+ os.path.splitext(self.script.filename)[0] + '.png'

        series = [(script,build,all_results)]
        if (old_build):
            series.append((script,old_build,old_all_results))
        grapher.graph(series=series,title=title,filename=graphname)
        return returncode


def main():
    parser = argparse.ArgumentParser(description='Click Performance Executor')
    parser.add_argument('--show-full', help='Show full execution results', dest='show_full', action='store_true')

    parser.add_argument('--quiet', help='Quiet mode', dest='quiet', action='store_true')
    parser.add_argument('--force-test', help='Force re-doing all tests even if data for the given uuid and variables is already known', dest='force_test', action='store_true')
    parser.add_argument('--tags', metavar='tag', type=str, nargs='+', help='list of tags');
    parser.add_argument('script', metavar='script path', type=str, nargs=1, help='path to script');
    parser.add_argument('repo', metavar='repo name', type=str, nargs=1, help='name of the repo/group of builds');
    parser.add_argument('uuid', metavar='uuid', type=str, nargs=1, help='build id');
    parser.add_argument('old_uuid', metavar='old_uuid', type=str, nargs='?', help='old build id to compare against');
    parser.set_defaults(show_full=False)
    parser.set_defaults(quiet=False)
    parser.set_defaults(force_test=False)
    parser.set_defaults(tags=[])
    args = parser.parse_args();

    repo=Repository(args.repo[0])
    tags = args.tags
    tags += repo.tags
    uuid=args.uuid[0]
    clickpath=repo.reponame+"/build"

    build = Build(repo, uuid)
    if args.old_uuid and len(args.old_uuid):
        old_uuid=args.old_uuid
        old_build=Build(repo,old_uuid)
    else:
        old_build=None

    script = Script(args.script[0],clickpath,quiet=args.quiet,tags=tags,show_full=args.show_full)

    regression = Regression(script)

    print(script.info.content.strip())

    returncode = regression.run(build, old_build, force_test=args.force_test);
    sys.exit(returncode)


if __name__ == "__main__":
    main()
