from subprocess import Popen, PIPE
from subprocess import TimeoutExpired
import os
import sys
import numpy as np
import signal
import random
import multiprocessing
from typing import Dict, List, Set
from pathlib import Path

from multiprocessing import Queue

from src.section import *


class Run:
    def __init__(self, variables):
        self.variables = variables

    def format_variables(self, hide={}):
        s = []
        for k, v in self.variables.items():
            if k in hide: continue
            if type(v) is tuple:
                s.append('%s = %s' % (k, v[1]))
            else:
                s.append('%s = %s' % (k, v))
        return ', '.join(s)

    def print_variable(self, k):
        v = self.variables[k]
        if type(v) is tuple:
            return v[1]
        else:
            return v

    def copy(self):
        newrun = Run(self.variables.copy())
        return newrun

    def inside(self, o):
        for k, v in self.variables.items():
            if not k in o.variables:
                return False
            ov = o.variables[k]
            if type(v) is tuple:
                v = v[1]
            if type(ov) is tuple:
                ov = ov[1]
            if is_numeric(v) and is_numeric(ov):
                if not get_numeric(v) == get_numeric(ov):
                    return False
            else:
                if not v == ov:
                    return False
        return True

    def intersect(self, common):
        difs = set.difference(set(self.variables.keys()), common)
        for dif in difs:
            del self.variables[dif]
        return self

    def __eq__(self, o):
        return self.inside(o) and o.inside(self)

    def __hash__(self):
        n = 0
        for k, v in self.variables.items():
            if type(v) is tuple:
                v = v[1]
            n += str(v).__hash__()
            n += k.__hash__()
        return n

    def __repr__(self):
        return "Run(" + self.format_variables() + ")"

    def __cmp__(self, o):
        for k, v in self.variables.items():
            if not k in o.variables: return 1
            ov = o.variables[k]
            if type(v) is str or type(ov) is str:
                if str(v) < str(ov):
                    return -1
                if str(v) > str(ov):
                    return 1
            else:
                if v < ov:
                    return -1
                if v > ov:
                    return 1
        return 0

    def __lt__(self, o):
        return self.__cmp__(o) < 0


Dataset = Dict[Run, List]


def _parallel_exec(args):
    (testie, script, commands, n_retry, build, queue) = args

    pid, o, e, c = testie._exec(testie, commands, build, queue)
    if pid == 0:
        return False, "Timeout expired" + o, e, script
    else:
        if testie.config["autokill"] or pid == -1:
            Testie.killall(queue)
        if pid == -1:
            return -1, o, e, script
        return True, o, e, script


class Testie:
    @staticmethod
    def _addr_gen():
        mac = [0xAE, 0xAA, 0xAA,
               random.randint(0x01, 0x7f),
               random.randint(0x01, 0xff),
               random.randint(0x01, 0xfe)]
        macaddr = ':'.join(map(lambda x: "%02x" % x, mac))
        ip = [10, mac[3], mac[4], mac[5]]
        ipaddr = '.'.join(map(lambda x: "%d" % x, ip))
        return macaddr, ipaddr

    def get_name(self):
        return self.filename

    def __init__(self, testie_path, options, tags=None):
        self.sections = []
        self.files = []
        self.scripts = []
        self.filename = os.path.basename(testie_path)
        self.options = options
        self.tags = tags if tags else []
        self.network = {}

        for i in range(32):
            mac, ip = Testie._addr_gen()
            self.network['MAC%d' % i] = mac
            self.network['RAW_MAC%d' % i] = ''.join(mac.split(':'))
            self.network['IP%d' % i] = ip
        section = ''

        f = open(testie_path, 'r')
        for i, line in enumerate(f):
            if line.startswith("#"):
                continue
            elif line.startswith("%"):
                result = line[1:].split(' ')
                section = SectionFactory.build(self, result)
                if not section is SectionNull:
                    self.sections.append(section)
            elif not section:
                raise Exception("Bad syntax, file must start by a section. Line %d :\n%s" % (i, line));
            else:
                section.content += line
        f.close()

        if not hasattr(self, "info"):
            self.info = Section("info")
            self.info.content = self.filename
            self.sections.append(self.info)

        if not hasattr(self, "stdin"):
            self.stdin = Section("stdin")
            self.sections.append(self.stdin)

        if not hasattr(self, "variables"):
            self.variables = SectionVariable()
            self.sections.append(self.variables)

        if not hasattr(self, "require"):
            self.require = SectionRequire()
            self.sections.append(self.require)

        if not hasattr(self, "config"):
            print("no config")
            self.config = SectionConfig()
            self.sections.append(self.config)

        for section in self.sections:
            section.finish(self)

    def test_tags(self):
        missings = []
        print("%s requires " % self.get_name(), self.config.get_list("require_tags"))
        for tag in self.config.get_list("require_tags"):
            if not tag in self.tags:
                missings.append(tag)
        return missings

    def _replace_all(self, v, content):
        p = content
        for d in [v, self.network]:
            for k, v in d.items():
                if type(v) is tuple:
                    p = p.replace("$" + k, str(v[0]))
                else:
                    p = p.replace("$" + k, str(v))
        return p

    def create_files(self, v):
        for s in self.files:
            f = open(s.filename, "w")
            p = self._replace_all(v, s.content)
            f.write(p)
            f.close()

    def test_require(self, v, build):
        if self.require.content:
            p = self._replace_all(v, self.require.content)
            pid, output, err, returncode = self._exec(self, p, build)
            if returncode != 0:
                if not self.options.quiet:
                    print("Requirement not met :")
                    print(output)
                    print(err)
                return False
            return True
        return True

    def cleanup(self):
        for s in self.files:
            path = Path(s.filename)
            if path.is_file():
                path.unlink()

    @staticmethod
    def _exec(testie, cmd, build, queue: Queue = None):
        env = os.environ.copy()
        env["PATH"] = build.get_bin_folder() + ":" + env["PATH"]
        if testie.options.show_cmd:
            print("Executing (PATH=%s) :\n%s" % (env['PATH'], cmd))

        p = Popen(cmd,
                  stdin=PIPE, stdout=PIPE, stderr=PIPE,
                  shell=True, preexec_fn=os.setsid,
                  env=env)
        pid = p.pid
        pgpid = os.getpgid(pid)
        if queue:
            queue.put(pgpid)
        try:
            s_output, s_err = [x.decode() for x in
                               p.communicate(testie.stdin.content, timeout=testie.config["timeout"])]
            p.stdin.close()
            p.stderr.close()
            p.stdout.close()
            return pid, s_output, s_err, p.returncode
        except TimeoutExpired:
            print("Test expired")
            p.terminate()
            p.kill()
            os.killpg(pgpid, signal.SIGKILL)
            os.killpg(pgpid, signal.SIGTERM)
            s_output, s_err = [x.decode() for x in p.communicate()]
            print(s_output)
            print(s_err)
            p.stdin.close()
            p.stderr.close()
            p.stdout.close()
            return 0, s_output, s_err, p.returncode
        except KeyboardInterrupt:
            os.killpg(pgpid, signal.SIGKILL)
            return -1, s_output, s_err, p.returncode

    @staticmethod
    def killall(queue):
        while not queue.empty():
            pid = queue.get()
            try:
                os.killpg(pid, signal.SIGKILL)
            except OSError:
                pass

    def execute(self, build, v, n_runs=1, n_retry=0):
        self.create_files(v)
        results = []
        for i in range(n_runs):
            for i_try in range(n_retry + 1):
                output = ''
                err = ''
                n = len(self.scripts)
                p = multiprocessing.Pool(n)
                m = multiprocessing.Manager()
                queue = m.Queue()

                try:
                    parallel_execs = p.map(_parallel_exec,
                                           [(self, script, self._replace_all(v, script.content), n_retry, build, queue)
                                            for script in self.scripts])
                except KeyboardInterrupt:
                    p.close()
                    p.terminate()
                    sys.exit(1)
                p.close()
                p.terminate()
                worked = False
                for i, (r, o, e, script) in enumerate(parallel_execs):
                    if r == 0:
                        continue
                    if r == -1:
                        sys.exit(1)

                for i, (r, o, e, script) in enumerate(parallel_execs):
                    if len(self.scripts) > 1:
                        output += "Output of script %d for %s :\n" % (i, script.slave)
                        err += "Output of script %d for %s :\n" % (i, script.slave)

                    if r:
                        worked = True
                        output += o
                        err += e
                if not worked:
                   continue

                nr = re.search("RESULT[ \t]+([0-9.]+)[ ]*([gmk]?)(b|byte|bits)?", output.strip(), re.IGNORECASE)
                if nr:
                    n = float(nr.group(1))
                    mult = nr.group(2).lower()
                    if mult == "k":
                        n *= 1024
                    elif mult == "m":
                        n *= 1024 * 1024
                    elif mult == "g":
                        n *= 1024 * 1024 * 1024

                    if not (n == 0 and self.config["zero_is_error"]):
                        results.append(n)
                        break
                    else:
                        print("Result is 0 !")
                        print("stdout:")
                        print(output)
                        print("stderr:")
                        print(err)
                        continue

                else:
                    print("Could not find result !")
                    print("stdout:")
                    print(output)
                    print("stderr:")
                    print(err)
                    continue

        self.cleanup()
        return results, output, err

    def has_all(self, prev_results, build):
        if prev_results is None:
            return False
        for variables in self.variables:
            if not self.test_require(variables, build):
                continue

            run = Run(variables)

            if prev_results and run in prev_results:
                results = prev_results[run]
                if not results or results is None or (len(results) < self.config["n_runs"]):
                    return False
            else:
                return False
        return True

    def execute_all(self, build, options, prev_results: Dataset = None, do_test=True) -> Dataset:
        """Execute script for all variables combinations
        :param build: A build object
        :param prev_results: Previous set of result for the same build to update or retrieve
        :return: Dataset(Dict of variables as key and arrays of results as value)
        """
        all_results = {}
        for variables in self.variables:
            run = Run(variables)
            if not self.options.quiet:
                print(run.format_variables(self.config["var_hide"]))
            if not self.test_require(variables, build):
                continue
            if prev_results and not options.force_test:
                results = prev_results.get(run, [])
                if results is None:
                    results = []
            else:
                results = []

            new_results = False
            n_runs = self.config["n_runs"] - (0 if options.force_test else len(results))
            if n_runs > 0 and do_test:
                nresults, output, err = self.execute(build, variables, n_runs, self.config["n_retry"])
                if nresults:
                    if self.options.show_full:
                        print("stdout:")
                        print(output)
                        print("stderr:")
                        print(err)
                    results += nresults
                    new_results = True
            if results:
                if not self.options.quiet:
                    print(results)
                all_results[run] = results
            else:
                all_results[run] = None

            # Save results
            if all_results and new_results:
                if prev_results:
                    prev_results[run] = all_results[run]
                    build.writeversion(self, prev_results)
                else:
                    build.writeversion(self, all_results)

        return all_results

    def get_title(self):
        if "title" in self.config:
            title = self.config["title"]
        elif hasattr(self, "info"):
            title = self.info.content.strip().split('\n', 1)[0]
        else:
            title = self.filename
        return title

    def reject_outliers(self, data):
        m = self.config["accept_outliers_mult"]
        mean = np.mean(data)
        std = np.std(data)
        data = data[abs(data - mean) <= m * std]
        return data

    def expand_folder(testie_path, options, tags=None) -> List:
        testies = []
        if not os.path.exists(testie_path):
            print("The testie path %s does not exist" % testie_path)
            return testies
        if os.path.isfile(testie_path):
            testie = Testie(testie_path, options=options, tags=tags)
            testies.append(testie)
        else:
            for root, dirs, files in os.walk(testie_path):
                for file in files:
                    if file.endswith(".testie"):
                        testie = Testie(os.path.join(root, file), options=options, tags=tags)
                        testies.append(testie)

        for testie in testies:
            missing_tags = testie.test_tags()
            if len(missing_tags) > 0:
                testies.remove(testie)
                if not options.quiet:
                    print(
                        "Passing testie %s as it lacks tags %s" % (testie.filename, ','.join(missing_tags)))
                continue

        return testies
