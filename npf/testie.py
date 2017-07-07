import multiprocessing
import os
import sys
import time
from pathlib import Path
from queue import Empty
from typing import Tuple, Dict

import numpy as np

from npf.build import Build
from npf.node import NIC
from npf.section import *
from npf.types.dataset import Run, Dataset


class RemoteParameters:
    def __init__(self):
        self.default_role_map = None
        self.role = None
        self.delay = None
        self.executor = None
        self.bin_paths = None
        self.queue = None
        self.terminated_event = None
        self.sudo = None
        self.autokill = None
        self.queue = None
        self.terminated_event = None
        self.timeout = None
        self.options = None
        self.stdin = None
        self.commands = None

    pass


def _parallel_exec(param: RemoteParameters):
    executor = npf.executor(param.role, param.default_role_map)
    time.sleep(param.delay)
    pid, o, e, c = executor.exec(cmd=param.commands,
                                 stdin=param.stdin,
                                 timeout=param.timeout,
                                 bin_paths=param.bin_paths,
                                 queue=param.queue,
                                 options=param.options,
                                 terminated_event=param.terminated_event,
                                 sudo=param.sudo)
    if pid == 0:
        return False, o, e, param.commands
    else:
        if param.autokill or pid == -1:
            Testie.killall(param.queue, param.terminated_event)
        if pid == -1:
            return -1, o, e, param.commands
        return True, o, e, param.commands


class ScriptInitException(Exception):
    pass


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

        try:
            section = None
            f = open(testie_path, 'r')

            for i, line in enumerate(f):
                line = re.sub(r'(^|[ ])//.*$', '', line)
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
        except Exception as e:
            raise Exception("An exception occured while parsing %s :\n%s" % (testie_path, e.__str__()))

        # Check that all reference roles are defined
        known_roles = {'self', 'default'}.union(set(npf.roles.keys()))
        for script in self.get_scripts():
            known_roles.add(script.get_role())
        # for file in self.files:
        #            for nicref in re.finditer(Node.NICREF_REGEX, file.content, re.IGNORECASE):
        #                if nicref.group('role') not in known_roles:
        #                    raise Exception("Unknown role %s" % nicref.group('role'))

        # Create imports testies
        for imp in self.imports:
            from npf.module import Module
            imp.testie = Module(imp.module, options, tags, imp.get_role())
            if len(imp.testie.variables.dynamics()) > 0:
                raise Exception("Imports cannot have dynamic variables. Their parents decides what's dynamic.")
            if 'delay' in imp.params:
                for script in imp.testie.scripts:
                    delay = script.params.setdefault('delay', 0)
                    script.params['delay'] = float(delay) + float(imp.params['delay'])
                del imp.params['delay']
            overriden_variables = {}
            for k, v in imp.params.items():
                overriden_variables[k] = VariableFactory.build(k, v)
            imp.testie.variables.override_all(overriden_variables)
            for script in imp.testie.scripts:
                if script.get_role():
                    raise Exception('Modules cannot have roles, their importer defines it')
                script._role = imp.get_role()

        for excludes in self.config.get_list("role_exclude"):
            s = excludes.split('+')
            m = set()
            for role in s:
                node = npf.node(role)
                if node in m:
                    raise Exception(
                        "Roles %s cannot be on the same node ! Please use --cluster argument to set them accross nodes" % ' and '.join(
                            s))
                m.add(node)

    def build_deps(self, repo_under_test: List[Repository]):
        # Check for dependencies
        deps = set()
        for script in self.get_scripts():
            deps = deps.union(script.get_deps())
        for dep in deps:
            if dep in repo_under_test:
                continue
            deprepo = Repository.get_instance(dep, self.options)
            if deprepo.url is None or deprepo.reponame in self.options.no_build_deps:
                continue
            if not deprepo.get_last_build().build(force_build=deprepo.reponame in self.options.force_build_deps):
                raise Exception("Could not build dependency %s" % dep)
        for imp in self.imports:
            imp.testie.build_deps(repo_under_test)
        return True

    def test_tags(self):
        missings = []
        # print("%s requires " % self.get_name(), self.config.get_list("require_tags"))
        for tag in self.config.get_list("require_tags"):
            if not tag in self.tags:
                missings.append(tag)
        return missings

    def create_files(self, v, self_role=None):
        for s in self.files:
            role = s.get_role() if s.get_role() else self_role

            p = SectionVariable.replace_variables(v, s.content, role, self.config.get_dict("default_role_map"))
            if self.options.show_files:
                print("File %s:" % s.filename)
                print(p.strip())
            for node in npf.nodes(role):
                node.executor.writeFile(s.filename, p)

    def test_require(self, v, build):
        for require in self.requirements:
            p = SectionVariable.replace_variables(v, require.content, require.role(),
                                                  self.config.get_dict("default_role_map"))
            pid, output, err, returncode = npf.executor(require.role(), self.config.get_dict("default_role_map")).exec(
                cmd=p, bin_paths=[build.get_bin_folder()], options=self.options, terminated_event=None)
            if returncode != 0:
                return False, output, err
            continue
        return True, '', ''

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

            i = 0
            while killer.is_alive() and i < 100:
                time.sleep(0.010)
                i += 1
            try:
                killer.force_kill()
            except OSError:
                pass

    def execute(self, build, run, v, n_runs=1, n_retry=0, allowed_types=SectionScript.ALL_TYPES_SET) -> Tuple[
        Dict[str, List], str, str]:
        # Get address definition for roles from scripts
        self.parse_script_roles()
        self.create_files(v, self.role)

        for imp in self.imports:
            imp.testie.parse_script_roles()
            imp.imp_v = {}
            for k, val in imp.testie.variables.statics().items():
                imp.imp_v[k] = val.makeValues()[0]

            imp.imp_v.update(v)
            if hasattr(imp.testie, 'late_variables'):
                imp.imp_v = imp.testie.late_variables.execute(imp.imp_v, imp.testie)
            imp.testie.create_files(imp.imp_v, imp.get_role())

        results = {}
        m = multiprocessing.Manager()
        for i in range(n_runs):
            for i_try in range(n_retry + 1):
                if i_try > 0 and not self.options.quiet:
                    print("Re-try tests %d/%d..." % (i_try, n_retry + 1))
                output = ''
                err = ''

                queue = m.Queue()
                terminated_event = m.Event()

                remote_params = []
                for t, v, role in [(imp.testie, imp.imp_v, imp.get_role()) for imp in self.imports] + [(self, v, None)]:
                    for script in t.scripts:
                        if not script.get_type() in allowed_types:
                            continue
                        param = RemoteParameters()
                        param.commands = SectionVariable.replace_variables(v, script.content,
                                                                           role if role else script.get_role(),
                                                                           self.config.get_dict(
                                                                               "default_role_map"))
                        param.terminated_event = terminated_event
                        param.options = self.options
                        param.queue = queue
                        param.stdin = t.stdin.content
                        param.timeout = t.config['timeout']
                        param.role = script.get_role()
                        param.default_role_map = self.config.get_dict("default_role_map")
                        param.delay = script.delay()
                        deps_bin_path = [repo.get_bin_folder() for repo in script.get_deps_repos(self.options)]
                        param.bin_paths = deps_bin_path + [build.get_bin_folder()]
                        param.sudo = script.params.get("sudo", False)
                        autokill = script.params.get("autokill", t.config["autokill"])
                        if type(autokill) is str and autokill.lower() == "false":
                            autokill = False
                        else:
                            autokill = bool(autokill)
                        param.autokill = autokill

                        remote_params.append(param)

                n = len(remote_params)
                if n == 0:
                    return {}, None, None

                try:
                    if self.options.allow_mp:
                        p = multiprocessing.Pool(n)
                        parallel_execs = p.map(_parallel_exec,
                                               remote_params)
                    else:
                        parallel_execs = []
                        for remoteParam in remote_params:
                            parallel_execs.append(_parallel_exec(remoteParam))

                except KeyboardInterrupt:
                    if self.options.allow_mp:
                        p.close()
                        p.terminate()
                    sys.exit(1)
                if self.options.allow_mp:
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
                        output += "Output of script %d :\n" % i
                        err += "Output of script %d :\n" % i

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
                        result_type = nr.group("type")
                        if result_type is None:
                            result_type = ''
                        n = float(nr.group("value"))
                        mult = nr.group("multiplier").lower()
                        if mult == "k":
                            n *= 1024
                        elif mult == "m":
                            n *= 1024 * 1024
                        elif mult == "g":
                            n *= 1024 * 1024 * 1024

                        if n != 0 or (result_type in self.config["accept_zero"]):
                            results.setdefault(result_type, []).append(n)
                            has_values = True
                        else:
                            print("Result for %s is 0 !" % result_type)
                            print("stdout:")
                            print(output)
                            print("stderr:")
                            print(err)
                if has_values:
                    break

                for result_type in self.config['results_expect']:
                    if result_type not in results:
                        print("Could not find expected result '%s' !" % result_type)
                        print("stdout:")
                        print(output)
                        print("stderr:")
                        print(err)

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

    #    def has_all(self, prev_results, build):
    #        if prev_results is None:
    #            return None
    #        all_results = {}
    #        for variables in self.variables:
    #            run = Run(variables)
    #            if not self.test_require(variables, build):
    #                continue
    #
    #            if run in prev_results:
    #                results = prev_results[run]
    #                if not results:
    #                    return None
    #                for result_type,data in results.items():
    #                    if not data or data is None or (len(data) < self.config["n_runs"]):
    #                        return None
    #                all_results[run] = results
    #            else:
    #                return None
    #        return all_results

    def do_init_all(self, build, options, do_test, allowed_types=SectionScript.ALL_TYPES_SET):
        if not build.build(options.force_build, options.no_build, options.quiet_build, options.show_build_cmd):
            raise ScriptInitException()

        if not self.build_deps([build.repo]):
            raise ScriptInitException()

        if (allowed_types is None or "init" in allowed_types) and options.do_init:
            if len(self.imports) > 0:
                msg_shown = options.quiet
                for imp in self.imports:
                    if len([script for script in imp.testie.scripts if script.get_type() == "init"]) == 0:
                        continue
                    if not msg_shown:
                        print("Executing imports init scripts...")
                        msg_shown = True
                    imp_res, sub_init_done = imp.testie.execute_all(build, options=options, do_test=do_test,
                                                                    allowed_types={"init"})
                if msg_shown:
                    print("All imports passed successfully...")

            init_scripts = [script for script in self.scripts if script.get_type() == "init"]
            if len(init_scripts) > 0:
                if not options.quiet:
                    print("Executing init scripts...")
                vs = {}
                for k, v in self.variables.statics().items():
                    vs[k] = v.makeValues()[0]
                results, output, err = self.execute(build, Run(vs), v=vs, n_runs=1, n_retry=0, allowed_types={"init"})

                if len(results) == 0:
                    if not options.quiet:
                        print("Aborting as init scripts did not run correctly !")
                    raise ScriptInitException()

    def execute_all(self, build, options, prev_results: Dataset = None, do_test=True,
                    allowed_types=SectionScript.ALL_TYPES_SET) -> Tuple[Dataset, bool]:
        """Execute script for all variables combinations. All tools reliy on this function for execution of the testie
        :param allowed_types:Tyeps of scripts allowed to run. Set with either init, scripts or both
        :param do_test: Actually run the tests
        :param options: NPF options object
        :param build: A build object
        :param prev_results: Previous set of result for the same build to update or retrieve
        :return: Dataset(Dict of variables as key and arrays of results as value)
        """

        init_done = False

        if not SectionScript.TYPE_SCRIPT in allowed_types:
            # If scripts is not in allowed_types, we have to run the init by force now
            self.do_init_all(build, options, do_test=do_test, allowed_types=allowed_types)
            return {}, True

        all_results = {}
        for variables in self.variables:
            run = Run(variables)
            if hasattr(self, 'late_variables'):
                variables = self.late_variables.execute(variables, self)
            r_status, r_out, r_err = self.test_require(variables, build)
            if not r_status:
                if not self.options.quiet:
                    print("Requirement not met for %s" % run.format_variables(self.config["var_hide"]))
                    if r_out.strip():
                        print(output.strip())
                    if r_err.strip():
                        print(err.strip())

                continue

            if prev_results and prev_results is not None and not options.force_test:
                run_results = prev_results.get(run, {})
                if run_results is None:
                    run_results = {}
            else:
                run_results = {}

            if not run_results and options.use_last:
                for version in build.repo.method.get_history(build.version):
                    oldb = Build(build.repo, version)
                    r = oldb.load_results(self)
                    if r and run in r:
                        run_results = r[run]
                        break

            for result_type in self.config['results_expect']:
                if result_type not in run_results:
                    run_results = {}

            have_new_results = False

            n_runs = self.config["n_runs"] - (0 if options.force_test or len(run_results) == 0 else min(
                [len(results) for result_type, results in run_results.items()]))
            if n_runs > 0 and do_test:
                if not init_done:
                    self.do_init_all(build, options, do_test, allowed_types=allowed_types)
                    init_done = True
                if not self.options.quiet:
                    print(run.format_variables(self.config["var_hide"]))

                new_results, output, err = self.execute(build, run, variables, n_runs, n_retry=self.config["n_retry"],
                                                        allowed_types={SectionScript.TYPE_SCRIPT})
                if new_results:
                    if self.options.show_full:
                        print("stdout:")
                        print(output)
                        print("stderr:")
                        print(err)
                    for k, v in new_results.items():
                        run_results.setdefault(k, []).extend(v)
                        have_new_results = True
            else:
                if not self.options.quiet:
                    print(run.format_variables(self.config["var_hide"]))

            if len(run_results) > 0:
                if not self.options.quiet:
                    if len(run_results) == 1:
                        print(list(run_results.values())[0])
                    else:
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

        return all_results, init_done

    def get_title(self):
        if "title" in self.config and self.config["title"] is not None:
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

    @staticmethod
    def expand_folder(testie_path, options, tags=None) -> List['Testie']:
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

        filtered_testies = []
        for testie in testies:
            missing_tags = testie.test_tags()
            if len(missing_tags) > 0:
                if not options.quiet:
                    print(
                        "Passing testie %s as it lacks tags %s" % (testie.filename, ','.join(missing_tags)))
            else:
                filtered_testies.append(testie)

        return filtered_testies

    def parse_script_roles(self):
        """
        Look for parameters of scripts and imports for configuration that affects the test, such as NICs parameters like
        the IP address
        """
        for script in (self.scripts + self.imports):
            for k, val in script.params.items():
                nic_match = re.match(r'(?P<nic_idx>[0-9]+)[:](?P<type>' + NIC.TYPES + '+)', k, re.IGNORECASE)
                if nic_match:
                    npf.node(script.get_role(), self.config.get_dict("default_role_map")).nics[
                        int(nic_match.group('nic_idx'))][nic_match.group('type')] = val
