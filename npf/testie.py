import multiprocessing
import os
import sys
import time
from multiprocessing import Event
from pathlib import Path
from queue import Empty, Queue
from typing import Tuple, Dict

import numpy as np

from npf import npf
from npf.build import Build
from npf.node import Node, NIC
from npf.section import *
from npf.types.dataset import Run, Dataset


def _parallel_exec(exec_args : Tuple['Testie',SectionScript,str,'Build',Queue,Event,str]):
    (testie, scriptSection, commands, build, queue, terminated_event, deps_bin_path) = exec_args

    time.sleep(scriptSection.delay())
    pid, o, e, c = npf.executor(scriptSection.get_role()).exec(cmd=commands,
                                                                stdin=testie.stdin.content,
                                                                timeout=testie.config["timeout"],
                                                                bin_paths=deps_bin_path + [build.get_bin_folder()],
                                                                queue=queue,
                                                                options=testie.options,
                                                                terminated_event=terminated_event,
                                                                sudo=scriptSection.params.get("sudo",False))
    if pid == 0:
        return False, o, e, commands
    else:
        # By default, we kill all other scripts when the first finishes
        if testie.config["autokill"] or pid == -1:
            Testie.killall(queue, terminated_event)
        if pid == -1:
            return -1, o, e, commands
        return True, o, e, commands


class Testie:
    def get_name(self):
        return self.filename

    def get_scripts(self) -> List[SectionScript]:
        return self.scripts

    def __init__(self, testie_path, options, tags=None, role=None):
        if os.path.exists(npf.find_local(testie_path)):
            testie_path = npf.find_local(testie_path)
        else:
            if not os.path.exists(npf.find_local(testie_path + '.testie')):
                raise Exception("Could not find testie %s" % testie_path)
            testie_path = npf.find_local(testie_path + '.testie')

        self.sections = []
        self.files = []
        self.scripts = []
        self.imports = []
        self.requirements = []
        self.filename = os.path.basename(testie_path)
        self.options = options
        self.tags = tags if tags else []
        self.role = role

        section = None

        f = open(testie_path, 'r')

        for i, line in enumerate(f):
            line = re.sub(r'(^|[ ])//.*$','',line)
            if line.startswith('#') and section is None:
                print("Warning : comments now use // instead of #. This will be soon deprecated")
                continue
            if line.strip() == '' and not section:
                continue

            if line.startswith("%"):
                result = line[1:]
                section = SectionFactory.build(self, result.strip())

                if not section is SectionNull:
                    self.sections.append(section)
            elif section is None:
                raise Exception("Bad syntax, file must start by a section. Line %d :\n%s" % (i, line))
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

        if not hasattr(self, "config"):
            self.config = SectionConfig()
            self.sections.append(self.config)

        for section in self.sections:
            section.finish(self)

        #Check that all reference roles are defined
        known_roles= {'self', 'default'}.union(set(npf.roles.keys()))
        for script in self.get_scripts():
            known_roles.add(script.get_role())
        for file in self.files:
            for nicref in re.finditer(Node.NICREF_REGEX, file.content, re.IGNORECASE):
                if nicref.group('role') not in known_roles:
                    raise Exception("Unknown role %s" % nicref.group('role'))

        #Create imports testies
        for imp in self.imports:
            imp.testie = Testie(imp.module,options, tags, imp.get_role())
            if len(imp.testie.variables.dynamics()) > 0:
                raise Exception("Imports cannot have dynamic variables. Their parents decides what's dynamic.")
            if 'delay' in imp.params:
                for script in imp.testie.scripts:
                    delay = script.params.setdefault('delay',0)
                    script.params['delay'] = delay + float(imp.params['delay'])
                del imp.params['delay']
            overriden_variables={}
            for k,v in imp.params.items():
                overriden_variables[k] = VariableFactory.build(k, v)
            imp.testie.variables.override_all(overriden_variables)
            for script in imp.testie.scripts:
                if script.get_role():
                    raise Exception('Modules cannot have roles, their importer defines it')
                script._role = imp.get_role()

    def build_deps(self, repo_under_test : List[Repository]):
        # Check for dependencies
        deps = set()
        for script in self.get_scripts():
            deps = deps.union(script.get_deps())
        for dep in deps:
            if dep in repo_under_test:
                continue
            deprepo = Repository.get_instance(dep, self.options)
            if not deprepo.get_last_build().build():
                raise Exception("Could not build dependency %s" + dep)
        for imp in self.imports:
            imp.testie.build_deps(repo_under_test)
        return True

    def test_tags(self):
        missings = []
        #        print("%s requires " % self.get_name(), self.config.get_list("require_tags"))
        for tag in self.config.get_list("require_tags"):
            if not tag in self.tags:
                missings.append(tag)
        return missings

    def create_files(self, v, selfRole=None):
        for s in self.files:
            f = open(s.filename, "w")
            p = SectionVariable.replace_variables(v, s.content, selfRole)
            if self.options.show_files:
                print("File %s:" % s.filename)
                print(p.strip())
            f.write(p)
            f.close()

    def test_require(self, v, build):
        for require in self.requirements:
            p = SectionVariable.replace_variables(v, require.content, require.role())
            pid, output, err, returncode = npf.executor(require.role()).exec(cmd=p, bin_paths=[build.get_bin_folder()], options=self.options, terminated_event=None)
            if returncode != 0:
                if not self.options.quiet:
                    print("Requirement not met")
                    if output.strip():
                        print(output.strip())
                    if err.strip():
                        print(err.strip())
                return False
            continue
        return True

    def cleanup(self):
        for s in self.files:
            path = Path(s.filename)
            if path.is_file():
                path.unlink()

    @staticmethod
    def killall(queue, terminated_event):
        terminated_event.set()
        while not queue.empty():
            try:
                killer = queue.get(block=False)
            except Empty:
                continue
            try:
                killer.kill()
            except OSError:
                pass
            time.sleep(1)
            try:
                killer.force_kill()
            except OSError:
                pass

    def execute(self, build, run, v, n_runs=1, n_retry=0, allowed_types=None) -> Tuple[Dict[str,List],str,str]:
        if allowed_types is None:
            allowed_types = {"init", "script"}

        #Get address definition for roles from scripts
        self.parse_script_roles()
        self.create_files(v, self.role)

        for imp in self.imports:
            imp.testie.parse_script_roles()
            imp_v = {}
            for k, val in imp.testie.variables.statics().items():
                imp_v[k] = val.makeValues()[0]
            imp_v.update(v)
            imp.testie.create_files(imp_v, imp.get_role())

        results = {}
        for i in range(n_runs):
            for i_try in range(n_retry + 1):
                if i_try > 0 and not self.options.quiet:
                    print("Re-try tests %d/%d...",i_try,n_retry + 1)
                output = ''
                err = ''

                m = multiprocessing.Manager()
                queue = m.Queue()
                terminated_event = m.Event()

                import_scripts = []
                for imp in self.imports:
                    import_scripts += [(imp.testie, script, SectionVariable.replace_variables(v, script.content, imp.get_role()),
                                        build, queue, terminated_event,
                                        [repo.get_bin_folder() for repo in script.get_deps_repos(self.options)])
                                       for script in imp.testie.scripts if script.get_type() in allowed_types]

                testie_scripts = [(self, script, SectionVariable.replace_variables(v, script.content, script.get_role()), build, queue,
                                   terminated_event, [repo.get_bin_folder() for repo in script.get_deps_repos(self.options)])
                                            for script in self.scripts if script.get_type() in allowed_types]
                scripts = import_scripts + testie_scripts

                n = len(scripts)
                p = multiprocessing.Pool(n)

                try:
                    parallel_execs = p.map(_parallel_exec,
                                           scripts)
                except KeyboardInterrupt:
                    p.close()
                    p.terminate()
                    sys.exit(1)
                p.close()
                p.terminate()
                worked = False
                for iscript, (r, o, e, script) in enumerate(parallel_execs):
                    if r == 0:
                        print("Timeout expired...")
                        if self.options.show_full:
                            print("stdout:")
                            print(o)
                            print("stderr:")
                            print(e)
                        continue
                    if r == -1:
                        sys.exit(1)

                for iparallel, (r, o, e, script) in enumerate(parallel_execs):
                    if len(self.scripts) > 1:
                        output += "Output of script %d :\n" % (i)
                        err += "Output of script %d :\n" % (i)

                    if r:
                        worked = True
                        output += o
                        err += e
                if not worked:
                    continue

                if not self.config["result_regex"]:
                    break

                has_values = False
                for result_regex in self.config.get_list("result_regex"):
                    for nr in re.finditer(result_regex, output.strip(), re.IGNORECASE):
                        type = nr.group("type")
                        if type is None:
                            type = ''
                        n = float(nr.group("value"))
                        mult = nr.group("multiplier").lower()
                        if mult == "k":
                            n *= 1024
                        elif mult == "m":
                            n *= 1024 * 1024
                        elif mult == "g":
                            n *= 1024 * 1024 * 1024

                        if not (n == 0 and self.config["zero_is_error"]):
                            results.setdefault(type,[]).append(n)
                            has_values = True
                        else:
                            print("Result for %s is 0 !" % (type))
                            print("stdout:")
                            print(output)
                            print("stderr:")
                            print(err)
                if has_values:
                    break

                if len(results) == 0:
                    print("Could not find results !")
                    print("stdout:")
                    print(output)
                    print("stderr:")
                    print(err)
                    continue

        for imp in self.imports:
            imp.testie.cleanup()
        self.cleanup()
        return results, output, err

    def has_all(self, prev_results, build):
        if prev_results is None:
            return None
        all_results = {}
        for variables in self.variables:
            run = Run(variables)
            if not self.test_require(variables, build):
                continue

            if run in prev_results:
                results = prev_results[run]
                if not results or results is None or (len(results) < self.config["n_runs"]):
                    return None
                all_results[run] = results
            else:
                return None
        return all_results

    def execute_all(self, build, options, prev_results: Dataset = None, do_test=True, allowed_types = None) -> Dataset:
        """Execute script for all variables combinations. All tools reliy on this function for execution of the testie
        :param do_test: Actually run the tests
        :param options: NPF options object
        :param build: A build object
        :param prev_results: Previous set of result for the same build to update or retrieve
        :return: Dataset(Dict of variables as key and arrays of results as value)
        """

        if do_test:
            if not build.build(options.force_build, options.no_build, options.quiet_build, options.show_build_cmd):
                return None

            if not self.build_deps([build.repo]):
                return None

            if allowed_types is None or "init" in allowed_types:
                if len(self.imports) > 0:
                    msg_shown = options.quiet
                    for imp in self.imports:
                        if len([script for script in imp.testie.scripts if script.get_type() == "init"]) == 0:
                            continue
                        if not msg_shown:
                            print("Executing imports init scripts...")
                            msg_shown=True
                        imp_res = imp.testie.execute_all(build, options=options, do_test=do_test, allowed_types={"init"})
                        for k,v in imp_res.items():
                            if v == None:
                                if not options.quiet:
                                    print("Aborting as imports did not run correctly");
                                return None
                    if msg_shown:
                        print("All imports passed successfully...")

                # init_scripts =[script for script in self.scripts if script.get_type() == "init"]
                # if len(init_scripts) > 0:
                #     if not options.quiet:
                #         print("Executing init scripts...")
                #     nresults, output, err = self.execute(build, options=options, do_test=do_test, allowed_types={"init"})
                #     if nresults == 0:
                #         if not options.quiet:
                #             print("Aborting as imports did not run correctly");
                #         return None

        all_results = {}
        for variables in self.variables:
            run = Run(variables)
            if hasattr(self,'late_variables'):
                variables = self.late_variables.execute(variables,self)
            if not self.options.quiet:
                print(run.format_variables(self.config["var_hide"]))
            if not self.test_require(variables, build):
                continue
            if prev_results and prev_results is not None and not options.force_test:
                run_results = prev_results.get(run, {})
                if run_results is None:
                    run_results = {}
            else:
                run_results = {}

            have_new_results = False
            n_runs = self.config["n_runs"] - (0 if options.force_test or len(run_results) == 0 else min([len(results) for result_type,results in run_results.items()]))
            if n_runs > 0 and do_test:
                new_results, output, err = self.execute(build, run, variables, n_runs, self.config["n_retry"], allowed_types={"script"})
                if new_results:
                    if self.options.show_full:
                        print("stdout:")
                        print(output)
                        print("stderr:")
                        print(err)
                    for k,v in new_results.items():
                        run_results.setdefault(k,[]).extend(v)
                        have_new_results = True

            if len(run_results) > 0:
                if not self.options.quiet:
                    print(run_results)
                all_results[run] = run_results
            else:
                all_results[run] = {}

            # Save results
            if all_results and have_new_results:
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

    def parse_script_roles(self):
        for script in self.scripts:
            for k,val in script.params.items():
                nic_match = re.match(r'(?P<nic_idx>[0-9]+)[:](?P<type>' + NIC.TYPES + '+)',k, re.IGNORECASE)
                if nic_match:
                    npf.node(script.get_role()).nics[int(nic_match.group('nic_idx'))][nic_match.group('type')] = val
