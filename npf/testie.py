import multiprocessing
import os
import sys
import threading
import time
import random
import shutil
import datetime
from pathlib import Path
from queue import Empty
from typing import Tuple, Dict
import numpy as np
from npf.build import Build
from npf.node import NIC
from npf.section import *
from npf.types.dataset import Run, Dataset
from npf.eventbus import EventBus
from decimal import *

class RemoteParameters:
    def __init__(self):
        self.default_role_map = None
        self.role = None
        self.delay = None
        self.executor = None
        self.bin_paths = None
        self.queue = None
        self.sudo = None
        self.autokill = None
        self.queue = None
        self.timeout = None
        self.options = None
        self.stdin = None
        self.commands = None
        self.testdir = None
        self.waitfor = None
        self.event = None
        self.title = None

    pass

def _parallel_exec(param: RemoteParameters):
    executor = npf.executor(param.role, param.default_role_map)
    if param.waitfor:
        param.event.listen(param.waitfor)
    param.event.wait_for_termination(param.delay)
    if param.event.is_terminated():
        return 1, 'Killed before execution', 'Killed before execution', 0, param.script
    pid, o, e, c = executor.exec(cmd=param.commands,
                                 stdin=param.stdin,
                                 timeout=param.timeout,
                                 bin_paths=param.bin_paths,
                                 queue=param.queue,
                                 options=param.options,
                                 sudo=param.sudo,
                                 testdir=param.testdir,
                                 event=param.event,
                                 title=param.name)
    if pid == 0:
        return False, o, e, c, param.script
    else:
        if param.autokill or pid == -1:
            Testie.killall(param.queue, param.event)
        if pid == -1:
            return -1, o, e, c, param.script
        return True, o, e, c, param.script


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
        self.init_files = []
        self.late_variables = []
        self.scripts = []
        self.imports = []
        self.requirements = []
        self.filename = os.path.basename(testie_path)
        self.path = os.path.dirname(testie_path)
        self.options = options
        self.tags = tags if tags else []
        self.role = role

        i = -1
        try:
            section = None
            f = open(testie_path, 'r')
            for i, line in enumerate(f):
                if section is None or section.noparse is False:
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
            if i == -1:
                raise Exception("An exception occured while accessing the file %s" % (testie_path))
            else:
                raise Exception("An exception occured while parsing %s at line %d:\n%s" % (testie_path, i, e.__str__()))

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
            imp.testie = Module(imp.module, options, self, imp, tags, imp.get_role())
            if len(imp.testie.variables.dynamics()) > 0:
                raise Exception("Imports cannot have dynamic variables. Their parents decides what's dynamic.")
            if 'as_init' in imp.params:
                for script in imp.testie.scripts:
                    script.init = True
            if 'delay' in imp.params:
                delay = script.params.setdefault('delay', 0)
                for script in imp.testie.scripts:
                    script.params['delay'] = float(delay) + float(imp.params['delay'])
                del imp.params['delay']
            if 'waitfor' in imp.params:
                for script in imp.testie.scripts:
                    script.params['waitfor'] = imp.params['waitfor']
                del imp.params['waitfor']
            overriden_variables = {}
            for k, v in imp.params.items():
                overriden_variables[k] = VariableFactory.build(k, v)
            imp.testie.variables.override_all(overriden_variables)
            if not imp.is_include:
                for script in imp.testie.scripts:
                    if script.get_role():
                        raise Exception('Modules cannot have roles, their importer defines it')
                script._role = imp.get_role()

    def build_deps(self, repo_under_test: List[Repository]):
        # Check for dependencies
        deps = set()
        for script in self.get_scripts():
            deps = deps.union(script.get_deps())
        for dep in deps:
            if dep in [repo.reponame for repo in repo_under_test]:
                continue
            deprepo = Repository.get_instance(dep, self.options)
            if deprepo.url is None or deprepo.reponame in self.options.no_build_deps:
                continue
            if not deprepo.get_last_build().build(force_build=deprepo.reponame in self.options.force_build_deps):
                raise Exception("Could not build dependency %s" % dep)
        for imp in self.imports:
            imp.testie.build_deps(repo_under_test)
        # Send dependencies for nfs=0 nodes
        for script in self.get_scripts():
            role = script.get_role()
            node = npf.node(role)
            if not node.nfs:
                for dep in script.get_deps():
                    deprepo = Repository.get_instance(dep, self.options)
                    print("Sending %s ..." % dep)
                    node.executor.sendFolder(deprepo.get_build_path())

        return True

    def test_tags(self):
        missings = []
        # print("%s requires " % self.get_name(), self.config.get_list("require_tags"))
        for tag in self.config.get_list("require_tags"):
            if not tag in self.tags:
                missings.append(tag)
        return missings

    def build_file_list(self, v, self_role=None, files=None) -> List[Tuple[str, str, str]]:
        list = []
        if files is None:
            files = self.files
        for s in files:
            role = s.get_role() if s.get_role() else self_role
            if not s.noparse:
                p = SectionVariable.replace_variables(v, s.content, role, self.config.get_dict("default_role_map"))
            else:
                p = s.content
            list.append((s.filename, p, role))
        return list

    def create_files(self, file_list, path_to_root):
        unique_list = {}
        for filename, p, role in file_list:
            if filename in unique_list:
                if unique_list[filename+(role if role else '')][1] != p:
                    raise Exception(
                        "File name conflict ! Some of your scripts try to create some file with the same name but different content (%s) !" % filename)
            else:
                unique_list[filename+(role if role else '')] = (filename,p,role)

        for whatever, (filename,p,role) in unique_list.items():
            if self.options.show_files:
                print("File %s:" % filename)
                print(p.strip())
            for node in npf.nodes(role):
                if not node.executor.writeFile(filename,path_to_root, p):
                    raise Exception("Could not create file %s on %s",filename,node.name)

    def test_require(self, v, build):
        for require in self.requirements:
            p = SectionVariable.replace_variables(v, require.content, require.role(),
                                                  self.config.get_dict("default_role_map"))
            pid, output, err, returncode = npf.executor(require.role(), self.config.get_dict("default_role_map")).exec(
                cmd=p, bin_paths=[build.get_bin_folder()], options=self.options, event=None, testdir=None)
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
    def killall(queue, event):
        event.terminate()
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

    def execute(self, build, run, v, n_runs=1, n_retry=0, allowed_types=SectionScript.ALL_TYPES_SET, do_imports=True, test_folder = None, event = None) \
            -> Tuple[Dict[str, List], str, str, int]:

        # Get address definition for roles from scripts
        self.parse_script_roles()

        #Create temporary folder
        v_internals = {'NPF_ROOT':'../', 'NPF_BUILD':'../' + build.build_path()}
        v.update(v_internals)
        if test_folder is None:
            test_folder = self.make_test_folder()
            f_mine = True
        else:
            f_mine = False
        if not os.path.exists(test_folder):
            os.mkdir(test_folder)
        os.chdir(test_folder)

        #Build file list
        file_list = []
        if SectionScript.TYPE_INIT in allowed_types:
            initv = {}
            for k, vinit in self.variables.statics().items():
                initv[k] = vinit.makeValues()[0]
            file_list.extend(self.build_file_list(initv, self.role, files=self.init_files))
        else:
            file_list.extend(self.build_file_list(v, self.role))

        n_exec = 0
        n_err = 0

        for imp in self.get_imports():
            imp.testie.parse_script_roles()
            imp.imp_v = {}
            for k, val in imp.testie.variables.statics().items():
                imp.imp_v[k] = val.makeValues()[0]
            imp.imp_v.update(v)
            for late_variables in imp.testie.get_late_variables():
                imp.imp_v.update(late_variables.execute(imp.imp_v, imp.testie))
            if SectionScript.TYPE_INIT in allowed_types:
                file_list.extend(imp.testie.build_file_list(imp.imp_v, imp.get_role(), files=imp.testie.init_files))
            else:
                file_list.extend(imp.testie.build_file_list(imp.imp_v, imp.get_role()))

        self.create_files(file_list,test_folder)

        #Launching the tests in itself
        data_results = OrderedDict() # dict of result_name -> [val, val, val]
        time_results = OrderedDict() # dict of time -> {result_name -> [val, val, val]}
        m = multiprocessing.Manager()
        all_output = []
        all_err = []
        for i in range(n_runs):
            for i_try in range(n_retry + 1):
                new_time_results = {}
                if i_try > 0 and not self.options.quiet:
                    print("Re-try tests %d/%d..." % (i_try, n_retry + 1))
                output = ''
                err = ''


                queue = m.Queue()

                event = EventBus(m)

                remote_params = []
                for t, v, role in (
                [(imp.testie, imp.imp_v, imp.get_role()) for imp in self.imports] if do_imports else []) + [
                    (self, v, None)]:
                    for script in t.scripts:
                        if not script.get_type() in allowed_types:
                            continue
                        param = RemoteParameters()
                        param.commands = "mkdir -p "+test_folder+" && cd " + test_folder + ";\n" + SectionVariable.replace_variables(v,
                                                                                                         script.content,
                                                                                                         role if role else script.get_role(),
                                                                                                         self.config.get_dict(
                                                                                                             "default_role_map"))
                        param.options = self.options
                        param.queue = queue
                        param.stdin = t.stdin.content
                        timeout = t.config['timeout'] if t.config['timeout'] > 0 else None
                        if 'timeout' in script.params:
                            timeout = float(script.params['timeout'])
                        if self.config['timeout'] > timeout:
                            timeout = self.config['timeout']

                        param.timeout = timeout
                        script.timeout = timeout
                        param.role = script.get_role()
                        param.default_role_map = self.config.get_dict("default_role_map")
                        param.delay = script.delay()
                        deps_bin_path = [repo.get_bin_folder() for repo in script.get_deps_repos(self.options)]
                        param.bin_paths = deps_bin_path + [build.get_bin_folder()]
                        param.sudo = script.params.get("sudo", False)
                        param.testdir = test_folder
                        param.event = event
                        param.script = script
                        param.name = script.get_name(True)
                        param.autokill = npf.parseBool(script.params.get("autokill", t.config["autokill"]))

                        if 'waitfor' in script.params:
                            param.waitfor = script.params['waitfor']

                        remote_params.append(param)

                n = len(remote_params)
                n_exec += n
                if n == 0:
                    break

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
                    print("Program is interrupted")
                    if self.options.allow_mp:
                        p.close()
                        p.terminate()

                    if not self.options.preserve_temp:
                        for imp in self.imports:
                            imp.testie.cleanup()
                        self.cleanup()
                    os.chdir('..')
                    if not self.options.preserve_temp:
                        shutil.rmtree(test_folder)
                    else:
                        print("Test files have been preserved in :" + test_folder)
                    sys.exit(1)


                if self.options.allow_mp:
                    p.close()
                    p.terminate()
                worked = False
                critical_failed = False
                for iscript, (r, o, e, c, script) in enumerate(parallel_execs):
                    if r == 0:
                        print("Timeout of %d seconds expired for script %s on %s..." % (script.timeout, script.get_name(),script.get_role()))
                        if not self.options.quiet:
                            if not self.options.show_full:
                                print("stdout:")
                                print(o)
                            print("stderr:")
                            print(e)
                        continue
                    if r == -1:
                        os.chdir('..')
                        if not self.options.preserve_temp and f_mine:
                            shutil.rmtree(test_folder)
                        sys.exit(1)
                    if c != 0:
                        n_err = n_err + 1
                        if npf.parseBool(script.params.get("critical", t.config["critical"])):
                            critical_failed=True
                            print("[ERROR] A critical script failed ! Results will be ignored")
                        print("Bad return code (%d) for script %s on %s ! Something probably went wrong..." % (c,script.get_name(),script.get_role()))
                        if not self.options.quiet:
                            if not self.options.show_full:
                                print("stdout:")
                                print(o)
                            print("stderr:")
                            print(e)
                        continue


                for iparallel, (r, o, e, c, script) in enumerate(parallel_execs):
                    if len(self.scripts) > 1:
                        output += "stdout of script %s on %s :\n" % (script.get_name(),script.get_role())
                        err += "stderr of script %s on %s :\n" % (script.get_name(),script.get_role())

                    if r:
                        worked = True
                        output += o
                        err += e

                all_output.append(output)
                all_err.append(err)

                if not worked or critical_failed:
                    continue

                if not self.config["result_regex"]:
                    break

                has_values = False
                has_err = False
                for result_regex in self.config.get_list("result_regex"):
                    result_types = OrderedDict()
                    try:
                        for nr in re.finditer(result_regex, output.strip(), re.IGNORECASE):
                            result_type = nr.group("type")

                            time = nr.group("time")
                            if result_type is None:
                                result_type = ''
                            n = float(nr.group("value"))
                            mult = nr.group("multiplier")
                            unit = ""
                            if nr.group("unit"):
                                unit = nr.group("unit")
                            if unit.lower() == "sec" or unit.lower() == "s":
                                unit = "s"

                            if unit == "s":
                                if mult == "m":
                                    n = n / 1000 #Keep all results in seconds
                                elif mult == "u" or mult=="µ":
                                    n = n / 1000000
                                elif mult == "n":
                                    n = n / 1000000000
                            else:
                                mult = mult.upper()

                            if mult == "K":
                                n *= 1024
                            elif mult == "M":
                                n *= 1024 * 1024
                            elif mult == "G":
                                n *= 1024 * 1024 * 1024
                            if n != 0 or (self.config.match("accept_zero", result_type)) or time is not None:
                                if time:
                                    new_time_results.setdefault(float(time),{}).setdefault(result_type, []).append(n)
                                else:
                                    if result_type in result_types:
                                        result_types[result_type] += n
                                    else:
                                        result_types[result_type] = n
                                has_values = True
                            else:
                                print("Result for %s is 0 !" % result_type)
                                has_err = True
                        for result_type, val in result_types.items():
                            data_results.setdefault(result_type, []).append(val)

                    except Exception as e:
                        print("Exception while parsing results :")
                        has_err = True
                        raise e

                if new_time_results:
                    min_time = min(new_time_results.keys())
                    nonzero = set()
                    all_result_types = set()
                    for time, results in new_time_results.items():
                        for result_type, result in results.items():
                            if (np.asarray(result) != 0).any():
                                nonzero.add(result_type)
                            all_result_types.add(result_type)
                            time_results.setdefault(Decimal(("%.0" + str(self.config['time_precision']) + "f") % round(float(time - min_time), int(self.config['time_precision']))),{}).setdefault(result_type, []).extend(result)
                    diff = all_result_types.difference(nonzero)
                    if diff:
                        print("Result for %s is 0 !" % ', '.join(diff))
                        has_err = True

                if has_values:
                    break

                for result_type in self.config.get_list('results_expect'):
                    if result_type not in results:
                        print("Could not find expected result '%s' !" % result_type)
                        has_err = True

                if len(data_results) + len(time_results) == 0:
                    print("Could not find results !")

                    has_err = True
                    continue

                if has_err:
                    if not self.options.show_full:
                        print("stdout:")
                        print(output)
                    print("stderr:")
                    print(err)

        if not self.options.preserve_temp:
            for imp in self.imports:
                imp.testie.cleanup()
            self.cleanup()
        os.chdir('..')
        if not self.options.preserve_temp and f_mine:
            shutil.rmtree(test_folder)
        return data_results, time_results, all_output, all_err, n_exec, n_err


    def do_init_all(self, build, options, do_test, allowed_types=SectionScript.ALL_TYPES_SET,test_folder=None):
        if not build.build(options.force_build, options.no_build, options.quiet_build, options.show_build_cmd):
            raise ScriptInitException()
        if not self.build_deps([build.repo]):
            raise ScriptInitException()

        if (allowed_types is None or "init" in allowed_types) and options.do_init:
            if not options.quiet:
                print("Executing init scripts...")
            vs = {}
            for k, v in self.variables.statics().items():
                vs[k] = v.makeValues()[0]
            for late_variables in self.get_late_variables():
                vs.update(late_variables.execute(vs, self))
            data_results, time_results, output, err, num_exec, num_err = self.execute(build, Run(vs), v=vs, n_runs=1, n_retry=0,
                                                              allowed_types={"init"}, do_imports=True,test_folder=test_folder)

            if num_err > 0:
                if not options.quiet:
                    print("Aborting as init scripts did not run correctly !")
                    print("Stdout:")
                    print("\n".join(output))
                    print("Stderr:")
                    print("\n".join(err))
                raise ScriptInitException()

    def execute_all(self, build, options, prev_results: Dataset = None, do_test=True, on_finish = None,
            allowed_types=SectionScript.ALL_TYPES_SET, prev_time_results : Dataset = None) -> Tuple[Dataset, bool]:
        """Execute script for all variables combinations. All tools reliy on this function for execution of the testie
        :param allowed_types:Tyeps of scripts allowed to run. Set with either init, scripts or both
        :param do_test: Actually run the tests
        :param options: NPF options object
        :param build: A build object
        :param prev_results: Previous set of result for the same build to update or retrieve
        :return: Dataset(Dict of variables as key and arrays of results as value)
        """

        init_done = False
        test_folder=self.make_test_folder()

        if not SectionScript.TYPE_SCRIPT in allowed_types:
            # If scripts is not in allowed_types, we have to run the init by force now

            self.do_init_all(build, options, do_test=do_test, allowed_types=allowed_types)
            if not self.options.preserve_temp:
                shutil.rmtree(test_folder)
            return {}, True

        all_data_results = OrderedDict()
        all_time_results = OrderedDict()
        #If one first, we first ensure 1 result per variables then n_runs
        if options.onefirst:
            total_runs = [1,self.config["n_runs"]]
        else:
            total_runs = [self.config["n_runs"]]
        for runs_this_pass in total_runs: #Number of results to ensure for this run
            n = 0
            for variables in self.variables.expand(method = options.expand):
                n += 1
                run = Run(variables)
                variables = variables.copy()
                for late_variables in self.get_late_variables():
                    variables.update(late_variables.execute(variables, self))
                r_status, r_out, r_err = self.test_require(variables, build)
                if not r_status:
                    if not self.options.quiet:
                        print("Requirement not met for %s" % run.format_variables(self.config["var_hide"]))
                        if r_out.strip():
                            print(r_out.strip())
                        if r_err.strip():
                            print(r_err.strip())

                    continue

                if prev_results and prev_results is not None and not (options.force_test or options.force_retest):
                    run_results = prev_results.get(run, None)
                    if run_results is None:
                        run_results = {}
                else:
                    run_results = {}

                time_results = OrderedDict()
                if prev_time_results and prev_time_results is not None and not (options.force_test or options.force_retest):
                    nprev_time_results = OrderedDict()
                    for trun, results in prev_time_results.items():
                        if run.inside(trun):
                            time_results[trun] = results
                        else:
                            nprev_time_results[trun] = results
                    prev_time_results = nprev_time_results
                elif prev_time_results and options.force_retest:
                    nprev_time_results = OrderedDict()
                    for trun, results in prev_time_results.items():
                        if not run.inside(trun):
                            nprev_time_results[trun] = results;
                    prev_time_results = nprev_time_results

                if not run_results and options.use_last and build.repo.url:
                    for version in build.repo.method.get_history(build.version, limit=options.use_last):
                        oldb = Build(build.repo, version)
                        r = oldb.load_results(self)
                        if r and run in r:
                            run_results = r[run]
                            break

                if run_results:
                    for result_type in self.config.get_list('results_expect'):
                        if result_type not in run_results:
                            print("Missing result type %s, re-doing the run" % result_type)
                            run_results = {}

                have_new_results = False

                n_runs = runs_this_pass - (0 if (options.force_test or options.force_retest) or len(run_results) == 0 else min(
                    [len(results) for result_type, results in run_results.items()]))
                if n_runs > 0 and do_test:
                    if not init_done:
                        self.do_init_all(build, options, do_test, allowed_types=allowed_types,test_folder=test_folder)
                        init_done = True
                    if not self.options.quiet:
                        if len(self.variables) > 0:
                            print(run.format_variables(self.config["var_hide"]),"[%d runs for %d/%d]" % (n_runs,n,len(self.variables)))
                        else:
                            print("Executing single run...")

                    new_data_results, new_time_results, output, err, n_exec, n_err = self.execute(build, run, variables, n_runs,
                                                                    n_retry=self.config["n_retry"],
                                                                    allowed_types={SectionScript.TYPE_SCRIPT},
                                                                    test_folder=test_folder)
                    if new_data_results:
                        for result_type, values in new_data_results.items():
                            if options.force_retest:
                                run_results[result_type] = values
                            else:
                                run_results.setdefault(result_type, []).extend(values)
                            have_new_results = True
                    if new_time_results:
                        have_new_results = True
                else:
                    if not self.options.quiet:
                        print(run.format_variables(self.config["var_hide"]))

                if len(run_results) > 0:
                    if not self.options.quiet:
                        if len(run_results) == 1:
                            print(list(run_results.values())[0])
                        else:
                            print(", ".join(['{0}: {1}'.format(k, run_results[k]) for k in sorted(run_results)]))

                    all_data_results[run] = run_results
                else:
                    all_data_results[run] = {}

                if have_new_results and len(new_time_results) > 0:
                    for time, results in sorted(new_time_results.items()):
                        time_run = Run(run.variables.copy())
                        time_run.variables['time'] = time
                        for result_type, result in results.items():
                            rt = time_results.setdefault(time_run,{}).setdefault(result_type,[])
                            if options.force_retest:
                                rt.clear()
                            rt.extend(result)
                for result_type, result in time_results.items():
                    all_time_results[result_type] = result

                if on_finish and have_new_results:
                    def call_finish():
                        on_finish(all_data_results, all_time_results)
                    thread = threading.Thread(target=call_finish, args=())
                    thread.daemon = True
                    thread.start()

                # Save results
                if all_data_results and have_new_results:
                    if prev_results or prev_time_results:
                        prev_results[run] = all_data_results[run]
                        build.writeversion(self, prev_results, allow_overwrite=True)
                        if prev_time_results:
                            prev_time_results.update(time_results)
                        else:
                            prev_time_results = time_results
                        build.writeversion(self, prev_time_results, allow_overwrite=True, time=True)
                    else:
                        build.writeversion(self, all_data_results, allow_overwrite=True)
                        build.writeversion(self, all_time_results, allow_overwrite=True, time=True)

        if not self.options.preserve_temp:
            shutil.rmtree(test_folder)
        else:
            print("Test files have been kept in folder %s" % test_folder)

        return all_data_results, all_time_results, init_done

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
                for filename in files:
                    if filename.endswith(".testie"):
                        try:
                            testie = Testie(os.path.join(root, filename), options=options, tags=tags)
                            testies.append(testie)
                        except Exception as e:
                            print("Error during the parsing of %s :\n%s" % (filename, e))

        filtered_testies = []
        for testie in testies:
            missing_tags = testie.test_tags()
            if len(missing_tags) > 0:
                if not options.quiet:
                    print(
                        "Passing testie %s as it lacks tags %s" % (testie.filename, ','.join(missing_tags)))
            else:
                if testie.test_roles_mapping():
                    filtered_testies.append(testie)
                else:
                    raise Exception(
                        "Roles %s cannot be on the same node ! Please use --cluster argument to set them accross nodes" % ' and '.join(
                            s))

        return filtered_testies

    def test_roles_mapping(self):
        for excludes in self.config.get_list("role_exclude"):
            s = excludes.split('+')
            m = set()
            for role in s:
                node = npf.node(role)
                if node in m:
                    return False
                m.add(node)
        return True

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

    def get_imports(self) -> List[SectionImport]:
        return self.imports

    def get_late_variables(self) -> List[SectionLateVariable]:
        return self.late_variables

    def make_test_folder(self):
        test_folder = "testie%s-%05d" % (datetime.datetime.now().strftime("%y%m%d%H%M"), random.randint(1, 2 << 16))
        os.mkdir(test_folder)
        return test_folder
